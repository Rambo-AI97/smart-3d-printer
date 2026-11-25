"""Print dashboard: `p3d web` (service p3d-web). Stdlib only. Read-only except the POST endpoints
(cancel, pause, resume, retry, cooldown, level, queue/next|move|remove|add, models/slice (also reslice), knowledge/save, ideas),
allowed from localhost and config `cancel_from` / `control_from` IPs only."""
import csv, datetime, json, os, pathlib, re, subprocess, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config, fridge, ideas, insights, pause, printers, printlog, runner, spools, tracker

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
        c["jid"], c["sliced"] = "", ""
        try:  # job folder + gcode still on disk -> "Add to queue" possible
            gp = pathlib.Path(r.get("file") or "").resolve()
            if gp.is_file() and gp.parent.parent == config.get().jobs.resolve() and not job_meta_manual(gp):
                c["jid"], c["sliced"] = gp.parent.name, gcode_filament(gp)
        except Exception:
            pass
        out.append(c)
    return out


def job_meta_manual(g):
    return bool(runner.job_meta(g).get("manual_z"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_csv(name):
    try:
        return list(csv.DictReader(open(config.get().data / name, newline="")))
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


def advice_note(gcode):
    """' · advice: ...' for a slice result (empty when it looks good). Never raises."""
    from .. import advisor
    try:
        lines = advisor.advise(advisor.gather(gcode))
    except Exception:
        return ""
    return " · advice: " + "; ".join(lines) if lines else ""


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


def loaded_filament():
    """Material in the printer: active spool's, else config `filament`. Empty material = unknown (never guess)."""
    try:
        s = spools.active(spools.load())
        if s and s.get("material"):
            return {"material": str(s["material"]).upper(), "source": "spool " + str(s.get("name", ""))}
    except Exception:
        pass
    f = str(config.Config().raw.get("filament") or "").strip()
    return {"material": f.upper(), "source": "config" if f else ""}


_FIL = {}


def gcode_filament(path):
    """`; filament_type = X` of a gcode, read from the tail (Orca writes its settings last), else the head. Cached by mtime."""
    try:
        st = pathlib.Path(path).stat()
    except OSError:
        return ""
    key = (path, st.st_mtime)
    if key not in _FIL:
        v = ""
        try:
            with open(path, "rb") as f:
                for pos in (max(0, st.st_size - 262144), 0):
                    f.seek(pos)
                    m = None
                    for m in re.finditer(rb"^; filament_type = ([^;\r\n]+)", f.read(262144), re.M):
                        pass
                    if m:
                        v = m.group(1).decode().strip().upper()
                        break
        except Exception:
            pass
        _FIL[key] = v
    return _FIL[key]


def job_gcode(jid):
    """Gcode of a job folder under the jobs dir. `jid` must be a plain basename of an existing folder; else None."""
    if not jid or jid != pathlib.Path(jid).name or jid in (".", ".."):
        return None
    d = config.get().jobs / jid
    try:
        return runner.resolve_gcode(d) if d.is_dir() else None
    except runner.Refuse:
        return None


def pause_layers(v):
    """Validated list of 1-based layers from a number or a list (empty/None = none). Raises Refuse."""
    if v in (None, "", []):
        return []
    try:
        out = sorted({int(x) for x in (v if isinstance(v, (list, tuple)) else [v])})
    except (TypeError, ValueError):
        raise runner.Refuse("pause layer must be a whole number") from None
    if any(x < 2 or x > 10000 for x in out):
        raise runner.Refuse("pause layer must be between 2 and 10000")
    return out


def queue_add(b):
    g = job_gcode(str(b.get("job") or ""))
    if not g:
        raise runner.Refuse("no such job folder")
    q = runner.q_add(runner.q_load(), g, str(b.get("note") or "")[:200], pause_layers(b.get("pause_at")))
    runner.q_save(q)
    p = q[-1].get("pause_at")
    return f"queued #{len(q)}: {q[-1]['name']}" + (f" (pauses before layer {', '.join(map(str, p))})" if p else "")


def models_dir():
    return pathlib.Path(os.environ.get("P3D_MODELS_LIB") or pathlib.Path(__file__).resolve().parents[3] / "models")


def _slice_info(stl):
    try:
        return json.loads(stl.with_suffix(".slice.json").read_text()).get("msg", "")
    except Exception:
        return ""


def model_list():
    """Printable library, newest first: every *.stl under models/ (id = path relative to it), with the sibling .png
    if present. Hidden folders (.trash) are skipped."""
    root, out = models_dir(), []
    for p in root.rglob("*.stl") if root.is_dir() else []:
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        mt = p.stat().st_mtime
        out.append({"id": rel.as_posix(), "name": p.stem, "folder": rel.parent.as_posix() if rel.parent.as_posix() != "." else "",
                    "picture": p.with_suffix(".png").is_file(), "mtime": mt, "info": _slice_info(p),
                    "date": datetime.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M")})
    return sorted(out, key=lambda m: -m["mtime"])


def model_delete(b):
    """Move a library model (its .stl and same-stem .png/.scad/.3mf siblings) to models/.trash/ (recoverable)."""
    mid = str(b.get("id") or "")
    if mid not in {m["id"] for m in model_list()}:
        raise runner.Refuse("unknown model")
    root = models_dir()
    stl = root / mid
    trash = root / ".trash" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    trash.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in [stl, *(stl.with_suffix(x) for x in (".png", ".3mf"))]:
        if f.is_file():
            f.rename(trash / f.name)
            moved.append(f.name)
    return f"deleted {stl.stem} (moved {len(moved)} file(s) to models/.trash)"


_TASKS, _TLOCK = {}, threading.Lock()
QUALITIES = ("draft", "standard", "fine")
MODEL_EXT = (".stl", ".3mf", ".obj")


def filament_choices():
    """Filaments that have a slicer profile (profiles/filament-NAME.json), e.g. pla, petg, tpu."""
    return sorted(p.stem.split("-", 1)[1] for p in config.get().profiles.glob("filament-*.json"))


def job_source(jid):
    """Source model file a job was sliced from (job.json), or None if not recorded / gone / not a model file."""
    d = job_gcode(jid)
    if not d:
        return None
    try:
        m = pathlib.Path(json.loads((d.parent / "job.json").read_text()).get("model") or "")
    except Exception:
        return None
    return m if m.suffix.lower() in MODEL_EXT and m.is_file() else None


def _process(quality):
    try:
        return json.loads((config.get().profiles / f"process-{quality}.json").read_text())
    except Exception:
        return {}


def reslice_defaults(b):
    """Form defaults for a reslice of job `job` (original settings from job.json / process.json) or library model `model`."""
    loaded = loaded_filament()["material"].lower()
    st = {"filament": loaded if loaded in filament_choices() else "", "quality": "standard", "walls": "", "infill": "",
          "brim": False, "supports": False, "keep_orient": False}
    out = {"filaments": filament_choices(), "qualities": list(QUALITIES), "settings": st, "source": "", "recorded": False, "note": ""}
    jid = str(b.get("job") or "")
    if jid:
        d = job_gcode(jid)
        if not d:
            raise runner.Refuse("no such job folder")
        src = job_source(jid)
        out["source"] = src.name if src else ""
        if not src:
            out["note"] = "The source model of this job was not recorded (older slice), so it cannot be resliced. New slices record it."
        jd = d.parent
        fil = gcode_filament(d).lower()  # the job's old filament only fills in when the loaded one is unknown
        job_fil = fil if fil in out["filaments"] else ""
        try:
            meta = json.loads((jd / "job.json").read_text()).get("settings")
        except Exception:
            meta = None
        try:
            proc = json.loads((jd / "process.json").read_text())
        except Exception:
            proc = {}
        if meta and meta.get("filament") in out["filaments"]:
            job_fil = meta["filament"]
        if not st["filament"]:
            st["filament"] = job_fil
        elif job_fil and job_fil != st["filament"]:
            out["note"] = (out["note"] + " " if out["note"] else "") + \
                f"Was sliced for {job_fil.upper()}; defaulting to the loaded {st['filament'].upper()}."
        if meta:  # recorded by p3d slice: exact
            out["recorded"] = True
            st.update({k: meta[k] for k in ("quality", "supports", "brim", "keep_orient") if k in meta and meta[k] is not None})
            st["walls"] = meta.get("walls") or ""
            st["infill"] = meta.get("infill") or ""
            if meta.get("filament") in out["filaments"]:
                job_fil = meta["filament"]
        elif proc:  # older job: read the process snapshot
            for q in QUALITIES:
                ref = _process(q)
                if ref and proc.get("name") == ref.get("name") and proc.get("layer_height") == ref.get("layer_height"):
                    st["quality"] = q
                    break
            st["supports"] = proc.get("enable_support") == "1"
            st["brim"] = proc.get("brim_type") not in (None, "no_brim", "")
            ref = _process(st["quality"])
            if proc.get("wall_loops") and proc.get("wall_loops") != ref.get("wall_loops"):
                st["walls"] = int(proc["wall_loops"])
            if proc.get("sparse_infill_density") and proc.get("sparse_infill_density") != ref.get("sparse_infill_density"):
                st["infill"] = int(float(str(proc["sparse_infill_density"]).rstrip("%")))
    else:
        mid = str(b.get("model") or "")
        if mid not in {m["id"] for m in model_list()}:
            raise runner.Refuse("unknown model")
        out["source"] = mid
    return out


def _new_task(kind, **kw):
    """Register a background task (one at a time across all kinds). Caller holds nothing; raises Refuse."""
    with _TLOCK:
        if any(t["state"] == "running" for t in _TASKS.values()):
            raise runner.Refuse("another task is running, wait for it")
        tid = str(int(time.time() * 1000))
        while tid in _TASKS:
            tid = str(int(tid) + 1)
        _TASKS[tid] = {"id": tid, "kind": kind, "state": "running", **kw}
        for old in sorted(_TASKS)[:-20]:
            _TASKS.pop(old, None)
    return tid


def _task_end(tid, **kw):
    with _TLOCK:
        _TASKS[tid].update(kw)


def slice_start(b, run=None):
    """Start `p3d slice` in a background thread (one task at a time). Body: `model` (library id) or `job` (reslice its source),
    optional filament, quality, walls, infill, brim, supports, keep_orient. With `reslice` the result is NOT queued (the page offers
    Add to queue); otherwise it is queued. Returns the task id. Raises runner.Refuse. Never prints. `run` is for tests."""
    reslice = bool(b.get("reslice") or b.get("job"))
    if b.get("job"):
        path = job_source(str(b["job"]))
        if not path:
            raise runner.Refuse("source model of this job was not recorded or is gone: "
                                "slice it again from the Models tab (new slices record it)")
        mid = str(b["job"])
    else:
        known = {m["id"] for m in model_list()}
        mid = str(b.get("model") or "")
        if mid not in known:
            raise runner.Refuse("unknown model")
        path = models_dir() / mid
    fil = str(b.get("filament") or "").lower()
    if fil:
        if fil not in filament_choices():
            raise runner.Refuse("no slicer profile for filament " + fil)
    else:
        fil = loaded_filament()["material"].lower()
        if fil not in ("pla", "petg", "tpu"):
            raise runner.Refuse("loaded filament unknown (or not PLA/PETG): run p3d spool use")
    opts = {}
    quality = str(b.get("quality") or "standard")
    if quality not in QUALITIES:
        raise runner.Refuse("quality: " + ", ".join(QUALITIES))
    ref = _process(quality)
    try:
        for k, lo, hi in (("walls", 1, 10), ("infill", 0, 100)):
            v = b.get(k)
            if v not in (None, ""):
                v = int(v)
                if not lo <= v <= hi:
                    raise ValueError
                # only an override when it differs from the quality profile (walls also raise the shell layers)
                default = ref.get("wall_loops") if k == "walls" else str(ref.get("sparse_infill_density", "")).rstrip("%")
                if str(v) != str(default):
                    opts[k] = v
    except (TypeError, ValueError):
        raise runner.Refuse("walls must be 1-10 and infill 0-100") from None
    if quality != "standard":
        opts["quality"] = quality
    for k in ("brim", "supports", "keep_orient"):
        if b.get(k):
            opts[k] = True
    tid = _new_task("slice", model=mid, msg="slicing...", queue=not reslice)

    def work():
        try:
            if run:
                job_dir_, final = run(path, fil, **opts) if opts else run(path, fil)
            else:
                from .. import cli
                job_dir_, final, _ = cli.slice_model(path, filament=fil, **opts)
            adv = advice_note(final)
            if reslice:
                f = gcode_facts(str(final)) or {}
                _task_end(tid, state="done", msg="sliced: " + " / ".join(
                    x for x in (f.get("est_min") and mins(f["est_min"]),
                                f.get("grams") and f"{float(f['grams']):.1f} g", fil.upper()) if x) + adv,
                    job=job_dir_.name, est_min=f.get("est_min", ""), grams=f.get("grams", ""), filament=fil)
            else:
                with _TLOCK:
                    q = runner.q_add(runner.q_load(), final)
                    runner.q_save(q)
                    _TASKS[tid].update(state="done", msg=f"queued #{len(q)}: {q[-1]['name']}" + adv, n=len(q), job=job_dir_.name)
        except SystemExit as e:
            _task_end(tid, state="error", msg=str(e.code))
        except Exception as e:
            _task_end(tid, state="error", msg=str(e))

    threading.Thread(target=work, daemon=True).start()
    return tid


def mins(m):
    try:
        m = round(float(m))
    except (TypeError, ValueError):
        return ""
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


# ---- controls bar: retry, bed level, cooldown ----

ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ---- uploads from the phone / a Printables link (files are untrusted data: never executed, only parsed) ----
UPLOAD_EXT = (".stl", ".3mf", ".obj", ".step", ".stp", ".zip")
MAX_UPLOAD = 100 * 1024 * 1024
MAX_UNPACKED = 300 * 1024 * 1024


def _safe_name(n, default="model"):
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", pathlib.PurePosixPath(str(n).replace("\\", "/")).name).lstrip(".")
    return n[:80] or default


def _stl_write(tris, out):
    import struct
    with open(out, "wb") as f:
        f.write(b"p3d upload".ljust(80, b" ") + struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<12fH", 0, 0, 0, *a, *b, *c, 0))


def _obj_to_stl(src, out):
    v, tris = [], []
    with open(src, errors="replace") as f:
        for line in f:
            w = line.split()
            if not w:
                continue
            if w[0] == "v" and len(w) >= 4:
                v.append(tuple(float(x) for x in w[1:4]))
            elif w[0] == "f" and len(w) >= 4:
                ix = [int(x.split("/")[0]) for x in w[1:]]
                ix = [i - 1 if i > 0 else len(v) + i for i in ix]
                tris += [(v[ix[0]], v[ix[k]], v[ix[k + 1]]) for k in range(1, len(ix) - 1)]
    if not tris:
        raise runner.Refuse("no mesh found in the OBJ file")
    _stl_write(tris, out)


def _3mf_to_stl(src, out):
    """3MF (zip + XML) -> binary STL: all build items, with transforms and component references. Entity-bearing XML is refused."""
    import xml.etree.ElementTree as ET, zipfile
    with zipfile.ZipFile(src) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".model")]
        name = "3D/3dmodel.model" if "3D/3dmodel.model" in z.namelist() else (names[0] if names else None)
        if not name or z.getinfo(name).file_size > MAX_UNPACKED:
            raise runner.Refuse("no 3D model found in the 3MF file")
        data = z.read(name)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise runner.Refuse("refused: the 3MF contains XML entities")
    tag = lambda e: e.tag.rsplit("}", 1)[-1]
    objs, items = {}, []
    for e in ET.fromstring(data).iter():
        if tag(e) == "object":
            o = {"v": [], "t": [], "c": []}
            for m in e.iter():
                if tag(m) == "vertex":
                    o["v"].append((float(m.get("x")), float(m.get("y")), float(m.get("z"))))
                elif tag(m) == "triangle":
                    o["t"].append((int(m.get("v1")), int(m.get("v2")), int(m.get("v3"))))
                elif tag(m) == "component" and not m.get("path"):
                    o["c"].append((m.get("objectid"), m.get("transform")))
            objs[e.get("id")] = o
        elif tag(e) == "item":
            items.append((e.get("objectid"), e.get("transform")))
    if not items:
        items = [(i, None) for i, o in objs.items() if o["t"]]

    def mat(t):
        return [float(x) for x in t.split()] if t and len(t.split()) == 12 else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]

    def mul(a, b):  # apply a then b (row vectors)
        return [sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3)) for r in range(3) for c in range(3)] + \
               [sum(a[9 + k] * b[k * 3 + c] for k in range(3)) + b[9 + c] for c in range(3)]

    tris = []

    def walk(oid, m, depth=0):
        o = objs.get(oid)
        if not o or depth > 6:
            return
        pts = [tuple(sum(p[k] * m[k * 3 + c] for k in range(3)) + m[9 + c] for c in range(3)) for p in o["v"]]
        tris.extend((pts[a], pts[b], pts[c]) for a, b, c in o["t"] if max(a, b, c) < len(pts))
        for cid, ct in o["c"]:
            walk(cid, mul(mat(ct), m), depth + 1)

    for oid, t in items:
        walk(oid, mat(t))
    if not tris:
        raise runner.Refuse("no mesh found in the 3MF file")
    _stl_write(tris, out)


