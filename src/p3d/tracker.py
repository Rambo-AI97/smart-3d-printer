"""Print tracker: a lifecycle per job, like a bug tracker for prints. Stored as extra columns in print_log.csv.

  queued -> printing -> check (finished, waiting for a verdict) -> passed | failed (tags + note); cancelled stays cancelled.
  A reprint of a design links back with reprint_of (V1 failed -> V2 passed). `reopen` marks a design as needing another version.
  Starting a new print auto-closes any job still in `check` as passed ("assumed pass": the bed was cleared).

  p3d verdict [JOB|last] pass|fail [--tags warping,stringing] [--note TEXT]
  p3d tracker [--open|--all|--search WORD]
  p3d reopen JOB --note TEXT [--new JOB2]
"""
import json
import pathlib
import sys
import time

from . import config, printlog

STATES = ("queued", "printing", "check", "passed", "failed", "cancelled", "reopened")
OPEN = ("queued", "printing", "check")
ASSUMED = "assumed pass: plate cleared for next print"


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def job_id(r):
    return pathlib.Path(r.get("file") or "").parent.name or r.get("name", "")


def state_of(r):
    """Lifecycle state of a log row; rows from before the tracker are derived from status/rating."""
    if r.get("state"):
        return r["state"]
    st, rt = r.get("status"), r.get("rating") or ""
    if st in ("failed", "cancelled"):
        return st
    if st == "done":
        return "failed" if rt.isdigit() and int(rt) <= 2 else "passed"
    return st or ""


def find(ident="last"):
    """Printed log row by 'last', job folder name or job name (newest match)."""
    pr = printlog.printed_rows()
    if not pr:
        sys.exit("no printed jobs yet")
    if ident in (None, "", "last"):
        return pr[-1]
    for r in reversed(pr):
        if ident in (job_id(r), r.get("name")):
            return r
    sys.exit(f"no printed job named {ident} (p3d tracker --all)")


def _log_line(msg):
    try:
        f = config.get().data / "tracker.log"
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a") as fh:
            fh.write(f"{now()}  {msg}\n")
    except OSError:
        pass


def set_verdict(ident, verdict, tags=None, note="", ssh=True):
    """verdict: pass|fail. Updates the row, the Fridge request and (pass + request) pings Alex. Returns the row."""
    if verdict not in ("pass", "fail"):
        sys.exit("verdict is pass or fail")
    r = find(ident) if isinstance(ident, (str, type(None))) else ident
    tags = [t.strip().lower() for t in (tags.split(",") if isinstance(tags, str) else tags or []) if t.strip()]
    kw = dict(state="passed" if verdict == "pass" else "failed", verdict=verdict, verdict_date=now(),
              verdict_tags=",".join(tags), verdict_note=note or "")
    if tags and all(t in printlog.ISSUES for t in tags):
        kw["issues"] = ",".join(tags)
    if note:
        kw["notes"] = note
    r = printlog.update_row(r, **kw) or r
    _log_line(f"verdict {verdict} {r.get('name')} {','.join(tags)} {note}")
    _sync_request(r, ssh=ssh)
    return r


def _sync_request(r, ssh=True):
    try:
        from . import fridge
        n = r.get("request")
        if n:
            fridge.set_request(n, job=job_id(r), state=r["state"], verdict_note=r.get("verdict_note", ""))
            if r["state"] == "passed" and ssh:
                fridge.notes_done(n, f"{r.get('name')} is printed and came out well. It is ready to pick up.")
        fridge.refresh()
    except Exception as e:
        print(f"p3d tracker: fridge sync failed: {e}", file=sys.stderr)


def rating_verdict(row, rating):
    """`p3d rate`: rating <=2 -> failed, >=3 -> passed, only when no verdict yet."""
    r = next((x for x in printlog.rows() if printlog.row_key(x) == printlog.row_key(row)), row)
    if r.get("verdict") or r.get("status") not in ("done", "failed"):
        return None
    return set_verdict(r, "fail" if rating <= 2 else "pass", note=r.get("notes", ""), ssh=True)


