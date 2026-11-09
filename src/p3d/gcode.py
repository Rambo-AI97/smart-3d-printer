"""G-code helpers (pure functions, no printer access): layer table, position tracking, footprint,
and the rewriting used by `p3d recover` / `p3d addon` and the host-side pause.

Layers come from the slicer's ';LAYER_CHANGE' / ';Z:' comments (Orca/Prusa style), numbered from 1.
A file written by recover carries '; p3d_layer_offset = N' so its layers keep the original numbers.
"""
import re

AXIS = re.compile(r"\b([XYZEF])(-?\d*\.?\d+)", re.I)
Z_MAX = 245.0   # highest Z any rewritten move may use (Ender-3 V3 SE: 250 mm)


def strip(raw):
    return raw.split(";", 1)[0].strip()


def parse(lines):
    """Raw G-code lines -> (cmds, layer_at, layer_z, total).

    cmds: commands without comments/blank lines (exactly what the sender streams, in order)
    layer_at[i]: layer number of cmds[i] (0 = before the first layer)
    layer_z[n]: nominal Z of layer n
    """
    cmds, layer_at, layer_z = [], [], {}
    layer, offset, pending = 0, 0, False
    for raw in lines:
        s = raw.strip()
        if s.startswith(";"):
            if s.startswith(";LAYER_CHANGE"):
                layer += 1
                pending = True
            elif pending and s.startswith(";Z:"):
                try:
                    layer_z[layer + offset] = float(s[3:])
                except ValueError:
                    pass
                pending = False
            elif s.startswith("; p3d_layer_offset"):
                offset = int(s.split("=")[1])
            continue
        c = strip(raw)
        if c:
            cmds.append(c)
            layer_at.append(layer + offset if layer else 0)
    return cmds, layer_at, layer_z, (layer + offset)


def load(path):
    with open(path, errors="replace") as f:
        return parse(f.read().splitlines())


class Tracker:
    """Follows a command stream: position, extruder mode, targets, fan. feed() one command at a time."""

    def __init__(self):
        self.x = self.y = self.z = None
        self.e = 0.0
        self.abs_xyz = True
        self.e_mode = None      # M82 -> "abs", M83 -> "rel"; None = follows G90/G91
        self.nozzle = self.bed = 0.0
        self.fan = 0
        self.last = {}      # last full line of M204/M205/M220/M221, restored by recover

    @property
    def abs_e(self):
        return (self.e_mode == "abs") if self.e_mode else self.abs_xyz

    def feed(self, cmd):
        """Returns True if cmd was an extruding move (XY travel with E pushing filament)."""
        code = cmd.split(None, 1)[0].upper() if cmd else ""
        if code in ("G0", "G1"):
            v = {m.group(1).upper(): float(m.group(2)) for m in AXIS.finditer(cmd)}
            extruding = False
            if "E" in v:
                extruding = (v["E"] > 0) if not self.abs_e else (v["E"] > self.e)
                self.e = (self.e + v["E"]) if not self.abs_e else v["E"]
            for k, attr in (("X", "x"), ("Y", "y"), ("Z", "z")):
                if k in v:
                    cur = getattr(self, attr)
                    setattr(self, attr, v[k] if self.abs_xyz else (cur or 0.0) + v[k])
            return extruding and ("X" in v or "Y" in v)
        if code == "G90":
            self.abs_xyz = True
        elif code == "G91":
            self.abs_xyz = False
        elif code == "M82":
            self.e_mode = "abs"
        elif code == "M83":
            self.e_mode = "rel"
        elif code == "G92":
            for m in AXIS.finditer(cmd):
                if m.group(1).upper() == "E":
                    self.e = float(m.group(2))
                elif m.group(1).upper() == "Z":
                    self.z = float(m.group(2))
        elif code in ("M104", "M109", "M140", "M190"):
            m = re.search(r"\bS(-?[\d.]+)", cmd)
            if m:
                if code in ("M104", "M109"):
                    self.nozzle = float(m.group(1))
                else:
                    self.bed = float(m.group(1))
        elif code == "M106":
            m = re.search(r"\bS(\d+)", cmd)
            self.fan = int(m.group(1)) if m else 255
        elif code == "M107":
            self.fan = 0
        elif code in ("M204", "M205", "M220", "M221"):
            self.last[code] = cmd
        return False


