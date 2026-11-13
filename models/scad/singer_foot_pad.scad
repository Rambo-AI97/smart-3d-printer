// Singer 4432 base foot pad V2 (2026-11-12 evening). V1 printed: sat too low + pin fell out of the hole.
// RESULT 2026-11-12: pad #1 fits (6 mm tall, pin 4.2). Default now prints that one pad; -D set=1 for the test set.
// V3 test set: heights 6/8/10 mm paired with pins 4.2/4.7/5.2 (1/2/3 dots) - one print tests both.
// V2: pad 4 mm taller (8 mm) and a fit SET of 3 pads with fatter pins (4.2 / 4.7 / 5.2 mm base, labelled 1-3 dots
// on the side). Press each in: keep the tightest one that goes in fully, re-print that size if wanted.
// Original header:
// Replaces 1 of the 4 screwed-on clear pads; no screw on hand.
// Measured: pad 12.5 mm dia, screw hole ~6 mm deep (a bit less). Pad height = PLACEHOLDER until
// a remaining pad's height (how far it sticks out of the base) is measured; it must match or the machine rocks.
// - Instead of the screw: tapered pin with 6 crush ribs, 3.4 -> 2.2 mm, 5.5 mm long. Press in by hand;
//   the ribs shave to fit any small screw hole. Loose? one drop of super glue on the pin.
// - Table face: ring grooves (PETG slides more than rubber; a felt/rubber dot sticks on well).
// Prints table-face DOWN, pin up, no supports.
//   p3d make singer_foot_pad --walls 3 --infill 100
$fn = 64;
D     = 12.5;   // pad diameter (measured)
hts   = [6, 8, 10];  // V1 4 mm sat too low; test set steps 2 mm (2026-11-12)
pin_l = 5.5;    // screw hole depth ~6, a bit less
pins  = [4.2, 4.7, 5.2]; // V1 3.4 fell out. base diameters; ribs reach +0.5, tip = base - 1.0
ch    = 0.6;    // edge chamfer

module pad(pin_b, n, H) {
  pin_t = pin_b - 1.0;
  difference() {
    union() {
      hull() { cylinder(d = D - 2 * ch, h = 0.01); translate([0, 0, ch]) cylinder(d = D, h = H - 2 * ch);
               translate([0, 0, H - 0.01]) cylinder(d = D - 2 * ch, h = 0.01); }
      translate([0, 0, H - 0.01]) {
        cylinder(d1 = pin_b, d2 = pin_t, h = pin_l);
        for (i = [0 : 5]) rotate(i * 60)          // crush ribs
          hull() { translate([pin_b / 2, 0, 0]) cylinder(d = 0.9, h = 0.01, $fn = 12);
                   translate([pin_t / 2, 0, pin_l - 0.8]) cylinder(d = 0.6, h = 0.01, $fn = 12); }
      }
    }
    // grip rings on the table face
    for (r = [D * 0.18, D * 0.33]) difference() { translate([0, 0, -1]) cylinder(r = r + 0.4, h = 1.4);
                                                  translate([0, 0, -2]) cylinder(r = r - 0.4, h = 3); }
  }
}

set = 0;
if (!set) pad(4.2, 1, 6);
else for (i = [0 : 2]) translate([i * (D + 6), 0, 0]) pad(pins[i], i + 1, hts[i]);
