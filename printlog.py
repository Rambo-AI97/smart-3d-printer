"""Print log: data/print_log.csv (one row per job) + data/printer_stats.csv (lifetime counters).

  python3 printlog.py import      add past G-code files found on this PC (sliced jobs)
  python3 printlog.py stats       snapshot the printer's lifetime counters (M78)
"""
import csv, datetime, json, os, pathlib, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
# Logs live in the family hub (Syncthing → Rambo). Override with P3D_DATA.
DATA = pathlib.Path(os.environ.get("P3D_DATA", pathlib.Path.home() / ".local/share/p3d"))
LOG = DATA / "print_log.csv"
STATS = DATA / "printer_stats.csv"
FIELDS = ["date", "name", "status", "est_min", "actual_min", "grams", "filament", "layer_mm", "nozzle_mm", "source", "file",
          # added 2026-11-06 (older rows leave these empty)
          "started", "ended", "nozzle_set", "bed_set", "flow_ratio", "retraction_mm", "quality", "outer_speed",
          "max_nozzle", "min_nozzle", "avg_bed", "layers", "samples_file", "rating", "issues", "notes", "model"]
ISSUES = ["stringing", "adhesion", "warping", "layer-shift", "blobs", "under-extrusion", "over-extrusion",
          "supports", "first-layer", "spaghetti", "other"]
PRINTED = ("done", "failed", "cancelled")
SEARCH = [pathlib.Path.home() / "Downloads", pathlib.Path.home() / ".config/OrcaSlicer/log"]


def to_min(s):
    """'1d 2h 3m 4s' -> minutes."""
    mult = {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}
    return round(sum(float(n) * mult[u] for n, u in re.findall(r"(\d+)([dhms])", s or "")), 1)


def gcode_info(path):
    info = {}
    keys = {"estimated printing time (normal mode)": "est", "total filament used [g]": "grams",
            "filament used [g]": "grams", "filament_type": "filament", "layer_height": "layer",
            "nozzle_diameter": "nozzle", "TIME": "est_s", "Filament used": "metres",
            "nozzle_temperature": "nozzle_set", "nozzle_temperature_initial_layer": "nozzle_first",
            "hot_plate_temp": "bed_hot", "textured_plate_temp": "bed_tex", "filament_flow_ratio": "flow",
            "retraction_length": "retract", "outer_wall_speed": "outer_speed", "total layer number": "layers"}
    with open(path, errors="replace") as f:
        for line in f:
            m = re.match(r";\s*([^=:]+?)\s*[=:]\s*(.*)", line)
            if m and m.group(1) in keys:
                info.setdefault(keys[m.group(1)], m.group(2).strip())
    est = to_min(info.get("est")) if "est" in info else (round(int(info["est_s"]) / 60, 1) if info.get("est_s", "").isdigit() else "")
    first = lambda k: re.split(r"[;,]", info.get(k, ""))[0].strip()
    return {"est_min": est, "grams": info.get("grams", ""), "filament": info.get("filament", "").split(";")[0],
            "layer_mm": info.get("layer", ""), "nozzle_mm": info.get("nozzle", "").split(",")[0],
            "nozzle_set": first("nozzle_set"), "bed_set": first("bed_hot") or first("bed_tex"),
            "flow_ratio": first("flow"), "retraction_mm": first("retract"), "outer_speed": first("outer_speed"),
            "layers": first("layers")}


def rows():
    if not LOG.exists():
        return []
    return list(csv.DictReader(open(LOG)))


def migrate():
    """Rewrite the header in place if columns were added (rows kept, new cells empty)."""
    if not LOG.exists():
        return
    with open(LOG, newline="") as f:
        head = next(csv.reader(f), [])
    if head == FIELDS:
        return
    old = list(csv.DictReader(open(LOG, newline="")))
    write_all(old)


