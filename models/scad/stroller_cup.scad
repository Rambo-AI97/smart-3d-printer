// Stroller cup holder (2026-11-06). Two parts, no hardware:
//   clip: snaps on the handlebar (fit test: 32-33 mm clips fit the foam bar)
//   cup:  hangs from the clip by a dovetail; the slot is closed at the top, so the
//         cup's own weight seats it. Lower the cup onto the clip; lift to remove.
// Strength: the clip prints FLAT (layers run around the ring, not across it).
// Coordinates as installed: bar along X, cup on +Y side (seat side), Z up, bar centre at 0.
// Export: openscad -D 'part="print"' -o stroller_cup.stl stroller_cup.scad
part = "print";       // "print" (both, laid out for printing) | "clip" | "cup" | "assembly"

bar_d    = 32;        // clip inner diameter (fit test 2026-11-06: 32 and 33 fit; 32 grips foam harder)
clip_w   = 3.2;       // ring wall (8 lines)
clip_len = 30;        // along the bar
rib_h    = 1.5;       // grip ribs: how far they press into the foam
gap_frac = 0.68;      // snap opening (test clips used 0.72 with a thinner wall)
cup_id   = 77;        // 73 mm bottle/mug + 4 mm clearance
cup_wall = 3.2;
cup_h    = 65;
slot_w   = 24;        // front slot for a mug handle (0 = none)
fit      = 0.3;       // dovetail clearance per side
$fn = 120;

r_in  = bar_d / 2;
r_out = r_in + clip_w;
plate_y = 24;                 // plate face (cup side)
tongue  = [12, 18, 6];        // neck width, wide width, depth
t_top = -9; t_bot = -45;      // 9 mm solid roof over the slot carries the cup      // tongue z range
plate_bot = -48;

module dovetail(neck, wide, depth, h) {   // trapezoid in XY, extruded along Z
  linear_extrude(h) polygon([[-neck/2, 0], [neck/2, 0], [wide/2, depth], [-wide/2, depth]]);
}

module clip() {
  difference() {
    union() {
      rotate([0, 90, 0]) cylinder(h = clip_len, r = r_out, center = true);
      translate([-clip_len/2, r_in, plate_bot]) cube([clip_len, plate_y - r_in, -plate_bot]);  // plate
      translate([0, plate_y, t_bot]) dovetail(tongue[0], tongue[1], tongue[2], t_top - t_bot);
    }
    rotate([0, 90, 0]) cylinder(h = clip_len + 2, r = r_in, center = true);
    // snap opening on top
    translate([-clip_len, -gap_frac * bar_d / 2, 0]) cube([2 * clip_len, gap_frac * bar_d, r_out + 1]);
    // zip-tie groove (optional extra squeeze on the foam)
    rotate([0, 90, 0]) difference() { cylinder(h = 5, r = r_out + 1, center = true); cylinder(h = 6, r = r_out - 0.8, center = true); }
  }
  // grip ribs that press into the foam (stop the cup swinging round the bar)
  // rounded ribs, rib_h into the foam (2026-11-06 test: thick ribs fit the bar very well)
  for (a = [110, 145, 180, 215, 250]) rotate([a, 0, 0]) translate([0, 0, r_in - rib_h + 1.2])
    rotate([0, 90, 0]) cylinder(h = clip_len, r = 1.2, center = true, $fn = 24);
  for (a = [110, 145, 180, 215, 250]) rotate([a, 0, 0]) translate([-clip_len/2, -1.2, r_in - rib_h + 1.2])
    cube([clip_len, 2.4, rib_h - 0.2]);
}

cup_y = plate_y + fit + tongue[2] + 3 + cup_id/2 + cup_wall - 2;   // cup centre
module cup() {
  difference() {
    union() {
      translate([0, cup_y, -cup_h]) cylinder(h = cup_h, r = cup_id/2 + cup_wall);
      translate([-clip_len/2, plate_y + fit, plate_bot]) cube([clip_len, cup_y - plate_y - cup_id/2, -plate_bot]);  // rib
    }
    translate([0, cup_y, -cup_h + 3]) cylinder(h = cup_h, r = cup_id/2);
    translate([0, cup_y, -1.99]) cylinder(h = 2, r1 = cup_id/2, r2 = cup_id/2 + 1.5);         // rim chamfer
    translate([0, cup_y, -cup_h - 1]) cylinder(h = 5, r = 14);                                 // drain
    if (slot_w > 0) translate([-slot_w/2, cup_y, -cup_h + 20]) cube([slot_w, cup_id, cup_h]);   // handle slot
    // dovetail slot: open at the bottom, closed ~9 mm below the rim
    translate([0, plate_y + fit - 0.01, plate_bot - 1])
      dovetail(tongue[0] + 2*fit, tongue[1] + 2*fit, tongue[2] + fit, (t_top + fit) - plate_bot + 1);
  }
}

if (part == "clip") clip();
else if (part == "cup") cup();
else if (part == "assembly") { color("tan") clip(); cup(); }
else {  // print layout: clip flat (bar axis vertical), cup upright
  translate([-70, 0, clip_len/2]) rotate([0, -90, 0]) rotate([0, 0, 0]) clip();
  translate([40, -cup_y + 0, cup_h]) cup();
}
