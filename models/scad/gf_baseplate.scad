// Gridfinity baseplate (2026-11-12), wraps gridfinity-rebuilt-openscad (kennetek, MIT).
// Render with OPENSCADPATH=<folder holding gridfinity-rebuilt-openscad>.
// Choices:
//  - THIN plate (4.65 mm, style 0): drawers/shelves, fastest + least filament. Bins seat on the 45 deg profile.
//  - No magnets by default (small child in the house).
//  - Elephant foot: the spec's 0.35 mm vertical clearance at the cell bottom already absorbs PETG squish,
//    so no compensation. EF (outer bottom chamfer) is OFF: even 0.3 mm makes Orca flag a floating
//    cantilever on the 2.85 mm outer wall and adds time (4x4 1h18 -> 1h26). Tiles still butt within ~0.2 mm.
//  - Fit to drawer: DX/DY = inside size in mm (0 = exact grid). FITX/FITY put the solid padding on
//    -1 = -X/-Y side, 0 = split, 1 = +X/+Y. Use gf_drawer_plan.py to split a big drawer into bed-sized tiles.
//  - Bed 220x220: tiles <= 4x4 cells (168 mm) with a brim (big flat PETG warps); 5 cells = 210 mm only fits without one.
// OPENSCADPATH=~/projects/vendor openscad -D GX=3 -D GY=2 -o out.stl gf_baseplate.scad
use <gridfinity-rebuilt-openscad/gridfinity-rebuilt-baseplate.scad>
use <gridfinity-rebuilt-openscad/src/core/gridfinity-rebuilt-holes.scad>
include <gridfinity-rebuilt-openscad/src/core/standard.scad>
$fa = 8; $fs = 0.25;

GX = 2;  GY = 2;          // cells
DX = 0;  DY = 0;          // drawer/tile outer size in mm (0 = GX*42)
FITX = 0; FITY = 0;       // where padding goes
STYLE = 0;                // 0 thin, 2 skeleton (thicker, for magnets/screws)
MAGNETS = false;
EF = 0;                   // outer bottom chamfer (mm), 0 = off (see above)

W = max(GX * 42, DX);  D = max(GY * 42, DY);
// plate centre offset when padding is one-sided (mirrors kennetek's fit_offset math)
cx = (W - GX * 42) * (FITX / 2);  cy = (D - GY * 42) * (FITY / 2);

module rrect(w, d, r) { offset(r) square([w - 2 * r, d - 2 * r], center = true); }

module ef_cutter() {
  r = BASEPLATE_OUTER_RADIUS;
  translate([cx, cy, 0]) difference() {
    translate([0, 0, -1]) linear_extrude(EF + 1) square([W + 10, D + 10], center = true);
    hull() {
      translate([0, 0, -1.01]) linear_extrude(1.01) rrect(W - 2 * EF, D - 2 * EF, r - EF);
      translate([0, 0, 0]) linear_extrude(0.01) rrect(W - 2 * EF, D - 2 * EF, r - EF);
      translate([0, 0, EF]) linear_extrude(0.01) rrect(W, D, r);
    }
  }
}

holes = bundle_hole_options(refined_hole = false, magnet_hole = MAGNETS, screw_hole = false,
                            crush_ribs = true, chamfer = true, supportless = false);
difference() {
  gridfinityBaseplate([GX, GY], 42, [DX, DY], STYLE, holes, 0, [FITX, FITY]);
  if (EF > 0) ef_cutter();
}