def write_all(rs):
    tmp = LOG.with_name(LOG.name + ".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rs:
            w.writerow({k: (v if v is not None else "") for k, v in r.items() if k in FIELDS})
    os.replace(tmp, LOG)


def append(row):
    DATA.mkdir(parents=True, exist_ok=True)
    migrate()
    new = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def quality_of(name, layer):
    if name.startswith("calib"):
        return "calib"
    try:
        h = float(layer)
    except (TypeError, ValueError):
        return ""
    return "draft" if h >= 0.25 else "fine" if h <= 0.15 else "standard"


def log_job(gcode, status, actual_min, source="p3d", extra=None):
    """Called by sender.py when a job ends. extra: started, ended, max_nozzle, min_nozzle, avg_bed, samples_file."""
    row = gcode_info(gcode)
    name = pathlib.Path(gcode).stem
    row.update(date=time.strftime("%Y-%m-%d %H:%M"), name=name, status=status,
               actual_min=actual_min, source=source, file=str(gcode), quality=quality_of(name, row.get("layer_mm")))
    try:
        row["model"] = json.loads((pathlib.Path(gcode).parent / "job.json").read_text()).get("model", "")
    except Exception:
        pass
    row.update(extra or {})
    append(row)


def printed_rows():
    return [r for r in rows() if r.get("status") in PRINTED]


def cmd_rate(rating=None, issues=None, note=None, job=None):
    pr = printed_rows()
    if job:
        pr = [r for r in pr if r["name"] == job]
        if not pr:
            sys.exit(f"no printed job named {job}")
    if not pr:
        sys.exit("no printed jobs yet")
    last = pr[-1]
    if rating is None and issues is None and note is None:
        print(f"last job: {last['name']} ({last['status']}, {last['date']}) rating={last.get('rating') or '-'} "
              f"issues={last.get('issues') or '-'}")
        print("rate it: p3d rate 1-5 [--issues " + ",".join(ISSUES[:4]) + ",...] [--note \"text\"]")
        print("issue tags: " + ", ".join(ISSUES))
        return
    tags = [t.strip() for t in (issues or "").split(",") if t.strip()]
    bad = [t for t in tags if t not in ISSUES]
    if bad or (rating is not None and not 1 <= rating <= 5):
        sys.exit(f"bad input: rating 1-5; issue tags: {', '.join(ISSUES)}" + (f" (unknown: {bad})" if bad else ""))
    migrate()
    all_rows = rows()
    for r in all_rows:
        if r["date"] == last["date"] and r["name"] == last["name"] and r["file"] == last["file"]:
            if rating is not None:
                r["rating"] = str(rating)
            if issues is not None:
                r["issues"] = ",".join(tags)
            if note is not None:
                r["notes"] = note
            last = r
    write_all(all_rows)
    print(f"rated {last['name']}: rating={last.get('rating') or '-'} issues={last.get('issues') or '-'} notes={last.get('notes') or '-'}")


def cmd_history():
    pr = printed_rows()
    if not pr:
        print("no printed jobs yet")
        return
    n = len(pr)
    cnt = {s: sum(r["status"] == s for r in pr) for s in PRINTED}
    f = lambda v: float(v) if v not in (None, "") else 0.0
    hours = sum(f(r["actual_min"]) for r in pr) / 60
    grams = sum(f(r["grams"]) for r in pr if r["status"] == "done")
    rated = [int(r["rating"]) for r in pr if (r.get("rating") or "").isdigit()]
    print(f"{n} printed: {cnt['done']} done, {cnt['failed']} failed, {cnt['cancelled']} cancelled "
          f"(success {round(100 * cnt['done'] / n)}%)")
    print(f"{hours:.1f} h printed, {grams:.0f} g filament, avg rating "
          + (f"{sum(rated) / len(rated):.1f} ({len(rated)} rated)" if rated else "-"))
    for r in pr[-5:]:
        print(f"  {r['date'][:16]}  {r['status']:9} {r['name'][:30]:30} {r['actual_min'] or '-':>5} min  "
              f"rating {r.get('rating') or '-'}  {r.get('issues') or ''}")


def cmd_import():
    known = {r["file"] for r in rows()}
    n = 0
    for base in SEARCH:
        for g in sorted(base.rglob("*.gcode")) if base.exists() else []:
            if str(g) in known or "ams_" in g.name:
                continue
            row = gcode_info(g)
            row.update(date=datetime.datetime.fromtimestamp(g.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                       name=re.sub(r"_(PLA|PETG)_[\dhdms]+$", "", g.stem), status="sliced",
                       source="history", file=str(g))
            append(row)
            n += 1
    print(f"imported {n} past jobs -> {LOG}")


def parse_stats(text):
    """Parse M78 text -> row list for printer_stats.csv, or None."""
    m = re.search(r"Prints: (\d+), Finished: (\d+), Failed: (\d+)", text or "")
    if not m:
        return None
    t = re.search(r"Total time: ([\dhdms ]+?), Longest job: ([\dhdms ]+)", text)
    fil = re.search(r"Filament used: ([\d.]+)m", text)
    return [time.strftime("%Y-%m-%d"), *m.groups(), round(to_min(t.group(1)) / 60, 1) if t else "",
            round(to_min(t.group(2).strip()) / 60, 1) if t else "", fil.group(1) if fil else ""]


def append_stats(text):
    row = parse_stats(text)
    if not row:
        return None
    DATA.mkdir(parents=True, exist_ok=True)
    new = not STATS.exists()
    with open(STATS, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "prints", "finished", "failed", "total_hours", "longest_hours", "filament_m"])
        w.writerow(row)
    return row


def cmd_stats(text=None):
    """Snapshot the printer's lifetime counters (M78); pass text to parse instead of asking the printer."""
    if text is None:
        import serial
        with serial.Serial("/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0", 115200, timeout=1, exclusive=True) as s:
            time.sleep(3); s.write(b"\n"); time.sleep(.5); s.reset_input_buffer()
            s.write(b"M78\n"); time.sleep(2)
            text = s.read(2000).decode(errors="replace")
    row = append_stats(text)
    if not row:
        sys.exit("no M78 stats in reply")
    print(f"printer lifetime: {row[1]} prints ({row[3]} failed), {round(float(row[4] or 0))} h, {row[6]} m")


if __name__ == "__main__":
    {"import": cmd_import, "stats": cmd_stats}[sys.argv[1]]()