def _unzip(zpath, dest):
    """Extract only .stl/.3mf/.obj members, flattened to safe names (no paths, so no traversal), size/count capped."""
    import zipfile
    out, total = [], 0
    with zipfile.ZipFile(zpath) as z:
        for zi in z.infolist():
            base = pathlib.PurePosixPath(zi.filename.replace("\\", "/"))
            if zi.is_dir() or "__MACOSX" in base.parts or base.suffix.lower() not in (".stl", ".3mf", ".obj"):
                continue
            total += zi.file_size
            if total > MAX_UNPACKED or len(out) >= 30:
                raise runner.Refuse("zip is too big or has too many model files")
            t, n = dest / _safe_name(base.name), 2
            while t.exists():
                t = dest / f"{_safe_name(base.stem)}_{n}{base.suffix.lower()}"
                n += 1
            with z.open(zi) as src, open(t, "wb") as dst:
                left = zi.file_size + 1
                while left > 0:
                    chunk = src.read(min(1 << 20, left))
                    if not chunk:
                        break
                    dst.write(chunk)
                    left -= len(chunk)
            out.append(t)
    if not out:
        raise runner.Refuse("no STL / 3MF / OBJ files found in the zip")
    return out


def _printables_files(url):
    """Printables model URL -> [(name, https link)] of its STL files via the public GraphQL API (no login). Raises Refuse."""
    import urllib.request
    m = re.search(r"printables\.com/(?:[a-z]{2}/)?model/(\d+)", str(url))
    if not m:
        raise runner.Refuse("not a Printables model link (expected printables.com/model/<number>-name)")
    mid = m.group(1)

    def gql(query, variables):
        rq = urllib.request.Request("https://api.printables.com/graphql/", json.dumps({"query": query, "variables": variables}).encode(),
                                    {"Content-Type": "application/json", "User-Agent": "p3d"})
        try:
            with urllib.request.urlopen(rq, timeout=30) as r:
                return json.loads(r.read(2_000_000)).get("data") or {}
        except Exception as e:
            raise runner.Refuse(f"could not reach Printables ({e}); download the file on the phone and upload it instead") from None

    pr = (gql("query($id:ID!){print(id:$id){name stls{id name}}}", {"id": mid}).get("print")) or {}
    stls = pr.get("stls") or []
    if not stls:
        raise runner.Refuse("this Printables model has no STL files that can be fetched; download it and upload the file instead")
    out = []
    for f in stls[:10]:
        d = gql("mutation($id:ID!,$m:ID!){getDownloadLink(id:$id,printId:$m,fileType:stl,source:model_detail){ok output{link}}}",
                {"id": f["id"], "m": mid}).get("getDownloadLink") or {}
        link = ((d.get("output") or {}).get("link")) or ""
        host = urllib.parse.urlparse(link).hostname or ""
        if d.get("ok") and link.startswith("https://") and host.endswith(".printables.com"):
            out.append((_safe_name(f.get("name"), "model.stl"), link))
    if not out:
        raise runner.Refuse("Printables would not give a download link (login needed?); download the file and upload it instead")
    return _safe_name(pr.get("name"), "printables-" + mid), out


