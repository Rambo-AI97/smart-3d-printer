// Baby rattle hammer V3 (2026-11-11). Supervised use only. PETG.
// V1 snapped at the handle/head joint: it printed standing, so layer lines crossed the
// handle (weakest direction) and the neck sat on a thin 4 mm chamber roof.
// V3 prints LYING DOWN: layer lines run along the handle (bending-strong in every
// direction), the neck flares into a 12 mm solid block that ties into the head's floor
// and roof plates (in-layer, strong). The handle sits at the head's mid-height on a 33 deg
// keel (teardrop section, like an axe haft) so it needs no supports.
// Choke-safe by size: ball 35 > 31.7 small-parts cylinder, both ends far wider than the
// 33 mm rattle test hole, no 5-12 mm holes, all edges rounded, relief only 0.6-0.8 mm.
// Norse ornament: name in Elder Futhark runes on top (stroke font below, set with
// -D name="..."; "" = none), triquetras on both hammer faces + knob end, braid on the back.
// Ball: prints beside it; at the pause pop it off, set it flat side down in the middle of
// the chamber (between the ribs), resume -> the roof bridges over it.
//   p3d slice baby_rattle_v3.stl -f petg --walls 6 --infill 30 --keep-orient --brim
//   p3d print JOB --pause-at-layer N   (N = first layer above pause_z)
$fn = 64;
part = "plate";   // "plate" | "rattle" | "ball" | "cut"
name = "";

ball_d = 35; ball_cut = 2.5;               // flat so it prints; height 32.5
// head (hammer length along X, handle leaves the +Y face)
hx = 64; hy = 56; H = 46; hr = 8; ch = 3;
floor_t = 4;
cav_l = 52; cav_w = 39; cav_h = 37.5;       // ball travel 17 mm, rolls with 2.5 mm headroom
cav_y = -hy + 5 + cav_w / 2;                // 5 mm back wall, 12 mm solid neck block
pause_z = floor_t + ball_d - ball_cut + 2;     // 38.5: ball top 36.5, chamber open to 41.5
rib_x = 12; rib_r = 1.8;
zc = H / 2;                                 // handle axis height
keel = 33;                                  // keel half-angle from vertical (<= 34 so it reaches the bed)
grip_r = 13;                                // 26 mm grip
relief = 0.8;

