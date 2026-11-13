#!/usr/bin/env python3
"""Split a drawer/shelf (inside W x D mm) into printable Gridfinity baseplate tiles.

usage: gf_drawer_plan.py W D [--max 4] [--gap 0.5] [--render OUTDIR]
Each tile is <= MAX cells per side (bed 220 + brim). Leftover space (< 42 mm per axis) becomes solid
padding, split between the two outer edges so the grid sits centred; seams stay on cell boundaries.
--gap: total clearance so the plates drop in (default 0.5 mm).
"""
import argparse, os, pathlib, subprocess

ap = argparse.ArgumentParser()
ap.add_argument("w", type=float); ap.add_argument("d", type=float)
ap.add_argument("--max", type=int, default=4); ap.add_argument("--gap", type=float, default=0.5)
ap.add_argument("--render", metavar="OUTDIR")
a = ap.parse_args()

def split(n, m):  # n cells into near-equal chunks <= m
    k = -(-n // m); base, extra = divmod(n, k)
    return [base + (i < extra) for i in range(k)]

def axis(size):
    usable = size - a.gap; n = int(usable // 42); pad = usable - n * 42
    chunks = split(n, a.max); out = []
    for i, c in enumerate(chunks):  # (cells, outer mm, fit): pad halves go on the first and last tile
        if len(chunks) == 1:
            out.append((c, c * 42 + pad, 0))
        elif i == 0:
            out.append((c, c * 42 + pad / 2, -1))
        elif i == len(chunks) - 1:
            out.append((c, c * 42 + pad / 2, 1))
        else:
            out.append((c, c * 42, 0))
    return n, pad, out

nx, px, xs = axis(a.w); ny, py, ys = axis(a.d)
print(f"drawer {a.w} x {a.d} mm -> {nx} x {ny} cells, padding {px:.1f} / {py:.1f} mm, {len(xs) * len(ys)} tiles")
scad = pathlib.Path(__file__).with_name("gf_baseplate.scad")
for j, (cy, dy, fy) in enumerate(ys):
    for i, (cx, dx, fx) in enumerate(xs):
        name = f"tile_r{j + 1}c{i + 1}_{cx}x{cy}"
        defs = dict(GX=cx, GY=cy, DX=round(dx, 2), DY=round(dy, 2), FITX=fx, FITY=fy)
        print(f"  {name}: {dx:.1f} x {dy:.1f} mm  " + " ".join(f"-D {k}={v}" for k, v in defs.items()))
        if a.render:
            out = pathlib.Path(a.render).expanduser(); out.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ, OPENSCADPATH=os.path.expanduser("~/projects/vendor"))
            cmd = ["openscad", *[x for k, v in defs.items() for x in ("-D", f"{k}={v}")], "-o", str(out / f"{name}.stl"), str(scad)]
            subprocess.run(cmd, env=env, check=True, capture_output=True)
