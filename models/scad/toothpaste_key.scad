// Steampunk toothpaste key (2026-11-12, V2 built in). One piece, no supports, prints standing.
// Push the flat crimped end of the tube through the slot, twist the cog: the tube rolls up on the
// hex shaft and squeezes paste forward. Stands on its cog on the sink.
// - Slot 2.6 x 62 mm: fits crimp ends up to ~60 mm (most 75-170 ml tubes are 45-58 mm).
// - Strength first: 14 mm hex, 7 mm solid ends + pointed slot ends (no stress corners), tall hub
//   cone into a 5 mm cog, walls 4. Torsion of a full tube roll is far below PETG layer strength.
// - Shaft halves joined at both ends; inner slot edges chamfered so the crimp starts easily.
// - Cog: 12 teeth = finger grip, spoked with round lightening holes; 10 rivets on the rim bead.
// - Top: hex-nut cap with a 45 deg underside (prints without supports), rivet ring.
//   p3d slice toothpaste_key.stl --walls 4 --infill 40 --keep-orient
$fn = 48;
slot_l = 62;     // slot length (tube crimp width)
slot_w = 2.6;
af     = 14;     // shaft hex across flats
cog_d  = 42;  cog_t = 5;  teeth = 12;
cap_af = 20;  cap_t = 6;
end    = 7;      // solid shaft above/below the slot (torsion goes through these layers)
shaft_h = slot_l + 2 * end + 3;   // +3 = hub cone

module hex(af, h) cylinder(d = af / cos(30), h = h, $fn = 6);

module cog2d() {
  difference() {
    union() {
      circle(d = cog_d - 5);
      for (i = [0 : teeth - 1]) rotate(i * 360 / teeth)
        hull() { translate([cog_d / 2 - 4, 0]) square([0.1, 6], center = true);
                 translate([cog_d / 2 - 1, 0]) square([2, 4.2], center = true); }
    }
    // spokes: 5 round holes between hub and rim
    for (i = [0 : 4]) rotate(i * 72 + 36) translate([cog_d * 0.29, 0]) circle(d = 7.5);
  }
}

module key() {
  difference() {
    union() {
      linear_extrude(cog_t) cog2d();
      // rim bead + hub boss
      translate([0, 0, cog_t]) difference() {
        cylinder(d = cog_d - 5, h = 0.8); translate([0, 0, -1]) cylinder(d = cog_d - 8, h = 3);
      }
      translate([0, 0, cog_t]) cylinder(d1 = af / cos(30) + 10, d2 = af / cos(30), h = 5);
      // rivets on the rim bead (solid ring outside the spoke holes, never over air)
      for (i = [0 : 9]) rotate(i * 36) translate([(cog_d - 6.5) / 2, 0, cog_t + 0.8]) sphere(d = 2.2, $fn = 16);
      // shaft
      hex(af, cog_t + shaft_h);
      // hex-nut cap, 45 deg underside
      translate([0, 0, cog_t + shaft_h]) {
        hull() { hex(af, 0.01); translate([0, 0, (cap_af - af) / 2]) hex(cap_af, cap_t - (cap_af - af) / 2); }
      }
      // rivet ring on the cap
      translate([0, 0, cog_t + shaft_h + cap_t]) for (i = [0 : 5]) rotate(i * 60) translate([cap_af * 0.34, 0, 0]) sphere(d = 2, $fn = 16);
    }
    // slot through the shaft (runs flat-to-flat), chamfered entry both sides
    translate([0, 0, cog_t + 3 + end + slot_l / 2]) {
      // slot with 45-deg pointed ends: no flat bridge on top, no sharp stress corners
      hull() for (z = [-1, 1]) translate([0, 0, z * (slot_l / 2 - slot_w / 2)])
        rotate([90, 0, 0]) rotate([0, 0, 45]) cube([slot_w / sqrt(2), slot_w / sqrt(2), af + 6], center = true);
      for (s = [-1, 1]) translate([0, s * af / 2, 0]) rotate([0, 0, 45]) cube([1.6, 1.6, slot_l], center = true);
    }
    // centre bore through cap: see-through "axle" look, saves plastic
    translate([0, 0, cog_t + shaft_h - 0.01]) cylinder(d = 5, h = cap_t + 1);
  }
}

key();
