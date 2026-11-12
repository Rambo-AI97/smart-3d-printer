// Ratcheting toothpaste winder (2026-11-12, replaces toothpaste_key). Two parts, no supports, PETG.
// BODY: frame that rides on the tube. The tube passes through a 2 mm squeeze slit; its crimped end
//   goes through the slotted KEY shaft. Turn the cog: the tube rolls up, the slit squeezes the paste
//   forward, 3 spring pawls in the body click into the gear on the key and stop it unwinding.
//   To swap tubes: pull the key straight out (the pawls let go axially).
// What others struggled with (Printables 398914 + remix 527118, MakerWorld "Ratcheted Toothpaste
// Squeezer" 3.0-7.0, Starship PiP, smysnk 64133) and what this design does about it:
//  - Ratchet pawls snapped / print-in-place ratchets fused or failed to stick -> NOT print-in-place:
//    pawls are long curved flexures (1.6 mm, ~1.2 % strain) printed flat ON THE BED in the body,
//    so layers run along each arm; 3 pawls share the load and centre the shaft.
//  - Handles snapped -> no thin handle: 42 mm cog knob, shaft 13 mm round, solid above/below the slot.
//  - Tight tolerances + elephant's foot made assembly hard -> 0.3 mm radial journal clearance,
//    0.5 mm chamfers on every bed-side bore edge, gear has a lead-in cone that cams the pawls open.
//  - Tube too wide for the body (remix had to add 6 mm) -> 62 mm slot (most crimps 45-58 mm).
//  - Tube only partly unwinds / no lock -> real ratchet; quick release by pulling the key.
//  - More teeth = smoother -> 18 teeth.
//   p3d make toothpaste_ratchet -q draft --brim --walls 3 --infill 15   (layer height only changes Z; teeth/pawls are vertical extrusions)
$fn = 64;
part   = "plate";   // "plate" | "body" | "key" | "assembly"
slot_l = 62;  slot_w = 2.6;
sd     = 13;        // shaft diameter
cl     = 0.3;       // radial clearance in the far bearing
ct     = 6;         // ratchet cheek thickness (= gear length)
gap    = 2.0;       // squeeze slit
// ratchet
nt = 18; rg_tip = 10; rg_root = 8.5;     // gear on the key
cav = 15.5;                               // pawl cavity radius in the cheek
arm_in = 12.4; arm_out = 14.0;            // pawl arm radial band (1.6 thick)
arm_span = 70; pawl_r = 9.0;              // pawl tip reaches r 9 (1 mm into the teeth)
// frame
Rc  = 21;           // cheek outer radius
ys  = 22;           // slit centre distance from shaft axis
wt  = 4;            // slit wall thickness (posts are the frame: keep them stiff)
spine_y = 20; spine_d = 9;
z_slot0 = ct + 2;  z_slot1 = z_slot0 + slot_l;   // body z of the slot
z_post  = z_slot1 + 2;                          // posts end, gussets start
z_ring  = z_post + 20;  ring_h = 4;  ring_r = 9.5;   // tall gussets: every underside >= 45 deg
body_h  = z_ring + ring_h;
cog_d = 42; cog_t = 6; teeth = 12;

function P(r, a) = [r * cos(a), r * sin(a)];

// ---------------- body ----------------
module cheek2d() hull() { circle(Rc); translate([-(gap / 2 + wt), -ys - 6]) square([gap + 2 * wt, 12]); }

module pawls2d() for (k = [0 : 2]) rotate(k * 120) {
  a0 = 0; a1 = a0 + arm_span;
  // root stub welded into the cavity wall
  polygon(concat([for (a = [a0 - 8 : 2 : a0 + 4]) P(cav + 0.6, a)], [for (a = [a0 + 4 : -2 : a0 - 8]) P(arm_in, a)]));
  // curved arm
  polygon(concat([for (a = [a0 : 2 : a1]) P(arm_out, a)], [for (a = [a1 : -2 : a0]) P(arm_in, a)]));
  // tip: radial lock face on the root side, cam slope on the far side
  polygon([P(arm_out, a1 - 10), P(pawl_r, a1 - 8), P(pawl_r, a1 - 2), P(arm_out, a1 + 2), P(arm_out, a1 - 2)]);
}