def _download(link, dest):
    import urllib.request
    n = 0
    with urllib.request.urlopen(urllib.request.Request(link, headers={"User-Agent": "p3d"}), timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            if n > MAX_UPLOAD:
                raise runner.Refuse("file is bigger than 100 MB")
            f.write(chunk)


def upload_folder(name):
    root = models_dir() / "uploads"
    base = f"{datetime.date.today():%Y-%m-%d}-{_safe_name(pathlib.PurePosixPath(name).stem, 'upload')}"
    d, n = root / base, 2
    while d.exists():
        d = root / f"{base}~{n}"
        n += 1
    d.mkdir(parents=True)
    return d


def upload_start(name, folder, saved=None, link=None):
    """Background task: (download link |) unpack/convert the saved upload into STL(s), render a preview, slice each with defaults
    (PETG, standard) into a model card. NEVER queues or prints. Returns task id. `saved` is the already-written raw file."""
    tid = _new_task("upload", model=name, msg="processing upload...", queue=False)

    def work():
        try:
            files = []
            if link:
                _task_end(tid, msg="fetching from Printables...")
                title, got = _printables_files(link)
                for fn, url in got:
                    _download(url, folder / fn)
                    files.append(folder / fn)
            else:
                files = [saved]
            stls = []
            for f in files:
                ext = f.suffix.lower()
                if ext == ".zip":
                    found = _unzip(f, folder)
                    f.unlink()
                elif ext in (".step", ".stp"):
                    raise runner.Refuse("STEP files cannot be converted here yet: export an STL or 3MF and upload that")
                else:
                    found = [f]
                for g in found:
                    if g.suffix.lower() == ".stl":
                        stls.append(g)
                    else:
                        _task_end(tid, msg=f"converting {g.name}...")
                        (_3mf_to_stl if g.suffix.lower() == ".3mf" else _obj_to_stl)(g, g.with_suffix(".stl"))
                        stls.append(g.with_suffix(".stl"))
            from .. import cli, preview
            done, bad = [], []
            for i, stl in enumerate(stls):
                _task_end(tid, msg=f"slicing {stl.name} ({i + 1}/{len(stls)})...")
                try:
                    preview.make(stl, stl.with_suffix(".png"))
                except Exception:
                    pass
                try:
                    job_dir_, final, _ = cli.slice_model(stl, filament="petg")
                except SystemExit as e:  # one bad model in a zip must not lose the others
                    bad.append(f"{stl.name}: {e.code}")
                    continue
                f = gcode_facts(str(final)) or {}
                msg = "sliced (PETG, standard): " + " / ".join(
                    x for x in (f.get("est_min") and mins(f["est_min"]), f.get("grams") and f"{float(f['grams']):.1f} g") if x) + advice_note(final)
                stl.with_suffix(".slice.json").write_text(json.dumps({"msg": msg, "job": job_dir_.name}))
                done.append(msg)
            if not done:
                raise runner.Refuse("; ".join(bad))
            _task_end(tid, state="done", msg=f"{len(done)} model(s) ready in the Models tab; " + done[-1] +
                      (f" (could not slice: {'; '.join(bad)})" if bad else ""), job=job_dir_.name)
        except SystemExit as e:
            _task_end(tid, state="error", msg=str(e.code))
        except Exception as e:
            _task_end(tid, state="error", msg=str(e))

    threading.Thread(target=work, daemon=True).start()
    return tid



def level_running():
    return any(t["state"] == "running" and t.get("kind") == "level" for t in _TASKS.values())


def printer_info():
    """Printer type and what it can do (the page hides buttons whose cap is missing)."""
    try:
        t = printers.printer_type()
        return {"type": t, "caps": printers.caps_for()}
    except printers.BackendError:
        return {"type": "marlin", "caps": printers.caps_for_type("marlin")}


def cap_refusal(cap):
    p = printer_info()
    return "" if cap in p["caps"] else f"not available for {p['type']} printers (needs a USB Marlin connection)"


def level_refusal():
    """Why a bed probe must not start now, or ''. The probe moves the printer and holds the serial port."""
    if cap_refusal("level"):
        return cap_refusal("level")
    if config.print_cancellable():
        return "a print is running or heating"
    if level_running():
        return "a bed check is already running"
    return ""


def parse_level(text):
    """(grid back row first, span, verdict) from `p3d level` output (ANSI stripped)."""
    grid, span, verdict = [], None, ""
    for line in ANSI.sub("", text).splitlines():
        m = re.match(r"^\s*(?:back|front)?\s*((?:[+-]\d+\.\d+\s+){2,}[+-]\d+\.\d+)\s*$", line)
        if m:
            grid.append([float(v) for v in m.group(1).split()])
        m = re.search(r"Span:\s*([\d.]+)\s*mm\s*->\s*(.+?)\s*\(", line)
        if m:
            span, verdict = float(m.group(1)), m.group(2)
    return grid, span, verdict


_LEVEL_PROC = [None]


def run_level(args, on_line=None):
    """Run `p3d level ARGS` as a child process, feeding each output line to on_line; returns (exit code, output)."""
    pr = subprocess.Popen([sys.executable, "-u", "-m", "p3d", "level", *args], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    _LEVEL_PROC[0] = pr
    out = []
    try:
        for line in pr.stdout:
            out.append(line)
            if on_line:
                try:
                    on_line(ANSI.sub("", line).rstrip())
                except Exception:
                    pass
        pr.wait(timeout=1500)
    finally:
        _LEVEL_PROC[0] = None
        try:
            (config.XDG_DATA / "p3d" / "level_last.log").write_text("".join(out))
        except Exception:
            pass
    return pr.returncode, "".join(out)


def level_progress(tid, line):
    """Turn one `p3d level` output line into live task fields: phase, bed/target temp, probed points."""
    t = _TASKS.get(tid)
    if t is None:
        return
    m = re.match(r"\s*bed ([\d.]+) / ([\d.]+) C", line)
    if m:
        t.update(phase="heating", bed=float(m.group(1)), target=float(m.group(2)),
                 msg=f"heating the bed: {float(m.group(1)):.0f} of {float(m.group(2)):.0f} C")
        return
    m = re.match(r"\s*settle (\d+)s left, bed ([\d.]+) C", line)
    if m:
        t.update(phase="settle", left_s=int(m.group(1)), bed=float(m.group(2)),
                 msg=f"bed at temperature, letting it settle: {int(m.group(1)) // 60}:{int(m.group(1)) % 60:02d} left")
        return
    m = re.search(r"point\s+(\d+)\s+X\s*([-\d.]+)\s+Y\s*([-\d.]+)\s+Z\s*([-+\d.]+)", line)
    if m:
        pts = t.setdefault("points", [])
        pts.append([float(m.group(2)), float(m.group(3)), float(m.group(4))])
        t.update(phase="probing", msg=f"probing point {len(pts)} of 16")
        return
    if line.startswith("Homing"):
        t.update(phase="homing", msg="homing (finding the corner and the nozzle height)")
    elif line.startswith("Probing"):
        t.update(phase="probing", points=[], msg="probing point 1 of 16")
    elif line.startswith(("Bed already", "Bed still warm", "Heating bed")):
        t.update(msg=line.strip())
    elif line.startswith("Stopped"):
        t.update(phase="stopped", msg=line.strip())


def level_stop():
    """Stop a running bed check: heater off, breaks the heat-up wait. A probe pass in progress finishes in the firmware."""
    pr = _LEVEL_PROC[0]
    if not level_running() or pr is None:
        raise runner.Refuse("no bed check is running")
    pr.terminate()
    for t in _TASKS.values():
        if t.get("kind") == "level" and t["state"] == "running":
            t.update(msg="stopping: heater off...", phase="stopping")
    return "stopping the bed check (heater off)"


def level_start(show=False, bed=70, run=None):
    """Bed probe (`p3d level --hot 70`, once, no adjust loop) or `--show`, as a background task. Raises Refuse."""
    if cap_refusal("level"):
        raise runner.Refuse(cap_refusal("level"))
    if not show:
        why = level_refusal()
        if why:
            raise runner.Refuse(why)
    elif config.print_running():
        raise runner.Refuse("the printer port is busy (print or cooldown running)")
    if not show:
        runner.end_cooldown_if_idle()   # bed still warm from the print: stop the cooldown and probe now
        if config.print_running():
            raise runner.Refuse("could not stop the cooldown (printer port busy)")
    tid = _new_task("level", model="bed mesh" if show else "bed check",
                    msg="reading the saved mesh..." if show else "heating, probing (about 5 minutes)...")

    def work():
        try:
            a = ["--show"] if show else ["--hot", str(bed)]
            code, out = run(a) if run else run_level(a, lambda l: level_progress(tid, l))
            grid, span, verdict = parse_level(out)
            if code == 3 or _TASKS[tid].get("phase") in ("stopping", "stopped"):
                _task_end(tid, state="stopped", msg="bed check stopped, heater off")
            elif code or not grid:
                tail = [x for x in ANSI.sub("", out).strip().splitlines() if x.strip()]
                _task_end(tid, state="error", msg=tail[-1] if tail else "bed check failed")
            else:
                _task_end(tid, state="done", grid=grid, span=span, verdict=verdict, turns=bed_turns(grid),
                          msg=f"span {span:.2f} mm: {verdict}" if span is not None else "done")
        except Exception as e:
            _task_end(tid, state="error", msg=str(e))

    threading.Thread(target=work, daemon=True).start()
    return tid


def bed_turns(grid):
    """Screw turns for a grid stored back row first (dashboard order)."""
    from .. import level as _lv
    try:
        return [{"corner": n, "action": a, "mm": round(d, 2)} for n, a, d in _lv.turns(grid[::-1])]
    except (IndexError, TypeError):
        return []


def level_last():
    """Newest finished bed result: from the task list, else the last row of bed_mesh_log.csv (rows are stored front to back)."""
    done = [t for t in _TASKS.values() if t.get("kind") == "level" and t.get("state") == "done"]
    if done:
        t = max(done, key=lambda t: t["id"])
        return {"grid": t["grid"], "span": t["span"], "verdict": t["verdict"], "when": "this session", "turns": bed_turns(t["grid"])}
    rows = read_csv("bed_mesh_log.csv")
    for r in reversed(rows):
        try:
            grid = [[float(v) for v in row.split()] for row in (r.get("grid_rows_front_to_back") or "").split("|")][::-1]
            span = float(r["span_mm"])
        except (ValueError, KeyError):
            continue
        return {"grid": grid, "span": span,
                "verdict": "GOOD" if span <= 0.30 else "OK" if span <= 0.60 else "NEEDS WORK", "when": r.get("date", ""),
                "turns": bed_turns(grid)}
    return None


def cooldown_start():
    if cap_refusal("level"):   # the cooldown watcher talks USB serial
        raise runner.Refuse(cap_refusal("level"))
    runner.start_unit("p3d-cooldown", ["--cooldown"])
    return "cooldown watcher started: after the print, heaters off, wait until cool, motors off"


def controls():
    """Which control-bar buttons make sense right now (and why not), polled by the page."""
    s = read_state()
    st = "stale" if s.get("stale") else (s.get("status") or "idle")
    live = config.print_cancellable()
    lvl = level_running()
    nxt = runner.next_refusal(runner.q_load())
    last = runner.last_reprintable()
    why = {}
    if not live:
        why["pause"] = why["stop"] = "no print is running"
    if st != "paused":
        why["resume"] = "the print is not paused"
    if nxt:
        why["next"] = nxt
    if lvl:
        why["next"] = why["retry"] = why["level"] = "a bed check is running"
    if live:
        why["retry"] = "a print is running or heating"
    elif not last:
        why["retry"] = "no reprintable job in the print log"
    lr = level_refusal()
    if lr:
        why["level"] = lr
    if config.print_running():
        why["show"] = "the printer port is busy (print or cooldown running)"
    if cap_refusal("level"):
        why["show"] = why["level"] = why["cooldown"] = cap_refusal("level")
    if cap_refusal("pause"):
        why["pause"] = cap_refusal("pause")
    return {"status": st, "why": why, "retry_name": (last or {}).get("name", ""),
            **{k: k not in why for k in ("pause", "resume", "stop", "next", "retry", "level", "show")}, "cooldown": not lvl and "cooldown" not in why, "lstop": lvl,
            "printer": printer_info(),
            "spools": spool_list()}


def spool_list():
    """Spools for the 'Loaded filament' picker: the active one decides the material for slicing and queue checks."""
    d = spools.load()
    return {"active": d["active"], "materials": filament_choices(),
            "list": [{"name": s["name"], "material": s["material"], "color": s.get("color", ""),
                      "left_g": round(float(s.get("left_g") or 0))} for s in d["spools"]]}


def spool_edit(b):
    """use: make a spool active (= loaded filament). add: register a new roll (and make it active)."""
    d = spools.load()
    name = str(b.get("name") or "").strip()
    try:
        if b.get("action") == "add":
            mat = str(b.get("material") or "").lower()
            if mat not in filament_choices():
                raise runner.Refuse("material must be one of " + ", ".join(filament_choices()))
            if not name or len(name) > 40:
                raise runner.Refuse("spool name required (max 40 chars)")
            spools.add(d, name, mat, float(b.get("grams") or 1000), str(b.get("color") or "")[:20])
        elif b.get("action") != "use":
            raise runner.Refuse("action: use | add")
        s = spools.use(d, name)
    except ValueError as e:
        raise runner.Refuse(str(e))
    spools.save(d)
    return f"loaded: {s['name']} ({s['material'].upper()}, {round(float(s['left_g']))} g left)"


# ---- knowledge tab: a fixed allowlist of hub markdown files (never a path from the client) ----

KNOWLEDGE = (("rules", "Rules", "rules.md"), ("filaments", "Filament guide", "filaments.md"),
             ("lessons", "Lessons", "lessons"), ("ideas", "Ideas", "ideas.md"))
MAX_KNOWLEDGE = 512 * 1024


def knowledge_path(kid):
    """Allowlisted file for an id, resolved from data_dir (<hub>/projects/3d-printer/data); None for any other id."""
    data = config.get().data.resolve()
    for k, _, f in KNOWLEDGE:
        if k == kid:
            if k == "lessons":  # <hub>/_system/lessons/printer.md
                return data.parents[2] / "_system/lessons/printer.md" if len(data.parents) > 2 else None
            return data.parent / f
    return None


def knowledge_list():
    out = []
    for k, title, _ in KNOWLEDGE:
        p = knowledge_path(k)
        out.append({"id": k, "title": title, "exists": bool(p and p.is_file()), "size": p.stat().st_size if p and p.is_file() else 0})
    return out


def knowledge_read(kid):
    p = knowledge_path(kid)
    if not p:
        raise runner.Refuse("not an editable file")
    return {"id": kid, "text": p.read_text() if p.is_file() else "", "exists": p.is_file()}


def knowledge_save(b):
    """Write an allowlisted file atomically, keeping the previous version as NAME.bak. Raises Refuse."""
    p = knowledge_path(str(b.get("id") or ""))
    text = b.get("text")
    if not p:
        raise runner.Refuse("not an editable file")
    if not isinstance(text, str) or len(text.encode()) > MAX_KNOWLEDGE:
        raise runner.Refuse("text missing or over 512 KB")
    if not p.parent.is_dir():
        raise runner.Refuse("folder for this file does not exist here")
    if p.is_file():
        bak = p.with_name(p.name + ".bak")
        bak.write_bytes(p.read_bytes())
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)
    return "saved " + p.name


def job_folder(g):
    """Job folder name of a gcode path under the jobs dir (picture or not), else ''."""
    try:
        p = pathlib.Path(g).resolve()
        return p.parent.name if p.parent.parent == config.get().jobs.resolve() else ""
    except Exception:
        return ""


def queue_view():
    out = []
    for n, e in enumerate(runner.q_load(), 1):
        g = e.get("gcode") or ""
        f = gcode_facts(g)
        out.append({"n": n, "name": e.get("name"), "note": e.get("note", ""),
                    "pause_at": e.get("pause_at", []), "added": e.get("added", ""),
                    "missing": f is None, "job": job_id_of(g), "jid": job_folder(g), "sliced": gcode_filament(g),
                    **(f or {"est_min": "", "grams": "", "filament": ""})})
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
            s["printer"] = printer_info()
            s["loaded_filament"] = loaded_filament()
            s["job_note"] = ""
            if s.get("job_dir"):  # queue note saved with the job (shows WHICH version is printing)
                try:
                    s["job_note"] = str(json.loads((pathlib.Path(s["job_dir"]) / "job.json").read_text()).get("note") or "")
                except Exception:
                    pass
            self.send(json.dumps(s).encode(), "application/json")
        elif path == "/api/preview.png":
            d = job_dir(read_state())
            p = d / "preview.png" if d else None
            if p and p.exists():
                self.send(p.read_bytes(), "image/png")
            else:
                self.send(b"", "text/plain", 404)
        elif path == "/api/filament":
            self.send(json.dumps(loaded_filament()).encode(), "application/json")
        elif path == "/api/models":
            self.send(json.dumps(model_list()).encode(), "application/json")
        elif path == "/api/model.png":
            mid = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0]
            p = (models_dir() / mid).with_suffix(".png") if mid in {m["id"] for m in model_list()} else None
            if p and p.is_file():
                self.send(p.read_bytes(), "image/png")
            else:
                self.send(b"", "text/plain", 404)
        elif path == "/api/tasks":
            self.send(json.dumps(list(_TASKS.values())).encode(), "application/json")
        elif path.startswith("/api/tasks/"):
            t = _TASKS.get(pathlib.Path(path).name)
            self.send(json.dumps(t).encode() if t else b"not found", "application/json" if t else "text/plain", 200 if t else 404)
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
        elif path == "/api/controls":
            self.send(json.dumps(controls()).encode(), "application/json")
        elif path == "/api/level/last":
            self.send(json.dumps(level_last()).encode(), "application/json")
        elif path == "/api/reslice/defaults":
            qs = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
            try:
                self.send(json.dumps(reslice_defaults(qs)).encode(), "application/json")
            except runner.Refuse as e:
                self.reply({"error": str(e)}, 404)
        elif path == "/api/knowledge":
            self.send(json.dumps(knowledge_list()).encode(), "application/json")
        elif path == "/api/knowledge/file":
            try:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self.send(json.dumps(knowledge_read(qs.get("id", [""])[0])).encode(), "application/json")
            except runner.Refuse as e:
                self.reply({"error": str(e)}, 404)
        elif path == "/api/log":
            self.send(json.dumps(log_rows()).encode(), "application/json")
        elif path == "/api/tracker":
            self.send(json.dumps(tracker.items()).encode(), "application/json")
        elif path == "/api/requests":
            self.send(json.dumps(fridge.load_requests()).encode(), "application/json")
        elif path.startswith("/api/request/shot/"):
            f = config.get().fridge / "shots" / pathlib.Path(path[len("/api/request/shot/"):]).name  # basename only
            if f.is_file():
                self.send(f.read_bytes(), "image/jpeg")
            else:
                self.send(b"not found", "text/plain", 404)
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
        if path not in ("/api/cancel", "/api/pause", "/api/pause/remove", "/api/resume", "/api/queue/next",
                        "/api/queue/move", "/api/verdict",
                        "/api/queue/remove", "/api/queue/add", "/api/models/slice", "/api/models/delete", "/api/ideas", "/api/retry",
                        "/api/cooldown", "/api/level", "/api/level/show", "/api/level/stop", "/api/knowledge/save", "/api/spool", "/api/upload", "/api/upload/link"):
            return self.send(b"not found", "text/plain", 404)
        ip = self.client_address[0].removeprefix("::ffff:")
        c = config.get()
        allowed = ("127.0.0.1", "::1", *c.cancel_from) if path == "/api/cancel" else c.control_ips
        if ip not in allowed:
            return self.reply({"error": "forbidden"}, 403)
        try:
            if path in ("/api/upload", "/api/upload/link"):
                try:
                    if path.endswith("link"):
                        link = str(self.body().get("url") or "")
                        if not re.search(r"printables\.com/(?:[a-z]{2}/)?model/\d+", link):
                            raise runner.Refuse("not a Printables model link (expected printables.com/model/<number>-name)")
                        folder = upload_folder("printables")
                        try:
                            tid = upload_start(link, folder, link=link)
                        except runner.Refuse:
                            folder.rmdir()
                            raise
                        return self.reply({"ok": "fetching", "task": tid}, 202)
                    name = _safe_name(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("name", [""])[0], "upload.stl")
                    if pathlib.Path(name).suffix.lower() not in UPLOAD_EXT:
                        raise runner.Refuse("file type not supported (use .stl .3mf .obj .step .zip)")
                    size = int(self.headers.get("Content-Length") or 0)
                    if not 0 < size <= MAX_UPLOAD:
                        return self.reply({"error": "file must be 1 byte to 100 MB"}, 413)
                    folder = upload_folder(name)
                    try:
                        dest, left = folder / name, size
                        with open(dest, "wb") as f:
                            while left > 0:
                                chunk = self.rfile.read(min(1 << 20, left))
                                if not chunk:
                                    raise runner.Refuse("upload was cut off")
                                f.write(chunk)
                                left -= len(chunk)
                        tid = upload_start(name, folder, saved=dest)
                    except Exception:
                        import shutil
                        shutil.rmtree(folder, ignore_errors=True)
                        raise
                    return self.reply({"ok": "uploaded", "task": tid}, 202)
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
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
            if path == "/api/pause/remove":
                b = self.body()
                try:
                    layers = None if b.get("clear") else [int(b["layer"])]
                except (KeyError, TypeError, ValueError):
                    return self.reply({"error": "layer (integer) or clear:true required"}, 400)
                return self.reply({"ok": pause.remove_pause_layers(layers)})
            if path == "/api/resume":
                return self.reply({"ok": pause.request_resume()})
            if path in ("/api/retry", "/api/cooldown", "/api/level", "/api/level/show", "/api/level/stop", "/api/knowledge/save"):
                try:
                    if path == "/api/retry":
                        if level_running():
                            raise runner.Refuse("a bed check is running")
                        return self.reply({"ok": runner.retry_last(notify=True)})
                    if path == "/api/cooldown":
                        return self.reply({"ok": cooldown_start()})
                    if path == "/api/level/stop":
                        return self.reply({"ok": level_stop()})
                    if path == "/api/knowledge/save":
                        return self.reply({"ok": knowledge_save(self.body())})
                    return self.reply({"ok": "started", "task": level_start(show=path.endswith("show"))}, 202)
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
            if path == "/api/verdict":
                b = self.body()
                if b.get("verdict") not in ("pass", "fail"):
                    return self.reply({"error": "verdict: pass | fail"}, 400)
                try:
                    r = tracker.set_verdict(str(b.get("job") or "last"), b["verdict"], b.get("tags") or "", str(b.get("note") or ""))
                except SystemExit as e:
                    return self.reply({"error": str(e)}, 409)
                return self.reply({"ok": f"{r['name']}: {r['state']}"})
            if path == "/api/queue/next":
                try:
                    if level_running():
                        raise runner.Refuse("a bed check is running")
                    return self.reply({"ok": runner.queue_next(notify=True)})
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
            if path == "/api/spool":
                try:
                    return self.reply({"ok": spool_edit(self.body())})
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
            if path == "/api/queue/add":
                try:
                    return self.reply({"ok": queue_add(self.body())})
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
            if path == "/api/models/delete":
                try:
                    return self.reply({"ok": model_delete(self.body())})
                except runner.Refuse as e:
                    return self.reply({"error": str(e)}, 409)
            if path == "/api/models/slice":
                try:
                    return self.reply({"ok": "slicing", "task": slice_start(self.body())}, 202)
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
    fridge.start_loop()
    ThreadingHTTPServer((host or c.web_host, int(port or c.web_port)), H).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
