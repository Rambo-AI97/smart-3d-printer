"""Any-printer support: Orca profile catalogue, geometry, flatten, config.bed, setup. Uses a tiny fake Orca tree."""
import json
import tomllib

import pytest

from p3d import config, flatten_profile, gcode, machines, setup_wizard


def put(root, vendor, kind, preset, **kw):
    d = root / vendor / kind
    d.mkdir(parents=True, exist_ok=True)
    kw.setdefault("name", preset)
    (d / f"{preset}.json").write_text(json.dumps(kw))


@pytest.fixture
def orca(tmp_path, monkeypatch):
    r = tmp_path / "orca_profiles"
    # Vendor Alpha: Prusa-like, process chain via inherits, compat by list and by condition
    put(r, "Alpha", "machine", "fdm_common", type="machine", machine_end_gcode="M104 S0\nG90\nM84\n", layer_change_gcode=";L",
        use_relative_e_distances="1", printable_height="200")
    put(r, "Alpha", "machine", "Alpha MK4 0.4 nozzle", type="machine", instantiation="true", inherits="fdm_common",
        nozzle_diameter=["0.4"], printable_area=["0x0", "250x0", "250x210", "0x210"], printable_height="220",
        printer_notes="ALPHA_MK4", machine_start_gcode="G28\n")
    put(r, "Alpha", "machine", "Alpha MK4 0.6 nozzle", type="machine", instantiation="true", inherits="fdm_common",
        nozzle_diameter=["0.6"], printable_area=["0x0", "250x0", "250x210", "0x210"], printable_height="220", printer_notes="ALPHA_MK4")
    put(r, "Alpha", "machine", "Alpha MK4", type="machine_model")  # not instantiable preset
    put(r, "Alpha", "process", "fdm_process", type="process", layer_height="0.2")
    put(r, "Alpha", "process", "0.20mm Standard @MK4", type="process", instantiation="true", inherits="fdm_process",
        compatible_printers=["Alpha MK4 0.4 nozzle"])
    put(r, "Alpha", "process", "0.24mm Standard @MK4", type="process", instantiation="true", inherits="fdm_process",
        layer_height="0.24", compatible_printers=["Alpha MK4 0.4 nozzle"])
    put(r, "Alpha", "process", "0.12mm Detail @MK4", type="process", instantiation="true", inherits="fdm_process",
        layer_height="0.12", compatible_printers_condition='printer_notes=~/.*ALPHA_MK4.*/ and nozzle_diameter[0]==0.4')
    put(r, "Alpha", "process", "0.16mm Optimal @MK4", type="process", instantiation="true", inherits="fdm_process",
        layer_height="0.16", compatible_printers_condition='printer_notes=~/.*ALPHA_MK4.*/ and nozzle_diameter[0]==0.4')
    put(r, "Alpha", "process", "0.30mm Draft @MK4 0.6", type="process", instantiation="true", inherits="fdm_process",
        layer_height="0.30", compatible_printers=["Alpha MK4 0.6 nozzle"])
    put(r, "Alpha", "filament", "Alpha Generic PLA @MK4", type="filament", instantiation="true", filament_type=["PLA"],
        compatible_printers=["Alpha MK4 0.4 nozzle"])
    put(r, "Alpha", "filament", "Alpha Generic PETG @MK4", type="filament", instantiation="true", filament_type=["PETG"],
        compatible_printers=["Alpha MK4 0.4 nozzle"])
    # Vendor Beta: Bambu-like (vendor BBL), generics only from the shared library
    put(r, "BBL", "machine", "Bambu Lab Z1 0.4 nozzle", type="machine", instantiation="true", nozzle_diameter=["0.4"],
        printable_area=["0x0", "256x0", "256x256", "0x256"], printable_height="256", printer_model="Bambu Lab Z1",
        machine_end_gcode="G90\n", machine_start_gcode="G28\n", name="Bambu Lab Z1 0.4 nozzle")
    put(r, "BBL", "process", "0.20mm Standard @BBL Z1", type="process", instantiation="true", layer_height="0.2",
        compatible_printers=["Bambu Lab Z1 0.4 nozzle"])
    put(r, "OrcaFilamentLibrary", "filament", "Generic PLA @System", type="filament", instantiation="true", filament_type=["PLA"])
    put(r, "OrcaFilamentLibrary", "filament", "Generic PETG @System", type="filament", instantiation="true", filament_type=["PETG"])
    put(r, "OrcaFilamentLibrary", "filament", "Generic TPU @System", type="filament", instantiation="true", filament_type=["TPU"])
    put(r, "OrcaFilamentLibrary", "filament", "Generic PLA-CF @System", type="filament", instantiation="true", filament_type=["PLA"])
    monkeypatch.setenv("P3D_ORCA_PROFILES", str(r))
    machines.reset()
    yield r
    machines.reset()


