"""Stream a G-code file to Marlin safely: line numbers + checksums, wait for 'ok', honour Resend.

Writes progress to state.json, stops cleanly when the STOP file appears, pings ntfy when done/failed.
Run via `p3d print`, not directly.
"""
import json, os, pathlib, re, subprocess, sys, time
import serial
import printlog

ROOT = pathlib.Path(__file__).resolve().parent
STATE, STOP = pathlib.Path(os.environ.get("P3D_STATE", ROOT / "state.json")), ROOT / "STOP"
PORT = os.environ.get("P3D_PORT", "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0")
NOTIFY = pathlib.Path.home() / ".local/bin/p3d-notify"
SILENCE_LIMIT = 300  # s with no reply at all → assume the link is dead
SAFE_STOP = ["M104 S0", "M140 S0", "M107", "G91", "G1 Z10 F600", "G90", "G1 X0 Y220 F3000", "M84"]


def notify(title, msg, tags="printer"):
    if os.environ.get("P3D_NO_NOTIFY"):
        return
    subprocess.run([str(NOTIFY), title, msg, tags], check=False)


def header_info(path):
    """Layer count from the slicer header (comments are stripped by load())."""
    layers = None
    with open(path, errors="replace") as f:
        for i, line in enumerate(f):
            m = re.match(r";\s*total layer number\s*[:=]\s*(\d+)", line)
            if m:
                layers = int(m.group(1))
                break
            if i > 400:
                break
    return layers


TEMP_RE = {k: re.compile(p) for k, p in {
    "nozzle": r"T:\s*(-?[\d.]+)\s*/\s*(-?[\d.]+)", "bed": r"B:\s*(-?[\d.]+)\s*/\s*(-?[\d.]+)"}.items()}


def parse_temps(line):
    out = {}
    for k, rx in TEMP_RE.items():
        m = rx.search(line)
        if m:
            out[k], out[k + "_target"] = float(m.group(1)), float(m.group(2))
    return out


def load(path):
    lines = []
    for raw in open(path, errors="replace"):
        cmd = raw.split(";", 1)[0].strip()
        if cmd:
            lines.append(cmd)
    return lines


def framed(n, cmd):
    body = f"N{n} {cmd}"
    cs = 0
    for ch in body.encode():
        cs ^= ch
    return f"{body}*{cs}\n".encode()


class Link:
    def __init__(self):
        self.ser = serial.Serial(PORT, 115200, timeout=1, exclusive=True)
        time.sleep(3)  # board resets on connect
        self.ser.write(b"\n")
        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.temps = ""
        self.t = {}
        self.exchange(0, "M110 N0")  # reset line numbering

    def exchange(self, n, cmd):
        """Send line n, block until 'ok'. Returns the next line number (earlier one if Marlin asks to resend)."""
        self.ser.write(framed(n, cmd))
        nxt, last = n + 1, time.time()
        while True:
            line = self.ser.readline().decode(errors="replace").strip()
            if STOP.exists() and cmd.startswith(("M109", "M190")) and not getattr(self, "broke", False):
                self.ser.write(b"M108\n")  # emergency parser: break out of the heat-up wait
                self.broke = True
            if not line:
                if time.time() - last > SILENCE_LIMIT:
                    raise RuntimeError(f"no reply for {SILENCE_LIMIT}s after: {cmd}")
                continue
            last = time.time()
            low = line.lower()
            if "T:" in line:
                self.temps = line.replace("ok", "").strip()
                self.t.update(parse_temps(line))
            if low.startswith(("resend", "rs:")):
                digits = "".join(ch for ch in line.split(":")[-1] if ch.isdigit())
                nxt = int(digits) if digits else n
            elif low.startswith("ok"):
                return nxt
            elif "kill" in low or "halted" in low or "heating failed" in low or "thermal runaway" in low:
                raise RuntimeError(f"printer error: {line}")

    def run(self, cmds, check_stop=False, on_progress=None):
        """Stream cmds as lines 1..len (renumbered from 0 first)."""
        self.exchange(0, "M110 N0")
        n = 1
        while n <= len(cmds):
            if check_stop and STOP.exists():
                raise KeyboardInterrupt(n)
            n = self.exchange(n, cmds[n - 1])
            if on_progress:
                on_progress(n)
        if on_progress:
            on_progress(len(cmds))


