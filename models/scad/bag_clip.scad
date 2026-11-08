// v2 (2026-11-08): no snap gate; round hole for the belt's metal clip. v1 below kept as part="v1".
// Used-poop-bag clip. Hooks onto a belt (<=40 mm), belt buckle, leash or D-ring
// through a snap gate; two keyholes hold tied bags (push knot through the
// round hole, slide the neck down the slot). Prints flat, no supports.
t = 4.5;          // thickness
W = 52;           // overall width
plate_h = 36;
key_d = 16;       // knot hole
slot_w = 4;       // bag-neck slot (tapers to slot_w - 1)
// hook loop
in_w = 42; in_h = 10; wall = 5;
gap_lo = 41; gap_hi = 47;   // opening in the right wall
gate_r = 0.7;               // gate is 1.4 mm thick
$fn = 64;

module rrect(x0, y0, x1, y1, r) {
  translate([x0 + r, y0 + r]) offset(r) square([x1 - x0 - 2 * r, y1 - y0 - 2 * r]);
}

loop_y0 = plate_h - 2;
in_y0 = loop_y0 + wall;           // 39
in_y1 = in_y0 + in_h;             // 49

module clip2d() {
  difference() {
    union() {
      rrect(-W / 2, 0, W / 2, plate_h, 5);
      rrect(-W / 2, loop_y0, W / 2, in_y1 + wall, 5);
    }
    // loop opening
    rrect(-in_w / 2, in_y0, in_w / 2, in_y1, 0.5);
    // entry gap in right wall
    translate([in_w / 2 - 1, gap_lo]) square([wall + 2, gap_hi - gap_lo]);
    // keyholes
    for (x = [-12, 12]) {
      translate([x, 24]) circle(d = key_d);
      hull() {
        translate([x, 24]) circle(d = slot_w);
        translate([x, 7]) circle(d = slot_w - 1);
      }
    }
  }
  // snap gate: rooted in the lower stub, tip rests just inside the upper stub
  hull() {
    translate([in_w / 2 + 3, in_y0 + 1]) circle(gate_r);
    translate([in_w / 2 - 1.4, gap_hi + 0.9]) circle(gate_r);
  }
}

part = "v2";

module clip2d_v2() {
  hole_d = 10;  ring_w = 4;  ry = plate_h + hole_d / 2 + 1;
  difference() {
    union() {
      rrect(-W / 2, 0, W / 2, plate_h, 5);
      hull() {                                  // tab with the clip hole
        translate([0, ry]) circle(d = hole_d + 2 * ring_w);
        translate([-12, plate_h - 6]) square([24, 1]);
      }
    }
    translate([0, ry]) circle(d = hole_d);
    for (x = [-12, 12]) {
      translate([x, 24]) circle(d = key_d);
      hull() {
        translate([x, 24]) circle(d = slot_w);
        translate([x, 7]) circle(d = slot_w - 1);
      }
    }
  }
}

if (part == "v1") linear_extrude(t) clip2d(); else linear_extrude(t) clip2d_v2();