def test_list_and_search(orca):
    ms = machines.list_machines()
    assert ("Alpha", "Alpha MK4 0.4 nozzle") in ms and ("BBL", "Bambu Lab Z1 0.4 nozzle") in ms
    assert all(n != "Alpha MK4" for _, n in ms)          # machine_model entries are not printers
    assert len(ms) == 3
    assert machines.list_machines("mk4")[0] == ("Alpha", "Alpha MK4 0.4 nozzle")
    assert [n for _, n in machines.list_machines("mk4 0.6")] == ["Alpha MK4 0.6 nozzle"]
    assert machines.list_machines("bambu z1")[0][0] == "BBL"
    assert machines.list_machines("zzz") == []


def test_geometry_resolves_inherits(orca):
    g = machines.geometry("Alpha MK4 0.4 nozzle")
    assert (g["x"], g["y"], g["z"], g["nozzle"], g["bambu"]) == (250, 210, 220, 0.4, False)
    assert machines.geometry("Alpha MK4 0.6 nozzle")["nozzle"] == 0.6
    assert machines.geometry("Bambu Lab Z1 0.4 nozzle")["bambu"] is True
    with pytest.raises(KeyError):
        machines.geometry("Nope")


def test_presets_for(orca):
    p = machines.presets_for("Alpha MK4 0.4 nozzle")
    assert p["process"] == {"draft": "0.24mm Standard @MK4", "standard": "0.20mm Standard @MK4",
                            "fine": "0.16mm Optimal @MK4"}   # 0.12 Detail is further from 0.16 than Optimal; condition parsed
    assert p["filament"]["pla"] == "Alpha Generic PLA @MK4" and p["filament"]["petg"] == "Alpha Generic PETG @MK4"
    assert p["filament"]["tpu"] == "Generic TPU @System"      # vendor has none -> Orca's generic library
    z = machines.presets_for("Bambu Lab Z1 0.4 nozzle")
    assert z["filament"]["pla"] == "Generic PLA @System"        # not the PLA-CF variant
    assert z["process"] == {"draft": "0.20mm Standard @BBL Z1", "standard": "0.20mm Standard @BBL Z1",
                            "fine": "0.20mm Standard @BBL Z1"}
    six = machines.presets_for("Alpha MK4 0.6 nozzle")
    assert six["process"]["standard"] == "0.30mm Draft @MK4 0.6"   # only compatible one, never a 0.4 preset


def test_config_bed_defaults(orca, monkeypatch):
    assert config.Config(raw={}).bed == (220, 220, 250)
    assert config.Config(raw={}).park_y == 220 and config.Config(raw={}).z_home_xy == [110, 110]
    c = config.Config(raw={"printer_model": "Alpha MK4 0.4 nozzle"})
    assert c.bed == (250, 210, 220) and c.park_y == 210 and c.z_home_xy == [125, 105]
    assert config.Config(raw={"bed_size": [180, 180]}).bed == (180, 180, 250)
    assert config.Config(raw={"bed_size": [180, 190, 200], "park_y": 150}).park_y == 150
    assert config.Config(raw={"printer_model": "Unknown printer"}).bed == (220, 220, 250)


def test_ender_numbers_unchanged():
    assert gcode.z_max() == 245 == gcode.Z_MAX
    assert gcode.shift_line("G1 Z249 X1", dz=5) == "G1 Z245 X1"
    from p3d import advisor
    assert flatten_profile.lift_line(250) == "G1 Z{min(max_layer_z + 40, 245)} F600 ;Lift clear\n"
    pytest.importorskip("trimesh")
    from p3d.eng import geom
    assert geom.bed() == (220, 220, 250)
    assert advisor.advise({"footprint": [0, 0, 50, 50], "bed": None} ) is not None


def test_z_max_follows_printer(orca):
    config.reset()
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text('printer_model = "Alpha MK4 0.4 nozzle"\n')
    config.reset()
    assert gcode.z_max() == 215
    assert gcode.shift_line("G1 Z219", dz=5) == "G1 Z215"


def test_flatten_other_machine(orca, tmp_path, monkeypatch):
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text('printer_model = "Alpha MK4 0.4 nozzle"\n')
    config.reset()
    monkeypatch.setenv("P3D_ORCA_USER_DIR", str(tmp_path / "gui"))
    flatten_profile.main()
    out = config.CONFIG_FILE.parent / "profiles"
    m = json.loads((out / "machine.json").read_text())
    assert "inherits" not in m and m["printer_settings_id"] == "Alpha MK4 0.4 nozzle"
    assert "G1 Z{min(max_layer_z + 40, 215)} F600" in m["machine_end_gcode"]       # clamped to this machine's height
    assert m["layer_change_gcode"].endswith("G92 E0")
    pe = json.loads((out / "filament-petg.json").read_text())
    assert pe["filament_type"] == ["PETG"] and pe["hot_plate_temp_initial_layer"] == ["70"]
    assert "nozzle_temperature" not in pe or pe["nozzle_temperature"] != ["225"]  # Ender-tuned temps stay Ender-only
    assert json.loads((out / "process-fine.json").read_text())["layer_height"] == "0.16"
    assert "travel_speed" not in json.loads((out / "process-fine.json").read_text())
    assert not (tmp_path / "gui").exists()


