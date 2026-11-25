"""Run a print on a network printer (Klipper, OctoPrint, PrusaLink, Bambu) and track it like sender.py does.

Uploads and starts the job through the printer backend, then polls its status every few seconds and writes the same
state.json fields as sender.py (dashboard, `p3d status`, print log, spools and alerts work unchanged). STOP / PAUSE /
RESUME control files and pause-at-layer are honoured by calling the backend.
Run by the p3d-print service (`p3d print`), not directly: python -m p3d.netsender FILE | --queued
"""
import csv, pathlib, re, sys, time

from . import config, pause, printlog, printers, spools
from .config import notify
from .printers import BackendError
from .sender import header_info, now_iso

POLL = 5                 # s between status polls (also the state.json write rate, like sender.py)
START_TIMEOUT = 600      # s the printer may take to report 'printing' after the upload
CANCEL_TIMEOUT = 120     # s to wait for the printer to confirm a cancel
MAX_ERRORS = 12          # consecutive failed polls (about a minute) before giving up on the printer
SAMPLE_EVERY = 30
COLS = ["time", "elapsed_min", "progress", "remaining_min", "z", "layer", "nozzle", "nozzle_target", "bed", "bed_target"]


def temps_text(s):
    if s.get("nozzle") is None and s.get("bed") is None:
        return ""
    f = lambda v: "?" if v is None else f"{v:.1f}"
    return f"T:{f(s.get('nozzle'))} /{f(s.get('nozzle_target'))} B:{f(s.get('bed'))} /{f(s.get('bed_target'))}"


def job_name(path):
    n = pathlib.Path(path).name
    for suf in (".gcode.3mf", ".3mf", ".gcode", ".bgcode"):
        if n.lower().endswith(suf):
            return n[:-len(suf)]
    return pathlib.Path(path).stem


