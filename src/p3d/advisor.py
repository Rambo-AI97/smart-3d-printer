"""Slice advisor: flags likely problems or waste in a sliced job BEFORE it prints.

`gather(path)` reads a G-code (or job dir) plus job.json / process.json, spools and the latest bed mesh into a plain dict;
`advise(info)` is a pure function over that dict and returns short lines ("... -> fix"). Used by `p3d inspect` and the dashboard.
Read-only: never touches the printer.
"""
import collections
import json
import pathlib
import re

# Rule 1: tall and narrow without a brim
TALL_RATIO = 2.5            # max_z / smaller footprint side
TALL_MM, NARROW_MM = 40.0, 30.0
# Rule 2: supports
SUPPORT_HIGH = 0.10         # support share of filament worth a look
SUPPORT_TINY = 0.02         # supports enabled but barely used
# Rule 3: heavy settings on a small part
SMALL_G = 15.0
HEAVY_WALLS, HEAVY_INFILL = 5, 35.0
LIGHT_WALLS, LIGHT_INFILL = 3, 15.0
# Rule 4: placement and bed mesh
BED_DEFAULT = (220.0, 220.0)
OFF_CENTRE_MM = 60.0        # centre of the part this far from the bed centre
BACK_LEFT_MARGIN = 10.0     # past the bed centre in X (left) and Y (back)
MESH_DEV_MM = 0.3
# Rule 6: long prints
LONG_MIN = 240
FINE_LAYER_MAX = 0.2        # layer height <= this counts as standard/fine
SPARSE_SHARE = 0.60         # sparse infill + inner walls share of filament
# Rule 7: tall part on several small first-layer islands (Gridfinity feet: gf_bathroom, gf_paste_tulip came loose)
ISLAND_SMALL_MM2 = 2000.0
ISLAND_TALL_MM = 25.0


def _num(v, default=None):
    try:
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return default


def _minutes(s):
    mult = {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}
    return sum(float(n) * mult[u] for n, u in re.findall(r"(\d+)([dhms])", s or ""))


def _has_brim(info):
    bt = str(info.get("brim_type", "")).lower()
    return (bt not in ("", "no_brim") and (_num(info.get("brim_width"), 5) or 0) > 0) or bool(info.get("brim_used"))


def _mesh_hits(info, fp, bed):
    """Count mesh points under the footprint with |dev| > MESH_DEV_MM; returns (hits, worst)."""
    grid = info.get("mesh")
    if not grid or not fp:
        return 0, 0.0
    rows, cols = len(grid), len(grid[0])
    hits, worst = 0, 0.0
    for j, r in enumerate(grid):
        for i, v in enumerate(r):
            x = bed[0] * i / (cols - 1) if cols > 1 else bed[0] / 2
            y = bed[1] * j / (rows - 1) if rows > 1 else bed[1] / 2
            hx, hy = bed[0] / max(cols - 1, 1) / 2, bed[1] / max(rows - 1, 1) / 2
            if fp[0] - hx <= x <= fp[2] + hx and fp[1] - hy <= y <= fp[3] + hy and abs(v) > MESH_DEV_MM:
                hits += 1
                worst = max(worst, abs(v))
    return hits, worst