def auto_close():
    """A new print is starting, so the bed was cleared: every job still in `check` passes. Returns the closed rows."""
    out = []
    for r in printlog.printed_rows():
        if r.get("state") == "check":
            r = printlog.update_row(r, state="passed", verdict="pass", verdict_date=now(), verdict_note=ASSUMED) or r
            out.append(r)
            _sync_request(r, ssh=False)  # no ping: nobody looked at it yet
    if out:
        msg = f"auto-closed {len(out)} job(s) in check as passed ({ASSUMED}): " + ", ".join(r["name"] for r in out)
        print("p3d tracker:", msg)
        _log_line(msg)
    return out


def new_row_fields(gcode, status, row):
    """Tracker columns for a freshly finished job (called by printlog.log_job)."""
    meta = {}
    try:
        meta = json.loads((pathlib.Path(gcode).parent / "job.json").read_text())
    except Exception:
        pass
    out = {"state": "check" if status == "done" else status if status in ("failed", "cancelled") else "",
           "request": str(meta.get("request") or ""), "who": str(meta.get("who") or ""),
           "reprint_of": str(meta.get("reprint_of") or "")}
    if status == "failed":
        out.update(verdict="fail", verdict_date=now(), verdict_note="printer reported a failure")
    if not out["reprint_of"] and row.get("model"):  # same model as an earlier failed/reopened job = its next version
        for r in reversed(printlog.printed_rows()):
            if r.get("model") == row["model"] and state_of(r) in ("failed", "reopened"):
                out["reprint_of"] = r["name"]
                break
    return out


def reopen(ident, note="", new=None):
    r = find(ident)
    r = printlog.update_row(r, state="reopened", verdict_note=note or r.get("verdict_note", ""), verdict_date=now()) or r
    _log_line(f"reopen {r['name']} {note}")
    if new:
        d = pathlib.Path(new).expanduser()
        d = d if d.is_dir() else config.get().jobs / new
        f = d / "job.json"
        meta = {}
        try:
            meta = json.loads(f.read_text())
        except Exception:
            pass
        meta["reprint_of"] = r["name"]
        f.write_text(json.dumps(meta))
    _sync_request(r, ssh=False)
    return r


def chain(r, rows):
    """Earlier versions of a job, oldest first (follows reprint_of)."""
    by = {x["name"]: x for x in rows}
    out, cur, seen = [], r, set()
    while cur.get("reprint_of") and cur["reprint_of"] in by and cur["reprint_of"] not in seen:
        seen.add(cur["reprint_of"])
        cur = by[cur["reprint_of"]]
        out.insert(0, {"name": cur["name"], "state": state_of(cur)})
    return out


def items():
    """Newest first: queued jobs, the one printing, then finished jobs with state/verdict."""
    from . import runner
    out = []
    for e in runner.q_load():
        meta = runner.job_meta(pathlib.Path(e.get("gcode", "")))
        out.append({"job": e.get("name", ""), "name": e.get("name", ""), "state": "queued", "date": e.get("added", ""),
                    "note": e.get("note", ""), "request": str(meta.get("request") or ""), "who": str(meta.get("who") or ""),
                    "verdict": "", "tags": "", "reprint_of": str(meta.get("reprint_of") or ""), "chain": []})
    s = config.read_state()
    if s.get("status") in ("printing", "paused", "queued") and config.print_running():
        meta = runner.job_meta(pathlib.Path(s.get("job_dir") or "x") / "x.gcode")
        out.append({"job": s.get("job_id") or s.get("file", ""), "name": s.get("file", ""), "state": "printing",
                    "date": s.get("started") or s.get("queued_at") or "", "note": "", "request": str(meta.get("request") or ""),
                    "who": str(meta.get("who") or ""), "verdict": "", "tags": "",
                    "reprint_of": str(meta.get("reprint_of") or ""), "chain": [], "progress": s.get("progress")})
    pr = printlog.printed_rows()
    for r in reversed(pr):
        out.append({"job": job_id(r), "name": r["name"], "state": state_of(r), "date": r.get("date", ""),
                    "verdict": r.get("verdict", ""), "verdict_date": r.get("verdict_date", ""), "tags": r.get("verdict_tags", ""),
                    "note": r.get("verdict_note") or r.get("notes", ""), "request": r.get("request", ""), "who": r.get("who", ""),
                    "reprint_of": r.get("reprint_of", ""), "chain": chain(r, pr), "grams": r.get("grams", ""),
                    "minutes": r.get("actual_min", "")})
    return out


