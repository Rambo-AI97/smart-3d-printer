"""Subprocess entry for the cad venv: argv = SRC MOD FUNC JSON_KWARGS; the last stdout line is the JSON result."""
import importlib
import json
import sys


def main():
    _, mod, func, kw = sys.argv[1:5]
    print(json.dumps(getattr(importlib.import_module(f"p3d.eng.{mod}"), func)(**json.loads(kw))))
