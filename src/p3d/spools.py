"""Filament spools: <data_dir>/spools.json. Grams are deducted when a job ends.

  p3d spool add NAME --material petg --grams 1000 [--color white]
  p3d spool list | use NAME | set NAME GRAMS
"""
import json
import os
import time

from . import config

LOW_G = 100.0


def path():
    return config.get().spools_file


def load():
    try:
        d = json.loads(path().read_text())
    except Exception:
        d = {}
    d.setdefault("active", "")
    d.setdefault("spools", [])
    return d


def save(d):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, p)


def find(d, name):
    for s in d["spools"]:
        if s["name"].lower() == (name or "").lower():
            return s
    return None


def add(d, name, material, grams, color=""):
    if find(d, name):
        raise ValueError(f"spool {name} exists (p3d spool set {name} GRAMS)")
    d["spools"].append({"name": name, "material": material.lower(), "color": color, "start_g": float(grams),
                        "left_g": float(grams), "added": time.strftime("%Y-%m-%d"), "uses": []})
    if not d["active"]:
        d["active"] = name
    return d


def use(d, name):
    s = find(d, name)
    if not s:
        raise ValueError(f"no spool {name}: " + ", ".join(x["name"] for x in d["spools"]))
    d["active"] = s["name"]
    return s


def set_left(d, name, grams):
    s = find(d, name)
    if not s:
        raise ValueError(f"no spool {name}")
    s["left_g"] = float(grams)
    s["uses"].append({"date": time.strftime("%Y-%m-%d %H:%M"), "job": "weighed", "g": 0.0})
    return s


def active(d):
    return find(d, d["active"])


def job_grams(grams, status, progress):
    """Filament a job really used: all of it when done, grams x progress fraction when it stopped early."""
    try:
        g = float(grams)
    except (TypeError, ValueError):
        return 0.0
    if status == "done":
        return round(g, 1)
    try:
        frac = max(0.0, min(float(progress) / 100.0, 1.0))
    except (TypeError, ValueError):
        frac = 0.0
    return round(g * frac, 1)


def deduct(d, name, grams, job=""):
    """Returns (left_g, was_low_crossing) or None if the spool is unknown."""
    s = find(d, name)
    if not s:
        return None
    before = s["left_g"]
    s["left_g"] = round(max(before - grams, 0.0), 1)
    s["uses"].append({"date": time.strftime("%Y-%m-%d %H:%M"), "job": job, "g": round(grams, 1)})
    return s["left_g"], before >= LOW_G > s["left_g"]


def check(d, grams_needed):
    """(ok, message) for starting a job that needs grams_needed of the active spool."""
    s = active(d)
    try:
        need = float(grams_needed)
    except (TypeError, ValueError):
        return True, ""
    if not s:
        return True, "no active spool set (p3d spool add/use): filament not tracked"
    if need > s["left_g"]:
        return False, f"needs {need:.0f} g but spool {s['name']} has {s['left_g']:.0f} g left"
    if s["left_g"] - need < LOW_G:
        return True, f"spool {s['name']} will be low after this job ({s['left_g'] - need:.0f} g left)"
    return True, ""


def on_job_end(name, grams, status, progress, job=""):
    """Called by the sender. Returns (used_g, left_g) and sends the low-spool ntfy."""
    used = job_grams(grams, status, progress)
    d = load()
    r = deduct(d, name, used, job)
    if r is None:
        return used, None
    save(d)
    if r[1]:
        config.notify("Spool low", f"{name}: {r[0]:.0f} g left", "warning")
    return used, r[0]


# ---- CLI ----

def cmd(a):
    d = load()
    try:
        if a.action == "add":
            if a.grams is None or not a.material:
                raise ValueError("p3d spool add NAME --material petg --grams 1000 [--color white]")
            add(d, a.name, a.material, a.grams, a.color or "")
            save(d)
            print(f"added {a.name}: {a.material} {a.grams:.0f} g" + (" (active)" if d["active"] == a.name else ""))
        elif a.action == "use":
            s = use(d, a.name)
            save(d)
            print(f"active spool: {s['name']} ({s['material']}, {s['left_g']:.0f} g left)")
        elif a.action == "set":
            if a.grams is None:
                raise ValueError("p3d spool set NAME GRAMS")
            s = set_left(d, a.name, a.grams)
            save(d)
            print(f"{s['name']}: {s['left_g']:.0f} g left")
        else:
            if not d["spools"]:
                print("no spools yet: p3d spool add NAME --material petg --grams 1000")
            for s in d["spools"]:
                bar = "#" * round(20 * s["left_g"] / (s["start_g"] or 1))
                print(f"{'*' if s['name'] == d['active'] else ' '} {s['name']:16} {s['material']:5} {s['color']:8} "
                      f"{s['left_g']:6.0f} / {s['start_g']:.0f} g  {bar}")
    except ValueError as e:
        raise SystemExit(str(e)) from None
