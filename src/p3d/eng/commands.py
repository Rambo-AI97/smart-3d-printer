"""CLI side of the eng tools: light (no geometry imports); the maths runs through eng.call() in the cad venv."""
import pathlib
import sys

from . import NO_LIBS, call


def A(*flags, **kw):
    return (flags, kw)


def resolve(name):
    """STL path, a build123d design (.py or models/py/NAME.py, exported to STL first), or a scad NAME (models/scad/NAME.stl)."""
    p = pathlib.Path(name).expanduser()
    from .. import shapecmds
    py = p if p.suffix.lower() == ".py" else shapecmds._py_src(name)
    if py.suffix.lower() == ".py" and py.exists():
        import json
        return pathlib.Path(json.loads(shapecmds._run_cad("p3d.shapes.build", py).splitlines()[-1])["stl"]).resolve()
    if p.suffix.lower() == ".stl" or p.exists():
        if not p.exists():
            sys.exit(f"no such model: {p}")
        return p.resolve()
    from .. import cli
    stl = cli._scad_src(name).with_suffix(".stl")
    if not stl.exists():
        sys.exit(f"no {stl}: run p3d scad {name} first")
    return stl


def show(lines):
    for lvl, text in lines:
        print(f"{lvl:<4} {text}")


def gate(stl, a):
    """Hook for `p3d make`: optional auto-orient, then the check. Exits on FAIL unless --force. Returns the STL to slice."""
    if getattr(a, "auto_orient", False):
        r = call("orient", "run", path=str(stl))
        if r is None:
            print("orient skipped:", NO_LIBS)
        elif r["changed"]:
            print(f"auto-orient: {r['top'][0]['name']}, score {r['current']['score']} -> {r['top'][0]['score']} ({r['out']})")
            stl = pathlib.Path(r["out"])
    res = call("check", "run", path=str(stl), multi=bool(getattr(a, "multi", False)))
    if res is None:
        print("check skipped:", NO_LIBS)
        return stl
    show(res["lines"])
    if res["worst"] == "FAIL":
        if getattr(a, "force", False):
            print("FAIL ignored (--force): slicing anyway")
        else:
            sys.exit("check FAILED: not slicing. Fix the model, or pass --force to slice anyway.")
    return stl


def cmd_check(a):
    path = resolve(a.model)
    res = call("check", "run", path=str(path), multi=a.multi)
    if res is None:
        sys.exit(NO_LIBS)
    show(res["lines"])
    print(f"check {path.name}: {res['worst']}")
    if res["worst"] == "FAIL":
        sys.exit(1)


def _xyz(s):
    return [float(t) for t in s.split(",")]


def cmd_stress(a):
    path = resolve(a.model)
    if a.material is None:
        from ..cli import default_filament
        a.material = default_filament()
    try:
        res = call("stress", "run", path=str(path), load_kg=a.load, material=a.material, section_at=a.section_at,
                   arm=a.arm, axis=a.axis, direction=a.dir, fix_face=a.fix_face,
                   load_at=_xyz(a.load_at) if a.load_at else None)
    except (ValueError, RuntimeError) as e:
        sys.exit(f"stress: {e}")
    if res is None:
        sys.exit(NO_LIBS)
    show(res["lines"])
    print("(screening estimate: static, linear, no stress concentrations; trust factors under ~2 as a no)")


def cmd_coupon(a):
    from .. import cli
    path = resolve(a.model)
    try:
        r = call("coupon", "cut", path=str(path), z=a.z, box=a.box)
    except (ValueError, RuntimeError) as e:
        sys.exit(f"coupon: {e}")
    if r is None:
        sys.exit(NO_LIBS)
    print(f"coupon: {r['out']}  {r['size']} mm, {r['volume_cm3']} of {r['full_volume_cm3']} cm3")
    out, final, info = cli.slice_model(pathlib.Path(r["out"]), a.quality, a.filament, keep_orient=True, tag="coupon")
    print(f"fit test: {info.get('estimated printing time (normal mode)')}, {info.get('total filament used [g]')} g; "
          f"job {out} (not queued)")


def cmd_orient(a):
    path = resolve(a.model)
    r = call("orient", "run", path=str(path), load_dir=a.load_dir, out=a.out)
    if r is None:
        sys.exit(NO_LIBS)
    print(f"{'rank':<4} {'score':>5}  {'support mm2':>11} {'bed mm2':>8} {'height':>6} {'strength':>8}  orientation")
    for i, t in enumerate(r["top"], 1):
        st = "-" if t["strength"] < 0 else t["strength"]
        print(f"{i:<4} {t['score']:>5}  {t['support_mm2']:>11} {t['contact_mm2']:>8} {t['height_mm']:>6} {st:>8}  {t['name']}")
    c = r["current"]
    print(f"as modelled: score {c['score']}. Best written to {r['out']}"
          + ("" if r["changed"] else " (same as the model: keep it)"))


MAKE_ARGS = [A("--multi", action="store_true", help="check: allow several separate bodies"),
             A("--force", action="store_true", help="check: slice even if the pre-slice check FAILS"),
             A("--auto-orient", action="store_true", help="try every stable face and print on the best (p3d orient)")]

COMMANDS = [
    ("check", cmd_check, "pre-slice gate: watertight, bodies, thin walls, empty layers, overhang, bed fit (PASS/WARN/FAIL)",
     [A("model", help="MODEL.stl or scad NAME"), A("--multi", action="store_true", help="allow several separate bodies")]),
    ("stress", cmd_stress, "beam/section strength for hooks, clamps, brackets: safety factor vs layer-line and in-plane strength",
     [A("model"), A("--load", type=float, required=True, metavar="KG"),
      A("--section-at", type=float, metavar="C", help="cut the section at this coordinate on --axis"),
      A("--arm", type=float, metavar="MM", help="lever arm from the section to the load, with --section-at"),
      A("--axis", default="z", choices=["x", "y", "z"], help="beam axis for --section-at (default z)"),
      A("--fix-face", metavar="-z", help="fixed end: -z/+z/-x/+x/-y/+y (face at that end of the bounding box)"),
      A("--load-at", metavar="X,Y,Z", help="load point in model coordinates, with --fix-face"),
      A("--dir", metavar="D", help="load direction: x, -z, or x,y,z (default -z = gravity)"),
      A("--material", choices=["petg", "pla", "tpu"], help="default: active spool / petg")]),
    ("coupon", cmd_coupon, "cut the critical slice (snap, thread) and slice it as a tiny fit test; never queued",
     [A("model"), A("--z", metavar="A..B", help="keep this Z range, e.g. 12..17"),
      A("--box", metavar="x0,y0,z0,x1,y1,z1", help="keep this box"),
      A("-q", "--quality", default="standard", choices=["draft", "standard", "fine"]),
      A("-f", "--filament", default="petg", choices=["pla", "petg", "tpu"])]),
    ("orient", cmd_orient, "score every stable face as the print orientation; write the best rotated STL",
     [A("model"), A("--load-dir", metavar="X,Y,Z", help="direction the part will be loaded, in model coordinates"),
      A("-o", "--out", help="output STL (default NAME_oriented.stl)")]),
]
