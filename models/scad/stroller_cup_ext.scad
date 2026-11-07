// Tall-bottle extension for the stroller cup holder (stroller_cup.scad), 2026-11-07.
// A collar that slides over the cup's rim and rests on it, adding ext_h of height so tall
// bottles don't tip out. No hardware: gravity + a snug slip fit. Lift off to use mugs again.
// Prints upright, no supports: the inner ledge is a 45 deg cone, the outer step goes inward.
// Export: p3d scad stroller_cup_ext
part = "print";       // "print" | "assembly" (with the cup, to check the fit)

cup_id   = 77;        // must match stroller_cup.scad
cup_wall = 3.2;
cup_od   = cup_id + 2 * cup_wall;   // 83.4
fit      = 0.5;       // clearance per side over the cup wall (PETG prints slightly tight)
overlap  = 15;        // how far the collar slides down over the cup
wall     = 2.4;       // collar wall (6 lines)
ext_h    = 50;        // added height above the cup rim
rib_w    = 30 + 2;    // notch for the cup's back rib to the clip (clip_len 30 + clearance)
$fn = 120;

sleeve_id = cup_od + 2 * fit;          // 84.4
sleeve_od = sleeve_id + 2 * wall;      // 89.2
ledge     = (sleeve_id - cup_id) / 2;  // 3.7 mm: rests on the cup rim
top_od    = cup_od;                    // flush with the cup below

module collar() {
  difference() {
    union() {
      cylinder(h = overlap, d = sleeve_od);                                   // sleeve over the cup
      translate([0, 0, overlap]) cylinder(h = ledge, d1 = sleeve_od, d2 = top_od);   // outer taper
      translate([0, 0, overlap]) cylinder(h = ext_h, d = top_od);             // extension wall
    }
    translate([0, 0, -0.01]) cylinder(h = overlap + 0.02, d = sleeve_id);       // fits over the cup
    translate([0, 0, overlap]) cylinder(h = ledge + 0.01, d1 = sleeve_id, d2 = cup_id);  // 45 deg ledge
    translate([0, 0, overlap]) cylinder(h = ext_h + 1, d = cup_id);           // bottle space
    // notch for the rib that joins the cup to the clip (back side, -Y)
    translate([-rib_w / 2, -sleeve_od / 2 - 1, -0.01]) cube([rib_w, sleeve_od / 2 - cup_id / 2 + 1, overlap + 0.02]);
    // soft top edge
    translate([0, 0, overlap + ext_h - 1.5]) cylinder(h = 1.51, d1 = cup_id, d2 = cup_id + 2);
  }
}

if (part == "assembly") {
  // cup rim at z=0 in stroller_cup.scad; its centre is at y=cup_y there, here at the origin
  color("tan") translate([0, 0, -overlap]) collar();
  translate([0, 0, -65]) difference() { cylinder(h = 65, d = cup_od); translate([0, 0, 3]) cylinder(h = 65, d = cup_id); }
} else {
  collar();
}
