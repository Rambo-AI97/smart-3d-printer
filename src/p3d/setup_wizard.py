"""`p3d setup`: first-run wizard. Picks the printer from Orca's profiles, finds how to reach it, asks a few
questions, writes the config (chmod 600) and builds the slicer profiles.

Non-interactive: p3d setup --printer "Prusa MK4" --connection prusalink --url http://x --api-key K --yes
"""
import json
import os
import pathlib
import shutil
import sys
import urllib.error
import urllib.request

from . import config, machines

ALWAYS_WRITE = ("printer_model", "printer_type")


def ask(q, default="", yes=False):
    if yes:
        return default
    a = input(f"{q} [{default}]: " if default else f"{q}: ").strip()
    return a or default


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write(values):
    lines = ["# p3d config (p3d setup wrote this; edit freely). All keys: config.example.toml in the repo."]
    lines += [f"{k} = {toml_value(v)}" for k, v in values.items()
              if v not in ("", None) and (v != [] or k in ALWAYS_WRITE)]
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text("\n".join(lines) + "\n")
    os.chmod(config.CONFIG_FILE, 0o600)   # holds API keys / access codes


def _num(x):
    return int(x) if float(x).is_integer() else x


# ---------- printer choice ----------

def _tree_ready():
    """True if Orca's profile tree is readable (extracting it from the AppImage once if needed)."""
    if machines.roots() and len(machines.tree().vendors) > 3:
        return True
    if config.get().orca and not os.environ.get("P3D_ORCA_PROFILES"):
        print("  reading Orca's printer list (first time only, ~20 s)...")
        if machines.extract_profiles():
            return True
    return bool(machines.roots())


def pick_printer(query, current, interactive):
    """Search Orca's machine presets. Returns the preset name."""
    if not _tree_ready():
        if not interactive and query and query.lower() not in current.lower():
            sys.exit(f"can't look up '{query}': Orca Slicer's printer list was not found. Install Orca Slicer "
                     "(install.sh does it), then run p3d setup again.")
        print("  no Orca profile list found (install Orca Slicer, run p3d setup again). Keeping " + current)
        return current
    while True:
        found = machines.list_machines(query)
        if not interactive:
            if not found:
                sys.exit(f"no printer matches '{query}' in Orca's profiles (see `p3d printers`)")
            exact = [n for _, n in found if n.lower() == query.lower()]
            return exact[0] if exact else next((n for _, n in found if "0.4" in n), found[0][1])
        if not found:
            print(f"  nothing matches '{query}'.")
        else:
            for i, (v, n) in enumerate(found[:8], 1):
                print(f"  {i}. {n}  ({v})")
            if len(found) > 8:
                print(f"  ...{len(found) - 8} more: type more words to narrow down")
            a = ask("Number to pick, or type to search again", "1")
            if a.isdigit() and 0 < int(a) <= min(8, len(found)):
                return found[int(a) - 1][1]
            query = a
            continue
        query = ask("Which printer? (name or model, e.g. mk4, a1 mini, ender 3 v3)")


# ---------- connection ----------

def _probe(url, path, timeout=3):
    """(HTTP status or None if unreachable, parsed JSON body or None) of GET url+path."""
    try:
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            body = r.read(20000)
            try:
                return r.status, json.loads(body)
            except ValueError:
                return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError):
        return None, None


def normalize_url(u):
    u = (u or "").strip().rstrip("/")
    return u if not u or "://" in u else "http://" + u


def detect(url):
    """Which print server answers at url? -> 'klipper' | 'octoprint' | 'prusalink' | ''."""
    st, body = _probe(url, "/server/info")
    if st == 200 and isinstance(body, dict) and "result" in body:
        return "klipper"
    st, body = _probe(url, "/api/version")
    if st in (200, 403):
        if isinstance(body, dict) and "PrusaLink" in str(body.get("text", "")):
            return "prusalink"
        return "octoprint"
    st, _ = _probe(url, "/api/v1/version")
    if st in (200, 401, 403):
        return "prusalink"
    return ""


