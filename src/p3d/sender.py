"""Stream a G-code file to Marlin safely: line numbers + checksums, wait for 'ok', honour Resend.

Writes progress to state.json, stops cleanly when the STOP file appears, pings ntfy when done/failed.
Every job ends with a final state: status done/failed/cancelled + ended_at (status/wait read it).
Run by the p3d-print service (`p3d print`), not directly.
"""
import csv, json, pathlib, re, sys, time

from . import config, gcode, pause, printlog, spools
from .config import notify

SILENCE_LIMIT = 300  # s with no reply at all → assume the link is dead
STOP = None  # set in main()/Link from config (a path; tests may override)


def safe_stop():
    return ["M104 S0", "M140 S0", "M107", "G91", "G1 Z10 F600", "G90", f"G1 X0 Y{config.get().park_y} F3000", "M84"]


def stop_file():
    return STOP or config.get().stop


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


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
        self.ser = config.open_serial(timeout=1)
        time.sleep(3)  # board resets on connect
        self.ser.write(b"\n")
        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.temps = ""
        self.t = {}
        self.on_temp = None   # called on every temp report, so the dashboard updates during heat-up waits
        self.exchange(0, "M110 N0")  # reset line numbering

    def exchange(self, n, cmd):
        """Send line n, block until 'ok'. Returns the next line number (earlier one if Marlin asks to resend)."""
        self.ser.write(framed(n, cmd))
        nxt, last = n + 1, time.time()
        while True:
            line = self.ser.readline().decode(errors="replace").strip()
            if stop_file().exists() and cmd.startswith(("M109", "M190")) and not getattr(self, "broke", False):
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
                if self.on_temp:
                    self.on_temp()
            if low.startswith(("resend", "rs:")):
                digits = "".join(ch for ch in line.split(":")[-1] if ch.isdigit())
                nxt = int(digits) if digits else n
            elif low.startswith("ok"):
                return nxt
            elif "kill" in low or "halted" in low or "heating failed" in low or "thermal runaway" in low:
                raise RuntimeError(f"printer error: {line}")

    def run(self, cmds, check_stop=False, on_progress=None, before=None):
        """Stream cmds as lines 1..len (renumbered from 0 first). before(n) runs ahead of line n (may call run() itself)."""
        self.exchange(0, "M110 N0")
        n = 1
        while n <= len(cmds):
            if check_stop and stop_file().exists():
                raise KeyboardInterrupt(n)
            if before and before(n):
                self.exchange(0, f"M110 N{n - 1}")  # the hook used its own numbering: carry on at line n
            n = self.exchange(n, cmds[n - 1])
            if on_progress:
                on_progress(n)
        if on_progress:
            on_progress(len(cmds))


COOL_NOZZLE, COOL_BED = 50.0, 40.0   # below these it's safe to switch the printer off


def cooldown(link, limit_min=60):
    """After a job: heaters off, wait until cool, then fans + all steppers off and ping ntfy.
    The printer has no software power switch (no smart plug yet), so this is 'safe to switch off'."""
    link.run(["M104 S0", "M140 S0", "M84"])
    t0 = time.time()
    while time.time() - t0 < limit_min * 60:
        link.run(["M105"])
        n, b = link.t.get("nozzle"), link.t.get("bed")
        if n is not None and b is not None and n < COOL_NOZZLE and b < COOL_BED:
            link.run(["M107", "M84"])
            notify("Printer cool", f"nozzle {n:.0f} C, bed {b:.0f} C, motors off. Safe to switch off / remove print.",
                   "snowflake", urgent=True)
            return True
        time.sleep(30)
    notify("Printer still warm", f"after {limit_min} min: nozzle {n} C, bed {b} C", "warning", urgent=True)
    return False


def save(**kw):
    config.write_state(**kw)


def main_cooldown():
    """Standalone: `p3d cooldown` (waits for a running print to end first)."""
    while config.print_running():
        time.sleep(30)
    cooldown(Link())


