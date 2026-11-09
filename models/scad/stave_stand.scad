// STAVE STAND (phone stand V2) - stave-church diagrid panel, 4 angles, charge while standing.
//  - Angle: a strut drops into one of 4 grooves in the base (55 / 63 / 71 / 80 deg). Lift the phone, move the foot.
//  - Pivot: panel pins sit in open U-seats in the two cheeks (lift out = flat-pack for travel).
//  - Charging: the plug hangs into a 20 mm well between the sills; the cable runs back under the panel
//    in a tunnel + floor channel and leaves at the back.
//  - Diagrid (triangulated) panel = stiff + light; gable top with crossed dragon-horn bargeboards; rune plaque.
// All parts print flat, no supports. Panel prints front face DOWN (smooth PEI texture against the phone).
// part = "plate1" (base + panel) | "plate2" (strut) | "base" | "panel" | "strut" | "assembly"
part  = "plate1";
angle = 63;               // assembly view only: one of angles[]

angles = [55, 63, 71, 80];
pw = 86;   pt = 6;   ph = 118;  gable = 24;   // panel: width (phones up to ~84 mm with case), thickness, length
bt = 5;    hs = 20;                            // base thickness, plug-well depth
sill_top = bt + hs;
hz = sill_top + 4;                             // pivot axis height
pin_r = 3; pin_l = 6;  clr = 0.6;
ch_in = pw/2 + clr;  ch_t = 6;  ch_out = ch_in + ch_t;
well = 16;                                     // half width of plug well / cable tunnel
fence_y = -30;  plaque_y = -44;
Lb = 72;                                       // strut seat on the panel, from the pivot
s  = 105;                                      // strut length, nose centre to foot centre
gr = 3.3;                                      // groove radius (strut ends are r 3)
zf = bt + 0.5;                                 // foot centre height in its groove
leg = [16, 24];                                // strut leg x range (cable runs between the legs)
$fn = 48;

function N(a) = [Lb*cos(a) + 3.5*sin(a), hz + Lb*sin(a) - 3.5*cos(a)];   // strut nose centre (y,z)
function G(a) = N(a)[0] + sqrt(s*s - pow(N(a)[1] - zf, 2));             // foot groove y
back_y = G(angles[0]) + 12;
echo(grooves = [for (a = angles) G(a)], base_len = back_y - plaque_y);

// ---------- runes (strokes in a 4 x 8 cell; the Runic font does not render in OpenSCAD) ----------
module stroke(a, b, w = 1.3) hull() { translate(a) circle(d = w, $fn = 12); translate(b) circle(d = w, $fn = 12); }
stav = [   // Elder Futhark S T A W ("stav" = stave)
  [[[3,8],[0,5.5]], [[0,5.5],[3,2.5]], [[3,2.5],[0,0]]],
  [[[2,0],[2,8]], [[2,8],[0,6]], [[2,8],[4,6]]],
  [[[0,0],[0,8]], [[0,8],[3,6]], [[0,5],[3,3]]],
  [[[0,0],[0,8]], [[0,8],[3,6]], [[3,6],[0,4]]]];
algiz = [[[2,0],[2,8]], [[2,4],[0,8]], [[2,4],[4,8]]];
module runes(list) for (i = [0 : len(list) - 1]) translate([i * 8, 0]) for (sg = list[i]) stroke(sg[0], sg[1]);

// ---------- base ----------
module cheek2d() difference() {
  hull() { translate([-16, 0]) square([30, 1]); translate([0, hz]) circle(r = 9); }
  translate([0, hz]) circle(r = pin_r + 0.3);
  translate([-(pin_r + 0.3), hz]) square([2*(pin_r + 0.3), 20]);
}
module base() difference() {
  union() {
    linear_extrude(bt) offset(r = 8) offset(delta = -8)
      translate([-ch_out, plaque_y]) square([2*ch_out, back_y - plaque_y]);
    for (m = [0, 1]) mirror([m, 0, 0]) {
      translate([well, fence_y, 0]) rotate([90, 0, 90]) linear_extrude(ch_in - well)       // sills, sloped back
        polygon([[0, 0], [-2 - fence_y, 0], [-2 - fence_y, sill_top - 6], [-2 - fence_y - 6, sill_top], [0, sill_top]]);
      translate([well, fence_y - 3, 0]) cube([ch_in - well, 3.01, sill_top + 8]);         // phone lip
      translate([ch_in, 0, 0]) rotate([90, 0, 90]) linear_extrude(ch_t) cheek2d();         // pivot cheeks
    }
    translate([-15, (plaque_y + fence_y - 3)/2 - 4, bt - 0.01]) linear_extrude(0.8) runes(stav);
  }
  for (a = angles) translate([0, G(a), zf]) rotate([0, 90, 0]) cylinder(r = gr, h = 2*leg[1] + 6, center = true);
  translate([-4, fence_y, bt - 2]) cube([8, back_y - fence_y + 10, 3]);                    // cable channel
}

