// Ornate ceiling swag hook for the chain chandelier (2026-11-12). PETG.
// Load: chandelier ~20 lb (9 kg). Two #10 x 3" wood screws, 60 mm apart, BOTH into the joist
// (run the bar along the joist). Screws in tension = the strong way.
// Parts (one plate):
//  1. Hook: printed ON ITS SIDE so every layer contains the whole hook outline (layers never split
//     under the load). Mount bar 80 x 10 x 16 sits on the ceiling, gothic stem with 2 beads, J-hook,
//     16 mm throat for the chain link, ball finial. Worst bending ~4 MPa (PETG creep-safe < ~10).
//  2+3. Rosette cover, 2 halves (split across the bar so the hook needs no threading through):
//     Ø100 ceiling medallion, 12 petals, bead ring, collar. Bar sits in its ceiling-side pocket;
//     each screw passes rosette + bar, so the rosette is clamped, the bar carries the load.
// Safety: hang test first with 2x weight (a 40 lb bag) for a day before the real fixture.
//   p3d make chandelier_hook --walls 6 --infill 40
$fn = 64;
T     = 16;          // hook thickness (print height)
bar_l = 80;  bar_h = 10;
scr   = 60;          // screw spacing
sd    = 5.2;         // #10 screw clearance
R     = 100;         // rosette diameter
rh    = 18;          // rosette height
lay   = 1.0;         // edge chamfer

// --- hook outline, in-use coords: y up, ceiling at y = 0, stem on x = 0
module stem2d() {   // stays 14 wide through the rosette + collar (y > -24), ornament below
  translate([-bar_l / 2, -bar_h]) square([bar_l, bar_h]);
  translate([-7, -78]) square([14, 78 - bar_h + 0.01]);
  translate([0, -27]) scale([1, 0.45]) circle(d = 22);                 // collar disc under the rosette
  for (y = [-38, -56]) translate([0, y]) circle(d = 24);              // beads
  translate([0, -47]) scale([1, 0.6]) circle(d = 17);                  // waist knot
  translate([-11, -36]) difference() { circle(r = 10); circle(r = 5.5); translate([0, -12]) square([24, 24]); } // C-scroll
  translate([-15, -44]) circle(d = 8);
}
module hook2d() {
  translate([15, -78]) difference() { circle(r = 22); circle(r = 8);
                                       translate([-30, 0]) square([60, 30]); }
  translate([23, -78]) square([14, 12]);                              // rising tip
  translate([30, -62]) circle(d = 17);                                // ball finial
}
module outline() { union() { stem2d(); hook2d(); } }

module hook3d() { difference() { hook_solid();   // screw holes: in-use vertical = horizontal in print -> diamond (no sag)
  for (s = [-1, 1]) translate([s * scr / 2, 1, T / 2]) rotate([90, 0, 0]) rotate(45) cylinder(d = sd + 0.8, h = bar_h + 2, $fn = 4); } }
module hook_solid() {   // print orientation: outline in XY, extruded up Z
  linear_extrude(lay) offset(-lay) outline();
  translate([0, 0, lay]) linear_extrude(T - 2 * lay) outline();
  translate([0, 0, T - lay]) linear_extrude(lay) offset(-lay) outline();
  // raised bead line down the stem face (top face only, decoration)
  for (y = [-17, -33, -51]) translate([0, y, T - 0.01]) cylinder(d1 = 4, d2 = 2.6, h = 0.8, $fn = 24);
}

// --- rosette (printed ceiling-face down, ornate face up)
module rosette_full() {
  difference() {
    union() {
      rotate_extrude($fn = 120) polygon([[0, 0], [R / 2, 0], [R / 2, 4], [R / 2 - 3, 8], [R / 2 - 8, 12],
                                         [R / 2 - 16, 14], [16, 16], [12, rh], [0, rh]]);
      for (a = [0 : 30 : 359]) rotate(a + 15) translate([R / 2 - 17, 0, 13])        // petals
        scale([1.7, 0.75, 0.5]) sphere(d = 13, $fn = 32);
      for (a = [0 : 10 : 359]) rotate(a) translate([R / 2 - 4, 0, 8.6]) sphere(d = 3.4, $fn = 16); // bead ring
      cylinder(d = 26, h = rh + 2);                                                 // collar
      translate([0, 0, rh + 2]) cylinder(d1 = 26, d2 = 22, h = 2);
    }
    translate([-bar_l / 2 - 0.4, -T / 2 - 0.4, -1]) cube([bar_l + 0.8, T + 0.8, bar_h + 1]); // bar pocket
    translate([-7.4, -T / 2 - 0.4, -1]) cube([14.8, T + 0.8, 40]);                          // stem slot
    for (s = [-1, 1]) translate([s * scr / 2, 0, 0]) {
      translate([0, 0, -1]) cylinder(d = sd, h = 40);
      translate([0, 0, bar_h + 3]) cylinder(d = 10.5, h = 40);                       // head counterbore
    }
    translate([0, 0, -50]) cube(0.01);
  }
}
module rosette_half(s) { intersection() { rosette_full(); translate([s > 0 ? 0.3 : -R, -R, -1]) cube([R - 0.3, 2 * R, 40]); } }

// in-use view for approval: p3d scad ... -D view=1
view = 0;
if (view) {
  rotate([90, 0, 0]) translate([0, 0, -T / 2]) hook3d();
  color("gold") translate([0, 0, 0]) mirror([0, 0, 1]) rosette_full();
} else {
translate([-20, 40, 0]) rotate(-90) hook3d();
translate([-55, -55, 0]) rosette_half(1);
translate([65, -55, 0]) rosette_half(-1);
}
