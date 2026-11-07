"""Read-only print dashboard: `p3d web` (service p3d-web). Stdlib only, no control endpoints."""
import csv, json, pathlib, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config, printlog

PAGE = pathlib.Path(__file__).resolve().parent / "index.html"
DATA = config.get().data


def read_state():
    s = config.read_state()
    if s.get("status") == "printing" and not config.print_running():
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
        elif path.startswith("/api/print/"):
            f = pathlib.Path(path[len("/api/print/"):]).name  # basename only: no path tricks
            rows = []
            try:
                for r in csv.DictReader(open(DATA / "prints" / f, newline="")):
                    rows.append({k: (num(v) if k != "time" else v) for k, v in r.items()})
            except Exception:
                return self.send(b"not found", "text/plain", 404)
            self.send(json.dumps(rows).encode(), "application/json")
        elif path == "/api/log":
            self.send(json.dumps(log_rows()).encode(), "application/json")
        else:
            self.send(b"not found", "text/plain", 404)

    def log_message(self, *a):
        pass


def main(port=None, host=None):
    c = config.get()
    ThreadingHTTPServer((host or c.web_host, int(port or c.web_port)), H).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
