// Cable clip set, one plate. All print flat, no supports.
//  A  single snap clip (stick on with tape): holds a cable / keeps a plug end on the table
//  B  double snap clip: two cords side by side (bedside table)
//  C  screw clip: one cable, one screw (under a desk, on a wall)
//  D  reusable cable tie: tail with teeth through the head slot; squeeze teeth to release
cable_d = 4.2;     // USB-C / phone-charger cable ~3.5-4 mm
ring    = 1.8;     // ring wall
open_f  = 0.72;    // snap opening as a fraction of cable_d
clip_w  = 10;      // clip length along the cable
base_t  = 2.5;
$fn = 48;
layout  = "plate";   // "plate" | "A" | "B" | "C" | "D" (one piece)

module snap2d(d = cable_d) {     // ring sitting on y = 0, opening at the top
  ro = d / 2 + ring;
  translate([0, base_t + d / 2 - 0.4]) difference() {
    circle(ro);
    circle(d / 2);
    translate([-d * open_f / 2, 0]) square([d * open_f, ro + 1]);
  }
}
module clipA() linear_extrude(clip_w) {
  translate([-9, 0]) square([18, base_t]);
  snap2d();
}
module clipB() linear_extrude(clip_w) {
  p = cable_d + 2 * ring + 1;
  translate([-p / 2 - 9, 0]) square([p + 18, base_t]);
  for (s = [-1, 1]) translate([s * p / 2, 0]) snap2d();
}
module clipC() difference() {
  linear_extrude(clip_w) {
    translate([-5, 0]) square([22, base_t]);
    snap2d();
  }
  // screw hole through the tab (for ~3.5 mm screws), with a countersink
  translate([11, -1, clip_w / 2]) rotate([-90, 0, 0]) {
    cylinder(d = 3.8, h = 10);
    translate([0, 0, base_t + 1 - 1.6]) cylinder(d1 = 3.8, d2 = 7.5, h = 1.61);
  }
}
module tieD(len = 120) {
  t = 1.4;  tail_w = 6;  tooth = 0.8;
  linear_extrude(t) {
    difference() {
      translate([-6, -12]) offset(2) offset(-2) square([12, 14]);
      translate([-(tail_w + 0.7) / 2, -7]) square([tail_w + 0.7, 2.2]);   // head slot
    }
    translate([-tail_w / 2, 0]) square([tail_w, len - 16]);
    for (y = [12 : 3.2 : len - 22]) translate([0, y])
      polygon([[-tail_w / 2, 0], [-tail_w / 2 - tooth, 2.4], [-tail_w / 2, 2.4],
               [tail_w / 2, 2.4], [tail_w / 2 + tooth, 2.4], [tail_w / 2, 0]]);
    translate([0, len - 16]) polygon([[-tail_w / 2, 0], [tail_w / 2, 0], [1, 10], [-1, 10]]);   // tip
  }
}

if (layout == "A") clipA();
else if (layout == "B") clipB();
else if (layout == "C") clipC();
else if (layout == "D") tieD();
else {   // plate: 3 x A, 3 x B, 4 x C, 4 x D
  for (i = [0 : 2]) translate([i * 24, 0, 0]) clipA();
  for (i = [0 : 2]) translate([i * 34, 22, 0]) clipB();
  for (i = [0 : 3]) translate([i * 28, 44, 0]) clipC();
  for (i = [0 : 3]) translate([115 + i * 18, 0, 0]) tieD();
}
