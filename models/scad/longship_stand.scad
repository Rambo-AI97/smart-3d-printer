// Viking longship pen & phone stand (2026-11-12).
// The phone stands upright in the middle like the square sail (portrait, leaning back 15 deg, screen to the
// front), pens stand in 10 holes in the bow and stern, a dragon head rises from the bow and a curled tail
// from the stern, 9 round shields line each side and the hull has overlapping clinker planks.
// - Phone slot sized for a Nothing Phone 3 in a case (phone 160.6 x 75.6 x 9.0 mm, maker spec):
//   84 long x 13 wide x 14 deep, chamfered lead-in. Phone weight sits over the flat 50 mm keel, tips past ~25 deg.
// - Pen holes 12.5 mm (fits markers and fat pens), 34 deep, chamfered top.
// - Shields have a 45 deg underside and the hull flares < 12 deg: only the dragon jaw and tail curl need supports.
// Prints upright on its flat keel, NO supports (every underside <= 45 deg; carved grooves < 1 mm bridge).  p3d make longship_stand --brim --infill 15
$fn = 48;
L = 180;          // hull length (end to end, without the posts)
WB = 25;          // half width of the flat keel at mid-ship
WT = 32;          // half width at the gunwale at mid-ship
H0 = 38;          // gunwale height at mid-ship
RISE = 24;        // extra height at the ends (sheer line)
N = 4;            // clinker planks per side
STEP = 1.1;       // plank overlap step
ST = 41;          // stations along the hull

phone_len = 84;  phone_w = 13;  phone_dep = 14;  phone_y = -8;  lean = 15;
pen_d = 12.5;  pen_dep = 34;

function tn(i) = -1 + 2 * i / (ST - 1);
function sw(t) = max(0.06, pow(1 - pow(abs(t), 2.4), 0.55));   // width factor along the hull
function hh(t) = H0 + RISE * pow(abs(t), 3);                     // sheer line
// half-profile from keel to gunwale with clinker steps, as [y, z]
function prof(t) = let(s = sw(t), h = hh(t))
  [for (k = [0 : N - 1]) each [
    [(WB + (WT - WB) * pow(k / N, 0.8)) * s - (k ? STEP * s : 0), h * k / N],
    [(WB + (WT - WB) * pow((k + 1) / N, 0.8)) * s, h * (k + 1) / N - 0.01]
  ]];
function ring(i) = let(t = tn(i), p = prof(t), x = t * L / 2)
  concat([for (q = p) [x, q[0], q[1]]], [for (j = [len(p) - 1 : -1 : 0]) [x, -p[j][0], p[j][1]]]);
M = 4 * N;

module hull_body() {
  pts = [for (i = [0 : ST - 1]) each ring(i)];
  faces = concat(
    [for (i = [0 : ST - 2], j = [0 : M - 1]) [i * M + j, i * M + (j + 1) % M, (i + 1) * M + (j + 1) % M, (i + 1) * M + j]],
    [[for (j = [M - 1 : -1 : 0]) j]],
    [[for (j = [0 : M - 1]) (ST - 1) * M + j]]);
  polyhedron(pts, [for (f = faces) [for (k = [len(f) - 1 : -1 : 0]) f[k]]], convexity = 6);  // OpenSCAD wants clockwise from outside
}

// half width at the gunwale / at height z, position x
function ywt(x) = WT * sw(2 * x / L);
function yat(x, z) = let(t = 2 * x / L, f = z / hh(t)) (WB + (WT - WB) * pow(f, 0.8)) * sw(t);

module chain(pts) {   // smooth tube through [x, z, r] points (y thickness = 1.25 r)
  for (k = [0 : len(pts) - 2]) hull() for (p = [pts[k], pts[k + 1]])
    translate([p[0], 0, p[1]]) scale([1, 1.25, 1]) sphere(r = p[2], $fn = 24);
}

module dragon() {    // bow post: S-neck rising from the stem, head looking forward. Every underside <= 45 deg.
  x0 = L / 2;
  chain([[x0 - 10, -2, 3], [x0 - 2, 22, 4], [x0 - 4, 50, 5.5]]);   // stem / cutwater down to the keel
  chain([[x0 - 14, 50, 6], [x0 - 4, 56, 6.5], [x0 + 3, 68, 6], [x0 + 5, 80, 5.5], [x0 + 3, 90, 5.5], [x0 + 3, 100, 6]]);
  hull() { translate([x0 + 5, 0, 80]) scale([1, 1.25, 1]) sphere(r = 5.5, $fn = 24);     // throat carries the jaw
           translate([x0 + 12, 0, 92]) scale([1, 1.2, 1]) sphere(r = 4, $fn = 24); }
  hull() {                                                                              // head, mouth closed
    translate([x0 + 4, 0, 101]) scale([1.1, 1.1, 1]) sphere(r = 6.5, $fn = 32);
    translate([x0 + 12, 0, 92]) scale([1, 1.2, 1]) sphere(r = 4, $fn = 24);
    translate([x0 + 17, 0, 97]) sphere(r = 2.5, $fn = 20);
    translate([x0 + 20, 0, 101]) scale([1, 0.9, 1]) sphere(r = 3, $fn = 20);
  }
  for (s = [-1, 1]) hull() { translate([x0 + 2, s * 3.5, 105]) sphere(r = 2.4, $fn = 16);   // swept-back horns
                             translate([x0 - 2, s * 4.5, 117]) sphere(r = 1.2, $fn = 12); }
  for (s = [-1, 1]) hull() { translate([x0 + 6, s * 5.2, 104.5]) sphere(r = 1.4, $fn = 12);   // brow ridges
                             translate([x0 + 11, s * 3.6, 104]) sphere(r = 1.1, $fn = 12); }
  for (p = [[x0 - 2, 72], [x0 - 2, 82], [x0 - 3, 92]]) hull() {                          // mane spikes
    translate([p[0], 0, p[1]]) sphere(r = 3, $fn = 16);
    translate([p[0] - 3.5, 0, p[1] + 6.5]) sphere(r = 0.8, $fn = 8); }
}
module dragon_cuts() {
  x0 = L / 2;
  for (s = [-1, 1]) {
    translate([x0 + 8, s * 7.0, 102]) sphere(r = 1.8, $fn = 16);                          // eyes
    translate([x0 + 22.3, s * 1.8, 102.5]) sphere(r = 0.9, $fn = 10);                       // nostrils
    hull() { translate([x0 + 20, s * 2.8, 98.6]) sphere(r = 0.7, $fn = 8);              // mouth line
             translate([x0 + 10, s * 5.0, 96.5]) sphere(r = 0.7, $fn = 8); }
  }
}

