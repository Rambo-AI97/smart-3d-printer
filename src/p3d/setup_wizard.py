"""`p3d setup`: first-run wizard. Finds the printer port and tools, asks a few questions, writes the config."""
import pathlib
import shutil

from . import config


def ask(q, default="", yes=False):
    if yes:
        return default
    a = input(f"{q} [{default}]: " if default else f"{q}: ").strip()
    return a or default


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write(values):
    lines = ["# p3d config (p3d setup wrote this; edit freely). All keys: config.example.toml in the repo."]
    lines += [f"{k} = {toml_value(v)}" for k, v in values.items() if v not in ("", None)]
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text("\n".join(lines) + "\n")


def run(defaults=False):
    old = config.get().raw if config.CONFIG_FILE.exists() else {}
    v = {k: old.get(k, d) for k, d in config.DEFAULTS.items()}
    print(f"p3d setup -> {config.CONFIG_FILE}" + (" (updating)" if old else ""))

    ports = config.find_ports()
    if ports:
        for i, p in enumerate(ports, 1):
            print(f"  {i}. {p}")
    else:
        print("  no USB serial device found (printer off or unplugged?). You can set it later.")
    cur = v["port"] or (ports[0] if ports else "")
    a = ask("Printer port (number or path)", cur, defaults)
    v["port"] = ports[int(a) - 1] if a.isdigit() and 0 < int(a) <= len(ports) else a

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
    if not defaults:
        y = ask("Bed depth in mm (park position on cancel)", str(v["park_y"]))
        v["park_y"] = int(y) if y.isdigit() else v["park_y"]
    for k, d in config.DEFAULTS.items():  # don't write defaults the user didn't change
        if v.get(k) == d and k not in old:
            v[k] = ""
    write(v)
    config.reset()
    pathlib.Path(config.get().data).mkdir(parents=True, exist_ok=True)
    print(f"saved {config.CONFIG_FILE}\nnext: p3d install-service, then p3d doctor")
