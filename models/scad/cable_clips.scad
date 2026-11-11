// Cable clip set, one plate. All print flat, no supports.
//  A  single snap clip (stick on with tape): holds a cable / keeps a plug end on the table
//  B  double snap clip: two cords side by side (bedside table)
//  C  screw clip: one cable, one screw (under a desk, on a wall)
//  D  reusable cable tie: tail with teeth through the head slot; squeeze teeth to release
//  E  zip-tie mount (v2 2026-11-09): screw (or tape) it down, a zip tie (<=5 mm) threads through the
//     tunnel over the screw head, both directions. Kit plate = layout "kit"
cable_d = 4.2;     // USB-C / phone-charger cable ~3.5-4 mm
ring    = 1.8;     // ring wall
open_f  = 0.72;    // snap opening as a fraction of cable_d
clip_w  = 10;      // clip length along the cable
base_t  = 2.5;
$fn = 48;
layout  = "kit";     // "kit" | "plate" | "A" | "B" | "C" | "D" | "E" (one piece)

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

module mountE() {
  m = 16;  h = 7.2;  tw = 5.6;  th = 2;  tz = 3.8;
  difference() {
    translate([-m / 2, -m / 2, 0]) linear_extrude(h) offset(2) offset(-2) square(m);
    for (r = [0, 90]) rotate(r) translate([-m, -tw / 2, tz]) cube([2 * m, tw, th]);   // cross tunnels
    translate([0, 0, -1]) cylinder(d = 3.8, h = 10);                                   // screw
    translate([0, 0, 1.6]) cylinder(d = 7.6, h = 10);                                  // head + driver access
  }
}

if (layout == "A") clipA();
else if (layout == "E") mountE();
else if (layout == "kit") {   // owner 2026-11-10: just the reusable ties, 4 lengths 80/120/160/200
  for (i = [0 : 3]) translate([10, i * 14, 0]) rotate(-90) tieD(80 + 40 * i);
}
else if (layout == "B") clipB();
else if (layout == "C") clipC();
else if (layout == "D") tieD();
else {   // plate: 3 x A, 3 x B, 4 x C, 4 x D
  for (i = [0 : 2]) translate([i * 24, 0, 0]) clipA();
  for (i = [0 : 2]) translate([i * 34, 22, 0]) clipB();
  for (i = [0 : 3]) translate([i * 28, 44, 0]) clipC();
  for (i = [0 : 3]) translate([115 + i * 18, 0, 0]) tieD();
}
