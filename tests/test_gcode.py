import pytest

from p3d import flatten_profile, gcode

LAYERS = """; total layer number: 3
M104 S240
M140 S70
G28
G1 X-2.1 Y20 Z0.28 F5000
G1 X-2.1 Y145 E15
M83
;TYPE:Custom
;LAYER_CHANGE
;Z:0.2
G1 Z0.2
G1 X50 Y60 F6000
G1 X70 Y60 E1
G1 X70 Y80 E1
;LAYER_CHANGE
;Z:0.4
M140 S60
M106 S128
G1 Z0.4
G1 X70 Y80
G1 X50 Y80 E1
;LAYER_CHANGE
;Z:0.6
G1 Z0.6
G1 X60 Y70
G1 X60 Y90 E1
;TYPE:Custom
G91
G1 Z10
; filament used [g] = 10.00
; total filament used [g] = 10.00
; estimated printing time (normal mode) = 1h 0m 0s
""".splitlines()


def test_parse_layers():
    cmds, at, z, total = gcode.parse(LAYERS)
    assert total == 3 and z == {1: 0.2, 2: 0.4, 3: 0.6}
    assert at[cmds.index("G1 Z0.4")] == 2 and at[0] == 0


def test_tracker_modes_and_targets():
    t = gcode.Tracker()
    for c in ["M83", "G1 X10 Y20 Z1 E2", "M140 S60", "M104 S225", "M106 S100", "G92 E0"]:
        t.feed(c)
    assert (t.x, t.y, t.z, t.bed, t.nozzle, t.fan, t.e) == (10, 20, 1, 60, 225, 100, 0)
    assert not t.abs_e
    t.feed("M82")
    assert t.feed("G1 X11 E5") and t.e == 5


def test_footprint_skips_start_prime_line():
    cmds, at, _, _ = gcode.parse(LAYERS)
    assert gcode.footprint(cmds, layer_at=at) == (50, 60, 70, 90)
    assert gcode.footprint(cmds, upto=1, layer_at=at) == (50, 60, 70, 80)


def test_z_home_safety():
    assert gcode.z_home_ok((50, 60, 70, 90), (110, 110), 12)
    assert not gcode.z_home_ok((100, 100, 120, 120), (110, 110), 12)
    assert not gcode.z_home_ok((90, 90, 101, 101), (110, 110), 12)  # inside the margin
    assert not gcode.z_home_ok(None, (110, 110), 12)                # unknown footprint: never auto


def test_shift_line():
    assert gcode.shift_line("G1 X10 Y20 Z0.2 E1 F600", 1, 2, 50) == "G1 X11 Y22 Z50.2 E1 F600"
    assert gcode.shift_line("G1 Z300", dz=10) == "G1 Z245"
    assert gcode.shift_line("M104 S200", 5, 5, 5) == "M104 S200"
    assert gcode.shift_line("G1 X1 ; hi", dx=1) == "G1 X2 ; hi"


def test_shift_all_skips_relative_blocks():
    out = gcode.shift_all(["G1 Z1", "G91", "G1 Z10", "G90", "G1 Z2 X1"], dx=1, dz=5)
    assert out[:4] == ["G1 Z6", "G91", "G1 Z10", "G90"]
    assert out[4].startswith("G1 Z7") and "X2" in out[4]


def test_recover_manual_never_probes_z():
    lines, info = gcode.build_recover(LAYERS, 2, auto_home=False)
    cmds = gcode.parse(lines)[0]
    assert not [c for c in cmds if c.split()[0] == "G28" and (len(c.split()) == 1 or "Z" in c)]
    assert "G28 X Y" in cmds and "G92 Z0.4" in cmds
    assert cmds.index("G92 Z0.4") < cmds.index("G28 X Y")
    assert info["layer"] == 3 and info["bed"] == 60
    _, at, z, total = gcode.parse(lines)
    assert total == 3 and 3 in z and 1 not in z      # numbering kept
    assert "M140 S60" in cmds and "M109 S240" in cmds and "M106 S128" in cmds


def test_recover_auto_homes_when_clear():
    lines, _ = gcode.build_recover(LAYERS, 1, auto_home=True)
    assert "G28" in gcode.parse(lines)[0]


def test_recover_scales_summary_and_rejects_bad_layer():
    lines, info = gcode.build_recover(LAYERS, 2, auto_home=False)
    assert any(ln.startswith("; total filament used [g] = ") and float(ln.split("=")[1]) < 10 for ln in lines)
    with pytest.raises(ValueError):
        gcode.build_recover(LAYERS, 3, auto_home=False)
    with pytest.raises(ValueError):
        gcode.build_recover(LAYERS, 0, auto_home=False)


def test_last_layer_at_or_below():
    assert gcode.last_layer_at_or_below({1: 0.2, 2: 0.4, 3: 0.6}, 0.45) == 2


def test_bed_step_down_all_plates():
    d = flatten_profile.bed_step_down(70, 60)
    for p in ("cool", "eng", "hot", "textured"):
        assert d[f"{p}_plate_temp_initial_layer"] == ["70"] and d[f"{p}_plate_temp"] == ["60"]
    assert flatten_profile.CALIBRATED["petg"]["hot_plate_temp"] == ["60"]
    assert flatten_profile.CALIBRATED["pla"]["hot_plate_temp_initial_layer"] == ["60"]
    assert flatten_profile.CALIBRATED["pla"]["hot_plate_temp"] == ["55"]
