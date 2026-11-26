"""Printer catalogue from Orca Slicer's system profiles: which machines exist, which presets fit, bed size.

Orca ships resources/profiles/<Vendor>/{machine,process,filament}/*.json. Presets chain through `inherits` (same
vendor first, then the shared filament library). We never edit them; flatten_profile.py merges the chosen ones.
"""
import functools
import glob
import json
import os
import pathlib
import re
import subprocess

from . import config

DEFAULT_MODEL = "Creality Ender-3 V3 SE 0.4 nozzle"
DEFAULT_BED = (220.0, 220.0, 250.0)   # the Ender-3 V3 SE: used when no profile tree is reachable
LAYER = {"draft": 0.24, "standard": 0.20, "fine": 0.16}
LAYER_WORD = {"draft": "draft", "standard": "standard", "fine": "optimal|fine|quality"}
MATERIALS = ("pla", "petg", "tpu")
BAMBU_VENDORS = ("BBL",)
LIBRARY = "OrcaFilamentLibrary"


# ---------- locating the profile tree ----------

def _roots():
    """Candidate directories that hold <Vendor>/ folders, best first. P3D_ORCA_PROFILES overrides everything."""
    env = os.environ.get("P3D_ORCA_PROFILES")
    if env:
        return [pathlib.Path(env).expanduser()]
    home = config.HOME
    out = []
    orca = config.get().orca
    if orca:
        real = pathlib.Path(orca).resolve().parent
        out += [real / "resources/profiles", real / "squashfs-root/resources/profiles", real.parent / "share/OrcaSlicer/profiles"]
    out.append(config.XDG_CACHE / "p3d/orca-profiles/squashfs-root/resources/profiles")
    out += [pathlib.Path(p) for p in sorted(glob.glob(str(home / "*/squashfs-root/resources/profiles")))]
    out += [pathlib.Path(p) for p in ("/usr/share/OrcaSlicer/resources/profiles", "/usr/share/orca-slicer/resources/profiles",
                                      "/opt/OrcaSlicer/resources/profiles")]
    flat = "/var/lib/flatpak/app/com.orcaslicer.OrcaSlicer/*/*/files/share/OrcaSlicer/profiles"
    out += [pathlib.Path(p) for p in sorted(glob.glob(flat))]
    out += [config.XDG_CONFIG / "OrcaSlicer/system", home / ".var/app/com.orcaslicer.OrcaSlicer/config/OrcaSlicer/system"]
    return [p for p in out if p.is_dir()]


def roots():
    return _roots()


