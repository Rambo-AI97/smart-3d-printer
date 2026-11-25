"""Engineering helpers: pre-slice check, stress estimate, fit coupon, orientation.

The heavy modules need trimesh/shapely/manifold3d (the `cad` extra). They run in-process when importable, otherwise in the
CAD venv (env P3D_CAD_PYTHON / config `cad_python` / the default made by `p3d install-cad`) through `call()`.
If neither exists `call()` returns None.
"""
import json
import pathlib
import subprocess

from .. import cad

SRC = pathlib.Path(__file__).resolve().parents[2]
NO_LIBS = cad.NOT_INSTALLED


def cad_python():
    return cad.configured_python()


def _local():
    return cad.importable("trimesh", "shapely")


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