VC = [-L / 2 + 2, 92];  VR = 9;   // stern volute centre (x, z) and radius
module tail() {      // stern post rising into a carved spiral scroll (teardrop: point down, no overhang > 45)
  x0 = -L / 2;
  chain([[x0 + 10, -2, 3], [x0 + 2, 22, 4], [x0 + 4, 50, 5.5]]);
  chain([[x0 + 14, 50, 6], [x0 + 4, 58, 6.5], [x0 + 2, 70, 6], [x0 + 2, 80, 5.5]]);   // straight up over the hull end
  translate([VC[0], 0, VC[1]]) rotate([90, 0, 0]) hull() {
    linear_extrude(10, center = true) offset(-1) tear();
    linear_extrude(12, center = true) offset(-2.2) tear();
  }
}
module tear() { hull() { circle(r = VR, $fn = 48); translate([0, -VR * 1.414]) circle(r = 0.5, $fn = 8); } }
module tail_cuts() {  // spiral groove on both faces
  for (s = [-1, 1]) for (k = [0 : 33]) hull() for (j = [k, k + 1]) let(a = j * 20, r = 7.2 - j * 0.17)
    translate([VC[0] + r * cos(a), s * 5.6, VC[1] + r * sin(a)]) sphere(r = 0.9, $fn = 8);
}

module shield(x) {   // round shield: 45 deg chamfer underneath, carved rim ring, cone boss (no overhang > 45)
  z = hh(2 * x / L) - 9;
  for (s = [-1, 1]) {
    y = yat(x, z - 9.6) - 0.3;           // back plane sits inside the flared hull everywhere
    translate([x, s * y, z]) rotate([s * -90, 0, 0]) difference() {
      union() {
        hull() { cylinder(r = 8, h = 3.2); translate([0, s * 14.4, -3.2]) cylinder(r = 0.6, h = 0.01); }   // 45 deg wedge buried in the hull
        translate([0, 0, 3.2]) cylinder(r1 = 2.6, r2 = 0.9, h = 1.7, $fn = 24);          // boss
      }
      translate([0, 0, 2.6]) difference() { cylinder(r = 7.0, h = 1); cylinder(r = 6.2, h = 1); }   // rim ring
      for (a = [0 : 90 : 270]) rotate(a + 45) translate([3.4, -0.35, 2.7]) cube([2.6, 0.7, 1]); // 4 spokes
    }
  }
}

SHIELDS = true;
pens = [[52, -9], [52, 9], [66, -8], [66, 8], [79, 0], [-52, -9], [-52, 9], [-66, -8], [-66, 8], [-79, 0]];

rotate([0, 0, 45]) difference() {   // diagonal on the bed: ~215 mm long overall
  intersection() { translate([-200, -200, 0]) cube(400); union() {   // flat on the bed
    hull_body();
    dragon();
    tail();
    if (SHIELDS) for (x = [-60 : 15 : 60]) shield(x);
  } }
  translate([0, phone_y, H0 - phone_dep]) rotate([-lean, 0, 0]) {   // phone slot, leaning back
    translate([-phone_len / 2, -phone_w / 2, 0]) cube([phone_len, phone_w, 60]);
    translate([0, 0, phone_dep / cos(lean) - 1.5]) hull() {          // lead-in chamfer
      translate([-phone_len / 2, -phone_w / 2, 0]) cube([phone_len, phone_w, 0.01]);
      translate([-phone_len / 2 - 2, -phone_w / 2 - 2, 4]) cube([phone_len + 4, phone_w + 4, 0.01]);
      translate([-phone_len / 2 - 6, -phone_w / 2 - 6, 8]) cube([phone_len + 12, phone_w + 12, 0.01]);
    }
  }
  for (p = pens) {
    top = hh(2 * p[0] / L);
    translate([p[0], p[1], top - pen_dep]) cylinder(d = pen_d, h = pen_dep + 20);   // through the sloped deck
    translate([p[0], p[1], top - 1.2]) cylinder(d1 = pen_d, d2 = pen_d + 12, h = 6);  // countersink, follows the slope
  }
  dragon_cuts();
  tail_cuts();
}