def save(**kw):
    tmp = STATE.with_name(STATE.name + ".tmp")
    tmp.write_text(json.dumps(kw, indent=1))
    os.replace(tmp, STATE)


def main(path):
    name = pathlib.Path(path).stem
    lines = ["M155 S5"] + load(path) + ["M155 S0"]  # Marlin auto-reports temps during the print
    total, t0 = len(lines), time.time()
    layers = header_info(path)
    info = printlog.gcode_info(path)
    est = info.get("est_min") or None
    job = {"est_total_min": est, "grams": info.get("grams") or None, "filament": info.get("filament") or None,
           "job_dir": str(pathlib.Path(path).resolve().parent), "total_layers": layers}
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))
    link = Link()
    cur = {"z": None, "layer": None, "pct": None, "rem": None, "last": 0.0, "z_seen": set()}
    layer_zs = []

    def write(status="printing", i=0, force=False):
        now = time.time()
        if not force and now - cur["last"] < 5:
            return
        cur["last"] = now
        pct = cur["pct"] if cur["pct"] is not None else round(100 * i / total, 1)
        rem = cur["rem"]
        if rem is None and est and pct:
            rem = max(round(est * (1 - pct / 100), 1), 0)
        eta = time.strftime("%H:%M", time.localtime(now + rem * 60)) if rem is not None else None
        save(file=name, status=status, progress=pct, remaining_min=rem,
             elapsed_min=round((now - t0) / 60, 1), eta=eta, z=cur["z"], layer=cur["layer"],
             nozzle=link.t.get("nozzle"), nozzle_target=link.t.get("nozzle_target"),
             bed=link.t.get("bed"), bed_target=link.t.get("bed_target"),
             temps=link.temps, started=started, updated=time.strftime("%Y-%m-%dT%H:%M:%S"), **job)

    def progress(i):
        cmd = lines[i - 2] if i >= 2 else ""  # the line just acknowledged
        m = re.match(r"M73 P(\d+)(?: R(\d+))?", cmd)
        if m:
            cur["pct"] = int(m.group(1))
            cur["rem"] = int(m.group(2)) if m.group(2) else cur["rem"]
        elif cmd.startswith(("G0 ", "G1 ")):
            z = re.search(r"\bZ(-?[\d.]+)", cmd)
            if z:
                cur["z"] = float(z.group(1))
                if cur["z"] > 0:
                    cur["z_seen"].add(cur["z"])
                    cur["layer"] = len(cur["z_seen"]) if not layers else min(len(cur["z_seen"]), layers)
        write(i=i)

    write(i=0, force=True)
    notify("Print started", name, "printer")

    try:
        link.run(lines, check_stop=True, on_progress=progress)
        mins = round((time.time() - t0) / 60)
        save(file=name, status="done", progress=100, minutes=mins, **job)
        notify("Print done", f"{name}: {mins} min", "white_check_mark")
        printlog.log_job(path, "done", mins)
    except KeyboardInterrupt as stop:
        link.run(SAFE_STOP)
        save(file=name, status="cancelled", at_line=stop.args[0] if stop.args else None, of=total, **job)
        notify("Print cancelled", name, "stop_sign")
        printlog.log_job(path, "cancelled", round((time.time() - t0) / 60))
    except Exception as e:
        try:
            link.run(SAFE_STOP)
        except Exception:
            pass
        save(file=name, status="failed", error=str(e), **job)
        notify("Print FAILED", f"{name}: {e}", "warning")
        printlog.log_job(path, "failed", round((time.time() - t0) / 60))
        raise
    finally:
        STOP.unlink(missing_ok=True)
        link.ser.close()


if __name__ == "__main__":
    main(sys.argv[1])
