"""Print dashboard: `p3d web` (service p3d-web). Stdlib only. Read-only except the POST endpoints
(cancel, pause, resume, queue/next|move|remove, ideas), allowed from localhost and config `cancel_from` / `control_from` IPs only."""
import csv, json, pathlib, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config, ideas, insights, pause, printlog, runner, spools

PAGE = pathlib.Path(__file__).resolve().parent / "index.html"
DATA = config.get().data


def read_state():
    s = config.read_state()
    if s.get("status") in ("printing", "paused") and not config.print_running():
        s["stale"] = True  # sender died without a final state
    return s


def job_dir(s):
    d = s.get("job_dir")
    if d and pathlib.Path(d).is_dir():
        return pathlib.Path(d)
    f = s.get("file")
    if f:
        hits = sorted(config.get().jobs.glob(f"*/{f}.gcode"))
        if hits:
            return hits[-1].parent
    return None


def log_rows():
    try:
        rows = list(csv.DictReader(open(DATA / "print_log.csv")))
    except Exception:
        return []
    return [r for r in rows if r.get("status") in ("done", "cancelled", "failed")][-20:][::-1]


def job_id_of(gcode):
    """Job folder name for a gcode path, only if that folder (under the jobs dir) still has a preview picture."""
    try:
        p = pathlib.Path(gcode).resolve()
        if p.parent.parent == config.get().jobs.resolve() and (p.parent / "preview.png").is_file():
            return p.parent.name
    except Exception:
        pass
    return ""


def history_cards(limit=50):
    """Newest-first past prints with picture ids, for the History page."""
    rows = [r for r in read_csv("print_log.csv") if r.get("status") in ("done", "cancelled", "failed")]
    out = []
    for r in rows[::-1][:limit]:
        c = {k: r.get(k) or "" for k in ("date", "name", "status", "actual_min", "est_min", "grams", "grams_used", "filament", "rating")}
        c["job"] = job_id_of(r.get("file") or "")
        out.append(c)
    return out


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_csv(name):
    try:
        return list(csv.DictReader(open(DATA / name, newline="")))
    except Exception:
        return []


def calibration():
    """Rows of the results table in <data_dir>/calibration.md (see docs/calibration.md)."""
    out = []
    try:
        for line in (DATA / "calibration.md").read_text().splitlines():
            c = [x.strip().replace("**", "") for x in line.strip().strip("|").split("|")]
            if line.startswith("|") and len(c) >= 3 and c[0][:2] == "20":
                out.append({"date": c[0], "what": c[1], "value": c[2], "where": c[3] if len(c) > 3 else ""})
    except Exception:
        pass
    return out


def history():
    import datetime
    jobs, weeks, issues = [], {}, {}
    for r in read_csv("print_log.csv"):
        if r.get("status") not in ("done", "cancelled", "failed"):
            continue
        d = (r.get("date") or "")[:10]
        jobs.append({k: r.get(k) or "" for k in ("date", "name", "status", "est_min", "actual_min", "grams", "filament",
                     "quality", "nozzle_set", "bed_set", "flow_ratio", "retraction_mm", "max_nozzle", "min_nozzle",
                     "avg_bed", "samples_file", "rating", "issues", "notes", "model")})
        try:
            dt = datetime.date.fromisoformat(d)
            wk = (dt - datetime.timedelta(days=dt.weekday())).isoformat()
        except ValueError:
            continue
        w = weeks.setdefault(wk, {"week": wk, "done": 0, "failed": 0, "cancelled": 0, "grams": 0.0})
        w[r["status"]] += 1
        if r["status"] == "done":
            w["grams"] = round(w["grams"] + (num(r.get("grams")) or 0), 1)
        for t in (r.get("issues") or "").split(","):
            if t.strip():
                issues[t.strip()] = issues.get(t.strip(), 0) + 1
    mesh = [{"date": r["date"], "span": num(r.get("span_mm"))} for r in read_csv("bed_mesh_log.csv") if num(r.get("span_mm")) is not None]
    stats = read_csv("printer_stats.csv")
    return {"jobs": jobs, "weeks": sorted(weeks.values(), key=lambda w: w["week"]), "issues": issues, "mesh": mesh,
            "stats": stats[-1] if stats else None, "calibration": calibration()}


def stats():
    rows = read_csv("print_log.csv")
    sp = spools.load()
    return {"weeks": insights.weekly(rows), "issues": insights.issue_counts(rows), "changes": insights.settings_changes(rows),
            "recurring": [{"tag": t, "n": n, "advice": a} for t, n, a in insights.recurring(rows)],
            "since_change": insights.since_last_change(rows), "spools": sp["spools"], "active": sp["active"],
            "jobs": [{k: r.get(k, "") for k in ("date", "name", "status", "rating", "profile_hash", "bed_first", "bed_other")}
                     for r in insights.printed(rows)]}


_INFO = {}


def gcode_facts(path):
    """est_min / grams / filament from the gcode header, cached by (path, mtime)."""
    try:
        key = (path, pathlib.Path(path).stat().st_mtime)
    except OSError:
        return None
    if key not in _INFO:
        try:
            i = printlog.gcode_info(path)
            _INFO[key] = {"est_min": i.get("est_min") or "", "grams": i.get("grams") or "", "filament": i.get("filament") or ""}
        except Exception:
            _INFO[key] = {"est_min": "", "grams": "", "filament": ""}
    return _INFO[key]


