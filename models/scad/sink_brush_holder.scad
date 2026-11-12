// Dish brush holder that sits on a sink divider/rim (2 in = 50.8 mm wide).
// The brush hangs head-down over the basin: slide the 13 mm neck in through the
// snap mouth (clicks past 12.4 mm), it drops until the handle's taper wedges.
// Prints UPSIDE DOWN (the top face on the bed, legs up): no supports.
// part = "print" (default) | "use" (flipped, with a ghost rim and brush).
part = "print";

rim   = 50.8;   // sink divider / rim width
gap   = rim + 1.0;
t     = 5;      // leg wall
tp    = 5;      // top plate
L     = 22;     // leg depth below the top plate
D     = 38;     // length along the rim
reach = 38;     // leg outer face -> slot centre (brush head ~50 mm clears the wall)
disc  = 48;     // ring plate around the slot
slot  = 15.5;   // slot (neck 13 mm, handle widens above)
mouth = 13.8;   // mouth: the 13 mm neck slides in, the handle taper wedges it
bump  = 0.7;    // grip bead on each leg tip
deb   = 0.6;    // debossed ornament depth (bed face, reads on top in use)
$fn = 96;

xo = gap / 2 + t;           // outer leg face
xc = xo + reach;            // slot centre

module lens(c1, c2, R) intersection() { translate(c1) circle(R); translate(c2) circle(R); }
module triquetra(d, w) {
  R = d / 2 / 1.155; c = [for (k = [0:2]) R / sqrt(3) * [cos(90 + 120 * k), sin(90 + 120 * k)]];
  for (k = [0:2]) difference() { lens(c[k], c[(k + 1) % 3], R); offset(-w) lens(c[k], c[(k + 1) % 3], R); }
  difference() { circle(d = d * 0.62); circle(d = d * 0.62 - 2 * w); }
}
module ring2d(d, w) difference() { circle(d = d); circle(d = d - 2 * w); }

// top outline: saddle + teardrop arm into the ring plate
module outline() hull() {
  offset(4) square([2 * xo - 8, D - 8], center = true);
  translate([xc, 0]) circle(d = disc);
}
module slot2d() {
  translate([xc, 0]) circle(d = slot);
  translate([xc, -mouth / 2]) square([disc, mouth]);
  // lead-in funnel at the outer edge
  translate([xc + disc / 2, 0]) rotate(45) square(12, center = true);
}

module body() difference() {
  union() {
    linear_extrude(tp) outline();
    // legs (point up while printing)
    for (s = [-1, 1]) translate([s * (gap / 2 + t / 2), 0, 0]) {
      hull() {
        translate([-t / 2, -D / 2 + 4, 0]) cube([t, D - 8, tp + L - 2]);
        for (j = [-1, 1]) translate([0, j * (D / 2 - 4), 0]) cylinder(d = t, h = tp + L - 2);
        translate([0, 0, tp + L - 2]) rotate([90, 0, 0]) cylinder(d = t, h = D - 8, center = true);
      }
      // grip bead on the inner face of the leg tip
      translate([-s * t / 2, 0, tp + L - 4]) rotate([90, 0, 0]) cylinder(r = bump + 0.6, h = D - 10, center = true, $fn = 24);
    }
  }
  // brush slot with snap mouth
  translate([0, 0, -1]) linear_extrude(tp + 2) slot2d();
  // ornaments, debossed into the bed face (= the top in use)
  translate([0, 0, -1]) linear_extrude(1 + deb) {
    triquetra(26, 1.6);
    translate([xc, 0]) difference() { ring2d(disc - 5, 1.2); slot2d(); offset(1.5) slot2d(); }
    offset(-2.2) difference() { offset(-0.1) outline(); offset(-1.3) outline(); }
  }
  // keep the inner gap clean (bead only sticks out bump mm)
  translate([-gap / 2 + bump, -D, tp + 0.01]) cube([gap - 2 * bump, 2 * D, L + 1]);
}

if (part == "use") {
  rotate([180, 0, 0]) body();
  %translate([-rim / 2, -60, -tp - 60]) cube([rim, 120, 60]);                       // sink divider
  %translate([xc, 0, -70]) { cylinder(d = 13, h = 60); translate([0, 0, -30]) cylinder(d = 50, h = 30); cylinder(d1 = 13, d2 = 28, h = 140); }
} else body();