// ---------- ornament (2D) ----------
// Elder Futhark strokes, unit height. Y -> jera (as in Freyja). Z/X/Q left out on purpose.
R_ = [
 ["A", [[[0,0],[0,1]], [[0,1],[0.5,0.75]], [[0,0.75],[0.5,0.5]]]],
 ["B", [[[0,0],[0,1]], [[0,1],[0.45,0.75]], [[0.45,0.75],[0,0.5]], [[0,0.5],[0.45,0.25]], [[0.45,0.25],[0,0]]]],
 ["C", [[[0.45,0.9],[0.05,0.6]], [[0.05,0.6],[0.45,0.3]]]],
 ["K", [[[0.45,0.9],[0.05,0.6]], [[0.05,0.6],[0.45,0.3]]]],
 ["D", [[[0,0],[0,1]], [[0.6,0],[0.6,1]], [[0,1],[0.6,0]], [[0,0],[0.6,1]]]],
 ["E", [[[0,0],[0,1]], [[0.6,0],[0.6,1]], [[0,1],[0.3,0.7]], [[0.3,0.7],[0.6,1]]]],
 ["F", [[[0,0],[0,1]], [[0,0.5],[0.5,0.75]], [[0,0.75],[0.5,1]]]],
 ["G", [[[0,0],[0.6,1]], [[0,1],[0.6,0]]]],
 ["H", [[[0,0],[0,1]], [[0.5,0],[0.5,1]], [[0,0.65],[0.5,0.35]]]],
 ["I", [[[0,0],[0,1]]]],
 ["J", [[[0.3,0.95],[0.05,0.72]], [[0.05,0.72],[0.3,0.5]], [[0.25,0.5],[0.5,0.28]], [[0.5,0.28],[0.25,0.05]]]],
 ["Y", [[[0.3,0.95],[0.05,0.72]], [[0.05,0.72],[0.3,0.5]], [[0.25,0.5],[0.5,0.28]], [[0.5,0.28],[0.25,0.05]]]],
 ["L", [[[0,0],[0,1]], [[0,1],[0.45,0.75]]]],
 ["M", [[[0,0],[0,1]], [[0.6,0],[0.6,1]], [[0,1],[0.6,0.6]], [[0.6,1],[0,0.6]]]],
 ["N", [[[0.25,0],[0.25,1]], [[0,0.65],[0.5,0.4]]]],
 ["O", [[[0.3,1],[0.6,0.65]], [[0.6,0.65],[0,0]], [[0.3,1],[0,0.65]], [[0,0.65],[0.6,0]]]],
 ["P", [[[0,0],[0,1]], [[0,1],[0.45,0.8]], [[0.45,0.8],[0.45,0.95]], [[0,0],[0.45,0.2]], [[0.45,0.2],[0.45,0.05]]]],
 ["R", [[[0,0],[0,1]], [[0,1],[0.45,0.8]], [[0.45,0.8],[0,0.55]], [[0,0.55],[0.5,0]]]],
 ["S", [[[0.5,1],[0.05,0.6]], [[0.05,0.6],[0.5,0.4]], [[0.5,0.4],[0.05,0]]]],
 ["T", [[[0.3,0],[0.3,1]], [[0.3,1],[0,0.7]], [[0.3,1],[0.6,0.7]]]],
 ["U", [[[0,0],[0,1]], [[0,1],[0.5,0.7]], [[0.5,0.7],[0.5,0]]]],
 ["V", [[[0,0],[0,1]], [[0,1],[0.5,0.7]], [[0.5,0.7],[0.5,0]]]],
 ["W", [[[0,0],[0,1]], [[0,1],[0.4,0.8]], [[0.4,0.8],[0,0.6]]]],
];
function up(c) = let(o = ord(c)) (o >= 97 && o <= 122) ? chr(o - 32) : c;
function rune(c) = let(i = search([up(c)], R_)[0]) is_num(i) ? R_[i][1] : [];
function rw(c) = let(s = rune(c)) len(s) == 0 ? 0 : max([for (g = s) for (p = g) p[0]]);
function xs(str, gap, i = 0, acc = 0) = i >= len(str) ? [acc - gap] : concat([acc], xs(str, gap, i + 1, acc + rw(str[i]) + gap));

module seg(a, b, w) hull() { translate(a) circle(d = w, $fn = 16); translate(b) circle(d = w, $fn = 16); }
module runes(str, h, w, gap = 0.32) {
  x = xs(str, gap);
  translate([-x[len(str)] * h / 2, -h / 2])
    for (i = [0:len(str) - 1]) for (g = rune(str[i])) seg(h * (g[0] + [x[i], 0]), h * (g[1] + [x[i], 0]), w);
}
module lens(c1, c2, R) intersection() { translate(c1) circle(R, $fn = 96); translate(c2) circle(R, $fn = 96); }
module triquetra(d, w) {             // three vesica outlines (pairwise circle overlaps) + ring
  R = d / 2 / 1.155; c = [for (k = [0:2]) R / sqrt(3) * [cos(90 + 120 * k), sin(90 + 120 * k)]];
  for (k = [0:2]) difference() { lens(c[k], c[(k + 1) % 3], R); offset(-w) lens(c[k], c[(k + 1) % 3], R); }
  difference() { circle(d = d * 0.62, $fn = 96); circle(d = d * 0.62 - 2 * w, $fn = 96); }
}
module braid(L, A, lam, w) {          // two strands, over-under alternating
  n = 60; f = function(x, s) [x, s * A * sin(360 * x / lam)];
  module strand(s) for (i = [0:n - 1]) seg(f(-L / 2 + L * i / n, s), f(-L / 2 + L * (i + 1) / n, s), w);
  cr = [for (x = [-L / 2 + lam / 4 : lam / 2 : L / 2]) x];   // crossings
  module gaps(par) for (i = [0:len(cr) - 1]) if (i % 2 == par && abs(cr[i]) < L / 2 - 1) translate([cr[i], 0]) circle(d = w * 3.2, $fn = 24);
  difference() { strand(1); gaps(1); }
  difference() { strand(-1); gaps(0); }
  for (s = [-1, 1]) seg([-L / 2 - 2, s * (A + 3)], [L / 2 + 2, s * (A + 3)], w * 0.7);
}
module frame(x, y, w, r = 4) difference() { offset(r) square([x - 2 * r, y - 2 * r], center = true); offset(r - w) square([x - 2 * r, y - 2 * r], center = true); }