def footprint(cmds, upto=None, layer_at=None, first=1):
    """XY bounding box (x0, y0, x1, y1) of everything extruded in layers first..upto, or None.
    The start-gcode prime line (layer 0) is not part of the object, so it is skipped."""
    t, box = Tracker(), None
    for i, c in enumerate(cmds):
        px, py = t.x, t.y
        ext = t.feed(c)
        layer = layer_at[i] if layer_at else 1
        if upto is not None and layer > upto:
            break
        if ext and layer >= first and t.x is not None:
            pts = [(t.x, t.y)] + ([(px, py)] if px is not None and py is not None else [])
            for x, y in pts:
                box = (x, y, x, y) if box is None else (min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y))
    return box


def covers(box, point, margin=0.0):
    """True if the XY point lies inside the box grown by margin."""
    if box is None:
        return False
    x, y = point
    return box[0] - margin <= x <= box[2] + margin and box[1] - margin <= y <= box[3] + margin


def z_home_ok(box, point, margin):
    """G28 is only safe when the part's footprint is known AND stays clear of the Z-probe point."""
    return box is not None and not covers(box, point, margin)


def last_layer_at_or_below(layer_z, z):
    """Highest layer whose nominal Z is <= z (tolerance 0.01), or 0."""
    ok = [n for n, v in layer_z.items() if v <= z + 0.01]
    return max(ok) if ok else 0


