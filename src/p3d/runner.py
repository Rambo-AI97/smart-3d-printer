"""Start a print job (shared by `p3d print`, `p3d queue next` and the dashboard) and the print queue."""
import json
import os
import pathlib
import subprocess
import time

from . import config, pause, spools


class Refuse(Exception):
    """A print must not start; the message says why and what to do."""


def service_dir():
    return config.XDG_CONFIG / "systemd/user"


def start_unit(unit, args):
    """Run `python -m p3d.sender ARGS` as a systemd user service (survives the terminal)."""
    if (service_dir() / f"{unit}.service").exists():
        subprocess.run(["systemctl", "--user", "reset-failed", unit], capture_output=True)
        subprocess.run(["systemctl", "--user", "start", "--no-block", unit], check=True)
        return
    from .service import exec_line
    subprocess.run(["systemd-run", "--user", f"--unit={unit}", "--collect", *exec_line(args, split=True)], check=True)


def resolve_gcode(arg):
    g = pathlib.Path(arg).expanduser().resolve()
    if g.is_dir():
        g = next(g.glob("*.gcode"), g)
    if g.suffix != ".gcode" or not g.exists():
        raise Refuse(f"not a G-code file: {g}")
    return g


def job_meta(g):
    try:
        return json.loads((g.parent / "job.json").read_text())
    except Exception:
        return {}


def end_cooldown_if_idle():
    """After a job the p3d-print unit stays active for the cooldown (heaters already off): stop it so a new print can start.
    Returns True if a cooldown was stopped. A running/heating job is never touched."""
    if config.print_running() and not config.print_cancellable():
        subprocess.run(["systemctl", "--user", "stop", "p3d-print"], capture_output=True, timeout=60)
        for _ in range(20):
            if not config.print_running():
                return True
            time.sleep(0.5)
    return False