def extract_profiles(orca=None):
    """Pull resources/profiles out of the Orca AppImage into the cache dir (no GUI start). Returns the tree or None."""
    orca = orca or config.get().orca
    if not orca:
        return None
    dest = config.XDG_CACHE / "p3d/orca-profiles"
    dest.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([orca, "--appimage-extract", "resources/profiles"], cwd=dest, capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    tree = dest / "squashfs-root/resources/profiles"
    reset()
    return tree if tree.is_dir() else None


class Tree:
    """Index of one or more profile roots: vendors -> machine/process/filament name -> file."""

    def __init__(self, root_dirs):
        self.roots = [pathlib.Path(r) for r in root_dirs]
        self.vendors = {}   # vendor -> [dirs]
        for r in self.roots:
            for d in sorted(r.iterdir()):
                if d.is_dir() and any((d / k).is_dir() for k in ("machine", "process", "filament")):
                    self.vendors.setdefault(d.name, []).append(d)
        self._idx = {}      # (vendor, kind) -> {name: path}
        self._cache = {}

    def index(self, vendor, kind):
        key = (vendor, kind)
        if key not in self._idx:
            names = {}
            for d in self.vendors.get(vendor, []):
                for p in sorted((d / kind).rglob("*.json")) if (d / kind).is_dir() else []:
                    names.setdefault(p.stem, p)
            self._idx[key] = names
        return self._idx[key]

    def load(self, path):
        if path not in self._cache:
            try:
                self._cache[path] = json.loads(pathlib.Path(path).read_text())
            except (OSError, ValueError):
                self._cache[path] = {}
        return self._cache[path]

    def find(self, name, kind, vendor):
        for v in (vendor, LIBRARY):
            p = self.index(v, kind).get(name)
            if p:
                return p
        for v in self.vendors:   # last resort: another vendor's (e.g. BBL generics used by a clone)
            p = self.index(v, kind).get(name)
            if p:
                return p
        return None

    def resolve(self, name, kind, vendor, _seen=()):
        """Preset merged with its `inherits` chain (child wins). {} if not found."""
        p = self.find(name, kind, vendor)
        if not p or name in _seen:
            return {}
        d = self.load(p)
        base = self.resolve(d["inherits"], kind, vendor, _seen + (name,)) if d.get("inherits") else {}
        return {**base, **d}

    def machines(self):
        """[(vendor, name)] of instantiable machine presets, sorted."""
        out = []
        for v in self.vendors:
            for name, p in self.index(v, "machine").items():
                d = self.load(p)
                if d.get("type") == "machine" and str(d.get("instantiation", "")).lower() == "true" \
                        and not (d.get("name") or name).startswith("fdm_"):
                    out.append((v, d.get("name") or name))
        return sorted(out, key=lambda t: (t[0].lower(), t[1].lower()))


@functools.lru_cache(maxsize=4)
def _tree_for(root_key):
    return Tree(root_key)


def tree(root_dirs=None):
    return _tree_for(tuple(str(r) for r in (root_dirs or _roots())))


def reset():
    _tree_for.cache_clear()
    machine_cache.clear()


machine_cache = {}


# ---------- queries ----------

def _norm(s):
    return re.sub(r"[^a-z0-9.]+", " ", s.lower()).split()


def _score(query, vendor, name):
    """Fuzzy: every query word must appear (prefix ok) in 'vendor name'; better when words are contiguous / early."""
    qs = _norm(query)
    hay = _norm(f"{vendor} {name}")
    joined = " ".join(hay)
    if not qs:
        return 0
    pos = 0
    for q in qs:
        hit = next((i for i, h in enumerate(hay) if h.startswith(q) or (len(q) > 2 and q in h)), None)
        if hit is None:
            # "ender3" vs "ender-3": compare without spaces
            if q in joined.replace(" ", ""):
                continue
            return None
        pos += hit
    return pos + len(hay) * 0.01 + (0 if " ".join(qs) in joined else 1)


def list_machines(query="", t=None):
    """[(vendor, machine preset name)], filtered and ranked by fuzzy query ('mk4', 'ender 3 v3', 'a1 mini')."""
    t = t or tree()
    all_m = t.machines()
    if not query.strip():
        return all_m
    scored = []
    for v, n in all_m:
        s = _score(query, v, n)
        if s is not None:
            scored.append((s, v.lower(), n.lower(), v, n))
    scored.sort()
    return [(v, n) for *_, v, n in scored]


def vendor_of(machine, t=None):
    t = t or tree()
    for v, n in t.machines():
        if n == machine:
            return v
    return None


# ---------- compatibility ----------

def _eval_condition(cond, machine_d):
    """Orca compatible_printers_condition, the common subset: printer_notes=~/re/ and nozzle_diameter[0]==x, with &&, ||, !."""
    notes = str(machine_d.get("printer_notes", ""))
    noz = _nozzle(machine_d)
    expr = cond
    expr = re.sub(r"printer_notes\s*=~\s*/((?:\\/|[^/])*)/", lambda m: f"bool(_re.fullmatch({m.group(1)!r}, _notes, _re.S))", expr)
    expr = re.sub(r"nozzle_diameter\[0\]\s*(==|!=|<=|>=|<|>)\s*([0-9.]+)", lambda m: f"(_noz {m.group(1)} {m.group(2)})", expr)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?!=)", " not ", expr)
    if re.search(r"printer_|nozzle_diameter|[A-Za-z_]+\[", re.sub(r"_re\.fullmatch|_notes|_noz", "", expr)):
        return False
    try:
        return bool(eval(expr, {"__builtins__": {}}, {"_re": re, "_notes": notes, "_noz": noz, "bool": bool}))  # noqa: S307
    except Exception:
        return False


