"""Load a python design file and export it. Runs in the cad venv.

    python -m p3d.shapes.build models/py/NAME.py [OUT.stl]      -> writes the STL, prints a one-line check

A design file defines `part()` (returns a build123d Part) and optionally `CONTEXT` (see shapes/sheet.py):
a preset name ('mantel', 'shelf', 'wall') or a list of {"label": str, "box": (x0, x1, y0, y1, z0, z1)}.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

from .core import check_solid, export_stl


def load_design(path):
    """Import the design file, return (part, context, name)."""
    path = pathlib.Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"design_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    if not hasattr(mod, "part"):
        raise SystemExit(f"{path} has no part()")
    return mod.part(), getattr(mod, "CONTEXT", None), path.stem


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    src = pathlib.Path(a[0])
    out = pathlib.Path(a[1]) if len(a) > 1 else src.with_suffix(".stl")
    part, _, name = load_design(src)
    export_stl(part, out)
    print(json.dumps({"stl": str(out), **check_solid(part)}))
    chk = check_solid(part)
    if chk["solids"] != 1 or not chk["watertight"]:
        print(f"WARNING: {name}: {chk['solids']} solids, watertight={chk['watertight']}", file=sys.stderr)


if __name__ == "__main__":
    main()