def queue_view():
    out = []
    for n, e in enumerate(runner.q_load(), 1):
        g = e.get("gcode") or ""
        f = gcode_facts(g)
        out.append({"n": n, "name": e.get("name"), "note": e.get("note", ""), "added": e.get("added", ""),
                    "missing": f is None, "job": job_id_of(g), **(f or {"est_min": "", "grams": "", "filament": ""})})
    return out


def queue_edit(b, remove=False):
    """Reorder/remove by 1-based index into the real queue. `name` guards against a stale view."""
    q = runner.q_load()
    n = int(b.get("n", 0))
    if b.get("name") is not None and 1 <= n <= len(q) and q[n - 1].get("name") != b["name"]:
        raise runner.Refuse("the queue changed, refreshed")
    if remove:
        r = runner.q_remove(q, n)
        runner.q_save(q)
        return "removed " + str(r.get("name"))
    runner.q_move(q, n, int(b.get("to", 0)))
    runner.q_save(q)
    return "moved"


class H(BaseHTTPRequestHandler):
    def send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            s = read_state()
            if s.get("est_total_min") is None and s.get("status") == "printing":  # old sender: read the gcode header
                try:
                    d = job_dir(s)
                    s["est_total_min"] = printlog.gcode_info(d / f"{s['file']}.gcode")["est_min"] or None
                except Exception:
                    pass
            s["server_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            s["server_ts"] = time.time()
            self.send(json.dumps(s).encode(), "application/json")
        elif path == "/api/preview.png":
            d = job_dir(read_state())
            p = d / "preview.png" if d else None
            if p and p.exists():
                self.send(p.read_bytes(), "image/png")
            else:
                self.send(b"", "text/plain", 404)
        elif path == "/api/history":
            self.send(json.dumps(history()).encode(), "application/json")
        elif path == "/api/history/cards":
            self.send(json.dumps(history_cards()).encode(), "application/json")
        elif path.startswith("/api/job/") and path.endswith("/preview.png"):
            jid = pathlib.Path(path[len("/api/job/"):-len("/preview.png")]).name  # basename only
            p = config.get().jobs / jid / "preview.png"
            if jid and p.is_file():
                self.send(p.read_bytes(), "image/png")
            else:
                self.send(b"", "text/plain", 404)
        elif path.startswith("/api/print/"):
            f = pathlib.Path(path[len("/api/print/"):]).name  # basename only: no path tricks
            rows = []
            try:
                for r in csv.DictReader(open(DATA / "prints" / f, newline="")):
                    rows.append({k: (num(v) if k != "time" else v) for k, v in r.items()})
            except Exception:
                return self.send(b"not found", "text/plain", 404)
            self.send(json.dumps(rows).encode(), "application/json")
        elif path == "/api/stats":
            self.send(json.dumps(stats()).encode(), "application/json")
        elif path == "/api/ideas":
            self.send(json.dumps({"statuses": ideas.STATUSES, "items": ideas.load()}).encode(), "application/json")
        elif path == "/api/queue":
            self.send(json.dumps(queue_view()).encode(), "application/json")
        elif path == "/api/log":
            self.send(json.dumps(log_rows()).encode(), "application/json")
        else:
            self.send(b"not found", "text/plain", 404)

    def reply(self, obj, code=200):
        self.send(json.dumps(obj).encode(), "application/json", code)

    def body(self):
        try:
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except Exception:
            return {}

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/api/cancel", "/api/pause", "/api/resume", "/api/queue/next", "/api/queue/move", "/api/queue/remove", "/api/ideas"):
            return self.send(b"not found", "text/plain", 404)
        ip = self.client_address[0].removeprefix("::ffff:")
        c = config.get()
        allowed = ("127.0.0.1", "::1", *c.cancel_from) if path == "/api/cancel" else c.control_ips
        if ip not in allowed:
            return self.reply({"error": "forbidden"}, 403)
        try:
            if path == "/api/cancel":
                if not config.print_cancellable():
                    return self.reply({"ok": "nothing to stop"})
                c.state_dir.mkdir(parents=True, exist_ok=True)
                c.stop.touch()  # same as `p3d cancel`: the sender turns heaters off, lifts, parks, logs it
                return self.reply({"ok": "cancel requested"})
            if path == "/api/pause":
                if not config.print_cancellable():
                    return self.reply({"ok": "nothing to pause"})
                return self.reply({"ok": pause.request_pause()})
            if path == "/api/resume":
                return self.reply({"ok": pause.request_resume()})
            if path == "/api/queue/next":
                try:
                    return self.reply({"ok": runner.queue_next(notify=True)})
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
            if path in ("/api/queue/move", "/api/queue/remove"):
                try:
                    msg = queue_edit(self.body(), remove=path.endswith("remove"))
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
                except (TypeError, ValueError):
                    return self.reply({"error": "n and to must be numbers"}, 400)
                return self.reply({"ok": msg})
            b = self.body()  # /api/ideas
            items = ideas.load()
            try:
                if b.get("action") == "add":
                    ideas.add(items, str(b.get("text", "")), b.get("status") or "idea", b.get("tags") or [])
                elif b.get("action") == "move":
                    ideas.move(items, b.get("id"), b.get("status"))
                else:
                    return self.reply({"error": "action: add | move"}, 400)
            except ValueError as e:
                return self.reply({"error": str(e)}, 400)
            ideas.save(items)
            self.reply({"ok": "saved", "items": items})
        except Exception as e:
            self.reply({"error": str(e)}, 500)

    def log_message(self, *a):
        pass


def main(port=None, host=None):
    c = config.get()
    ThreadingHTTPServer((host or c.web_host, int(port or c.web_port)), H).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
