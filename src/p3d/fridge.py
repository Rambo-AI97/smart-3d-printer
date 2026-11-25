"""Fridge link: plain files in <fridge_dir> (default <hub>/inbox/printer), one writer per file, synced by Syncthing.

  status.json    p3d writes (printer, spool, queue, last tracker items), refreshed every ~30 s and on events
  requests.json  p3d writes (print requests linked to Fridge notes)
  shots/         p3d copies the preview JPGs here
  approvals.json the Fridge writes; p3d only reads it (approve -> queue, change -> note). Never starts a print.
Schemas: docs/fridge-link.md
"""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import threading
import time

from . import config

REQ_STATES = ("awaiting_ok", "approved", "change_asked", "queued", "printing", "check", "passed", "failed")
SEEN_MAX = 500


def iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def atomic_write(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


def _read(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:
        return default


# ---------- requests.json ----------

def req_file():
    return config.get().fridge / "requests.json"


def load_requests():
    d = _read(req_file(), {})
    return d.get("requests", []) if isinstance(d, dict) else []


def save_requests(reqs):
    atomic_write(req_file(), {"updated": iso(), "requests": reqs})


def resolve_job(job):
    p = pathlib.Path(str(job)).expanduser()
    p = p if p.is_dir() else config.get().jobs / str(job)
    if not p.is_dir():
        raise ValueError(f"no job folder {job}")
    return p


def add_request(note, job, who="", title="", shot=None, reprint_of=None):
    """Create/replace the request for NOTE+JOB: copies a shot JPG into shots/ and tags the job (job.json) for the log."""
    from . import printlog
    d = resolve_job(job)
    g = next(d.glob("*.gcode"), None)
    info = printlog.gcode_info(g) if g else {}
    shots = config.get().fridge / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    name = f"note-{note}-{d.name}.jpg"
    try:
        if shot:
            shutil.copyfile(os.path.expanduser(shot), shots / name)
        else:
            from .shot import shot as make_shot
            make_shot([d], out=shots / name)
    except (SystemExit, OSError, ImportError) as e:
        print(f"p3d request: no shot ({e})", file=sys.stderr)
        name = ""
    q = {"note": str(note), "who": who, "title": title or d.name, "job": d.name, "shot": name, "time": info.get("est_min") or None,
         "grams": float(info["grams"]) if info.get("grams") else None, "state": "awaiting_ok", "reprint_of": reprint_of or "",
         "updated": iso()}
    reqs = [x for x in load_requests() if not (x["note"] == q["note"] and x["job"] == q["job"])]
    save_requests(reqs + [q])
    meta = _read(d / "job.json", {})
    meta.update(request=str(note), who=who, **({"reprint_of": reprint_of} if reprint_of else {}))
    try:
        (d / "job.json").write_text(json.dumps(meta))
    except OSError:
        pass
    refresh()
    return q


def set_request(note=None, job=None, state=None, **kw):
    """Update the newest open request matching note and/or job. Returns it or None."""
    reqs = load_requests()
    hits = [x for x in reqs if (note is None or x["note"] == str(note)) and (job is None or x["job"] == job)]
    if not hits:
        return None
    q = next((x for x in reversed(hits) if x["state"] not in ("passed", "failed")), hits[-1])
    if state:
        q["state"] = state
    q.update(kw)
    q["updated"] = iso()
    save_requests(reqs)
    return q


def on_job_start(job):
    set_request(job=job, state="printing")
    refresh()


def on_job_logged(row):
    """printlog.log_job finished a job: check / failed on its request; a cancelled print goes back to approved."""
    from .tracker import job_id
    st = {"check": "check", "failed": "failed"}.get(row.get("state"), "approved")
    set_request(job=job_id(row), state=st)
    refresh()


# ---------- verdict ping to Alex ----------

def notes_cmd(n, text):
    """argv for: ssh rambo bash -lc 'rambo notes done N "text"' (ssh joins argv with spaces, so the quoting is inside)."""
    return ["ssh", "rambo", "bash -lc " + shlex.quote(f"rambo notes done {int(n)} {shlex.quote(text)}")]


def notes_done(n, text):
    """Tick Fridge note N done (the other person phone pings). No-op when fridge_notes_ssh is false; never ssh under pytest / dry-run."""
    if not config.get().fridge_notes_ssh:
        return None
    cmd = notes_cmd(n, text)
    if os.environ.get("P3D_NOTES_DRYRUN") or os.environ.get("PYTEST_CURRENT_TEST"):
        print("[dry-run]", " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
        return cmd
    try:
        subprocess.run(cmd, timeout=30, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"p3d: notes done {n} failed: {e}", file=sys.stderr)
    return cmd


# ---------- status.json ----------

def printer_status():
    s = config.read_state()
    st = s.get("status", "idle")
    live = st in ("printing", "paused", "queued") and config.print_running()
    state = "idle" if not live else "paused" if st == "paused" else "printing"
    n = lambda k: s.get(k) if live else None
    return {"state": state, "job": s.get("file") if live else None, "percent": n("progress"), "minutes_left": n("remaining_min"),
            "nozzle": n("nozzle"), "nozzle_target": n("nozzle_target"), "bed": n("bed"), "bed_target": n("bed_target")}


def queue_status():
    from . import printlog, runner
    out = []
    for i, e in enumerate(runner.q_load(), 1):
        try:
            g = printlog.gcode_info(e["gcode"])
        except Exception:
            g = {}
        meta = runner.job_meta(pathlib.Path(e.get("gcode", "")))
        out.append({"n": i, "name": e.get("name"), "minutes": g.get("est_min") or None,
                    "grams": float(g["grams"]) if g.get("grams") else None, "request": str(meta.get("request") or "")})
    return out


def status():
    from . import spools, tracker
    d = spools.load()
    sp = spools.find(d, d.get("active")) or {}
    try:
        recent = [{k: i.get(k, "") for k in ("name", "state", "verdict", "date", "request", "who")} for i in tracker.items()
                  if i["state"] != "queued"][:10]
    except Exception:
        recent = []
    return {"schema": 1, "updated": iso(), "printer": printer_status(),
            "spool": {"name": sp.get("name") or None, "grams_left": sp.get("left_g")}, "queue": queue_status(), "tracker": recent}


def write_status():
    atomic_write(config.get().fridge / "status.json", status())


def refresh():
    """Best effort, never raises: status.json now (events call this)."""
    try:
        write_status()
    except Exception as e:
        print(f"p3d fridge: status.json not written: {e}", file=sys.stderr)


# ---------- approvals.json ----------

def seen_file():
    return config.get().state_dir / "fridge_seen.json"


def approval_id(a):
    return f"{a.get('note')}|{a.get('job')}|{a.get('action')}|{a.get('at')}"


def process_approvals():
    """Read approvals.json once per new entry: approve -> queue (never start), change -> store text. Returns [(id, outcome)]."""
    from . import runner
    items = _read(config.get().fridge / "approvals.json", [])
    if not isinstance(items, list):
        return []
    seen = _read(seen_file(), [])
    done = []
    for a in items:
        if not isinstance(a, dict) or a.get("action") not in ("approve", "change"):
            continue
        aid = approval_id(a)
        if aid in seen:
            continue
        seen.append(aid)
        note, job = str(a.get("note")), a.get("job")
        if a["action"] == "change":
            set_request(note, job, "change_asked", change_text=a.get("text", ""), change_by=a.get("by", ""))
            done.append((aid, "change_asked"))
            continue
        try:
            d = resolve_job(job)
            q = runner.q_load()
            if not any(pathlib.Path(e["gcode"]).parent.resolve() == d.resolve() for e in q):  # already waiting = fine
                runner.q_save(runner.q_add(q, d, f"Fridge #{note} ({a.get('by', '')})"))
            set_request(note, job, "queued", approved_by=a.get("by", ""))
            outcome = "queued"
        except (runner.Refuse, ValueError) as e:
            set_request(note, job, "approved", error=str(e))
            outcome = f"not queued: {e}"
        done.append((aid, outcome))
    if done:
        atomic_write(seen_file(), seen[-SEEN_MAX:])
    return done


def poll():
    try:
        process_approvals()
    except Exception as e:
        print(f"p3d fridge: approvals failed: {e}", file=sys.stderr)
    refresh()


def start_loop(every=30):
    """Daemon thread in the dashboard service: poll approvals + refresh status.json every `every` seconds."""
    def run():
        while True:
            poll()
            time.sleep(every)
    t = threading.Thread(target=run, daemon=True, name="fridge-link")
    t.start()
    return t
