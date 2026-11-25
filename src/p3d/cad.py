"""Where the CAD/engineering libraries (build123d, trimesh, shapely, manifold3d, ...) live, and `p3d install-cad`.

Lookup order for code that needs them:
  1. in-process: the libraries import in the Python that runs p3d (installed with `p3d[cad]` / `p3d[all]`)
  2. a Python named by env P3D_CAD_PYTHON or the config key `cad_python`
  3. the venv `p3d install-cad` creates: ~/.local/share/p3d/cad-venv (checked automatically)
Otherwise: NOT_INSTALLED.
"""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys

from . import config

# Mirror of the `cad` extra in pyproject.toml (used only if the installed metadata cannot be read).
CAD_PACKAGES = ["build123d", "trimesh", "manifold3d", "shapely", "numpy", "scipy", "matplotlib", "pillow"]
PYTHON_FOR_CAD = "3.12"   # build123d needs >=3.11,<3.15 and its OCP wheels are tested here on 3.12
NOT_INSTALLED = "CAD tools not installed: run `p3d install-cad`"


def venv_dir():
    return config.XDG_DATA / "p3d/cad-venv"


def venv_python(root=None):
    return (root or venv_dir()) / "bin/python"


def importable(*mods):
    return all(importlib.util.find_spec(m) is not None for m in mods)


def configured_python():
    """The Python from P3D_CAD_PYTHON / config `cad_python`, else the default cad-venv; None if none exists."""
    v = os.environ.get("P3D_CAD_PYTHON") or config.get().raw.get("cad_python")
    for p in ([pathlib.Path(v).expanduser()] if v else []) + [venv_python()]:
        if p.exists():
            return p
    return None


def find(*mods):
    """('process', None) when mods import here; ('venv', path) when a CAD Python exists; (None, None) otherwise."""
    if importable(*mods):
        return "process", None
    py = configured_python()
    return ("venv", py) if py else (None, None)


def python_for(*mods):
    """Interpreter to run CAD code with: this one if the libs import here, else the cad Python. Exits with NOT_INSTALLED."""
    kind, py = find(*mods)
    if kind == "process":
        return pathlib.Path(sys.executable)
    if kind == "venv":
        return py
    sys.exit(NOT_INSTALLED)


def requirements():
    """Requirement strings of the `cad` extra from the installed p3d metadata, else CAD_PACKAGES."""
    try:
        from importlib import metadata
        out = []
        for r in metadata.requires("p3d") or []:
            body, _, marker = r.partition(";")
            if "extra" in marker and "cad" in marker.replace("'", '"').split('"')[1::2]:
                out.append(body.strip())
        if out:
            return out
    except Exception:
        pass
    return list(CAD_PACKAGES)


def install(venv=None):
    """Create the cad venv (uv, else python3.12 -m venv) and install the cad extra there. Returns its python path."""
    root = pathlib.Path(venv) if venv else venv_dir()
    reqs = requirements()
    uv = shutil.which("uv")
    root.parent.mkdir(parents=True, exist_ok=True)
    if uv:
        steps = [[uv, "venv", "--python", PYTHON_FOR_CAD, "--allow-existing", str(root)],
                 [uv, "pip", "install", "--python", str(venv_python(root)), *reqs]]
    else:
        py = shutil.which(f"python{PYTHON_FOR_CAD}")
        if not py:
            sys.exit(f"need uv (https://docs.astral.sh/uv) or python{PYTHON_FOR_CAD} to build the CAD environment")
        steps = [[py, "-m", "venv", str(root)],
                 [str(venv_python(root)), "-m", "pip", "install", "--upgrade", "pip", *reqs]]
    for cmd in steps:
        print("+", " ".join(cmd))
        if subprocess.run(cmd).returncode:
            sys.exit(f"install-cad failed at: {' '.join(cmd[:3])}")
    return venv_python(root)