def test_flatten_unknown_printer_exits(orca):
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text('printer_model = "Nope 3000"\n')
    config.reset()
    with pytest.raises(SystemExit):
        flatten_profile.main()


def test_setup_noninteractive_writes_keys(orca, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("P3D_ORCA_USER_DIR", str(tmp_path / "gui"))
    setup_wizard.run(defaults=True, printer="Alpha MK4", connection="prusalink", url="printer.local", api_key="K")
    raw = tomllib.loads(config.CONFIG_FILE.read_text())
    assert raw["printer_model"] == "Alpha MK4 0.4 nozzle"
    assert raw["printer_type"] == "prusalink" and raw["printer_url"] == "http://printer.local" and raw["printer_api_key"] == "K"
    assert raw["bed_size"] == [250, 210, 220]
    assert oct(config.CONFIG_FILE.stat().st_mode & 0o777) == "0o600"
    assert (config.CONFIG_FILE.parent / "profiles/machine.json").exists()      # profile build ran
    assert config.get().bed == (250, 210, 220)


def test_setup_bambu(orca, monkeypatch):
    setup_wizard.run(defaults=True, printer="bambu z1", url="bambu.local", serial="SN1", access_code="123", build=False)
    raw = tomllib.loads(config.CONFIG_FILE.read_text())
    assert raw["printer_type"] == "bambu" and raw["bambu_serial"] == "SN1" and raw["bambu_access_code"] == "123"
    assert raw["printer_url"] == "http://bambu.local"


def test_setup_interactive_search_pick(orca, monkeypatch):
    answers = iter(["mk4", "2", "", "", "", "", ""])   # printer search, pick #2, then Enter through the rest
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(config, "find_ports", lambda: ["/dev/ttyFAKE"])
    setup_wizard.run(build=False)
    raw = tomllib.loads(config.CONFIG_FILE.read_text())
    assert raw["printer_model"] == "Alpha MK4 0.6 nozzle" and raw["printer_type"] == "marlin"


def test_setup_default_is_ender(orca, monkeypatch):
    monkeypatch.setattr(config, "find_ports", lambda: [])
    setup_wizard.run(defaults=True, build=False)
    raw = tomllib.loads(config.CONFIG_FILE.read_text())
    assert raw["printer_model"] == machines.DEFAULT_MODEL and "bed_size" not in raw
    assert config.get().bed == (220, 220, 250)


def test_detect(monkeypatch):
    def fake(url, path, timeout=3):
        return {"/server/info": (200, {"result": {}})}.get(path, (404, None))
    monkeypatch.setattr(setup_wizard, "_probe", fake)
    assert setup_wizard.detect("http://x") == "klipper"
    monkeypatch.setattr(setup_wizard, "_probe", lambda u, p, timeout=3: (403, None) if p == "/api/version" else (404, None))
    assert setup_wizard.detect("http://x") == "octoprint"
    monkeypatch.setattr(setup_wizard, "_probe", lambda u, p, timeout=3: (401, None) if p == "/api/v1/version" else (404, None))
    assert setup_wizard.detect("http://x") == "prusalink"
    monkeypatch.setattr(setup_wizard, "_probe", lambda u, p, timeout=3: (None, None))
    assert setup_wizard.detect("http://x") == ""


def test_printers_command(orca, capsys):
    from p3d import cli
    cli.cmd_printers(type("A", (), {"query": "mk4"})())
    out = capsys.readouterr().out
    assert "Alpha MK4 0.4 nozzle  (Alpha)" in out and out.strip().endswith("2 printers matching 'mk4'")


def test_doctor_warns_unknown_model(orca):
    from p3d import doctor
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text('printer_model = "Nope 3000"\n')
    config.reset()
    rows = [r for r in doctor.checks() if r[1] == "printer"]
    assert rows[0][0] == doctor.WARN and "not found in Orca" in rows[0][2]
    config.CONFIG_FILE.write_text('printer_model = "Alpha MK4 0.4 nozzle"\n')
    config.reset()
    rows = [r for r in doctor.checks() if r[1] == "printer"]
    assert rows[0][0] == doctor.OK and "250 x 210 x 220" in rows[0][2]