def advise(info):
    """info -> list of advice lines (empty = nothing to flag). Missing keys just skip their rule."""
    out = []
    fp = info.get("footprint")
    bed = tuple(info.get("bed") or BED_DEFAULT)
    grams = _num(info.get("grams"), 0.0) or 0.0
    shares = info.get("shares") or {}
    # 1 tall and narrow
    z = _num(info.get("max_z"))
    if fp and z and not _has_brim(info):
        side = min(fp[2] - fp[0], fp[3] - fp[1])
        if side > 0 and (z / side > TALL_RATIO or (z > TALL_MM and side < NARROW_MM)):
            out.append(f"tall and narrow ({z:.0f} mm high on a {side:.0f} mm base) with no brim -> reslice with --brim")
    # 2 supports
    sup = sum(v for k, v in shares.items() if k.startswith("Support"))
    enabled = str(info.get("support_enabled", "")).lower() in ("1", "true", "yes") or bool(info.get("supports"))
    if sup > SUPPORT_HIGH:
        out.append(f"supports are {sup * 100:.0f}% of filament -> try rotating the part / --keep-orient off")
    elif enabled and sup < SUPPORT_TINY:
        out.append("supports barely used -> try without --supports")
    # 3 heavy settings on a small part
    walls, infill = _num(info.get("walls")), _num(info.get("infill"))
    if grams and grams < SMALL_G and ((walls or 0) >= HEAVY_WALLS or (infill or 0) >= HEAVY_INFILL):
        wall_share = shares.get("Outer wall", 0) + shares.get("Inner wall", 0)
        save = 0.0
        if walls and walls > LIGHT_WALLS:
            save += wall_share * grams * (1 - LIGHT_WALLS / walls)
        if infill and infill > LIGHT_INFILL:
            save += shares.get("Sparse infill", 0) * grams * (1 - LIGHT_INFILL / infill)
        out.append(f"functional settings on a small part ({grams:.0f} g) -> walls 2-3 / infill 15% saves ~{save:.1f} g (estimate)")
    # 4 placement and bed mesh
    if fp:
        cx, cy = (fp[0] + fp[2]) / 2, (fp[1] + fp[3]) / 2
        dx, dy = cx - bed[0] / 2, cy - bed[1] / 2
        if dx < -BACK_LEFT_MARGIN and dy > BACK_LEFT_MARGIN:
            out.append("part sits back-left (lowest corner of the mesh) -> centre it")
        elif (dx * dx + dy * dy) ** 0.5 > OFF_CENTRE_MM:
            out.append(f"part is {(dx * dx + dy * dy) ** 0.5:.0f} mm from the bed centre -> centre it")
        hits, worst = _mesh_hits(info, fp, bed)
        if hits:
            out.append(f"footprint covers {hits} mesh points off by more than {MESH_DEV_MM} mm (worst {worst:.2f} mm) "
                       "-> move the part or re-level (p3d level)")
    # 5 filament mismatch
    ft, sm = str(info.get("filament_type", "")).strip().upper(), str(info.get("spool_material", "")).strip().upper()
    if ft and sm and ft != sm:
        out.append(f"G-code is sliced for {ft} but the active spool is {sm} -> reslice with -f {sm.lower()} or switch spool")
    # 6 long print (low priority)
    mins, lh = _num(info.get("minutes")), _num(info.get("layer_height"))
    sparse = shares.get("Sparse infill", 0) + shares.get("Inner wall", 0)
    if mins and mins > LONG_MIN and lh and lh <= FINE_LAYER_MAX and sparse > SPARSE_SHARE:
        out.append(f"long print ({mins / 60:.1f} h), mostly hidden infill/inner walls -> draft quality saves time if it is not cosmetic")
    # 7 tall part standing on separate small feet
    isl = info.get("islands") or []
    if len(isl) >= 2 and z and z > ISLAND_TALL_MM and min(isl) < ISLAND_SMALL_MM2:
        out.append(f"first layer is {len(isl)} separate islands (smallest {min(isl):.0f} mm2) under a {z:.0f} mm tall part "
                   "-> merge the feet into one base pad in the model (hull), and --brim")
    return out


def first_layer_islands(lines, cell=1.0):
    """Areas (mm2, rough) of the separate first-layer islands, brim/skirt excluded. Rasterized on a `cell` grid."""
    layer, feat, pts, x, y = 0, None, set(), None, None
    for line in lines:
        if line.startswith(";LAYER_CHANGE"):
            layer += 1
            if layer > 1:
                break
        elif line.startswith(";TYPE:"):
            feat = line[6:].strip()
        elif line.startswith(("G1", "G0")):
            m, n = re.search(r"X(-?[\d.]+)", line), re.search(r"Y(-?[\d.]+)", line)
            nx, ny = (float(m.group(1)) if m else x), (float(n.group(1)) if n else y)
            if layer == 1 and " E" in line and feat not in ("Brim", "Skirt", "Custom") and None not in (x, y, nx, ny):
                k = int(max(abs(nx - x), abs(ny - y)) / cell) + 1
                for i in range(k + 1):
                    pts.add((round((x + (nx - x) * i / k) / cell), round((y + (ny - y) * i / k) / cell)))
            x, y = nx, ny
    seen, out = set(), []
    for p in pts:
        if p in seen:
            continue
        stack, size = [p], 0
        seen.add(p)
        while stack:
            q = stack.pop()
            size += 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    r = (q[0] + dx, q[1] + dy)
                    if r in pts and r not in seen:
                        seen.add(r)
                        stack.append(r)
        out.append(size * cell * cell)
    return sorted(out, reverse=True)