def _fmt(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")


def shift_line(raw, dx=0.0, dy=0.0, dz=0.0, zmax=Z_MAX):
    """Shift absolute G0/G1 X/Y/Z by (dx, dy, dz). Z is clamped to zmax. Other lines untouched."""
    body, sep, comment = raw.partition(";")
    m = re.match(r"\s*(G0|G1)\b", body, re.I)
    if not m or not (dx or dy or dz):
        return raw

    def sub(mm):
        ax, v = mm.group(1).upper(), float(mm.group(2))
        if ax == "X":
            v += dx
        elif ax == "Y":
            v += dy
        elif ax == "Z":
            v = min(v + dz, zmax)
        else:
            return mm.group(0)
        return f"{mm.group(1)}{_fmt(v)}"
    out = AXIS.sub(sub, body)
    return out + (sep + comment if sep else "")


def shift_all(lines, dx=0.0, dy=0.0, dz=0.0, zmax=Z_MAX):
    """shift_line over a block, leaving moves alone while G91 (relative) is active."""
    out, absolute = [], True
    for raw in lines:
        code = strip(raw).split(None, 1)[0].upper() if strip(raw) else ""
        if code == "G91":
            absolute = False
        elif code == "G90":
            absolute = True
        out.append(shift_line(raw, dx, dy, dz, zmax) if absolute else raw)
    return out


def _restore_state(t):
    """Commands that put the printer back into the state the stream had before a given point."""
    out = ["G90", "M82" if t.abs_e else "M83", "G92 E0"]
    out += [t.last[k] for k in ("M204", "M205", "M220", "M221") if k in t.last]
    if t.fan:
        out.append(f"M106 S{t.fan}")
    return out


def start_header(nozzle, bed, z_ref, auto_home, prime_ok, return_z, comment="p3d header"):
    """Safe start for a job that begins mid-part.

    auto_home=True : G28 (the part is clear of the Z-probe point, checked by the caller).
    auto_home=False: Z is declared by hand: the nozzle must be touching the top of the part (G92 Z{z_ref});
                     X/Y are homed after lifting 10 mm straight up; the Z axis is never probed.
    prime_ok: prime line on the bed edge (left of the part); else a short purge in the air.
    """
    h = [f"; --- {comment} ---", f"M140 S{_fmt(bed)}", f"M104 S{_fmt(nozzle)}", f"M190 S{_fmt(bed)}"]
    if auto_home:
        h += ["G28 ; full homing: the Z probe point is clear of the part"]
    else:
        h += [f"G92 Z{_fmt(z_ref)} ; MANUAL Z: nozzle is touching the top of the part now",
              "G91", "G1 Z10 F300 ; straight up before any sideways move", "G90",
              "G28 X Y ; Z is NOT probed (the probe would land on the part)"]
    h += ["M420 S1 Z10 ; saved bed mesh", f"M109 S{_fmt(nozzle)}", "M83", "G92 E0"]
    if prime_ok:
        h += ["G1 Z2 F3000", "G1 X-2.1 Y20 F5000", "G1 Z0.3 F600", "G1 X-2.1 Y145 F1500 E12 ; prime line on the bed edge",
              "G1 E-1 F1800", f"G1 Z{_fmt(return_z)} F600 ; back above the part"]
    else:
        h += [f"G1 Z{_fmt(return_z)} F600", "G1 X0 Y0 F5000", "G1 E10 F200 ; purge in the air: pull the blob off with tweezers",
              "G1 E-1 F1800", "G4 S8"]
    h += ["G92 E0", f"; --- end {comment} ---"]
    return h


def build_recover(raw_lines, keep_layer, auto_home, bed=None, prime_ok=True):
    """New G-code that continues a print at layer keep_layer+1. Returns (lines, info)."""
    cmds, layer_at, layer_z, total = parse(raw_lines)
    nxt = keep_layer + 1
    if keep_layer < 1 or nxt > total:
        raise ValueError(f"layer {keep_layer} cannot be continued (file has {total} layers)")
    # raw index of the ';LAYER_CHANGE' that opens layer nxt
    seen, start = 0, None
    off = 0
    for i, raw in enumerate(raw_lines):
        s = raw.strip()
        if s.startswith("; p3d_layer_offset"):
            off = int(s.split("=")[1])
        if s.startswith(";LAYER_CHANGE"):
            seen += 1
            if seen + off == nxt:
                start = i
                break
    if start is None:
        raise ValueError(f"layer {nxt} not found")
    t = Tracker()
    for raw in raw_lines[:start]:
        c = strip(raw)
        if c:
            t.feed(c)
    z_ref = layer_z.get(keep_layer, 0.0)
    nxt_z = layer_z.get(nxt, z_ref + 0.2)
    nozzle = t.nozzle or 225.0
    bed = t.bed if bed is None else bed
    head = [r for r in raw_lines[:next(i for i, r in enumerate(raw_lines) if r.strip().startswith(";TYPE:Custom"))]
            if r.startswith(";") or r.startswith(("M201", "M203"))]
    head = [h for h in head if "p3d_layer_offset" not in h]
    box = footprint(cmds, upto=keep_layer, layer_at=layer_at)
    body = raw_lines[start:]
    # filament + time left (for the log and the spool): share of the E still to extrude
    e_before = _e_total(raw_lines[:start])
    e_all = _e_total(raw_lines)
    share = 1 - (e_before / e_all) if e_all else 1.0
    head, body = scale_summary(head, share), scale_summary(body, share)
    hdr = start_header(nozzle, bed, z_ref, auto_home, prime_ok, return_z=z_ref + 6)
    lines = (head + [f"; p3d_layer_offset = {keep_layer}", f"; p3d recover: continues at layer {nxt} (z {_fmt(nxt_z)})"]
             + hdr + _restore_state(t) + body)
    return lines, {"layer": nxt, "z_ref": z_ref, "box": box, "share": share, "total_layers": total,
                   "nozzle": nozzle, "bed": bed}


def _e_total(lines):
    """Sum of positive relative-E extrusion in a slice of raw lines (Orca prints relative E)."""
    t, tot = Tracker(), 0.0
    for raw in lines:
        c = strip(raw)
        if c:
            e0 = t.e
            t.feed(c)
            if not t.abs_e and c[:2] in ("G0", "G1") and t.e > e0:
                tot += t.e - e0
    return tot


def scale_summary(lines, share):
    """Return lines with 'filament used [g]' and the estimated time multiplied by share."""
    out = []
    for r in lines:
        m = re.match(r"(;\s*(?:total )?filament used \[g\]\s*=\s*)([\d.]+)", r)
        if m:
            r = f"{m.group(1)}{float(m.group(2)) * share:.2f}"
        m = re.match(r"(;\s*estimated printing time \(normal mode\)\s*=\s*)(.*)", r)
        if m:
            mult = {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}
            mins = sum(float(n) * mult[u] for n, u in re.findall(r"(\d+)([dhms])", m.group(2))) * share
            r = f"{m.group(1)}{int(mins // 60)}h {int(mins % 60)}m 0s"
        out.append(r)
    return out