def pick_connection(model, v, args, defaults):
    """Fill printer_type / printer_url / keys / bambu fields in v."""
    ports = config.find_ports()
    kind = args.get("connection")
    url = normalize_url(args.get("url"))
    if not kind:
        if machines.is_bambu(model):
            kind = "bambu"
        elif url:
            kind = detect(url) or "klipper"
        elif ports:
            kind = "marlin"
            print(f"  USB printer found: {ports[0]}")
        elif defaults:
            kind = v.get("printer_type") or "marlin"
        else:
            print("  no USB printer found.")
            url = normalize_url(ask("Printer address (IP or http://host:port; empty = USB, set up later)"))
            if url:
                kind = detect(url)
                print(f"  found a {kind} server" if kind else
                      "  nothing answered there (printer off? wrong address?). Saved as klipper; fix printer_type if wrong.")
                kind = kind or "klipper"
            else:
                kind = "marlin"
    v["printer_type"] = kind

    if kind == "marlin":
        if not defaults:
            cur = v["port"] or (ports[0] if ports else "")
            for i, p in enumerate(ports, 1):
                print(f"  {i}. {p}")
            a = ask("Printer port (number or path)", cur)
            v["port"] = ports[int(a) - 1] if a.isdigit() and 0 < int(a) <= len(ports) else a
        else:
            v["port"] = v["port"] or (ports[0] if ports else "")
        return
    if kind == "bambu":
        v["printer_url"] = url or ask("Printer IP address (printer screen: Settings > WLAN)", v["printer_url"], defaults)
        v["bambu_serial"] = args.get("serial") or ask("Serial number (Settings > Device)", v["bambu_serial"], defaults)
        v["bambu_access_code"] = args.get("access_code") or ask("LAN access code (Settings > WLAN)",
                                                               v["bambu_access_code"], defaults)
        return
    v["printer_url"] = url or normalize_url(ask("Printer address", v["printer_url"], defaults))
    if kind in ("octoprint", "prusalink"):
        v["printer_api_key"] = args.get("api_key") or ask("API key", v["printer_api_key"], defaults)


# ---------- main ----------

def run(defaults=False, printer=None, connection=None, url=None, api_key=None, serial=None, access_code=None,
        build=True):
    old = config.get().raw if config.CONFIG_FILE.exists() else {}
    v = {k: old.get(k, d) for k, d in config.DEFAULTS.items()}
    print(f"p3d setup -> {config.CONFIG_FILE}" + (" (updating)" if old else ""))
    args = {"connection": connection, "url": url, "api_key": api_key, "serial": serial, "access_code": access_code}

    # 1. which printer
    current = v["printer_model"] or machines.DEFAULT_MODEL
    if printer:
        model = pick_printer(printer, current, interactive=False)
    elif defaults:
        model = current
    else:
        a = ask(f"Which printer? (Enter = {current.replace(' 0.4 nozzle', '')}; or type a name to search)")
        model = pick_printer(a, current, interactive=True) if a else current
    changed = model != old.get("printer_model", machines.DEFAULT_MODEL)
    v["printer_model"] = model
    try:
        g = machines.geometry(model)
    except KeyError:
        g = None
    if model == machines.DEFAULT_MODEL:
        if changed:
            v["bed_size"] = []
    elif g and g["x"] > 0 and g["y"] > 0 and (changed or not v["bed_size"]):
        v["bed_size"] = [_num(g["x"]), _num(g["y"]), _num(g["z"])]
    elif not v["bed_size"]:
        print("  bed size unknown for this printer: set bed_size = [x, y, z] in the config.")
    if changed:
        v["park_y"], v["z_home_xy"] = 0, []     # re-derive from the new bed
    bx, by, bz = config.Config(raw=dict(v)).bed
    print(f"  {model}: bed {bx:.0f} x {by:.0f} x {bz:.0f} mm" + (", Bambu (sends .gcode.3mf)" if g and g["bambu"] else ""))

    # 2. how to reach it
    pick_connection(model, v, args, defaults)

    # 3. tools and the rest
    v["orca_slicer"] = ask("Orca Slicer (AppImage or command)", v["orca_slicer"] or config.find_orca(), defaults)
    if not v["orca_slicer"]:
        print("  Orca Slicer not found: download the Linux AppImage from github.com/SoftFever/OrcaSlicer/releases,"
              " chmod +x it, run p3d setup again.")
    v["openscad"] = ask("OpenSCAD", v["openscad"] or shutil.which("openscad") or "", defaults)
    if not v["openscad"]:
        print("  OpenSCAD not found (optional; for scad parts, calibration prints and previews): "
              "sudo apt install openscad")
    v["data_dir"] = ask("Data folder (print log, samples)", v["data_dir"] or str(config.XDG_DATA / "p3d"), defaults)
    v["ntfy_url"] = ask("Phone alerts: ntfy topic URL, e.g. https://ntfy.sh/your-secret-topic (empty = none)",
                        v["ntfy_url"], defaults)
    for k, d in config.DEFAULTS.items():  # don't write defaults the user didn't change
        if v.get(k) == d and k not in old and k not in ALWAYS_WRITE:
            v[k] = ""
    write(v)
    config.reset()
    machines.reset()
    pathlib.Path(config.get().data).mkdir(parents=True, exist_ok=True)
    print(f"saved {config.CONFIG_FILE}")

    # 4. slicer profiles for this printer
    if build:
        from . import flatten_profile
        try:
            flatten_profile.main()
        except SystemExit as e:
            print(f"  profiles not built: {e}\n  fix that, then run p3d profiles")
    print("next: p3d doctor" + (", then p3d install-service" if v["printer_type"] == "marlin" else ""))
