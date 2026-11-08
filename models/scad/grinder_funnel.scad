// Coffee grinder pour collar, Norse theme. Grips the grinder bowl (crush ribs = snug),
// rises past the rim into one smooth body with a measuring-cup pour point. Tip the grinder,
// the grounds run out of the point into the French press.
// Flair: shield band on the sleeve, a keel ridge running up into the pour point (longship bow),
// "KAFFI" runes on the back, flared rim. Printed upright on the sleeve flange, no supports.
bowl_d = 77;      // grinder bowl outside diameter (measured 2026-11-08)
grip_h = 25;      // sleeve depth (straight wall is 35)
part = "collar";  // "collar" | "fit" (8 mm test ring) | "plate" (collar + V2 scoop)

wall = 2.4;  rib = 0.5;  clear = 0.6;  relief = 0.8;
body_h = 24;      // collar height above the grinder rim
spout_l = 18;     // how far the pour point sticks out past the round body
tip_r = 3;        // roundness of the pour point
$fn = 120;

id = bowl_d + clear;            // sleeve bore; ribs bring it to bowl_d - 0.4 (squash fit)
od = id + 2 * wall;
ri = id / 2 - 1.6;              // body inside radius above the seat (= roughly the bowl's inside)
seat_h = 1.6;                   // 45 deg seat the bowl rim sits on
z1 = grip_h + seat_h;  ztop = grip_h + body_h;
tip_x = ri + spout_l;

module stroke(a, b, w = 1.2) hull() { translate(a) circle(d = w); translate(b) circle(d = w); }
kaffi = [   // Elder Futhark K A F F I, 4 x 8 cell
  [[[3,8],[0,4]], [[0,4],[3,0]]],
  [[[0,0],[0,8]], [[0,8],[3,6]], [[0,5],[3,3]]],
  [[[0,0],[0,8]], [[0,5],[3,7.5]], [[0,2.5],[3,5]]],
  [[[0,0],[0,8]], [[0,5],[3,7.5]], [[0,2.5],[3,5]]],
  [[[0,0],[0,8]]],
];

module drop(o) hull() { circle(r = ri + o); translate([tip_x, 0]) circle(r = tip_r + o); }   // top outline
module lay(z) translate([0, 0, z]) linear_extrude(0.01) children();

module outer() {
  cylinder(d = od, h = grip_h);
  hull() { lay(grip_h) circle(d = od); lay(ztop - 3) drop(wall); }           // one smooth loft round -> pour point
  hull() { lay(ztop - 3) drop(wall); lay(ztop) drop(wall + 1.5); }           // flared rim (45 deg)
  difference() { cylinder(d = od + 10, h = 0.8); translate([0, 0, -1]) cylinder(d = id, h = 3); }   // bed flange / finger lip
}
module inner() {
  translate([0, 0, -1]) cylinder(d = id, h = grip_h + 1);
  hull() { lay(grip_h - 0.01) circle(d = id); lay(z1) circle(r = ri); }      // seat: bowl rim stops here
  hull() { lay(z1) circle(r = ri); lay(ztop + 0.01) drop(0); }
  translate([0, 0, ztop]) linear_extrude(5) drop(5);
}
module ribs() for (a = [22.5 : 45 : 359]) rotate(a) translate([id / 2, 0, 0])
  hull() { translate([-rib + 0.6, 0, 2]) cylinder(d = 1.2, h = grip_h - 4, $fn = 12);
           translate([1, 0, 0]) cylinder(d = 1.6, h = grip_h, $fn = 12); }
module shields() for (a = [30 : 30 : 330]) rotate(a)   // skip the front, where the keel runs
  translate([od / 2 - 0.2, 0, grip_h / 2 + 1]) rotate([0, 90, 0]) {
    difference() { cylinder(d = 9, h = 1.4); translate([0, 0, 0.8]) cylinder(d = 7, h = 1); }
    cylinder(d1 = 2.8, d2 = 1.8, h = 1.8, $fn = 16);
  }
module keel() {   // ridge from the sleeve up the bow into the pour point
  hull() { translate([od / 2, 0, 3]) sphere(r = 1.4, $fn = 16); translate([od / 2, 0, grip_h]) sphere(r = 1.4, $fn = 16); }
  hull() { translate([od / 2, 0, grip_h]) sphere(r = 1.4, $fn = 16); translate([tip_x + tip_r + wall - 0.6, 0, ztop - 3]) sphere(r = 1.4, $fn = 16); }
}
module runes() {   // on the back (vertical wall), reading left to right
  h = 8;  n = len(kaffi);  zc = grip_h + body_h / 2 - 1;
  for (i = [0 : n - 1]) rotate(180 + (i - (n - 1) / 2) * 10)
    translate([ri + wall + 0.4, 0, zc]) rotate([90, 0, 90])
      translate([-2, -h / 2, 0]) linear_extrude(relief + 0.3) scale(h / 8) for (s = kaffi[i]) stroke(s[0], s[1], 1.3 * 8 / h);
}

module collar() { difference() { union() { outer(); shields(); keel(); runes(); } inner(); } ribs(); }
module fit_ring() intersection() { collar(); cylinder(d = 200, h = 8); }

use <phone_kit_v2.scad>
if (part == "fit") fit_ring();
else if (part == "plate") { translate([-45, 0, 0]) collar(); translate([62, 0, 0]) rotate(90) scoop(); }
else collar();