def _read_json(p):
    try:
        return json.loads(pathlib.Path(p).read_text())
    except Exception:
        return {}


def _latest_mesh():
    try:
        from . import config
        rows = pathlib.Path(config.get().data, "bed_mesh_log.csv").read_text().strip().splitlines()
        cell = rows[-1].rsplit(",", 1)[-1].strip().strip('"')
        return [[float(v) for v in r.split()] for r in cell.split("|")]
    except Exception:
        return None


def _spool_material():
    try:
        from . import spools
        s = spools.active(spools.load())
        return (s or {}).get("material", "")
    except Exception:
        return ""


def gather(path):
    """G-code file or job dir -> info dict for advise(). Reads only."""
    from . import gcode
    g = pathlib.Path(path).expanduser()
    jobdir = g if g.is_dir() else g.parent
    if g.is_dir():
        g = next(g.glob("*.gcode"))
    info = {"gcode": str(g)}
    proc = _read_json(jobdir / "process.json")
    job = _read_json(jobdir / "job.json").get("settings", {})
    feat, t, lines = collections.Counter(), None, []
    with open(g, errors="replace") as f:
        for line in f:
            lines.append(line)
            if line.startswith(";TYPE:"):
                t = line[6:].strip()
            elif t and line.startswith("G1") and " E" in line:
                m = re.search(r" E(\d*\.?\d+)", line)
                if m:
                    feat[t] += float(m.group(1))
            elif line.startswith("; ") and " = " in line:
                k, v = line[2:].split(" = ", 1)
                info.setdefault(k.strip(), v.strip())
            elif line.startswith("; max_z_height"):
                info.setdefault("max_z", line.split(":")[-1].strip())
    tot = sum(feat.values()) or 1
    info["shares"] = {k: v / tot for k, v in feat.items()}
    info["brim_used"] = "Brim" in feat
    info["max_z"] = info.get("max_z") or info.get("max_z_height")
    info["grams"] = info.get("total filament used [g]")
    info["minutes"] = _minutes(info.get("estimated printing time (normal mode)"))
    info["walls"] = info.get("wall_loops") or proc.get("wall_loops")
    info["infill"] = info.get("sparse_infill_density") or proc.get("sparse_infill_density")
    info["support_enabled"] = info.get("enable_support") or proc.get("enable_support") or ""
    info["supports"] = bool(job.get("supports"))
    if job.get("brim") and not info.get("brim_type"):
        info["brim_type"] = "outer_only"
    m = re.match(r"0x0,(\d+)x0,\d+x(\d+)", info.get("printable_area", ""))
    if m:
        info["bed"] = (float(m.group(1)), float(m.group(2)))
    cmds, layer_at, _, _ = gcode.parse(lines)
    info["footprint"] = gcode.footprint(cmds, upto=1, layer_at=layer_at)
    info["islands"] = first_layer_islands(lines)
    info["mesh"] = _latest_mesh()
    info["spool_material"] = _spool_material()
    return info


def format_advice(lines):
    return ["Advice: looks good"] if not lines else ["Advice:"] + [f"  - {x}" for x in lines]


def report(path):
    """Advice block for a G-code file or job dir, for printing after slice / queue add. Never raises."""
    try:
        return "\n".join(format_advice(advise(gather(path))))
    except Exception as e:  # advice must never block slicing or queueing
        return f"Advice: skipped ({e.__class__.__name__})"
