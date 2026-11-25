"""`p3d sheet` and `p3d build`: python (build123d) designs. The CAD work runs in the cad venv by subprocess,
because p3d's own environment does not need build123d/trimesh/matplotlib."""
import os
import pathlib
import subprocess
import sys

CAD_PYTHON = pathlib.Path(os.environ.get("P3D_CAD_PYTHON", "~/.venvs/cad/bin/python")).expanduser()


def _run_cad(module, *args):
    """Run `python -m module args` in the cad venv with p3d importable. Prints its output; exits on failure."""
    if not CAD_PYTHON.exists():
        sys.exit(f"cad venv python not found: {CAD_PYTHON} (set P3D_CAD_PYTHON)")
    env = dict(os.environ, PYTHONPATH=str(pathlib.Path(__file__).resolve().parent.parent))
    r = subprocess.run([str(CAD_PYTHON), "-m", module, *map(str, args)], capture_output=True, text=True, env=env)
    if r.returncode:
        sys.exit((r.stderr or r.stdout)[-2000:])
    if "WARNING" in r.stderr:
        print(r.stderr.strip(), file=sys.stderr)
    return r.stdout.strip()


def _py_src(name):
    from .cli import cfg
    p = pathlib.Path(name).expanduser()
    if p.exists():
        return p
    return cfg().models / "py" / (name if name.endswith(".py") else name + ".py")


def cmd_sheet(a):
    """Design sheet JPG (front/side/top/iso, mm, thinnest wall, context) from a .py design, STL or NAME."""
    from .cli import cfg
    src = pathlib.Path(a.model).expanduser()
    if not src.exists():
        py = _py_src(a.model)
        scad_stl = cfg().models / "scad" / (a.model.removesuffix(".stl") + ".stl")
        src = py if py.exists() else scad_stl
    if not src.exists():
        sys.exit(f"no design {a.model}: looked for models/py/NAME.py and models/scad/NAME.stl")
    extra = (["--context", a.context] if a.context else []) + (["--out", a.out] if a.out else [])
    print("sheet:", _run_cad("p3d.shapes.sheet", src, *extra))


def cmd_build(a):
    """models/py/NAME.py -> STL -> slice (kept orientation) -> warnings + small shot JPG."""
    from . import cli
    src = _py_src(a.name)
    if not src.exists():
        sys.exit(f"no {src}")
    print(_run_cad("p3d.shapes.build", src))
    a.model, a.keep_orient = str(src.with_suffix(".stl")), not a.orient
    final = cli.cmd_slice(a)
    from .shot import shot
    print("shot:", shot([pathlib.Path(final).parent]))
