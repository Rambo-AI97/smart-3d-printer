"""Engineering helpers: pre-slice check, stress estimate, fit coupon, orientation.

The heavy modules need trimesh/shapely/manifold3d. They run in-process when importable, otherwise in the cad venv
(P3D_CAD_PYTHON, default ~/.venvs/cad/bin/python) through `call()`. If neither exists `call()` returns None.
"""
import json
import os
import pathlib
import subprocess

SRC = pathlib.Path(__file__).resolve().parents[2]
NO_LIBS = "geometry libs missing (trimesh, shapely): install them or set P3D_CAD_PYTHON to the cad venv python; skipped"


def cad_python():
    p = pathlib.Path(os.environ.get("P3D_CAD_PYTHON", "~/.venvs/cad/bin/python")).expanduser()
    return p if p.exists() else None


def _local():
    try:
        import trimesh, shapely  # noqa: F401
        return True
    except ImportError:
        return False


def call(mod, func, **kw):
    """Run p3d.eng.<mod>.<func>(**kw) where the geometry libs live. Returns its JSON-able result, or None if no libs."""
    if _local():
        import importlib
        return getattr(importlib.import_module(f"p3d.eng.{mod}"), func)(**kw)
    py = cad_python()
    if not py:
        return None
    code = "import sys;sys.path.insert(0,sys.argv[1]);from p3d.eng.worker import main;main()"
    r = subprocess.run([str(py), "-c", code, str(SRC), mod, func, json.dumps(kw)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "eng worker failed")
    return json.loads(r.stdout.strip().splitlines()[-1])
