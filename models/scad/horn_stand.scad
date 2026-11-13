// Organic phone stand with a passive horn amplifier (2026-11-12).
// The phone stands portrait, leaning back 20 deg. Its bottom speaker (Nothing Phone 3: right of the USB-C port,
// seen from the front) fires straight into the horn throat, which spans the whole right half of the bottom
// edge so the exact grille position doesn't matter. The horn bends down, then forward and up, flaring
// ~4.5x in area to a teardrop mouth under the screen: sound comes out towards you instead of sideways.
// Research (Printables 172781 folded horn, 740888, MakerWorld long-taper stands): longer taper = more gain,
// seal the phone edge in the throat, no supports inside the horn (they can't be cleaned out).
// - Slot 80 x 12 (Nothing Phone 3 160.6 x 75.6 x 9.0 + case), 14 deep; phone rests on the left floor + right ledge.
// - Horn cross-sections are teardrops with the point UP: every roof is <= 45 deg, prints without supports.
// - Smooth pebble body (hull of ellipsoids), slim leaf back rest; phone weight sits over the rear foot.
// Prints upright, no supports.  p3d make horn_stand --infill 10
$fn = 64;
zb = 44;            // phone bottom edge height
lean = 20;
slot_w = 80;  slot_t = 12;  slot_dep = 14;
wall = 2.4;

// [y, dz, theta, w, h, apex 0..1, xc]  (theta: section normal = (0,-sin,cos) -> tangent of the horn path)
ST = [
  [  0,   0.5, 160, 30, 11, 0,   21],    // throat under the right half of the phone's bottom edge
  [ -4,  -11,  158, 31, 12, 0,   19],
  [-10,  -23,  140, 33, 13, 0.4, 15],
  [-21,  -31,  105, 36, 14, 0.9,  9],
  [-35,  -31,   80, 40, 16, 1,    4],
  [-50,  -26,   65, 46, 19, 1,    0],    // mouth
  [-62,  -19,   65, 52, 22, 1,    0]];   // past the mouth (cuts it open)

module sec(w, h, k) {
  r = min(w, h) / 2 * 0.9;
  hull() {
    offset(r = r) square([w - 2 * r, h - 2 * r], center = true);
    if (k > 0) translate([0, (h / 2 - r) + k * ((w / 2 - r) + r * 1.414)]) circle(r = 0.4, $fn = 8);
  }
}
module station(s) {
  translate([s[6], s[0], zb + s[1]]) rotate([s[2], 0, 0]) linear_extrude(0.02, center = true) sec(s[3], s[4], s[5]);
}
module horn() { for (i = [0 : len(ST) - 2]) hull() { station(ST[i]); station(ST[i + 1]); } }

module phone() {    // phone slab: bottom edge centred at y=0, z=zb, leaning back
  translate([0, 0, zb]) rotate([-lean, 0, 0]) translate([-slot_w / 2, -slot_t / 2, 0]) cube([slot_w, slot_t, 200]);
}
module along(s, t) { translate([0, 0, zb]) rotate([-lean, 0, 0]) translate([0, t, s]) children(); }
module blob(c, r) { translate(c) scale(r) sphere(r = 1); }

module body() {
  hull() {                                   // the pebble
    for (x = [-1, 1]) along(4, 0) translate([x * 37, 0, 0]) scale([1, 0.95, 1.15]) sphere(r = 12);   // phone cradle
    blob([0, -36, 12], [31, 26, 28]);        // front, round the horn mouth
    blob([0, 30, 8], [36, 22, 14]);          // rear foot
  }
  hull() {                                   // leaf back rest rising behind the phone
    for (x = [-1, 1]) along(2, slot_t / 2 + 4) translate([x * 30, 0, 0]) scale([1, 0.6, 1.2]) sphere(r = 10);
    along(40, slot_t / 2 + 3.5) scale([24, 3.5, 10]) sphere(r = 1);
    along(66, slot_t / 2 + 2.4) scale([15, 2.4, 8]) sphere(r = 1);   // petal tip
  }
}

intersection() {
  translate([-150, -150, 0]) cube(300);       // flat on the bed
  difference() {
    body();
    horn();
    phone();
    translate([0, ST[5][0], zb + ST[5][1]]) rotate([ST[5][2], 0, 0]) translate([-100, -100, 0]) cube(200);  // flat cut face at the mouth
    along(slot_dep - 2, 0) hull() {           // lead-in chamfer at the slot mouth
      translate([-slot_w / 2, -slot_t / 2, 0]) cube([slot_w, slot_t, 0.01]);
      translate([-slot_w / 2 - 2.5, -slot_t / 2 - 2.5, 4]) cube([slot_w + 5, slot_t + 5, 0.01]);
    }
  }
}
