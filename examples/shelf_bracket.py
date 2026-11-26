"""Shelf bracket: 60 x 60 mm L with a centre gusset, countersunk #8 screws, true fillets.

Prints on its side (the 30 mm width along Z) so the layer lines run around the L corner and the
gusset carries the load in-plane, the strong direction. No supports. Try: p3d sheet examples/shelf_bracket.py
"""
from build123d import Box, Polyline, make_face, extrude, Pos, Rot, Align, Axis, Plane

from p3d.shapes import soften
from p3d.shapes.hardware import _screw_cutter

LEG, W, T, GUSSET_T = 60.0, 30.0, 5.0, 4.0


def part():
    wall = Box(T, W, LEG, align=(Align.MIN, Align.CENTER, Align.MIN))      # against the wall (YZ)
    shelf = Box(LEG, W, T, align=(Align.MIN, Align.CENTER, Align.MIN))     # under the shelf (XY)
    tri = make_face(Polyline((T, 0), (LEG - 6, 0), (T, LEG - 6), close=True))
    gusset = Plane.XZ * extrude(tri, GUSSET_T / 2, both=True)
    body = soften(wall + shelf, 3.0, (wall + shelf).edges().filter_by(Axis.Y))   # inner + outer corner fillets
    body = body + Pos(0, 0, T) * gusset
    for z in (24, 48):    # wall screws, heads flush on the inside face
        body -= Pos(T, -8 if z == 24 else 8, z) * Rot(0, -90, 0) * _screw_cutter("#8", T)
    for x in (24, 48):    # shelf screws from below, heads flush on the underside
        body -= Pos(x, 8 if x == 24 else -8, 0) * Rot(180, 0, 0) * Pos(0, 0, -T) * _screw_cutter("#8", T)
    return body
