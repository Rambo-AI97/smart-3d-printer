# Shape workflow: sheet first, then build, then slice

Goal: get the shape right on the first print. Hand-written OpenSCAD hull chains come out blocky; the parts
library in `src/p3d/shapes/` builds one smooth solid (true fillets, swept hooks) with build123d.

```
1. write   models/py/NAME.py          part() returns a build123d Part; optional CONTEXT = "mantel" | "shelf" | "wall"
2. look    p3d sheet NAME             one small JPG: front / side / top / iso, mm on every view, thinnest wall,
                                      support body drawn dashed (context). Approve the SHAPE here.
3. build   p3d build NAME             STL -> slice (kept orientation) -> advisor -> shot, same as `p3d make`
4. print   the usual queue / print commands
```

`p3d sheet` also takes an `.stl` path or a `models/scad/NAME` STL, so old designs get the same check.
Sheets land in `<data_dir>/shots/` (`shots_dir` in the config moves them). The CAD libraries come with `p3d[all]` (the one-line installer does this). Otherwise run `p3d install-cad`: it builds
`~/.local/share/p3d/cad-venv` (Python 3.12; build123d supports 3.11-3.14) and p3d finds it by itself. To use a Python of
your own, set `P3D_CAD_PYTHON` or `cad_python` in the config. Lookup order: this Python, then that, then the default venv. `p3d make` for `.scad` is unchanged.

## Library (`from p3d.shapes import ...`, all mm, each function documents printing notes)

| Area | Functions |
|---|---|
| core | `soften` (fillet/chamfer one solid), `rounded_path` (polyline with tangent arcs), `sweep_profile` (round or rounded-rect profile along a path with smooth thickness taper), `export_stl`, `check_solid` |
| hardware | `tape_plate` (countersunk #4/#6/#8), `j_hook` (opening, wire, plate, clearance, optional candy stripes), `s_hook`, `nut_pocket` (M3/M4/M5 captive or heat-set), `thread` |
| mechanical | `snap_cantilever` + `snap_strain` (warns above PETG's 2.5 % strain), `print_in_place_hinge` |
| decoration | `emboss_text` (or engrave), `helical_grooves`, `flutes`, `bead_lines`, `path_stripes` + `cut_each` (diagonal grooves that follow a curved band) |

Example (`models/py/hook.py`):

```python
from p3d.shapes import j_hook
CONTEXT = "mantel"
def part():
    return j_hook(opening=6, wire=3, width=10, plate_len=16, clear=2.5, drop=9, stripes={})
```

Design frame used by `j_hook` and the context presets: `y = 0` is the tape face, the support body lies at
`y <= 0`, the shelf edge is `x = 0`, and the width runs along Z (so it prints on its side with no supports).

## Organic shapes (Blender)

`blender -b --python src/p3d/shapes/blender_smooth.py -- IN.stl OUT.stl --voxel 0.25 --smooth 10 [--subsurf 1]
[--bevel 0.4] [--solidify 1.2] [--scale 1]`: voxel remesh (watertight), corrective smooth, subdivision, bevel,
shell. Prints a JSON line with the triangle count and non-manifold edge count (0 = watertight). Run
`p3d sheet OUT.stl` on the result before slicing.

## Tests

`PYTHONPATH=src ~/.venvs/cad/bin/python -m pytest tests/test_shapes.py` (skipped where build123d is missing).
