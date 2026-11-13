// Sonicare toothbrush stand (2026-11-12). Stands the handle upright on a centre pin, like the charger.
// Pin from the HX6100 charger size used by published Sonicare stands: Ø5.8 mm (Thingiverse 5192550).
// Not measured on the actual brush: pin tapers 6.0 -> 5.0 so it self-centres in a slightly off hole;
// handle sits in a loose Ø36 seat (Sonicare handle base ~30 x 27 mm) with a chamfered lead-in.
// - Ornate plinth matching the pepper shaker: stepped diamond band, bead lines, fluted skirt.
// - Drip moat around the seat catches drips off the handle (wipe out).
// - Ø76 base = tips past ~20 deg with the brush in; 40 % infill for weight.
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
