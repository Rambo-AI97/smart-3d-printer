"""p3d.eng checks on tiny synthetic meshes. Skipped when the geometry libs are not in this interpreter."""
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("shapely")
np = pytest.importorskip("numpy")

from p3d.eng import check, stress  # noqa: E402


def box(x, y, z, at=(0, 0, 0)):
    m = trimesh.creation.box([x, y, z])
    m.apply_translation([at[0], at[1], at[2] + z / 2])
    return m


def stl(tmp_path, *meshes, name="m.stl"):
    p = tmp_path / name
    trimesh.util.concatenate(list(meshes)).export(str(p))
    return p


def levels(res):
    return [lvl for lvl, _ in res["lines"]]


def text(res, word):
    return next(t for _, t in res["lines"] if word in t)


def test_two_disjoint_cubes_fail_bodies(tmp_path):
    r = check.run(stl(tmp_path, box(10, 10, 10), box(10, 10, 10, at=(30, 0, 0))))
    assert r["worst"] == "FAIL" and r["bodies"] == 2
    assert check.run(stl(tmp_path, box(10, 10, 10), box(10, 10, 10, at=(30, 0, 0))), multi=True)["worst"] != "FAIL"


def test_gap_layer_fails_empty_layer(tmp_path):
    # the Orca "empty layer" bug: two slabs with a 0.2 mm hole in Z between them
    r = check.run(stl(tmp_path, box(10, 10, 5), box(10, 10, 5, at=(0, 0, 5.2))))
    assert r["worst"] == "FAIL"
    assert "empty layer" in text(r, "empty")


def test_thin_plate_warns_wall(tmp_path):
    r = check.run(stl(tmp_path, box(40, 40, 0.6)))
    assert next(l for l, t in r["lines"] if "under two lines" in t) == "WARN"


def test_solid_cube_passes(tmp_path):
    assert check.run(stl(tmp_path, box(20, 20, 20)))["worst"] == "PASS"


def test_cantilever_matches_hand_calc(tmp_path):
    p = stl(tmp_path, box(10, 10, 100))
    F = 1.0 * stress.G
    hand = F * 100 * 5 / (10 * 10 ** 3 / 12)       # M*c/I, MPa
    sec = stress.run(p, 1.0, section_at=0.5, arm=100, direction="x")
    assert sec["sigma"] == pytest.approx(hand, rel=0.05)
    reg = stress.run(p, 1.0, fix_face="-z", load_at=[0, 0, 100], direction="y")   # fixed base, tip load
    assert reg["sigma"] == pytest.approx(hand, rel=0.05)
