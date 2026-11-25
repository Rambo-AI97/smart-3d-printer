# usage: python tools/floating_islands.py FILE.gcode  -> islands with nothing under them (x, y, z, area)
# Rasterizes each layer's extrusions (from gcode_section.layers) and labels connected regions.
import sys, numpy as np
from scipy import ndimage
import re
def layers(path):
    z=None; x=y=0; e=0; w=0.45; rel=False; out={}
    for ln in open(path):
        if ln.startswith(';Z:'): z=round(float(ln[3:]),2); out.setdefault(z,[])
        elif ln.startswith(';WIDTH:'): w=float(ln[7:])
        elif ln.startswith('M83'): rel=True
        elif ln.startswith('M82'): rel=False
        elif ln.startswith('G92') and ' E' in ln: e=float(re.search(r'E(-?[\d.]+)',ln).group(1))
        elif ln.startswith(('G1 ','G0 ','G2 ','G3 ')):
            m=dict((k,float(v)) for k,v in re.findall(r'([XYE])(-?[\d.]+)',ln.split(';')[0]))
            nx=m.get('X',x); ny=m.get('Y',y)
            de=m.get('E',0) if rel else (m['E']-e if 'E' in m else 0)
            if 'E' in m and not rel: e=m['E']
            if de>0 and z is not None and (nx,ny)!=(x,y): out[z].append((x,y,nx,ny,w))
            x,y=nx,ny
    return out
C = 0.25
L = layers(sys.argv[1]); zs = sorted(z for z in L if L[z])
pts = [p for z in zs for s in L[z] for p in ((s[0], s[1]), (s[2], s[3]))]
x0, y0 = min(p[0] for p in pts) - 2, min(p[1] for p in pts) - 2
nx = int((max(p[0] for p in pts) - x0 + 2) / C) + 1; ny = int((max(p[1] for p in pts) - y0 + 2) / C) + 1
def mask(segs):
    m = np.zeros((nx, ny), bool)
    for a, b, c, d, w in segs:
        n = max(2, int(np.hypot(c - a, d - b) / (C / 2)))
        xs = ((np.linspace(a, c, n) - x0) / C).astype(int); ys = ((np.linspace(b, d, n) - y0) / C).astype(int)
        m[xs, ys] = True
    return ndimage.binary_dilation(m, iterations=max(1, int(0.2 / C)))
prev = None
for z in zs:
    m = mask(L[z])
    if prev is not None:
        lab, n = ndimage.label(m)
        sup = ndimage.binary_dilation(prev, iterations=2)
        for i in range(1, n + 1):
            r = lab == i
            if not (r & sup).any():
                xi, yi = np.argwhere(r).mean(0)
                print(f"floating z={z} x={x0 + xi * C:.1f} y={y0 + yi * C:.1f} area={r.sum() * C * C:.2f} mm2")
    prev = m
