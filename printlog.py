"""Print log: data/print_log.csv (one row per job) + data/printer_stats.csv (lifetime counters).

  python3 printlog.py import      add past G-code files found on this PC (sliced jobs)
  python3 printlog.py stats       snapshot the printer's lifetime counters (M78)
"""
import csv, datetime, pathlib, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
LOG = DATA / "print_log.csv"
STATS = DATA / "printer_stats.csv"
FIELDS = ["date", "name", "status", "est_min", "actual_min", "grams", "filament", "layer_mm", "nozzle_mm", "source", "file"]
SEARCH = [pathlib.Path.home() / "Downloads", pathlib.Path.home() / ".config/OrcaSlicer/log"]


def to_min(s):
    """'1d 2h 3m 4s' -> minutes."""
    mult = {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}
    return round(sum(float(n) * mult[u] for n, u in re.findall(r"(\d+)([dhms])", s or "")), 1)


def gcode_info(path):
    info = {}
    keys = {"estimated printing time (normal mode)": "est", "total filament used [g]": "grams",
            "filament used [g]": "grams", "filament_type": "filament", "layer_height": "layer",
            "nozzle_diameter": "nozzle", "TIME": "est_s", "Filament used": "metres"}
    with open(path, errors="replace") as f:
        for line in f:
            m = re.match(r";\s*([^=:]+?)\s*[=:]\s*(.*)", line)
            if m and m.group(1) in keys:
                info.setdefault(keys[m.group(1)], m.group(2).strip())
    est = to_min(info.get("est")) if "est" in info else (round(int(info["est_s"]) / 60, 1) if info.get("est_s", "").isdigit() else "")
    return {"est_min": est, "grams": info.get("grams", ""), "filament": info.get("filament", "").split(";")[0],
            "layer_mm": info.get("layer", ""), "nozzle_mm": info.get("nozzle", "").split(",")[0]}


def rows():
    if not LOG.exists():
        return []
    return list(csv.DictReader(open(LOG)))


def append(row):
    DATA.mkdir(exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def log_job(gcode, status, actual_min, source="p3d"):
    """Called by sender.py when a job ends."""
    row = gcode_info(gcode)
    row.update(date=time.strftime("%Y-%m-%d %H:%M"), name=pathlib.Path(gcode).stem, status=status,
               actual_min=actual_min, source=source, file=str(gcode))
    append(row)


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


def cmd_stats(text=None):
    """Parse M78 output (pass text, or read from the printer)."""
    if text is None:
        import serial
        with serial.Serial("/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0", 115200, timeout=1, exclusive=True) as s:
            time.sleep(3); s.write(b"\n"); time.sleep(.5); s.reset_input_buffer()
            s.write(b"M78\n"); time.sleep(2)
            text = s.read(2000).decode(errors="replace")
    m = re.search(r"Prints: (\d+), Finished: (\d+), Failed: (\d+)", text)
    t = re.search(r"Total time: ([\dhdms ]+), Longest job: ([\dhdms ]+)", text)
    fil = re.search(r"Filament used: ([\d.]+)m", text)
    if not m:
        sys.exit("no M78 stats in reply")
    DATA.mkdir(exist_ok=True)
    new = not STATS.exists()
    with open(STATS, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "prints", "finished", "failed", "total_hours", "longest_hours", "filament_m"])
        w.writerow([time.strftime("%Y-%m-%d"), *m.groups(), round(to_min(t.group(1)) / 60, 1),
                    round(to_min(t.group(2)) / 60, 1), fil.group(1)])
    print(f"printer lifetime: {m.group(1)} prints ({m.group(3)} failed), {round(to_min(t.group(1))/60)} h, {fil.group(1)} m")


if __name__ == "__main__":
    {"import": cmd_import, "stats": cmd_stats}[sys.argv[1]]()
