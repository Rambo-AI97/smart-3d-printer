"""Shapes library. Needs build123d + trimesh: run with ~/.venvs/cad/bin/python -m pytest tests/test_shapes.py
(skipped in an interpreter that lacks them)."""
import warnings

import pytest

pytest.importorskip("build123d")
pytest.importorskip("trimesh")
from p3d import shapes as S  # noqa: E402


def test_j_hook_one_watertight_solid_with_expected_size():
    h = S.j_hook(opening=6, wire=3, width=10, plate_len=16, clear=2.5, drop=9, stripes=None)
    c = S.check_solid(h)
    assert c["solids"] == 1 and c["valid"] and c["watertight"]
    x, y, z = c["size_mm"]
    assert z == pytest.approx(10, abs=0.05)
    assert x == pytest.approx(16 + 2.5 + 1.5 + 9 + 1.6, abs=0.3)      # plate + clearance + J + stem half-thickness
    assert y > 9 + 4.5                                                  # J depth below the shelf


def test_j_hook_below_the_shelf_stays_clear_of_the_wall_face():
    h = S.j_hook(clear=2.5, stripes=None)
    assert max(v.X for v in h.vertices() if v.Y < -2) <= -2.5 + 1e-3


def test_tape_plate_countersink_is_flush_and_sized():
    p = S.tape_plate(30, 20, 2.6, screw="#6")
    assert p.bounding_box().size.Z == pytest.approx(2.6, abs=1e-3)
    top_hole = [e for e in p.edges() if abs(e.center().Z - 2.6) < 1e-3 and e.geom_type.name == "CIRCLE"]
    assert top_hole and max(e.radius for e in top_hole) == pytest.approx(S.SCREWS["#6"][1] / 2, abs=0.05)


def test_snap_strain_warns_above_petg_limit_only():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        S.snap_cantilever(length=14, thickness=1.6, deflection=1.0)       # ~1.2 %: fine
        assert not w
        S.snap_cantilever(length=8, thickness=2, deflection=2)            # ~9 %: warn
        assert any("PETG" in str(x.message) for x in w)
    assert S.snap_strain(1.6, 14, 1.0) == pytest.approx(1.5 * 1.6 * 1.0 / 14 ** 2)


def test_hinge_is_two_free_solids_with_clearance():
    h = S.print_in_place_hinge(clearance=0.35)
    a, b = h.solids()
    assert a.distance_to(b) == pytest.approx(0.35, abs=0.02)


def test_sweep_taper_changes_thickness_smoothly():
    path = S.rounded_path([(0, 0), (20, 0), (20, 20)], [0, 5, 0])
    body = S.sweep_profile(path, [(0, 4), (1, 2)], width=6)
    assert body.is_valid and len(body.solids()) == 1
    assert path.length == pytest.approx(20 - 5 + 20 - 5 + 3.1416 * 5 / 2, abs=0.05)
