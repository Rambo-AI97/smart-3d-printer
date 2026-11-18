"""Build standalone Orca profiles for the Ender-3 V3 SE 0.4 from Orca's system presets: `p3d profiles`.

Orca's CLI ignores 'inherits', so each preset is merged with its parents into one file.
Writes ~/.config/p3d/profiles/ (used instead of the bundled ones). Run again after an Orca update.
Other printer: change MACHINE/PROCESSES/FILAMENTS below to the preset names Orca shows for it.
"""
import json, pathlib

from . import config

SYS = pathlib.Path.home() / ".config/OrcaSlicer/system"
OUT = config.CONFIG_DIR / "profiles"

MACHINE = "Creality Ender-3 V3 SE 0.4 nozzle"
PROCESSES = {
    "draft": "0.24mm Draft @Creality Ender3V3SE 0.4",
    "standard": "0.20mm Standard @Creality Ender3V3SE 0.4",
    "fine": "0.16mm Optimal @Creality Ender3V3SE 0.4",
}
FILAMENTS = {
    "pla": "Creality Generic PLA @Ender-3V3-all",
    "petg": "Creality Generic PETG @Ender-3V3-all",
    "tpu": "Creality Generic TPU @Ender-3V3-all",
}

PLATES = ("cool", "eng", "hot", "textured", "supertack")  # Orca's bed-plate variants: set all so the plate type never matters


def bed_step_down(first, rest):
    """Orca bed temps: `first` for layer 1 (grip), `rest` after it (never off). Orca emits the M140 at layer 2."""
    d = {}
    for p in PLATES:
        d[f"{p}_plate_temp_initial_layer"] = [str(first)]
        d[f"{p}_plate_temp"] = [str(rest)]
    return d


# Bed step-down per material: (first layer, other layers). 2026-11-09: PETG sticks at 70 but 60 holds it and warps/ stresses less.
BED = {"petg": (70, 60), "pla": (60, 55), "tpu": (55, 50)}  # TPU 95A box: bed 50-60

# Our calibration results, applied on top of the system presets (date: test that set it).
CALIBRATED = {
    "petg": {
        "nozzle_temperature_initial_layer": ["240"],  # a bit hotter first layer for grip
        "filament_flow_ratio": ["0.93"],              # 2026-11-06 flow test: 90-100 % of 0.95 smooth, 105+ ridged -> middle-low
        # 2026-11-06 faering boat: heavy stringing between thin parts (damp spool). Less ooze + less dragging:
        "nozzle_temperature": ["225"],                # temp tower clean 220-255; 230 strung on Benchy+boat -> 225 (cooler oozes less)
        "filament_z_hop": ["0.2"],                    # 0.4 normal lift pulled strings up between masts/posts
        "filament_z_hop_types": ["Spiral Lift"],
        "filament_wipe": ["1"],
        **bed_step_down(*BED["petg"]),
    },
    "pla": bed_step_down(*BED["pla"]),
    # 2026-11-18 first TPU 95A roll (black, box 210-230 C). Direct drive but soft: slow, short retract, no wipe/z-hop drag.
    "tpu": {
        "nozzle_temperature_initial_layer": ["225"],
        "nozzle_temperature": ["220"],
        "filament_max_volumetric_speed": ["3"],       # ~30 mm/s at 0.2 x 0.45: soft filament buckles in the extruder if pushed
        "filament_retraction_length": ["0.8"],        # long retracts tangle TPU in the gears
        "filament_retraction_speed": ["25"],
        "filament_z_hop": ["0"],
        **bed_step_down(*BED["tpu"]),
    },
}

# Applied to every process (draft/standard/fine). Date: print that set it.
PROCESS_TUNED = {
    "reduce_crossing_wall": "1",       # 2026-11-06 faering: travel inside the part, not across open air (fewer strings)
    "travel_speed": "200",             # 2026-11-06: faster travel = less time to ooze (stock 150)
    "support_type": "tree(auto)",      # 2026-11-06 faering: grid supports buried the boat; trees touch less, peel easier
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
    # end: lift well clear of the part (>= 40 mm above it, max 245) before presenting the bed
    d["machine_end_gcode"] = d["machine_end_gcode"].replace(
        "G90 ;Absolute positionning \n", "G90 ;Absolute positionning \nG1 Z{min(max_layer_z + 40, 245)} F600 ;Lift clear\n", 1)


def write_gui_filament(key, name):
    """Same calibrated values as an Orca GUI user preset '<KEY> (p3d)', so GUI and CLI slice alike."""
    gui = pathlib.Path.home() / ".config/OrcaSlicer/user/default/filament"
    gui.mkdir(parents=True, exist_ok=True)
    title = f"{key.upper()} (p3d)"
    d = {"inherits": name, "name": title, "from": "User", "filament_settings_id": [title],
         **CALIBRATED[key]}
    json.dump(d, open(gui / f"{title}.json", "w"), indent=4)
    base = resolve(name, "filament").get("setting_id", "")
    (gui / f"{title}.info").write_text(f"sync_info = create\nuser_id = \nsetting_id = \nbase_id = {base}\nupdated_time = 0\n")
    print(f"GUI preset: {title}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write("machine", MACHINE, "machine.json", fix_machine)
    for key, name in PROCESSES.items():
        write("process", name, f"process-{key}.json", lambda d: d.update(print_settings_id=d["name"], **PROCESS_TUNED))
    for key, name in FILAMENTS.items():
        write("filament", name, f"filament-{key}.json",
              lambda d, k=key: d.update(filament_settings_id=[d["name"]], **CALIBRATED.get(k, {})))
    for key, name in FILAMENTS.items():
        if key in CALIBRATED:
            write_gui_filament(key, name)
    print(f"profiles written to {OUT}")


if __name__ == "__main__":
    main()