def main(path, backend=None):
    path = str(pathlib.Path(path).resolve())
    name, job_id = job_name(path), pathlib.Path(path).parent.name
    c = config.get()
    b = backend or printers.get_backend(c)
    t0 = time.time()
    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))
    spool = spools.load().get("active", "")
    try:
        info = printlog.gcode_info(path) if path.endswith(".gcode") else {}
    except Exception:
        info = {}
    try:
        layers = header_info(path) if path.endswith(".gcode") else None
    except Exception:
        layers = None
    est = info.get("est_min") or None
    job = {"est_total_min": est, "grams": info.get("grams") or None, "filament": info.get("filament") or None,
           "job_dir": str(pathlib.Path(path).parent), "total_layers": layers, "job_id": job_id, "spool": spool}
    pause_at = set(pause.read_pause_at())
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(t0))
    samples = printlog.data_dir() / "prints" / f"{stamp}-{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}.csv"
    cur = {"status": "printing", "last": 0.0, "pct": 0.0, "rem": None, "layer": None, "t": {}, "used": "", "samp": 0.0, "samp_ok": True}
    sm = {"max_n": None, "min_n": None, "bed_sum": 0.0, "bed_n": 0}

    def save(**kw):
        config.write_state(**kw)

    def fail_early(msg):
        save(file=name, status="failed", error=msg, started=started, ended_at=now_iso(), **job)
        notify("Print FAILED", f"{name}: {msg}", "warning", urgent=True)

    if pause_at and not b.LAYERS:
        msg = f"--pause-at-layer is not available for {b.TYPE} printers (no layer number reported)"
        fail_early(msg)
        raise SystemExit(msg)

    def metrics():
        pct = cur["pct"]
        rem = cur["rem"]
        if rem is None and est and pct:
            rem = max(round(est * (1 - pct / 100), 1), 0)
        return pct, rem

    def track():
        t = cur["t"]
        n, b_ = t.get("nozzle"), t.get("bed")
        if n is not None:
            sm["max_n"] = n if sm["max_n"] is None else max(sm["max_n"], n)
            if (cur["layer"] or 0) >= 2 and (t.get("nozzle_target") or 0) > 150:
                sm["min_n"] = n if sm["min_n"] is None else min(sm["min_n"], n)
        if b_ is not None and (t.get("bed_target") or 0) > 0:
            sm["bed_sum"] += b_
            sm["bed_n"] += 1

    def sample(force=False):
        now = time.time()
        if not cur["samp_ok"] or (not force and now - cur["samp"] < SAMPLE_EVERY):
            return
        cur["samp"] = now
        pct, rem = metrics()
        t = cur["t"]
        try:
            samples.parent.mkdir(parents=True, exist_ok=True)
            new = not samples.exists()
            with open(samples, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(COLS)
                w.writerow([time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)), round((now - t0) / 60, 2), pct, rem, None,
                            cur["layer"], t.get("nozzle"), t.get("nozzle_target"), t.get("bed"), t.get("bed_target")])
        except Exception:
            cur["samp_ok"] = False

    def extra():
        e = {"started": started.replace("T", " ")[:16], "ended": time.strftime("%Y-%m-%d %H:%M"), "spool": spool,
             "grams_used": cur["used"], "max_nozzle": sm["max_n"], "min_nozzle": sm["min_n"],
             "avg_bed": round(sm["bed_sum"] / sm["bed_n"], 1) if sm["bed_n"] else ""}
        if samples.exists():
            e["samples_file"] = f"prints/{samples.name}"
        return e

    def finish(status, mins):
        """Final sample, spool deduction, print-log row (same order as sender.py). Never breaks the job end."""
        try:
            sample(force=True)
        except Exception:
            pass
        try:
            if spool:
                used, _ = spools.on_job_end(spool, job.get("grams"), status, metrics()[0] if status != "done" else 100, job=name)
                cur["used"] = used
        except Exception:
            pass
        try:
            printlog.log_job(path, status, mins, extra=extra())
        except Exception:
            pass

    def write(status=None, force=False):
        status = status or cur["status"]
        now = time.time()
        if not force and now - cur["last"] < POLL:
            return
        cur["last"] = now
        track()
        sample()
        pct, rem = metrics()
        eta = time.strftime("%H:%M", time.localtime(now + rem * 60)) if rem is not None else None
        t = cur["t"]
        lay = cur["layer"]
        save(file=name, status=status, progress=pct, remaining_min=rem, elapsed_min=round((now - t0) / 60, 1), eta=eta,
             z=None, layer=lay, nozzle=t.get("nozzle"), nozzle_target=t.get("nozzle_target"), bed=t.get("bed"),
             bed_target=t.get("bed_target"), temps=temps_text(t), started=started, updated=time.strftime("%Y-%m-%dT%H:%M:%S"),
             layer_done=max(lay - 1, 0) if lay else 0, z_done=None, **job)

    def final(status, **kw):
        cur["status"] = status
        save(file=name, status=status, started=started, ended_at=now_iso(), minutes=round((time.time() - t0) / 60), z=None,
             layer=cur["layer"], layer_done=max(cur["layer"] - 1, 0) if cur["layer"] else 0, z_done=None, **kw, **job)

    def take(s):
        """Copy a backend status into cur (progress as 0-100 like sender.py)."""
        if s.get("progress") is not None:
            cur["pct"] = round(100 * min(max(s["progress"], 0.0), 1.0), 1)
        cur["rem"] = round(s["left_s"] / 60, 1) if s.get("left_s") is not None else None
        if s.get("layer") is not None:
            cur["layer"] = int(s["layer"])
        cur["t"] = {k: s.get(k) for k in ("nozzle", "nozzle_target", "bed", "bed_target")}

    cur["status"] = "printing"
    save(file=name, status="printing", progress=0, started=started, updated=now_iso(), **job)
    try:
        b.start(path)
    except Exception as e:
        fail_early(f"cannot start on the printer: {e}")
        b.close()
        raise
    write(force=True)
    notify("Print started", name, "printer", urgent=True, quip_event="print_start")

    seen = cancelled_at = None
    errors = 0
    try:
        while True:
            if config.get().stop.exists() and cancelled_at is None:
                try:
                    b.cancel()
                except BackendError:
                    pass
                cancelled_at = time.time()
            try:
                s = b.status()
                errors = 0
            except BackendError as e:
                errors += 1
                if errors >= MAX_ERRORS:
                    raise RuntimeError(f"lost the printer: {e} (the job may still be running on it)") from None
                time.sleep(POLL)
                continue
            take(s)
            st = s["state"]
            if st in ("printing", "paused"):
                seen = True
            if cancelled_at is not None:
                if st in ("cancelled", "failed", "idle", "done") or time.time() - cancelled_at > CANCEL_TIMEOUT:
                    final("cancelled", progress=metrics()[0])
                    notify("Print cancelled", name, "stop_sign", urgent=True, quip_event="print_failed")
                    finish("cancelled", round((time.time() - t0) / 60))
                    return 0
            elif st == "done" and seen:
                mins = round((time.time() - t0) / 60)
                final("done", progress=100)
                notify("Print done", f"{name}: {mins} min. Rate it: p3d rate 1-5", "white_check_mark", urgent=True, quip_event="print_done")
                finish("done", mins)
                return 0
            elif st == "cancelled" and seen:  # stopped on the printer itself
                final("cancelled", progress=metrics()[0])
                notify("Print cancelled", name, "stop_sign", urgent=True, quip_event="print_failed")
                finish("cancelled", round((time.time() - t0) / 60))
                return 0
            elif st in ("failed", "idle") and seen:
                raise RuntimeError("printer reports the job failed" if st == "failed" else "printer went idle before the job finished")
            elif not seen and time.time() - t0 > START_TIMEOUT:
                raise RuntimeError(f"the printer did not start the job within {START_TIMEOUT // 60} min")

            cfgs = config.get()
            if st == "printing":
                cur["status"] = "printing"
                due = [L for L in pause.read_pause_at() if cur["layer"] is not None and cur["layer"] >= L]
                if cfgs.pause.exists() or due:
                    layer = cur["layer"]
                    cfgs.pause.unlink(missing_ok=True)
                    if due:
                        pause_at.difference_update(due)
                        pause.write_pause_at(sorted(set(pause.read_pause_at()) - set(due)))
                    b.pause()
                    cur["status"] = "paused"
                    write(force=True)
                    base = config.web_base()
                    note_f = pathlib.Path(path).parent / "PAUSE_NOTE.txt"
                    note = note_f.read_text().strip() + "\n\n" if note_f.exists() else ""
                    where = f" at layer {layer}" if layer else ""
                    notify("Print paused", f"{note}{name} paused{where}. Resume when ready.", "pause_button",
                           actions=f"http, Resume, {base}/api/resume, method=POST; http, Cancel, {base}/api/cancel, method=POST",
                           urgent=True)
                    cfgs.resume.unlink(missing_ok=True)
            elif st == "paused":
                cur["status"] = "paused"
                if cfgs.resume.exists():
                    cfgs.resume.unlink(missing_ok=True)
                    b.resume()
                    cur["status"] = "printing"
                    write(force=True)
                    notify("Print resumed", name, "arrow_forward")
                    continue
            write()
            time.sleep(POLL)
    except Exception as e:
        final("failed", error=str(e), progress=metrics()[0])
        notify("Print FAILED", f"{name}: {e}", "warning", urgent=True, quip_event="print_failed")
        finish("failed", round((time.time() - t0) / 60))
        raise
    finally:
        cfgs = config.get()
        for f in (cfgs.stop, cfgs.pause, cfgs.resume):
            f.unlink(missing_ok=True)
        b.close()


def cli(argv=None):
    """python -m p3d.netsender FILE | --queued (path from the queue file)"""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        sys.exit(cli.__doc__)
    if argv[0] == "--queued":
        q = config.get().queue
        path = q.read_text().strip()
        q.unlink(missing_ok=True)
        return main(path)
    return main(argv[0])


if __name__ == "__main__":
    cli()