def main(path):
    path = str(pathlib.Path(path).resolve())
    name = pathlib.Path(path).stem
    job_id = pathlib.Path(path).parent.name
    cmds, layer_at, layer_z, n_layers = gcode.load(path)
    lines = ["M155 S5"] + cmds + ["M155 S0"]  # Marlin auto-reports temps during the print
    total, t0 = len(lines), time.time()
    layers = header_info(path) or (n_layers or None)
    starts = {1 + i: layer_at[i] for i in range(len(cmds)) if layer_at[i] and (i == 0 or layer_at[i] != layer_at[i - 1])}
    spool = spools.load().get("active", "")
    info = printlog.gcode_info(path)
    est = info.get("est_min") or None
    job = {"est_total_min": est, "grams": info.get("grams") or None, "filament": info.get("filament") or None,
           "job_dir": str(pathlib.Path(path).parent), "total_layers": layers, "job_id": job_id, "spool": spool}
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))
    try:
        link = Link()
    except Exception as e:
        save(file=name, status="failed", error=f"cannot open printer: {e}", started=started, ended_at=now_iso(), **job)
        notify("Print FAILED", f"{name}: cannot open printer: {e}", "warning", urgent=True)
        raise
    cur = {"z": None, "layer": None, "pct": None, "rem": None, "last": 0.0, "z_seen": set(), "status": "printing",
           "layer_done": 0, "z_done": None}
    pos = gcode.Tracker()
    pause_at = set(pause.read_pause_at())
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(t0))
    samples = printlog.data_dir() / "prints" / f"{stamp}-{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}.csv"
    sm = {"last": 0.0, "ok": True, "max_n": None, "min_n": None, "bed_sum": 0.0, "bed_n": 0}
    COLS = ["time", "elapsed_min", "progress", "remaining_min", "z", "layer", "nozzle", "nozzle_target", "bed", "bed_target"]

    def metrics(i):
        now = time.time()
        pct = cur["pct"] if cur["pct"] is not None else round(100 * i / total, 1)
        rem = cur["rem"]
        if rem is None and est and pct:
            rem = max(round(est * (1 - pct / 100), 1), 0)
        return now, pct, rem

    def track():
        n, nt, b = link.t.get("nozzle"), link.t.get("nozzle_target"), link.t.get("bed")
        if n is not None:
            sm["max_n"] = n if sm["max_n"] is None else max(sm["max_n"], n)
            if (cur["layer"] or 0) >= 2 and (nt or 0) > 150:  # after the first layer, heater on
                sm["min_n"] = n if sm["min_n"] is None else min(sm["min_n"], n)
        if b is not None and (link.t.get("bed_target") or 0) > 0:
            sm["bed_sum"] += b
            sm["bed_n"] += 1

    def sample(i, force=False):
        """One CSV row every 30 s (and at the end). Never lets logging break the print."""
        now, pct, rem = metrics(i)
        if not sm["ok"] or (not force and now - sm["last"] < 30):
            return
        sm["last"] = now
        try:
            samples.parent.mkdir(parents=True, exist_ok=True)
            new = not samples.exists()
            with open(samples, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(COLS)
                w.writerow([time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)), round((now - t0) / 60, 2), pct, rem,
                            cur["z"], cur["layer"], link.t.get("nozzle"), link.t.get("nozzle_target"),
                            link.t.get("bed"), link.t.get("bed_target")])
        except Exception:
            sm["ok"] = False

    def extra():
        e = {"started": started.replace("T", " ")[:16], "ended": time.strftime("%Y-%m-%d %H:%M"), "spool": spool,
             "grams_used": cur.get("used", ""),
             "max_nozzle": sm["max_n"], "min_nozzle": sm["min_n"],
             "avg_bed": round(sm["bed_sum"] / sm["bed_n"], 1) if sm["bed_n"] else ""}
        if samples.exists():
            e["samples_file"] = f"prints/{samples.name}"
        return e

    def finish(status, mins):
        """Final sample, log row, lifetime counters (M78). Failures here must not break the job end."""
        try:
            sample(total, force=True)
        except Exception:
            pass
        try:
            if spool:
                used, left = spools.on_job_end(spool, job.get("grams"), status, metrics(cur.get("i", 0))[1] if status != "done" else 100,
                                               job=name)
                cur["used"] = used
        except Exception:
            pass
        try:
            printlog.log_job(path, status, mins, extra=extra())
        except Exception:
            pass
        try:
            ser = link.ser
            ser.reset_input_buffer()
            ser.write(b"M78\n")
            buf, end = "", time.time() + 6
            while time.time() < end:
                buf += ser.readline().decode(errors="replace")
                if "Filament used" in buf:
                    break
            printlog.append_stats(buf)
        except Exception:
            pass

    def write(status=None, i=0, force=False):
        status = status or cur["status"]
        now = time.time()
        if not force and now - cur["last"] < 5:
            return
        cur["last"] = now
        track()
        sample(i)
        _, pct, rem = metrics(i)
        eta = time.strftime("%H:%M", time.localtime(now + rem * 60)) if rem is not None else None
        save(file=name, status=status, progress=pct, remaining_min=rem,
             elapsed_min=round((now - t0) / 60, 1), eta=eta, z=cur["z"], layer=cur["layer"],
             nozzle=link.t.get("nozzle"), nozzle_target=link.t.get("nozzle_target"),
             bed=link.t.get("bed"), bed_target=link.t.get("bed_target"),
             temps=link.temps, started=started, updated=time.strftime("%Y-%m-%dT%H:%M:%S"),
             layer_done=cur["layer_done"], z_done=cur["z_done"], **job)

    def run_json():
        """Last completed layer, kept next to the G-code so `p3d recover` can use it after the next job overwrites the state."""
        try:
            (pathlib.Path(path).parent / "run.json").write_text(json.dumps(
                {"layer": cur["layer"], "layer_done": cur["layer_done"], "z_done": cur["z_done"], "status": cur["status"],
                 "total_layers": layers, "updated": now_iso()}))
        except Exception:
            pass

    def progress(i):
        cur["i"] = i
        cmd = lines[i - 2] if i >= 2 else ""  # the line just acknowledged
        if cmd:
            pos.feed(cmd)
        m = re.match(r"M73 P(\d+)(?: R(\d+))?", cmd)
        if m:
            cur["pct"] = int(m.group(1))
            cur["rem"] = int(m.group(2)) if m.group(2) else cur["rem"]
        elif cmd.startswith(("G0 ", "G1 ")):
            z = re.search(r"\bZ(-?[\d.]+)", cmd)
            if z:
                cur["z"] = float(z.group(1))
                if not layer_z and cur["z"] > 0:  # no layer markers in the file: count distinct Z values
                    cur["z_seen"].add(cur["z"])
                    cur["layer"] = len(cur["z_seen"]) if not layers else min(len(cur["z_seen"]), layers)
        if layer_z and 2 <= i - 1 <= len(cmds) + 1:
            lay = layer_at[i - 3] if 0 <= i - 3 < len(cmds) else 0   # layer of the line just acknowledged
            if lay and lay != cur["layer"]:
                cur["layer"] = lay
                cur["layer_done"] = lay - 1
                cur["z_done"] = layer_z.get(lay - 1)
                run_json()
        write(i=i)

    def hold(n):
        """Before line n: pause at a layer boundary when asked (PAUSE file or --pause-at-layer). True if it paused."""
        layer = starts.get(n - 1)
        if not layer:
            return False
        c = config.get()
        pause_at.update(pause.read_pause_at())
        if not pause.due(layer, c.pause.exists(), pause_at):
            return False
        cmds_ = pause.pause_cmds(pos, c.park_y)
        c.pause.unlink(missing_ok=True)
        pause_at.discard(layer)
        pause.write_pause_at(sorted(pause_at))
        if cmds_ is None:
            return False
        link.run(cmds_)
        cur["status"] = "paused"
        write(i=cur.get("i", 0), force=True)
        run_json()
        base = config.web_base()
        note_f = pathlib.Path(path).parent / "PAUSE_NOTE.txt"   # job-specific instruction (e.g. "drop the ball in")
        note = note_f.read_text().strip() + "\n\n" if note_f.exists() else ""
        notify("Print paused", f"{note}{name} paused before layer {layer}. Resume when ready (wipe ooze off the nozzle first).", "pause_button",
               actions=f"http, Resume, {base}/api/resume, method=POST; http, Cancel, {base}/api/cancel, method=POST", urgent=True)
        c.resume.unlink(missing_ok=True)
        waited = 0
        while not c.resume.exists():
            if stop_file().exists():
                raise KeyboardInterrupt(n)
            time.sleep(2)
            waited += 2
            if waited % 20 == 0:
                link.run(["M105"])  # keeps the link and the dashboard temps alive while parked
        c.resume.unlink(missing_ok=True)
        link.run(pause.resume_cmds(pos, link.t.get("nozzle_target") or 0))
        cur["status"] = "printing"
        write(i=cur.get("i", 0), force=True)
        notify("Print resumed", name, "arrow_forward")
        return True

    write(i=0, force=True)
    link.on_temp = lambda: write(i=cur.get("i", 0))  # write() rate-limits itself to every 5 s
    notify("Print started", name, "printer", urgent=True, quip_event="print_start")

    def final(status, **kw):
        link.on_temp = None  # temp replies during cooldown must not overwrite the final state with "printing"
        cur["status"] = status
        save(file=name, status=status, started=started, ended_at=now_iso(),
             minutes=round((time.time() - t0) / 60), z=cur["z"], layer=cur["layer"],
             layer_done=cur["layer_done"], z_done=cur["z_done"], **kw, **job)
        run_json()

    try:
        link.run(lines, check_stop=True, on_progress=progress, before=hold)
        mins = round((time.time() - t0) / 60)
        final("done", progress=100)
        notify("Print done", f"{name}: {mins} min. Rate it: p3d rate 1-5", "white_check_mark", urgent=True, quip_event="print_done")
        finish("done", mins)
        try:
            cooldown(link)
        except Exception:
            pass
    except KeyboardInterrupt as stop:
        link.run(safe_stop())
        final("cancelled", at_line=stop.args[0] if stop.args else None, of=total, progress=metrics(cur.get("i", 0))[1])
        notify("Print cancelled", name, "stop_sign", urgent=True, quip_event="print_failed")
        finish("cancelled", round((time.time() - t0) / 60))
    except Exception as e:
        try:
            link.run(safe_stop())
        except Exception:
            pass
        final("failed", error=str(e), progress=metrics(cur.get("i", 0))[1])
        notify("Print FAILED", f"{name}: {e}", "warning", urgent=True, quip_event="print_failed")
        finish("failed", round((time.time() - t0) / 60))
        raise
    finally:
        stop_file().unlink(missing_ok=True)
        for f in (config.get().pause, config.get().resume):
            f.unlink(missing_ok=True)
        link.ser.close()


def cli(argv=None):
    """python -m p3d.sender FILE.gcode | --queued (path from the queue file) | --cooldown"""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        sys.exit(cli.__doc__)
    if argv[0] == "--cooldown":
        return main_cooldown()
    if argv[0] == "--queued":
        q = config.get().queue
        path = q.read_text().strip()
        q.unlink(missing_ok=True)
        return main(path)
    return main(argv[0])


if __name__ == "__main__":
    cli()