def needs_version(it, all_items):
    """A failed/reopened design nobody reprinted yet counts as open."""
    return it["state"] in ("failed", "reopened") and not any(x.get("reprint_of") == it["name"] for x in all_items)


def select(mode="open", word=None):
    its = items()
    if word:
        w = word.lower()
        return [i for i in its if w in " ".join(str(v) for v in i.values()).lower()]
    if mode == "all":
        return its
    return [i for i in its if i["state"] in OPEN or needs_version(i, its)]


def cmd_tracker(a):
    its = select("all" if a.all else "open", a.search)
    if not its:
        print("nothing open" if not (a.all or a.search) else "no matches")
        return
    print(f"{'date':11} {'name':26} {'state':9} {'verdict':7} {'req':>4}  note")
    for i in its:
        print(f"{i['date'][5:16]:11} {i['name'][:26]:26} {i['state']:9} {i['verdict'] or '-':7} {i['request'] or '-':>4}  "
              f"{(i['tags'] + ' ' if i['tags'] else '') + (i['note'] or '')}"[:140])


def cmd_verdict(a):
    args = list(a.args)
    if args and args[-1] in ("pass", "fail"):
        v, ident = args[-1], (args[0] if len(args) > 1 else "last")
    elif args and args[0] in ("pass", "fail"):
        v, ident = args[0], (args[1] if len(args) > 1 else "last")
    else:
        sys.exit("p3d verdict [JOB|last] pass|fail [--tags warping,stringing] [--note TEXT]")
    r = set_verdict(ident, v, a.tags, a.note or "")
    print(f"{r['name']}: {r['state']}" + (f" ({r['verdict_tags']})" if r.get("verdict_tags") else ""))


def cmd_reopen(a):
    r = reopen(a.job, a.note or "", a.new)
    print(f"{r['name']}: reopened (needs another version)" + (f"; {a.new} linked as its reprint" if a.new else ""))


def commands(A):
    return [
        ("verdict", cmd_verdict, "verdict on a finished print: [JOB|last] pass|fail [--tags warping,...] [--note TEXT]",
         [A("args", nargs="*"), A("--tags", help="comma list: " + ", ".join(printlog.ISSUES[:5]) + ",..."), A("--note")]),
        ("tracker", cmd_tracker, "print tracker: --open (default) | --all | --search WORD",
         [A("--open", action="store_true"), A("--all", action="store_true"), A("--search")]),
        ("reopen", cmd_reopen, "mark a job's design as needing another version; --new JOB links the reprint",
         [A("job"), A("--note"), A("--new", help="job folder of the new version (sets its reprint_of)")]),
        ("request", cmd_request, "Fridge print requests: add NOTE JOB --who Alex --title TEXT | list",
         [A("action", choices=["add", "list"], nargs="?", default="list"), A("note", nargs="?"), A("job", nargs="?"),
          A("--who", default=""), A("--title", default=""), A("--shot", help="JPG to use instead of making one"),
          A("--reprint-of", help="earlier job this replaces")]),
    ]


def cmd_request(a):
    from . import fridge
    if a.action == "list":
        for q in fridge.load_requests():
            print(f"#{q['note']:>4} {q['state']:13} {q.get('who', ''):6} {q['title']} ({q['job']})")
        return
    if not (a.note and a.job):
        sys.exit("p3d request add NOTE JOB --who Alex --title TEXT")
    q = fridge.add_request(a.note, a.job, a.who, a.title, a.shot, a.reprint_of)
    print(f"request #{q['note']}: {q['title']} ({q['state']}), shot {q['shot'] or 'none'} -> {config.get().fridge}")