// ---------- panel (local: x across, y up the panel from the pivot, z = normal, +z = phone side) ----------
module panel_outline() {
  translate([-pw/2, 0]) square([pw, ph]);
  polygon([[-pw/2, ph - 0.01], [pw/2, ph - 0.01], [0, ph + gable]]);
}
module diagrid() translate([0, ph/2]) for (sg = [-1, 1]) for (i = [-6:6])
  rotate(sg*28) translate([i*21, 0]) square([3.4, 400], center = true);
module horns() {
  apex = [0, ph + gable];  e = [pw/2, ph];  d = (apex - e) / norm(apex - e);  tip = apex + 13*d;
  for (m = [0, 1]) mirror([m, 0]) {
    hull() { translate(e - [2, 0]) circle(r = 2.6); translate(apex) circle(r = 2.6); }
    hull() { translate(apex) circle(r = 2.6); translate(tip + [0, 4]) circle(r = 1.2); }   // crossed horn, upswept
  }
}
module panel2d() {
  fw = 6;
  difference() {
    panel_outline();
    difference() {
      translate([-pw/2 + fw, fw]) square([pw - 2*fw, ph - 2*fw]);
      diagrid();
      translate([-pw/2, Lb - 7]) square([pw, 14]);                                         // strut seat beam
    }
    polygon([[-16, ph + 3], [16, ph + 3], [0, ph + gable - 8]]);                            // gable window
  }
  horns();
}
module panel() difference() {
  union() {
    translate([0, 0, -pt/2]) linear_extrude(pt) panel2d();
    rotate([0, 90, 0]) cylinder(r = pin_r, h = pw + 2*(clr + pin_l) - 1, center = true);  // pivot pins
  }
  translate([0, Lb, -pt/2 - 0.5]) rotate([0, 90, 0]) cylinder(r = gr, h = 2*leg[1] + 4, center = true); // strut seat
}

// ---------- strut (local: x across, y from foot (0) to nose (s), z 0..6) ----------
module bar(x0, x1, y0, y1) hull() for (y = [y0, y1]) translate([x0, y, 3]) rotate([0, 90, 0]) cylinder(r = 3, h = x1 - x0);
module strut() {
  for (m = [0, 1]) mirror([m, 0, 0]) bar(leg[0], leg[1], 0, s);                            // legs
  bar(-leg[1], leg[1], s - 8, s);                                                           // nose beam
  bar(-leg[1], leg[1], 0, 0.01);                                                            // foot beam
  linear_extrude(5) {
    for (sg = [-1, 1]) hull() { translate([sg*leg[0], 18]) circle(r = 2.5); translate([-sg*leg[0], s - 18]) circle(r = 2.5); }
    translate([0, s/2]) circle(r = 9);                                                      // shield boss
  }
  translate([-2, s/2 - 4, 5 - 0.01]) linear_extrude(0.8) runes([algiz]);
}

// ---------- views ----------
module assembly(a) {
  color("white") base();
  color("gainsboro") translate([0, 0, hz]) rotate([a, 0, 0]) panel();
  F = [G(a), zf];  n = N(a);  phi = atan2(n[1] - F[1], n[0] - F[0]);
  color("silver") translate([0, F[0], F[1]]) rotate([phi, 0, 0]) translate([0, 0, -3]) strut();
}
module panel_flat() translate([0, 0, pt/2]) mirror([0, 0, 1]) panel();                      // phone side down

if (part == "base") base();
else if (part == "panel") panel_flat();
else if (part == "strut") strut();
else if (part == "assembly") assembly(angle);
else if (part == "plate1") {
  translate([-52, -(back_y + plaque_y)/2, 0]) base();
  translate([52, -(ph + gable)/2 - 4, 0]) panel_flat();
}
else if (part == "plate2") translate([0, -s/2, 0]) strut();
