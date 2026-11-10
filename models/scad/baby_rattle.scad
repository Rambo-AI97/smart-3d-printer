// Baby rattle "hammer" (2026-11-10, polished V1 = V2 built in). Supervised use only.
// Choke-safe by size: every piece (incl. the loose ball) is wider than the 31.7 mm
// small-parts cylinder, both ends far wider than the 33 mm rattle test hole,
// no holes/gaps 5-12 mm (fingers), all edges rounded/chamfered, name engraved (nothing to chew off).
// Prints STANDING: head on the bed, round handle straight up out of the head's centre
// (centred, fully round grip, no supports). One plate: the ball prints beside it; at the
// pause (chamber still open) pop the ball off, set it flat side down in the middle of the
// chamber, resume -> the roof seals it in. Two floor ribs make it clack, not just roll.
//   p3d slice baby_rattle.stl -f pla --walls 4 --infill 15 --keep-orient
//   p3d print JOB --pause-at-layer N   (N = layer at z = pause_z)
$fn = 72;
part    = "plate";   // "plate" | "rattle" | "ball" | "cut" (section view)
name    = "";        // engraved 0.6 mm in the head side, set with -D name="..." ("" = none)

ball_d  = 35;        // > 31.7 small-parts cylinder
ball_cut= 2.5;       // flat on the ball so it prints (contact ~18 mm)
// head: long axis Y (hammer head), handle comes out of its top face
hx = 52; hy = 82; hr = 11; ch = 4;      // cross-section 52, length 82, edge radius, 45 deg bottom chamfer
floor_t = 3; roof_t = 4;
cav_x = ball_d + 4; cav_y = 64;          // chamber: ball rolls ~29 mm end to end
cav_wall = 39;                           // vertical chamber wall above the floor
bridge_w = 13;                           // flat roof bridge after the 45 deg chamfers
ins = (cav_x - bridge_w) / 2;
hz = floor_t + cav_wall + ins + roof_t;  // 59
pause_z = floor_t + 37;                  // 40: ball top is 35.5 (flat side down), wall goes to 42
rib_y = 23; rib_r = 2;                   // clack ribs across the floor, ball sits between them
// handle (along +Z, round)
grip_r = 12.5;       // 25 mm grip = baby fist
grip_len = 88;       // from head top to knob
flare_r = 21;        // reinforced neck
knob_r = 22;         // 44 mm end knob: can't go in the mouth, hand can't slide off

module rbox(x, y, z, r) hull() for (i = [-1, 1], j = [-1, 1])
  translate([i * (x / 2 - r), j * (y / 2 - r), 0]) {
    cylinder(r1 = r - ch, r2 = r, h = ch);
    translate([0, 0, ch]) cylinder(r = r, h = z - r - ch);
    translate([0, 0, z - r]) sphere(r);
  }

module stadium(w, l, h) hull() for (j = [-1, 1]) translate([0, j * (l - w) / 2, 0]) cylinder(d = w, h = h);

module chamber() difference() {
  translate([0, 0, floor_t]) hull() {
    stadium(cav_x, cav_y, cav_wall);
    translate([0, 0, cav_wall]) stadium(bridge_w, cav_y - 2 * ins, ins);
  }
  for (j = [-1, 1]) translate([0, j * rib_y, floor_t]) rotate([0, 90, 0]) cylinder(r = rib_r, h = cav_x + 2, center = true, $fn = 24);
}

module head() difference() {
  rbox(hx, hy, hz, hr);
  if (name != "")   // on the +X side face, reads along the head
    translate([hx / 2 - 0.6, 0, hz * 0.45]) rotate([90, 0, 90]) linear_extrude(2)
      text(name, size = 12, font = "DejaVu Sans:style=Bold", halign = "center", valign = "center");
}

module handle() {
  z0 = hz - 8;                     // starts inside the head
  L = grip_len;
  g = [for (k = [0:2]) 30 + k * 15];          // 3 finger grooves, 45 deg flanks
  top = L + 8 + 14;
  dome = [for (a = [0:10:90]) [ (knob_r - 6) + 6 * cos(a) , L + 8 + 8 + 6 * sin(a)]];
  prof = concat(
    [[0, 0], [flare_r, 0], [flare_r, 8], [grip_r, 8 + flare_r - grip_r]],   // 45 deg neck
    [for (c = g) each [[grip_r, c - 3.5], [grip_r - 2, c - 1.5], [grip_r - 2, c + 1.5], [grip_r, c + 3.5]]],
    [[grip_r, L + 8 - (knob_r - grip_r)], [knob_r, L + 8], [knob_r, L + 8 + 8 - 6 + 6]],  // 45 deg flare to knob
    dome,
    [[0, top]]);
  translate([0, 0, z0]) intersection() {
    rotate_extrude() polygon(prof);
    translate([-hx / 2, -hy / 2, 0]) cube([hx, hy, 200]);     // neck never sticks past the head
  }
}

module rattle() difference() { union() { head(); handle(); } chamber(); }

module ball() translate([0, 0, ball_d / 2 - ball_cut]) intersection() {
  sphere(d = ball_d, $fn = 96);
  translate([0, 0, -(ball_d / 2 - ball_cut)]) cylinder(d = ball_d + 2, h = ball_d);
}

if (part == "rattle") rattle();
else if (part == "ball") ball();
else if (part == "cut") difference() { union() { rattle(); translate([0, 0, floor_t]) ball(); } translate([0, -150, -1]) cube([150, 300, 300]); }
else { rattle(); translate([hx / 2 + 30, 0, 0]) ball(); }
