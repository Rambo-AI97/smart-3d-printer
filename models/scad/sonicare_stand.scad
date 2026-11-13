// Sonicare toothbrush stand (2026-11-12). Stands the handle upright on a centre pin, like the charger.
// Pin from the HX6100 charger size used by published Sonicare stands: Ø5.8 mm (Thingiverse 5192550).
// Not measured on the actual brush: pin tapers 6.0 -> 5.0 so it self-centres in a slightly off hole;
// handle sits in a loose Ø36 seat (Sonicare handle base ~30 x 27 mm) with a chamfered lead-in.
// - Ornate plinth matching the pepper shaker: stepped diamond band, bead lines, fluted skirt.
// - Drip moat around the seat catches drips off the handle (wipe out).
// - Ø76 base = tips past ~20 deg with the brush in; 40 % infill for weight.
// + Toothpaste cup (2026-11-12): the tube stands upside down on its flip cap in a tapered oval funnel
//   (no cap size published: the cone holds any cap/shoulder 22x34 .. 38x58 mm and centres it), 24 deep,
//   on a fluted chalice with the same diamond band + beads, joined to the brush plinth by a low bridge.
// Prints flat, no supports.  p3d make sonicare_stand --walls 4 --infill 40
$fn = 96;
D = 76;  H = 16;
seat_d = 36;  seat_dep = 3;
pin_b = 6.0;  pin_t = 5.0;  pin_h = 10;

module body() {
  rotate_extrude() polygon([[0, 0], [D / 2, 0], [D / 2, 2], [D / 2 - 2, 4], [D / 2 - 2, 7], [D / 2 - 6, 10],
                            [D / 2 - 8, 13], [seat_d / 2 + 6, H], [0, H]]);
  for (a = [0 : 15 : 359]) rotate(a) translate([D / 2 - 0.9, 0, 0.6]) cylinder(d = 2.4, h = 1.6, $fn = 16);   // flutes
  for (a = [0 : 8 : 359]) rotate(a) translate([D / 2 - 5.5, 0, 10.5]) sphere(d = 2.6, $fn = 12);        // beads
  for (a = [0 : 30 : 359]) rotate(a + 15) translate([D / 2 - 3.2, 0, 5.5])                             // diamonds on the band
    rotate([0, 90, 0]) rotate(45) cube([4.6, 4.6, 2.6], center = true);
}
PASTE = true;
px = 64;   // cup centre
module brush() {
difference() {
  body();
  translate([0, 0, H - seat_dep]) cylinder(d1 = seat_d, d2 = seat_d + 3, h = seat_dep + 0.01);          // seat
  translate([0, 0, H - seat_dep - 1.5]) difference() { cylinder(d = seat_d, h = 2); cylinder(d = seat_d - 6, h = 2); } // moat
}
translate([0, 0, H - seat_dep - 0.01]) {
  cylinder(d1 = pin_b + 3, d2 = pin_b, h = 1.5);                         // root fillet
  cylinder(d1 = pin_b, d2 = pin_t, h = pin_h - 1.2);
  translate([0, 0, pin_h - 1.2]) cylinder(d1 = pin_t, d2 = pin_t - 1.6, h = 1.2);   // rounded-ish tip
}
}

// ---- toothpaste cup (oval: profile scaled 0.72 in y) ----
cH = 34;  cR = 33;  ky = 0.72;
module cup() {
  scale([1, ky, 1]) {
    rotate_extrude() polygon([[0, 0], [cR, 0], [cR, 2], [cR - 2, 4], [cR - 3, 10], [cR - 5, 16], [cR - 4, 22],
                              [cR - 1.5, 29], [cR - 1, 31], [cR - 2.5, cH], [0, cH]]);
    for (a = [0 : 15 : 359]) rotate(a) translate([cR - 2.6, 0, 4.5]) cylinder(d = 2.4, h = 5, $fn = 16);       // flutes
    for (a = [0 : 30 : 359]) rotate(a + 15) translate([cR - 4.6, 0, 19]) rotate([0, 90, 0]) rotate(45)       // diamonds
      cube([4.6, 4.6, 2.6], center = true);
  }
  for (a = [0 : 9 : 359]) translate([cos(a) * (cR - 1.4), sin(a) * (cR - 1.4) * ky, 30]) sphere(d = 2.4, $fn = 12); // beads
}
module funnel() {   // tapered oval: 22 x 34 at the floor, 40 x 60 at the rim
  translate([0, 0, cH - 24]) scale([1, 0.66, 1]) cylinder(d1 = 34, d2 = 58, h = 24.01);
  translate([0, 0, cH - 1.5]) scale([1, 0.66, 1]) cylinder(d1 = 58, d2 = 61, h = 1.51);   // soft lip
}
brush();
if (PASTE) {
  difference() {
    union() {
      translate([px, 0, 0]) cup();
      hull() { cylinder(d = 56, h = 6); translate([px, 0, 0]) scale([1, ky, 1]) cylinder(r = cR - 6, h = 6); }  // bridge
    }
    translate([px, 0, 0]) funnel();
    translate([0, 0, H - seat_dep - 1.5]) cylinder(d = seat_d, h = 20);   // keep the brush seat + moat clear
  }
}
