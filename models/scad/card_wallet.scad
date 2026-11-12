// Slim card wallet for up to 6 bank cards (ID-1: 85.6 x 54 x 0.76 mm).
// Cards slide in from the top and stick out 6 mm. A PETG leaf spring on the back
// presses them so they don't fall out. Push them up through the bottom window
// with your thumb; the top notch lets you pinch one card out.
// Prints STANDING on its bottom (open end up): no supports, brim on.
card_w = 85.6; card_h = 54;
cav_w  = card_w + 1.0;   // side play
cav_t  = 5.4;            // 6 cards (4.6) + embossing slack; the spring takes up the rest
wall   = 2.0;            // front/back faces
side   = 2.2;
floor_ = 2.0;
H      = 50;             // cards stick out card_h - (H - floor_) = 6 mm
leaf_w = 28; leaf_h = 26; leaf_z = 10; leaf_gap = 0.8; leaf_bump = 1.1;
deb    = 0.6;
$fn = 64;

W = cav_w + 2 * side; T = cav_t + 2 * wall;

module lens(c1, c2, R) intersection() { translate(c1) circle(R); translate(c2) circle(R); }
module triquetra(d, w) {
  R = d / 2 / 1.155; c = [for (k = [0:2]) R / sqrt(3) * [cos(90 + 120 * k), sin(90 + 120 * k)]];
  for (k = [0:2]) difference() { lens(c[k], c[(k + 1) % 3], R); offset(-w) lens(c[k], c[(k + 1) % 3], R); }
  difference() { circle(d = d * 0.62); circle(d = d * 0.62 - 2 * w); }
}
module rr(x, y, r) offset(r) square([x - 2 * r, y - 2 * r], center = true);
// 2D on the XZ face -> cut through/into the front (y-) or back (y+) face
module on_face(s, depth) translate([0, s * T / 2, 0]) rotate([90, 0, 0]) translate([0, 0, s > 0 ? -depth : 0]) linear_extrude(depth + 0.01 + (s > 0 ? 0.01 : 0)) children();

module shell() difference() {
  hull() for (i = [-1, 1], j = [-1, 1]) translate([i * (W / 2 - 3), j * (T / 2 - 3), 0]) {
    cylinder(r1 = 2.4, r2 = 3, h = 0.6);
    translate([0, 0, 0.6]) cylinder(r = 3, h = H - 1.6);
    translate([0, 0, H - 1]) cylinder(r1 = 3, r2 = 2, h = 1);
  }
  translate([-cav_w / 2, -cav_t / 2, floor_]) cube([cav_w, cav_t, H]);
  // front: thumb window at the bottom, pinch notch at the top
  translate([0, -T / 2 + wall / 2, 0]) {
    translate([0, 0, 4]) rotate([90, 0, 0]) linear_extrude(wall + 2, center = true) hull() for (i = [-1, 1]) translate([i * 10, 6]) circle(d = 12);
    translate([0, 0, H]) rotate([90, 0, 0]) cylinder(r = 13, h = wall + 2, center = true);
  }
  // back: U-cut leaf spring (fixed at the bottom, free at the top)
  translate([0, T / 2 - wall / 2, 0]) rotate([90, 0, 0]) linear_extrude(wall + 2, center = true)
    translate([0, leaf_z]) difference() {
      translate([-leaf_w / 2 - leaf_gap, 0]) square([leaf_w + 2 * leaf_gap, leaf_h + leaf_gap]);
      translate([-leaf_w / 2, -1]) square([leaf_w, leaf_h + 1]);
    }
  // ornaments: triquetras either side of the window, a border line, all debossed
  translate([0, -T / 2 - 0.01, 0]) rotate([90, 0, 0]) mirror([0, 0, 1]) linear_extrude(deb) {
    for (i = [-1, 1]) translate([i * 30, 24]) triquetra(24, 1.4);
    difference() { translate([0, H / 2]) rr(W - 7, H - 7, 3); translate([0, H / 2]) rr(W - 9.4, H - 9.4, 2); translate([0, H]) circle(r = 16); translate([0, 10]) square([36, 22], center = true); }
  }
  translate([0, T / 2 + 0.01, 0]) rotate([90, 0, 0]) linear_extrude(deb) for (i = [-1, 1]) translate([i * 30, 24]) triquetra(24, 1.4);
}
// inward bump at the top of the leaf: 45-degree ramps, so it prints standing
module bump() translate([0, cav_t / 2, leaf_z + leaf_h - 4]) rotate([0, 90, 0])
  linear_extrude(leaf_w - 4, center = true) polygon([[-3, 0.01], [0, -leaf_bump], [3, 0.01]]);

shell(); bump();
