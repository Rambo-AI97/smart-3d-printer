// Gridfinity bathroom row (2026-11-12): 2x2 Sonicare toothbrush bin + 2x1 toothpaste bin (tube upside down).
// Bases from gridfinity-rebuilt-openscad (kennetek, MIT): render with OPENSCADPATH=<folder holding it>.
// Toothbrush: pin 6.0 -> 5.0 (HX6100 charger pin 5.8, Thingiverse 5192550), Ø36 seat + drip moat, bead ring.
// Research 2026-11-12 (Printables 966032 gridfinity toothpaste: drain gaps; Sonicare stands: raise the handle so
//   it dries): 6 drying ribs in the brush seat, a drain slot in the funnel collar. No magnets (child in the house).
// Toothpaste: Colgate Total tube stands on its flip cap (~31 wide x 22 tall, scaled from Colgate's product photo)
//   in an oval cap pocket 32x20 -> 36x27 over 18 mm + lead-in flare, 24 deep, all in a 24 mm collar (floor = bin top, drain runs out)
//   that stays inside the 41.5 mm grid width so neighbours still fit.
// PART = "plate" (both, one print) | "toothbrush" | "paste".  Prints flat, no supports.
// OPENSCADPATH=~/projects/vendor p3d make gf_bathroom --walls 4 --infill 20
use <gridfinity-rebuilt-openscad/src/core/bin.scad>
include <gridfinity-rebuilt-openscad/src/core/standard.scad>
$fn = 96;
PART = "plate";
HU = 2;  top = HU * 7;
seat_d = 36;  seat_dep = 3;
pin_b = 6.0;  pin_t = 5.0;  pin_h = 10;

module diamond(p) { translate([p[0], p[1], top - 0.01]) hull() {
  linear_extrude(0.01) rotate(45) square(8, center = true);
  translate([0, 0, 1.2]) linear_extrude(0.01) rotate(45) square(3, center = true); } }

module toothbrush_bin() {
  bin_render(new_bin([2, 2], top, include_lip = false)) {
    translate([0, 0, -seat_dep]) cylinder(d1 = seat_d, d2 = seat_d + 3, h = seat_dep + 0.02);
    translate([0, 0, -seat_dep - 1.5]) difference() { cylinder(d = seat_d, h = 2); cylinder(d = seat_d - 6, h = 2); }
  }
  translate([0, 0, top - seat_dep - 0.01]) {
    cylinder(d1 = pin_b + 3, d2 = pin_b, h = 1.5);
    cylinder(d1 = pin_b, d2 = pin_t, h = pin_h - 1.2);
    translate([0, 0, pin_h - 1.2]) cylinder(d1 = pin_t, d2 = pin_t - 1.6, h = 1.2);
  }
  for (a = [0 : 60 : 359]) rotate(a + 30) translate([5, -0.8, top - seat_dep - 0.01])   // drying ribs: handle sits 1 mm up
    hull() { cube([9.5, 1.6, 1]); translate([0, 0.3, 0]) cube([9.5, 1, 1.1]); }
  for (a = [0 : 10 : 359]) rotate(a) translate([seat_d / 2 + 6, 0, top]) scale([1, 1, 0.7]) sphere(d = 3, $fn = 16);
  for (a = [0 : 90 : 359]) rotate(a + 45) diamond([40, 0]);
}

// toothpaste: funnel oval scale ky, rim at top + col_h
ky = 0.62;  col_h = 24;  f_dep = 24;   // pocket floor = bin top, so the drain slot runs out
module oval(w, d, z) { translate([0, 0, z]) scale([1, d / w, 1]) cylinder(d = w, h = 0.01); }
module funnel() {   // cap pocket: Colgate Total stand-up cap ~31 wide x ~22 tall (scaled from the product photo,
                    // tube seal ~50 mm); depth front-back unknown -> gentle taper fits 20..27
  z0 = top + col_h - f_dep;
  hull() { oval(32, 20, z0); oval(36, 27, z0 + 18); }
  hull() { oval(36, 27, z0 + 18); oval(42, 33, top + col_h + 0.01); }   // lead-in flare
}
module collar() {   // waisted oval chalice round the cap pocket, max 41 wide (grid cell 41.5)
  hull() { oval(60, 41, top - 0.01); oval(50, 37, top + 9); }
  hull() { oval(50, 37, top + 9); oval(52, 41, top + col_h - 0.01); }
}
module paste_bin() {
  difference() {
    union() {
      bin_render(new_bin([2, 1], top, include_lip = false));
      collar();
      for (a = [0 : 12 : 359]) translate([cos(a) * 24.4, sin(a) * 19.2, top + col_h - 2.6])  // beads
        scale([1, 1, 0.8]) sphere(d = 2.4, $fn = 12);
    }
    funnel();
    translate([-36, -3.5, top + 0.01]) cube([20, 7, 5]);   // low drain slot at the narrow end (wall above still holds the cap)
  }
  for (x = [-1, 1]) diamond([x * 35.5, 0]);
}

if (PART == "toothbrush") toothbrush_bin();
else if (PART == "paste") paste_bin();
else { translate([0, 22, 0]) toothbrush_bin(); translate([0, -45, 0]) paste_bin(); }
