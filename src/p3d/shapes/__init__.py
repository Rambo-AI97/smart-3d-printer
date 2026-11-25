"""Reusable build123d parts for the printer (mm, PETG).

Runs in ~/.venvs/cad (build123d, trimesh, matplotlib). Importing this package needs only build123d;
no p3d main dependencies. Typical design file (models/py/NAME.py)::

    from p3d.shapes import j_hook
    def part(): return j_hook(...)
"""
from .core import soften, rounded_path, sweep_profile, export_stl, check_solid
from .hardware import tape_plate, j_hook, s_hook, nut_pocket, thread, SCREWS, NUTS
from .mech import snap_cantilever, snap_strain, print_in_place_hinge
from .decor import emboss_text, helical_grooves, flutes, bead_lines, path_stripes, cut_each

__all__ = ["soften", "rounded_path", "sweep_profile", "export_stl", "check_solid", "tape_plate", "j_hook",
           "s_hook", "nut_pocket", "thread", "SCREWS", "NUTS", "snap_cantilever", "snap_strain",
           "print_in_place_hinge", "emboss_text", "helical_grooves", "flutes", "bead_lines", "path_stripes", "cut_each"]