def start(gcode, force=False, pause_at=(), confirm_z=False, stop_cooldown=False):
    """Queue the sender for gcode. Raises Refuse. Returns the status line."""
    from . import printlog
    g = resolve_gcode(gcode)
    if config.print_running():
        if stop_cooldown and end_cooldown_if_idle():
            pass
        else:
            raise Refuse("a print is already running (p3d status)" if config.print_cancellable()
                         else "the previous job is cooling down: heaters are off, `systemctl --user stop p3d-print` then print")
    meta = job_meta(g)
    if meta.get("manual_z") and not confirm_z:
        raise Refuse("this job needs the nozzle hand-placed on the part first (see its INSTRUCTIONS.txt); "
                     "then run: p3d print JOB --confirm-z")
    ok, msg = spools.check(spools.load(), printlog.gcode_info(g).get("grams"))
    if not ok and not force:
        raise Refuse(f"{msg} (--force to print anyway)")
    c = config.get()
    c.stop.unlink(missing_ok=True)
    c.pause.unlink(missing_ok=True)
    c.resume.unlink(missing_ok=True)
    pause.write_pause_at(list(pause_at))
    try:
        from . import preview
        preview.for_job(g.parent)
    except Exception:
        pass
    c.state_dir.mkdir(parents=True, exist_ok=True)
    c.queue.write_text(str(g))
    config.write_state(status="queued", file=g.stem, job_id=g.parent.name, job_dir=str(g.parent),
                       queued_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    start_unit("p3d-print", ["--queued"])
    out = f"started: {g.name}  (job {g.parent.name}; p3d status / p3d wait done / p3d cancel)"
    if msg:
        out += f"\n  note: {msg}"
    if pause_at:
        out += "\n  pauses before layer " + ", ".join(str(x) for x in sorted(set(pause_at)))
    return out


# ---- queue: <data_dir>/print_queue.json, only jobs already approved by the owner ----

def q_load():
    try:
        return json.loads(config.get().queue_file.read_text())
    except Exception:
        return []


def q_save(q):
    f = config.get().queue_file
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")  # atomic: the runner never sees a half-written queue
    tmp.write_text(json.dumps(q, indent=1))
    os.replace(tmp, f)


def q_add(q, gcode, note="", pause_at=()):
    g = resolve_gcode(gcode)
    if job_meta(g).get("manual_z"):
        raise Refuse("manual-Z jobs (recover/add-on) need hands on the printer: start them with p3d print --confirm-z, not the queue")
    e = {"gcode": str(g), "name": g.parent.name, "note": note, "added": time.strftime("%Y-%m-%d %H:%M")}
    if pause_at:
        e["pause_at"] = sorted({int(x) for x in pause_at})
    q.append(e)
    return q


def q_remove(q, n):
    if not 1 <= n <= len(q):
        raise Refuse(f"no queue entry {n} (p3d queue list)")
    return q.pop(n - 1)


def q_move(q, n, m):
    """Move entry n to position m (1-based), in place. Entries keep every field."""
    if not (1 <= n <= len(q) and 1 <= m <= len(q)):
        raise Refuse(f"queue positions are 1..{len(q)}")
    q.insert(m - 1, q.pop(n - 1))
    return q


def next_refusal(q):
    """Why `queue next` must not start now, or '' if it may. Pure given the inputs it reads."""
    if not q:
        return "the queue is empty (p3d queue add JOB_DIR)"
    if config.print_cancellable():
        return "a print is running or heating"
    return ""


def queue_next(force=False, notify=False):
    """Start the head of the queue. Assumes the bed is clear. Returns the message; raises Refuse (after notifying)."""
    q = q_load()
    try:
        why = next_refusal(q)
        if why:
            raise Refuse(why)
        head = q[0]
        if not pathlib.Path(head["gcode"]).exists():
            raise Refuse(f"{head['name']}: G-code is gone, remove it: p3d queue remove 1")
        msg = start(head["gcode"], force=force, pause_at=head.get("pause_at", []), stop_cooldown=True)
        q_save(q[1:])
        config.notify("Queued print started", f"{head['name']} (bed assumed clear)", "printer", quip_event="print_start")
        if notify:
            config.desktop_notify("3D printer", f"Started {head['name']} (bed assumed clear)")
        return msg
    except Refuse as e:
        config.notify("Print NOT started", str(e), "warning", urgent=True)
        if notify:
            config.desktop_notify("3D printer: not started", str(e))
        raise


# ---- retry the last real job (dashboard button, `p3d retry`) ----

SCRATCH_DIRS = ("/tmp/",)  # throw-away jobs are never retried
NOT_REPRINTABLE = ("purge", "calib", "temp_tower", "retraction", "flow", "firstlayer")


def last_reprintable():
    """Newest print-log row whose G-code still exists and is a real job (no purge/calibration/scratch). None if there is none."""
    import csv
    try:
        rows = list(csv.DictReader(open(config.get().data / "print_log.csv", newline="")))
    except Exception:
        return None
    for r in reversed(rows):
        f, n = r.get("file", ""), r.get("name", "")
        if not f or f.startswith(SCRATCH_DIRS) or n.startswith(NOT_REPRINTABLE):
            continue
        if os.path.exists(f):
            return {"name": n, "file": f, "est_min": r.get("est_min") or "", "status": r.get("status", "")}
    return None


def retry_last(notify=False):
    """Reprint the newest real job. Assumes the bed is clear. Returns the message; raises Refuse."""
    if config.print_cancellable():
        raise Refuse("a print is running or heating")
    r = last_reprintable()
    if not r:
        raise Refuse("no reprintable job found in the print log")
    msg = start(r["file"], stop_cooldown=True)
    config.notify("Retry started", f"{r['name']} (bed assumed clear)", "printer")
    if notify:
        config.desktop_notify("3D printer", f"Started {r['name']} (bed assumed clear)")
    return msg


def cmd_queue(a):
    try:
        q = q_load()
        if a.action == "add":
            if not a.arg:
                raise Refuse("p3d queue add JOB_DIR|FILE.gcode [--note TEXT]")
            q_save(q_add(q, a.arg, a.note or "", getattr(a, "pause_at_layer", None) or []))
            p = q[-1].get("pause_at")
            print(f"queued #{len(q)}: {q[-1]['name']}" + (f"  (pauses before layer {', '.join(map(str, p))})" if p else ""))
        elif a.action == "remove":
            r = q_remove(q, int(a.arg or 0))
            q_save(q)
            print("removed", r["name"])
        elif a.action == "move":
            q_save(q_move(q, int(a.arg or 0), int(getattr(a, "arg2", None) or 0)))
            print("moved; queue order saved")
        elif a.action == "next":
            print(queue_next(a.force, a.notify))
        else:
            for n, e in enumerate(q, 1):
                pause_txt = f"  [pause before layer {', '.join(map(str, e['pause_at']))}]" if e.get("pause_at") else ""
                print(f"{n}. {e['name']}  {e.get('note', '')}" + pause_txt)
            if not q:
                print("queue is empty")
    except Refuse as e:
        raise SystemExit(str(e)) from None
