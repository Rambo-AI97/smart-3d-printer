from p3d import advisor
from p3d.advisor import advise, format_advice, gather

BASE = {"footprint": (80, 80, 140, 140), "max_z": 30, "grams": 30, "shares": {"Outer wall": .3, "Inner wall": .3, "Sparse infill": .2},
        "walls": 2, "infill": "15%", "minutes": 60, "layer_height": 0.2, "brim_type": "no_brim", "brim_width": 5,
        "filament_type": "PETG", "spool_material": "PETG", "bed": (220, 220)}


def a(**kw):
    return advise({**BASE, **kw})


def test_looks_good():
    assert a() == []
    assert format_advice([]) == ["Advice: looks good"]


def test_tall_narrow_needs_brim():
    r = a(footprint=(100, 100, 110, 110), max_z=50)
    assert len(r) == 1 and "--brim" in r[0]
    assert not a(footprint=(100, 100, 110, 110), max_z=50, brim_type="outer_only")
    assert not a(footprint=(100, 100, 110, 110), max_z=50, brim_used=True)
    assert not a(footprint=(90, 90, 125, 125), max_z=45)
    assert "--brim" in a(footprint=(90, 90, 115, 115), max_z=45)[0]


def test_supports_heavy_and_tiny():
    assert "30%" in a(shares={"Support": .3})[0]
    assert "without --supports" in a(supports=True, shares={"Support": .005, "Outer wall": .9})[0]
    assert not a(supports=False, shares={"Outer wall": 1})


def test_heavy_settings_small_part():
    r = a(grams=10, walls=6, infill="40%", shares={"Inner wall": .5, "Outer wall": .2, "Sparse infill": .2})
    assert len(r) == 1 and "estimate" in r[0] and "saves ~" in r[0]
    assert not a(grams=40, walls=6)


def test_placement_back_left_and_far():
    assert "back-left" in a(footprint=(10, 170, 50, 210))[0]
    assert "from the bed centre" in a(footprint=(170, 10, 210, 40))[0]
    assert not a(footprint=(90, 90, 130, 130))


def test_bed_mesh_warning():
    grid = [[0.0] * 5 for _ in range(5)]
    grid[4][0] = 0.45          # back-left corner
    r = a(footprint=(100, 100, 120, 120), mesh=grid)
    assert not r
    r = a(footprint=(0, 190, 40, 220), mesh=grid)
    assert any("mesh" in x for x in r)


def test_filament_mismatch():
    r = a(filament_type="PLA")
    assert len(r) == 1 and "PLA" in r[0] and "PETG" in r[0]
    assert not a(filament_type="PLA", spool_material="")


def test_long_print():
    r = a(minutes=300, shares={"Sparse infill": .5, "Inner wall": .3})
    assert len(r) == 1 and "draft" in r[0]
    assert not a(minutes=300, layer_height=0.28, shares={"Sparse infill": .9})
    assert not a(minutes=100, shares={"Sparse infill": .9})


def test_gather_reads_gcode(tmp_path, monkeypatch):
    monkeypatch.setattr(advisor, "_latest_mesh", lambda: None)
    monkeypatch.setattr(advisor, "_spool_material", lambda: "PLA")
    g = tmp_path / "x.gcode"
    g.write_text("; max_z_height: 50.00\n; filament_type = PETG\n; total filament used [g] = 5.0\n; wall_loops = 2\n"
                 ";TYPE:Custom\nG1 X5 Y5 E1\n;LAYER_CHANGE\n;Z:0.2\n;TYPE:Outer wall\nG90\nM83\nG1 X100 Y100 F3000\n"
                 "G1 X104 Y100 E1\nG1 X104 Y104 E1\nG1 X100 Y104 E1\n")
    (tmp_path / "job.json").write_text('{"settings": {"supports": true}}')
    info = gather(tmp_path)
    assert info["footprint"] == (100, 100, 104, 104) and info["supports"] and info["spool_material"] == "PLA"
    r = advise(info)
    assert any("--brim" in x for x in r) and any("spool" in x for x in r)


def test_report_never_raises(tmp_path):
    from p3d import advisor
    assert advisor.report(tmp_path / "missing.gcode").startswith("Advice")


def test_dashboard_advice_note_never_raises(tmp_path):
    from p3d.web import server
    assert server.advice_note(str(tmp_path / "missing.gcode")) == ""


def test_small_feet_islands_flagged():
    from p3d.advisor import advise
    base = {"max_z": "48", "brim_type": "outer_only", "brim_width": "5"}
    assert any("islands" in a for a in advise({**base, "islands": [1365, 1365]}))
    assert not any("islands" in a for a in advise({**base, "islands": [2919]}))
