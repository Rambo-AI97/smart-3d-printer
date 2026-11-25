"""Mounting and fastening parts: tape plates, J/S hooks, nut pockets, threads. All units mm."""
from __future__ import annotations

import math

from build123d import (Align, Axis, Box, Cone, Cylinder, Helix, Part, Plane, Polygon, Pos, RegularPolygon, Rot,
                       extrude, sweep)

from .core import rounded_path, soften, sweep_profile

# wood/drywall screws: (clearance hole diameter, countersink head diameter) in mm, 0.2 mm slack on the shank
SCREWS = {"#4": (3.0, 5.7), "#6": (3.7, 7.1), "#8": (4.4, 8.4)}
# metric nuts: (across flats, thickness, bolt clearance hole), +0.2 clearance is added to the pocket
NUTS = {"M3": (5.5, 2.4, 3.4), "M4": (7.0, 3.2, 4.5), "M5": (8.0, 4.0, 5.5)}
HEATSET = {"M3": (4.0, 5.5), "M4": (5.6, 7.5), "M5": (6.4, 9.0)}  # (hole dia, depth) for standard inserts


def _screw_cutter(screw: str, thickness: float) -> Part:
    """Countersunk screw cutter along +Z: head (90 deg cone) flush at z=thickness, shank down to z=0."""
    d, head = SCREWS[screw]
    cone_h = (head - d) / 2
    shank = Pos(0, 0, -0.5) * Cylinder(d / 2, thickness + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cone = Pos(0, 0, thickness - cone_h) * Cone(d / 2, head / 2 + 0.01, cone_h + 0.01,
                                                align=(Align.CENTER, Align.CENTER, Align.MIN))
    return shank + cone


def tape_plate(length: float = 30, width: float = 20, thickness: float = 2.6, screw: str | None = "#4",
               corner: float = 3, edge: float = 0.6) -> Part:
    """Flat plate for double-sided tape: tape face on z=0, length along X, width along Y (mm).

    Optional countersunk screw hole (#4, #6 or #8) centred 5 mm... of the plate, head flush on the top face.
    corner = vertical corner radius, edge = top-edge fillet. Printing: lie flat; keep thickness >= 2.4 mm so
    the countersink leaves 4+ perimeters under the head. The tape face is the bed face: no elephant-foot
    chamfer, a slight foot is useful for tape grip.
    """
    p = Box(length, width, thickness, align=(Align.MIN, Align.CENTER, Align.MIN))
    p = soften(p, min(corner, width / 2 - 0.1), p.edges().filter_by(Axis.Z))
    top = p.faces().sort_by(Axis.Z)[-1].edges()
    p = soften(p, min(edge, thickness / 3), top)
    if screw:
        p = p - Pos(length - max(5.0, SCREWS[screw][1]), 0, 0) * _screw_cutter(screw, thickness)
    return p


def j_hook(opening: float = 6, wire: float = 3, width: float = 10, plate_len: float = 16, plate_t: float = 2.6,
           clear: float = 2.5, drop: float = 9, lip: float = 0, screw: str | None = "#4",
           taper: tuple = (1.1, 0.95), corner: float = 0.8, bend: float = 3.0,
           stripes: dict | None = None) -> Part:
    """J-hook over a shelf edge as ONE smooth swept solid, tape plate included. Units mm.

    Frame: plate on the tape face y=0 (body y>=0), x in [0, plate_len] on the shelf, x=0 = the shelf edge,
    width along Z (0..width). The arm crosses the edge, bends down (`bend` radius), drops so the J centre is
    `drop` below the shelf top, and curls back up; the tip points up, `clear` mm in front of the wall face
    (the wall face is the plane x=0 below the shelf).
    opening: inside gap between stem and tip. wire: stem thickness. taper = (stem multiplier near the bend,
    tip multiplier): the stem is thicker than the tip, smooth in between. lip: straight tip length after the
    curl. screw: countersunk hole in the plate (or None). stripes: None, or a dict of decor.path_stripes options
    (e.g. {} for candy-cane defaults) cut on the stem and J only, never on the plate.
    Printing: print on its side (width along Z is the print height): no supports, 4 walls, 0.2 layers.
    Thinnest wall = min(plate_t, tip thickness); a bend radius >= wire keeps it from snapping on the layer lines.
    """
    c = plate_t / 2
    R = (opening + wire) / 2
    xt = -(clear + wire / 2)               # tip centre-line x
    xd = xt - 2 * R                        # stem centre-line x
    pts = [(plate_len, c), (xd, c), (xd, -drop - R), (xt, -drop - R), (xt, -drop + lip)]
    path = rounded_path(pts, [0, bend, R, R, 0])
    s_edge = plate_len / path.length       # plate flat until the support edge, then the arm thickens
    t = [(0, plate_t), (s_edge, plate_t), (s_edge + 0.1, wire * taper[0]), (0.75, wire * taper[0]),
         (1, wire * taper[1])]
    body = Pos(0, 0, width / 2) * sweep_profile(path, t, width=width, corner=corner)
    xs = body.faces().sort_by(Axis.X)[-1].edges()   # plate end face: round it like the rest
    body = soften(body, min(corner * 0.55, plate_t / 3), xs)   # != corner: equal radii leave degenerate patches
    if stripes is not None:
        from .decor import cut_each, path_stripes
        s0 = (plate_len - xd - bend + math.pi / 2 * bend + 0.8) / path.length
        body = cut_each(body, Pos(0, 0, width / 2) * path_stripes(path, t, width, **{"s_range": (s0, 0.97), **stripes}))
    if screw:
        hx = plate_len - 5
        if hx - SCREWS[screw][1] / 2 < 0.8:
            raise ValueError("plate too short for that screw head")
        body = body - Pos(hx, 0, width / 2) * (Rot(-90, 0, 0) * _screw_cutter(screw, plate_t))
    return body


def s_hook(opening_a: float = 20, opening_b: float = 20, wire: float = 4, length: float = 40, lip: float = 8,
           width: float | None = None, corner: float = 0.8) -> Part:
    """S-hook as one swept solid. Units mm. Axis along Y, bends in the XY plane, lower cup opens right, upper left.

    opening_a/b: inside gaps of the two cups (mm). wire: round rod diameter (width=None) or thickness of a
    flat strap of the given `width` (rounded rectangle, printed on its side). length: stem centre-line
    length between the two U-turns' tangent points (>= the two bend radii). lip: straight tip length after each curl.
    Printing: round rod prints best lying down along the cups' plane; use 5 walls (strength is the walls).
    """
    ra, rb = (opening_a + wire) / 2, (opening_b + wire) / 2
    L = max(length, ra + rb)
    pts = [(2 * ra, ra + lip), (2 * ra, 0), (0, 0), (0, L), (-2 * rb, L), (-2 * rb, L - rb - lip)]
    path = rounded_path(pts, [0, ra, ra, rb, rb, 0])
    return sweep_profile(path, wire, width=width, corner=corner)


def nut_pocket(size: str = "M3", kind: str = "captive", depth: float | None = None, slot_len: float = 12,
               clearance: float = 0.2) -> Part:
    """Cutter for a nut or heat-set insert, to subtract from a part. Axis +Z, mouth at z=0, goes up to +Z. mm.

    kind="captive": hex pocket (+clearance) with a slot of `slot_len` to +X so the nut slides in from the side,
      plus the bolt hole through (depth defaults to nut thickness; hole runs 30 mm).
    kind="heatset": round hole for a standard brass insert (depth default per size). Use 4 walls round it.
    Printing: orient so Z is the bolt axis. The slot floor is 'bridging': pause and drop the nut in, or add
    a sacrificial 0.2 mm layer under the bolt hole.
    """
    if kind == "heatset":
        d, dep = HEATSET[size]
        return Cylinder(d / 2, depth or dep, align=(Align.CENTER, Align.CENTER, Align.MIN))
    af, th, hole = NUTS[size]
    af += clearance
    dia = af / math.cos(math.radians(30))     # corner-to-corner
    depth = depth or th + clearance
    hexa = extrude(Rot(0, 0, 0) * RegularPolygon(dia / 2, 6), depth)
    slot = Pos(slot_len / 2, 0, 0) * Box(slot_len, af, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    bolt = Pos(0, 0, -30) * Cylinder(hole / 2, 60, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return hexa + slot + bolt


def thread(diameter: float = 8, pitch: float = 1.25, length: float = 10, internal: bool = False,
           clearance: float = 0.25) -> Part:
    """Simple 60 deg ISO-style helical thread along +Z from z=0, as one solid (mm).

    External: a core + ridge with outer diameter `diameter`. Internal (internal=True): a cutter hole to
    subtract; its major diameter is enlarged by `clearance`. Not a standards-grade thread; coarse pitch
    (>= 1.0 mm) prints well at 0.2 mm layers on PETG. Prints with the axis vertical, no supports.
    """
    h = 0.6134 * pitch                       # thread depth (ISO external)
    major = diameter + (clearance if internal else 0)
    minor = major - 2 * h
    core = Cylinder(minor / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    helix = Helix(pitch, length - pitch, minor / 2 - 0.05)
    half = pitch * 0.42
    prof = Plane(origin=helix @ 0, x_dir=(1, 0, 0), z_dir=helix % 0) * Polygon(
        (-0.0, -half), (h + 0.05, -half * 0.12), (h + 0.05, half * 0.12), (0, half), align=None)
    # profile lives in plane (x radial, y axial)
    ridge = sweep(prof, path=helix, is_frenet=True)
    ridge = Pos(0, 0, pitch / 2) * ridge
    # trim the ridge ends flush with the core
    ridge = ridge & Cylinder(major / 2 + 1, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return core + ridge