module body() {
  difference() {
    union() {
      difference() {   // cheek ring, bed-side cavity chamfer vs elephant's foot
        linear_extrude(ct) difference() { cheek2d(); circle(cav); }
        translate([0, 0, -0.01]) cylinder(r1 = cav + 0.5, r2 = cav, h = 0.5);
      }
      // squeeze slit walls (rounded lead-in edges) + back spine
      for (s = [-1, 1]) translate([s * (gap / 2 + wt / 2), -ys, 0])
        hull() for (y = [-3.5, 3.5]) translate([0, y, 0]) cylinder(d = wt, h = z_post, $fn = 24);
      translate([0, spine_y, 0]) cylinder(d = spine_d, h = z_post);
      // gussets from the posts up into the far bearing ring (>= 45 deg, no supports)
      for (p = [[gap / 2 + wt / 2, -ys], [-(gap / 2 + wt / 2), -ys], [0, spine_y]]) hull() {
        translate([p[0], p[1], z_post - 2]) cylinder(d = p[1] > 0 ? spine_d : wt, h = 2, $fn = 24);
        translate([0, 0, z_ring]) cylinder(r = ring_r, h = ring_h);
      }
      translate([0, 0, z_ring]) cylinder(r = ring_r, h = ring_h);
    }
    // far bearing bore
    translate([0, 0, z_post - 3]) cylinder(r = sd / 2 + cl, h = body_h);
    translate([0, 0, body_h - 0.7]) cylinder(r1 = sd / 2 + cl, r2 = sd / 2 + cl + 1, h = 0.71);
  }
  linear_extrude(ct) pawls2d();   // after the cuts: pawls stand on the bed, no overhang
}

// ---------------- key ----------------
module gear2d() polygon([for (i = [0 : nt - 1], j = [0 : 2])
  let(b = i * 360 / nt) j == 0 ? P(rg_root, b) : j == 1 ? P(rg_tip, b + 360 / nt - 3) : P(rg_root, b + 360 / nt - 1.5)]);

module cog2d() difference() {
  union() {
    circle(d = cog_d - 5);
    for (i = [0 : teeth - 1]) rotate(i * 360 / teeth)
      hull() { translate([cog_d / 2 - 4, 0]) square([0.1, 6], center = true);
               translate([cog_d / 2 - 1, 0]) square([2, 4.2], center = true); }
  }
  for (i = [0 : 4]) rotate(i * 72 + 36) translate([cog_d * 0.29, 0]) circle(d = 7.5);
}

key_len = cog_t + body_h + 1.5;
module key() {
  difference() {
    union() {
      linear_extrude(cog_t) cog2d();
      // gear sits in the cheek; lead-in cone at its top cams the pawls open on insertion
      translate([0, 0, cog_t]) intersection() {
        linear_extrude(ct) gear2d();
        cylinder(r1 = rg_tip + ct - 1.5, r2 = rg_tip - 1.5, h = ct);   // 45 deg, 1.5 mm lead-in
      }
      translate([0, 0, cog_t]) cylinder(d = sd, h = key_len - cog_t - 0.8);
      translate([0, 0, key_len - 0.8]) cylinder(d1 = sd, d2 = sd - 1.6, h = 0.8);
    }
    // slot through the shaft, pointed ends (no flat bridge), chamfered entry on both faces
    translate([0, 0, cog_t + z_slot0 + slot_l / 2]) {
      hull() for (z = [-1, 1]) translate([0, 0, z * (slot_l / 2 - slot_w / 2)])
        rotate([90, 0, 0]) rotate([0, 0, 45]) cube([slot_w / sqrt(2), slot_w / sqrt(2), sd + 6], center = true);
      for (s = [-1, 1]) translate([0, s * sd / 2, 0]) rotate([0, 0, 45]) cube([1.6, 1.6, slot_l - 3], center = true);
    }
  }
}

if (part == "body") body();
else if (part == "key") key();
else if (part == "assembly") { body(); color("orange") translate([0, 0, -cog_t]) key(); }
else { translate([-26, 0, 0]) body(); translate([26, 4, 0]) key(); }
