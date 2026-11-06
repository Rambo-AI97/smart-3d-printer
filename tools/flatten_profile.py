"""Build standalone Orca profiles (profiles/*.json) for the Ender-3 V3 SE 0.4 from Orca's system presets.

Orca's CLI ignores 'inherits', so each preset is merged with its parents into one file.
Run again after an Orca update: python3 tools/flatten_profile.py
"""
import json, pathlib

SYS = pathlib.Path.home() / ".config/OrcaSlicer/system"
OUT = pathlib.Path(__file__).resolve().parent.parent / "profiles"

MACHINE = "Creality Ender-3 V3 SE 0.4 nozzle"
PROCESSES = {
    "draft": "0.24mm Draft @Creality Ender3V3SE 0.4",
    "standard": "0.20mm Standard @Creality Ender3V3SE 0.4",
    "fine": "0.16mm Optimal @Creality Ender3V3SE 0.4",
}
FILAMENTS = {
    "pla": "Creality Generic PLA @Ender-3V3-all",
    "petg": "Creality Generic PETG @Ender-3V3-all",
}

# Our calibration results, applied on top of the system presets (date: test that set it).
CALIBRATED = {
    "petg": {
        "nozzle_temperature": ["230"],                # 2026-11-06 temp tower: 220-255 all clean, strong; retraction test strung at 235 -> 230
        "nozzle_temperature_initial_layer": ["240"],  # a bit hotter first layer for grip
        "filament_flow_ratio": ["0.93"],              # 2026-11-06 flow test: 90-100 % of 0.95 smooth, 105+ ridged -> middle-low
    },
}


def find(name, kind):
    for vendor in ("Creality", "OrcaFilamentLibrary"):
        for p in (SYS / vendor / kind).rglob("*.json"):
            if p.stem == name:
                return p
    raise SystemExit(f"profile not found: {kind}/{name}")


def resolve(name, kind):
    d = json.load(open(find(name, kind)))
    base = resolve(d["inherits"], kind) if d.get("inherits") else {}
    base.update(d)
    return base


def write(kind, name, out, fix=None):
    d = resolve(name, kind)
    d.pop("inherits", None)
    d["from"] = "system"  # 'User' makes the CLI reject the process/printer pairing
    if fix:
        fix(d)
    json.dump(d, open(OUT / out, "w"), indent=1)
    print(f"{out}: {name}")


def fix_machine(d):
    d["printer_settings_id"] = d["name"]
    d["layer_change_gcode"] = "G92 E0"  # CLI refuses relative E without it
    if "M420" not in d["machine_start_gcode"]:  # turn the saved bed mesh on after homing
        d["machine_start_gcode"] = d["machine_start_gcode"].replace(
            "G28 ;Home \n", "G28 ;Home \nM420 S1 Z10 ;Use saved bed mesh\n", 1)


def write_gui_filament(key, name):
    """Same calibrated values as an Orca GUI user preset '<KEY> (Axiom)', so GUI and CLI slice alike."""
    gui = pathlib.Path.home() / ".config/OrcaSlicer/user/default/filament"
    gui.mkdir(parents=True, exist_ok=True)
    title = f"{key.upper()} (Axiom)"
    d = {"inherits": name, "name": title, "from": "User", "filament_settings_id": [title],
         **CALIBRATED[key]}
    json.dump(d, open(gui / f"{title}.json", "w"), indent=4)
    base = resolve(name, "filament").get("setting_id", "")
    (gui / f"{title}.info").write_text(f"sync_info = create\nuser_id = \nsetting_id = \nbase_id = {base}\nupdated_time = 0\n")
    print(f"GUI preset: {title}")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    write("machine", MACHINE, "machine.json", fix_machine)
    for key, name in PROCESSES.items():
        write("process", name, f"process-{key}.json", lambda d: d.update(print_settings_id=d["name"]))
    for key, name in FILAMENTS.items():
        write("filament", name, f"filament-{key}.json",
              lambda d, k=key: d.update(filament_settings_id=[d["name"]], **CALIBRATED.get(k, {})))
    for key, name in FILAMENTS.items():
        if key in CALIBRATED:
            write_gui_filament(key, name)
