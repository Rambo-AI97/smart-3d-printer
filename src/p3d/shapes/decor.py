"""Decoration: text, helical grooves, flutes, bead rings, diagonal stripes on swept bands. All units mm.

Every function returns a Part to ADD (emboss, beads) or SUBTRACT (grooves, flutes, engraved text).
Keep decorative depth >= 0.4 mm (two 0.2 mm layers) and width >= 0.8 mm (two 0.4 mm lines) to print cleanly.
"""
from __future__ import annotations

import math

from build123d import (Align, Circle, Cylinder, Helix, Part, Plane, Pos, Rot, Text, Torus, Vector, extrude,
                       sweep)


def emboss_text(text: str, size: float = 6, depth: float = 0.6, plane: Plane = Plane.XY, engrave: bool = False,
                font: str = "Arial", bold: bool = False) -> Part:
    """Text solid on `plane` (origin = text centre). Emboss: rises `depth` from the plane (sunk 0.1 mm into
    the base so it fuses). Engrave (engrave=True): a cutter going `depth` below the plane (+0.1 above).

    Printing: 0.8+ mm stroke widths; size >= 5 mm; embossed text on the top face prints best, engraved
    text on a vertical face needs depth >= 0.6 mm. Use a bold font for small sizes.
    """
    from build123d import FontStyle
    t = Text(text, size, font=font, font_style=FontStyle.BOLD if bold else FontStyle.REGULAR,
             align=(Align.CENTER, Align.CENTER))
    z0, h = (-depth, depth + 0.1) if engrave else (-0.1, depth + 0.1)
    return plane * Pos(0, 0, z0) * extrude(t, h)


def helical_grooves(radius: float, length: float, pitch: float = 10, groove_w: float = 1.2, depth: float = 0.6,
                    starts: int = 1) -> Part:
    """Candy-cane / barber-pole cutter for a cylinder of `radius` along +Z from z=0 (subtract it). mm.

    pitch = axial advance per turn per start. groove_w x depth rectangular-ish cross-section (round-bottomed:
    a circle of groove_w diameter centred on the surface, clipped to `depth` deep). starts = number of
    interleaved grooves. Printing: the cylinder axis vertical; grooves under 45 deg from vertical print
    without sagging only if pitch >= 3 * groove_w.
    """
    out = None
    helix_len = length - pitch / 2
    for k in range(starts):
        h = Helix(pitch, helix_len, radius + groove_w / 2 - depth)
        prof = Plane(origin=h @ 0, x_dir=(1, 0, 0), z_dir=h % 0) * Circle(groove_w / 2)
        g = sweep(prof, path=h, is_frenet=True)
        g = Rot(0, 0, 360 * k / starts) * Pos(0, 0, pitch / 4) * g
        out = g if out is None else out + g
    return out


def flutes(radius: float, length: float, count: int = 12, width: float = 1.6, depth: float = 0.8) -> Part:
    """Vertical round-bottom flute cutters around a cylinder of `radius` along +Z from z=0 (subtract). mm.

    Printing: flutes along the print Z axis print perfectly; keep width <= 2*depth + ... a half-round groove
    (width ~ 2 x depth) has no overhang over 45 deg.
    """
    r = (depth * depth + (width / 2) ** 2) / (2 * depth)   # circle through the groove edges
    out = None
    for k in range(count):
        c = Pos(radius - depth + r, 0, -0.5) * Cylinder(r, length + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
        c = Rot(0, 0, 360 * k / count) * c
        out = c if out is None else out + c
    return out


def bead_lines(radius: float, z_positions, bead_d: float = 1.2, inset: float = 0.3) -> Part:
    """Round bead rings around a cylinder of `radius` at the given heights (union them). mm.

    The bead centre sits at radius - inset + bead_d/2 -ish so it fuses with the wall. Printing: a bead on a
    vertical wall is a rounded step under 45 deg overhang if bead_d <= 1.6 mm: no supports.
    """
    out = None
    for z in z_positions:
        b = Pos(0, 0, z) * Torus(radius + bead_d / 2 - inset, bead_d / 2)
        out = b if out is None else out + b
    return out


def cut_each(body: Part, cutters) -> Part:
    """Subtract cutters one at a time, skipping any that would leave an invalid or split solid.

    One big boolean with dozens of swept cutters can fail on OCC; one by one is slower but robust.
    Returns the body; `cut_each.skipped` holds the count skipped on the last call.
    """
    skipped = 0
    for c in (cutters.solids() if hasattr(cutters, "solids") else cutters):
        try:
            nb = body - c
            if nb.is_valid and len(nb.solids()) == 1:
                body = nb
                continue
        except Exception:
            pass
        skipped += 1
    cut_each.skipped = skipped
    return body


def path_stripes(path, thickness, width: float, s_range=(0.3, 0.95), pitch: float = 2.4, groove_w: float = 1.1,
                 depth: float = 0.5, angle: float = 40) -> Part:
    """Diagonal candy-cane grooves across a band swept along `path` (core.sweep_profile). mm. Subtract it.

    The band width runs along Z, 0..width (same frame as j_hook). Each groove is a round-bottomed cutter
    swept along a spline that sits on the band face (offset along the local normal), so it follows tight
    curves exactly instead of cutting a flat chord. Cut on both faces, `depth` deep, one groove per `pitch`
    mm of centre-line between path fractions s_range, slanted `angle` deg from straight across.
    thickness: number or the same [(s, t)] list given to sweep_profile (local band thickness).
    Printing: band on its side; 0.5 deep x 1.1 wide grooves print without stringing at 0.2 mm layers.
    """
    from build123d import Compound, Spline
    from .core import _interp
    table = thickness if isinstance(thickness, (list, tuple)) else [(0, float(thickness)), (1, float(thickness))]
    L = path.length
    n = max(1, int(L * (s_range[1] - s_range[0]) / pitch))
    zs = [-1.0 + k * (width + 2.0) / 8 for k in range(9)]       # across the width, overshooting both sides
    r = groove_w / 2
    sols = []
    for k in range(n + 1):
        s0 = s_range[0] + (s_range[1] - s_range[0]) * k / n
        for side in (1, -1):
            pts = []
            for z in zs:
                s = s0 + (z - width / 2) * math.tan(math.radians(angle)) / L
                sc = min(1.0, max(0.0, s))
                T = path % sc
                N = Vector(0, 0, 1).cross(T)
                off = side * (_interp(table, sc) / 2 - depth + r)
                pts.append(path @ sc + T * ((s - sc) * L) + N * off + Vector(0, 0, z))   # straight beyond the ends
            c = Spline(*pts)
            prof = Plane(origin=c @ 0, z_dir=c % 0) * Circle(r)
            sols.append(sweep(prof, path=c))
    return Compound(sols)