def compatible(preset, machine_name, machine_d):
    cp = preset.get("compatible_printers")
    if cp:
        return machine_name in cp
    cond = (preset.get("compatible_printers_condition") or "").strip()
    if cond:
        return _eval_condition(cond, machine_d)
    return True


def _nozzle(d):
    v = d.get("nozzle_diameter")
    v = v[0] if isinstance(v, list) and v else v
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.4


def _first_num(v, default=0.0):
    v = v[0] if isinstance(v, list) and v else v
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _machine(machine, t):
    v = vendor_of(machine, t)
    if v is None:
        raise KeyError(f"unknown machine: {machine}")
    return v, t.resolve(machine, "machine", v)


def geometry(machine, t=None):
    """dict: x, y, z (mm), nozzle (mm), bambu (bool), vendor. Raises KeyError for an unknown machine."""
    t = t or tree()
    key = (machine, id(t))
    if key in machine_cache:
        return machine_cache[key]
    vendor, d = _machine(machine, t)
    xs, ys = [], []
    for pt in d.get("printable_area") or []:
        m = re.match(r"\s*(-?[\d.]+)\s*x\s*(-?[\d.]+)", str(pt))
        if m:
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
    x = (max(xs) - min(xs)) if xs else 0.0
    y = (max(ys) - min(ys)) if ys else 0.0
    z = _first_num(d.get("printable_height"), 0.0)
    g = {"x": x, "y": y, "z": z, "nozzle": _nozzle(d), "vendor": vendor,
         "bambu": vendor in BAMBU_VENDORS or str(d.get("printer_model", "")).startswith("Bambu Lab")}
    machine_cache[key] = g
    return g


def is_bambu(machine, t=None):
    try:
        return geometry(machine, t)["bambu"]
    except KeyError:
        return False


def presets_for(machine, t=None):
    """{'process': {draft|standard|fine: name}, 'filament': {pla|petg|tpu: name}, 'vendor': v}. Missing ones are left out."""
    t = t or tree()
    vendor, md = _machine(machine, t)
    out = {"vendor": vendor, "process": {}, "filament": {}}

    procs = []
    for name, path in t.index(vendor, "process").items():
        raw = t.load(path)
        if str(raw.get("instantiation", "")).lower() != "true":
            continue
        d = t.resolve(name, "process", vendor)
        if compatible(d, machine, md):
            procs.append((raw.get("name") or name, _first_num(d.get("layer_height"), 0.0)))
    for q, target in LAYER.items():
        best = sorted(((round(abs(h - target), 3),
                        0 if re.search(LAYER_WORD[q], n, re.I) else 1, len(n), n) for n, h in procs if h > 0))
        if best:
            out["process"][q] = best[0][3]

    for mat in MATERIALS:
        out["filament"][mat] = _pick_filament(t, vendor, machine, md, mat) or None
    out["filament"] = {k: v for k, v in out["filament"].items() if v}
    return out


def _pick_filament(t, vendor, machine, md, mat):
    word = re.compile(rf"^(?:[\w\- ]*?)\bGeneric {mat}(?: @.*)?$", re.I)
    for v in (vendor, LIBRARY):
        cands = []
        for name, path in t.index(v, "filament").items():
            raw = t.load(path)
            if str(raw.get("instantiation", "")).lower() != "true":
                continue
            d = t.resolve(name, "filament", v)
            nm = raw.get("name") or name
            if not word.match(nm) or not compatible(d, machine, md):
                continue
            ftype = d.get("filament_type")
            ftype = ftype[0] if isinstance(ftype, list) and ftype else ftype
            if ftype and str(ftype).upper() != mat.upper():
                continue
            # prefer presets that name this machine (explicit compatibility) over catch-alls, then the shortest name
            explicit = 0 if machine in (d.get("compatible_printers") or []) else 1
            cands.append((explicit, len(nm), nm))
        if cands:
            return sorted(cands)[0][2]
    return None


def search_label(vendor, name):
    return f"{name}  ({vendor})"
