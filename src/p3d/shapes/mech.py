"""Mechanical parts: snap-fit cantilever with a strain check, print-in-place hinge. All units mm."""
from __future__ import annotations

import warnings

from build123d import Align, Axis, Box, Cylinder, Part, Polygon, Pos, extrude

from .core import soften

PETG_MAX_STRAIN = 0.025   # permissible strain for repeated snaps in PETG (2.5 %); PLA ~1.5 %, ABS ~2 %


def snap_strain(thickness: float, length: float, deflection: float, taper: float = 1.0) -> float:
    """Peak bending strain (fraction) of a cantilever snap arm root. mm in, 0.025 = 2.5 %.

    eps = 1.5 * t * y / L^2 for a uniform beam; a beam tapering to `taper` x thickness at the tip
    (taper 0.5 = half) gives eps = 0.67 * t * y / L^2 (formula from the standard snap-fit design guides).
    """
    k = 1.5 if taper >= 0.99 else 0.67 if taper <= 0.51 else 1.5 - (1 - taper) * 1.66
    return k * thickness * deflection / length ** 2


def snap_cantilever(length: float = 14, thickness: float = 1.6, width: float = 6, deflection: float = 1.0,
                    base: float = 4, root_fillet: float = 0.8, taper: float = 1.0) -> Part:
    """Cantilever snap arm with a catch hook. Arm along +X from a base block, hook rises +Y. Units mm.

    deflection = hook height (how far the arm must flex to engage) = y in the strain formula. Warns when
    peak strain exceeds PETG's 2.5 % (lengthen the arm, thin it, or reduce the hook height). The hook has a
    ~30 deg lead-in ramp on the insertion side (-X) and a 90 deg retaining face on the +X side.
    Printing: print with the arm's flex direction (Y) in the layer plane (arm lying along the bed, width up
    along Z) so layers do not peel at the root; the root fillet reduces stress concentration.
    """
    eps = snap_strain(thickness, length, deflection, taper)
    if eps > PETG_MAX_STRAIN:
        warnings.warn(f"snap arm strain {eps * 100:.1f} % > PETG limit {PETG_MAX_STRAIN * 100:.1f} %: "
                      f"lengthen the arm or lower the hook ({deflection} mm)", stacklevel=2)
    tip_t = thickness * taper
    ramp = deflection / 0.577                     # 30 deg lead-in
    pts = [(-base, -base), (0, -base), (0, 0), (length, 0), (length, tip_t + deflection),
           (length - ramp, tip_t), (0, thickness), (0, thickness + base), (-base, thickness + base)]
    part = extrude(Polygon(*pts, align=None), width)
    # fillet the two root corners (arm meets base) on the Z-parallel edges
    root = [e for e in part.edges().filter_by(Axis.Z)
            if abs(e.center().X) < 1e-3 and (abs(e.center().Y) < 1e-3 or abs(e.center().Y - thickness) < 1e-3)]
    return soften(part, root_fillet, root)


def print_in_place_hinge(knuckle_h: float = 8, knuckles: int = 5, pin_d: float = 3, leaf_len: float = 15,
                         leaf_t: float = 3, clearance: float = 0.35, wall: float = 1.6) -> Part:
    """Print-in-place pin hinge: two leaves (two solids) that already rotate. Units mm.

    Axis along Z at the origin, leaf A to -X (pin fused to it), leaf B to +X (bores around the pin).
    knuckles: odd count >= 3; A owns the odd ones (1st, 3rd...), B the even ones. clearance: radial and
    axial gap between moving parts (0.35 mm works on a tuned 0.4 nozzle in PETG; 0.3 can fuse).
    Total height = knuckles*knuckle_h + (knuckles-1)*clearance. Printing: print as modelled (axis vertical,
    leaves flat on the bed), no supports; do not add a brim touching both leaves. Break free by flexing it
    after the first print. Result is a Compound of 2 solids.
    """
    assert knuckles >= 3 and knuckles % 2 == 1, "use an odd knuckle count >= 3"
    pin_r = pin_d / 2
    R = pin_r + clearance + wall                       # barrel outer radius
    H = knuckles * knuckle_h + (knuckles - 1) * clearance

    def z0(i):
        return i * (knuckle_h + clearance)

    def mn(*size):
        return dict(align=(Align.CENTER, Align.CENTER, Align.MIN))

    def leaf(sign, own, is_pin):
        body = Pos(sign * (R + leaf_len), 0, 0) * Box(wall * 1.5, leaf_t, H, **mn())   # far-end spine
        for i in own:
            zb = z0(i)
            body += Pos(0, 0, zb) * Cylinder(R, knuckle_h, **mn())
            body += Pos(sign * (R + leaf_len) / 2, 0, zb) * Box(R + leaf_len, leaf_t, knuckle_h, **mn())
        if is_pin:
            return body + Cylinder(pin_r, H, **mn())
        return body - Pos(0, 0, -1) * Cylinder(pin_r + clearance, H + 2, **mn())

    return leaf(-1, range(0, knuckles, 2), True) + leaf(+1, range(1, knuckles, 2), False)