// ---------- head ----------
module rbox(x, y, z, r) hull() for (i = [-1, 1], j = [-1, 1])
  translate([i * (x / 2 - r), j * (y / 2 - r), 0]) {
    cylinder(r1 = r - ch, r2 = r, h = ch);
    translate([0, 0, ch]) cylinder(r = r, h = z - r - ch);
    translate([0, 0, z - r]) sphere(r);
  }
module stadium(w, l, h) hull() for (i = [-1, 1]) translate([i * (l - w) / 2, 0, 0]) cylinder(d = w, h = h);

module head() {
  translate([0, -hy / 2, 0]) rbox(hx, hy, H, hr);
  if (name != "") translate([0, -hy / 2 + 1, H - 0.01]) linear_extrude(relief) rotate(180) {
    runes(name, 11, 1.7);
  }
  translate([0, -hy / 2 + 1, H - 0.01]) linear_extrude(relief) frame(hx - 2 * hr - 1, hy - 2 * hr - 3, 1.1);
  for (s = [-1, 1]) translate([s * (hx / 2 - 0.01), -hy / 2, zc + 1.5]) rotate([90, 0, s * 90]) linear_extrude(relief) triquetra(30, 2.0);
  translate([0, -hy + 0.01, zc + 1.5]) rotate([90, 0, 0]) linear_extrude(relief) braid(hx - 2 * hr - 6, 4.5, 11, 1.7);
}
module chamber() difference() {
  translate([0, cav_y, floor_t]) stadium(cav_w, cav_l, cav_h);
  for (i = [-1, 1]) translate([i * rib_x, cav_y, floor_t]) rotate([90, 0, 0]) cylinder(r = rib_r, h = cav_w + 2, center = true, $fn = 24);
}

// ---------- handle (sequence of teardrop slices, y = distance from the head face) ----------
module td(r) intersection() {
  hull() { translate([0, zc]) circle(r, $fn = 64); translate([0, zc - r / sin(keel)]) circle(0.6, $fn = 12); }
  translate([-hx / 2, 0]) square([hx, H]);
}
module slice(y, r) translate([0, y, 0]) rotate([90, 0, 0]) linear_extrude(0.01, center = true) td(r);
neck = 24; g1 = 86; k0 = 95; k1 = 104; kend = 109; knob_r = 22;
function rr(y) =
  y < 0 ? 27 :
  y < neck ? grip_r + 14 * pow(1 - y / neck, 2) :                       // concave fillet 27 -> 13
  y < g1 ? grip_r :
  y < k0 ? grip_r + (knob_r - grip_r) * (1 - cos(180 * (y - g1) / (k0 - g1))) / 2 :
  y < k1 ? knob_r :
  (knob_r - 5) + sqrt(max(0, 25 - pow(y - k1, 2)));                   // 5 mm round-over, flat end
ys = concat([-12, -0.01], [for (y = [1:1.5:neck]) y], [neck, g1], [for (y = [g1 + 1:1:k0]) y], [k1], [for (y = [k1 + 0.5:0.5:kend]) y]);
bands = [28, 31.5, 53.5, 57, 79.5, 83];     // three double binding bands
module handle() {
  for (i = [0:len(ys) - 2]) hull() { slice(ys[i], rr(ys[i])); slice(ys[i + 1], rr(ys[i + 1])); }
  for (b = bands) hull() { slice(b - 0.6, grip_r + 0.7); slice(b + 0.6, grip_r + 0.7); }
  translate([0, kend - 0.01, zc]) rotate([-90, 0, 0]) linear_extrude(0.6) triquetra(23, 1.7);
}

module rattle() difference() { union() { head(); handle(); } chamber(); }
module ball() translate([0, 0, ball_d / 2 - ball_cut]) intersection() {
  sphere(d = ball_d, $fn = 96);
  translate([0, 0, -(ball_d / 2 - ball_cut)]) cylinder(d = ball_d + 2, h = ball_d);
}

if (part == "rattle") rattle();
else if (part == "ball") ball();
else if (part == "cut") difference() { union() { rattle(); translate([0, cav_y, floor_t]) ball(); } translate([0, -100, -1]) cube([100, 300, 100]); }
else { rattle(); translate([hx / 2 + 28, -hy / 2, 0]) ball(); }
