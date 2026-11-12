// Singer 4432 base foot pad (2026-11-12). Replaces 1 of the 4 rubber cushions (Singer F31103000?).
// !! DIMENSIONS ARE PLACEHOLDERS (common Singer pad ~16 mm dia). Measure a remaining pad and set
// D, H, stem_d, stem_l before printing. stem_l = 0 -> flat pad to glue/double-tape into the recess.
// - Table face has ring grooves (less sliding than flat PETG; add a felt/rubber dot for more grip).
// - Push-in stem with a 45 deg barb that snaps into the base hole; split so it squeezes in.
// Prints table-face DOWN (flat, true, no supports).
//   p3d slice singer_foot_pad.stl --walls 3 --infill 100 --keep-orient
$fn = 64;
D      = 16;    // pad diameter
H      = 7;     // pad height (how far the machine is lifted)
stem_d = 6;     // stem diameter = base hole diameter - 0.2
stem_l = 6;     // stem length (0 = no stem)
barb   = 0.7;   // barb overhang per side
ch     = 0.8;   // edge chamfer

module pad() {
  difference() {
    union() {
      hull() { cylinder(d = D - 2 * ch, h = 0.01); translate([0, 0, ch]) cylinder(d = D, h = H - 2 * ch);
               translate([0, 0, H - 0.01]) cylinder(d = D - 2 * ch, h = 0.01); }
      if (stem_l > 0) translate([0, 0, H - 0.01]) {
        cylinder(d = stem_d, h = stem_l);
        // barb: widens 45 deg, then 45 deg back (printable both ways)
        translate([0, 0, stem_l - 2 * barb - 1]) {
          cylinder(d1 = stem_d, d2 = stem_d + 2 * barb, h = barb);
          translate([0, 0, barb]) cylinder(d1 = stem_d + 2 * barb, d2 = stem_d - 0.4, h = barb + 1);
        }
      }
    }
    // grip rings on the table face
    for (r = [D * 0.18, D * 0.33]) difference() { translate([0, 0, -1]) cylinder(r = r + 0.4, h = 1.4);
                                                  translate([0, 0, -2]) cylinder(r = r - 0.4, h = 3); }
    // slit so the barbed stem squeezes into the hole
    if (stem_l > 0) translate([0, 0, H + 1.5 + stem_l / 2]) cube([1.2, stem_d + 3, stem_l], center = true);
  }
}

pad();
