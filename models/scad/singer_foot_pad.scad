// Singer 4432 base foot pad (2026-11-12). Replaces 1 of the 4 screwed-on clear pads; no screw on hand.
// Measured: pad 12.5 mm dia, screw hole ~6 mm deep (a bit less). Pad height = PLACEHOLDER until
// a remaining pad's height (how far it sticks out of the base) is measured; it must match or the machine rocks.
// - Instead of the screw: tapered pin with 6 crush ribs, 3.4 -> 2.2 mm, 5.5 mm long. Press in by hand;
//   the ribs shave to fit any small screw hole. Loose? one drop of super glue on the pin.
// - Table face: ring grooves (PETG slides more than rubber; a felt/rubber dot sticks on well).
// Prints table-face DOWN, pin up, no supports.
//   p3d make singer_foot_pad --walls 3 --infill 100
$fn = 64;
D     = 12.5;   // pad diameter (measured)
H     = 4;      // pad height: MEASURE a remaining pad
pin_l = 5.5;    // screw hole depth ~6, a bit less
pin_b = 3.4;    // pin base diameter (ribs reach +0.5)
pin_t = 2.2;    // pin tip diameter
ch    = 0.6;    // edge chamfer

module pad() {
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

pad();
