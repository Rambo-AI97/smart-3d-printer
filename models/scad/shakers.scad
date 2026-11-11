// Ornate salt & pepper shakers (Victorian / baroque), sized for COARSE pepper and kosher salt.
// Pepper: tall hourglass tower, straight fluting, diamond band, 5 x 4.2 mm holes.
// Salt:   shorter teardrop, swirled gadroons, fine neck flutes, 7 x 3.8 mm holes.
// Bottom-loading: 30 mm screw cap (P3, 45 deg flanks, 0.3 mm radial clearance), wide plinth base.
// FDM / PETG: every surface <= 45 deg (checked by echo), walls >= 2.4 mm, no supports anywhere.
// Holes: 90 deg countersink on top, 45 deg funnel lead-in underneath (short 3.4 mm bore, no clogging).
// Print: body upright on its foot ring WITH BRIM, one body per plate, centre of bed; cap flange-down. License CC BY-SA 4.0.
kind = "pepper";   // "pepper" | "salt"
part = "plate";    // "body" | "cap" | "plate" (all 4 parts) | "pair" (assembled) | "cut" (cut-away) | "fit"
n  = 240;          // segments around (smooth diamond edges)
dz = 0.4;          // ring spacing
wall = 2.4;
clear = 0.3;       // radial thread clearance (PETG)

// ---- thread ----
P = 3; th = 1.2;  Rmin = 13.5;  Rmax = Rmin + th;  Lt = 10;   // female length in body
cap_t = 4;  spig = 9;                                         // cap flange thickness, spigot length

// ---- per-kind design: profile [z, r], beads z, flutes [z0,z1,N,amp,twist], diamonds [zc,N,wz,D] ----
PEP = [[0,24.6],[0.8,25],[4,25],[6,23.6],[9,21.4],[12,20.6],[16,19.2],[24,17.2],[34,15.3],[44,13.9],[52,13.5],
       [60,13.9],[68,15],[76,16.2],[84,16.6],[90,16.2],[95,14.8],[99,13.4],[103,13],[107,13.8],[110,14.6]];
SAL = [[0,26.6],[0.8,27],[4,27],[6,25.6],[9,24.6],[14,25.6],[22,27.2],[30,27.2],[38,25.2],[46,21.6],[54,17.6],
       [60,15.2],[66,14.2],[72,14.2],[78,14.8],[83,15.8],[88,16.6]];
prof  = kind == "pepper" ? PEP : SAL;
H     = prof[len(prof) - 1][0];
beads = kind == "pepper" ? [5.2, 13, 52, 72.5, 91.5, 101] : [5.2, 11, 45, 68, 77];
flutes = kind == "pepper" ? [[14.5, 50.5, 16, 1.1, 0], [93, 99.5, 16, 0.6, 0]]
                          : [[12.5, 43.5, 12, 1.6, 34], [47, 66.5, 20, 0.6, 0]];
dias  = kind == "pepper" ? [[82, 8, 6.8, 1.0], [62, 16, 3.2, 0.7]] : [[82, 12, 3.4, 0.8], [56, 12, 3, 0.7]];
holes = kind == "pepper" ? [5, 4.2, 6.0] : [7, 3.8, 7.0];    // count (1 centre + ring), diameter, ring radius
rcyl  = kind == "pepper" ? 10 : 11;                          // lead-in zone radius (keeps neck wall >= 2.4)
zap   = H - 2.6;                                             // chamber apex (45 deg roof)

// ---- smooth profile (Catmull-Rom) ----
function seg(Q, z, i = 0) = (i >= len(Q) - 2 || z < Q[i + 1][0]) ? i : seg(Q, z, i + 1);
function base_r(z) = z < 0.8 ? prof[0][1] + (prof[1][1] - prof[0][1]) * max(0, z) / 0.8 : base_r_s(z);   // linear 45 deg foot chamfer
function base_r_s(z) = let(Q = prof, i = seg(Q, z), m = len(Q),
    p0 = Q[max(i - 1, 0)][1], p1 = Q[i][1], p2 = Q[i + 1][1], p3 = Q[min(i + 2, m - 1)][1],
    t = max(0, min(1, (z - Q[i][0]) / (Q[i + 1][0] - Q[i][0]))))
  0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (3 * p1 - p0 - 3 * p2 + p3) * t * t * t);

function clamp01(x) = max(0, min(1, x));
function bead(z) = max([for (b = beads) 0.9 * clamp01(1 - abs(z - b) / 1.3)]);       // V rings, 35 deg flanks
function flute(t, z) = max([for (f = flutes) (z < f[0] || z > f[1]) ? 0 :
    let(u = (z - f[0]) / (f[1] - f[0]), env = clamp01(3 * sin(180 * u)),
        c = 0.5 + 0.5 * cos(f[2] * (t + f[4] * u)))
    f[3] * env * pow(c, 1.4)]);
function dia(t, z) = max([for (d = dias) let(
    w = 360 / d[1], a = (t / w + 0.5) - floor(t / w + 0.5) - 0.5,                  // -0.5..0.5 of a cell
    s = 1 - (2 * abs(a) + abs(z - d[0]) / d[2]))
    d[3] * clamp01(3 * s)]);                                                        // flat-topped diamonds
function outer_r(t, z) = base_r(z) + max(bead(z), flute(t, z), dia(t, z));

// ---- mesh helpers ----
module lathe(f, zs, nn) {
  m = len(zs);
  pts = [for (z = zs) for (i = [0:nn - 1]) let(t = i * 360 / nn, r = f(t, z)) [r * cos(t), r * sin(t), z]];
  side = [for (k = [0:m - 2]) for (i = [0:nn - 1]) let(a = k * nn + i, b = k * nn + (i + 1) % nn)
            each [[a, a + nn, b + nn], [a, b + nn, b]]];
  polyhedron(pts, concat([[for (i = [0:nn - 1]) i]], [[for (i = [nn - 1:-1:0]) (m - 1) * nn + i]], side));
}
function zlist(a, b, s) = [for (i = [0:ceil((b - a) / s)]) min(b, a + i * s)];

// interior: inset by wall, 45 deg roof to apex, then clamped so no ceiling is steeper than 45 deg
zin  = zlist(Lt - 0.5, zap - 0.3, 0.5);
raw  = [for (z = zin) min(base_r(z) - wall, zap - z)];
rin  = [for (k = [0:len(zin) - 1]) min([for (j = [k:len(zin) - 1]) raw[j] + zin[j] - zin[k]])];
function rin_at(z) = let(k = max(0, min(len(zin) - 2, floor((z - zin[0]) / 0.5))),
                         u = (z - zin[k]) / (zin[k + 1] - zin[k])) rin[k] + (rin[k + 1] - rin[k]) * u;

// thread solid (right-hand), profile: 45 deg flanks, 0.3 flats
function tprof(u) = let(v = u - floor(u), a = 0.3 / P, b = th / P)
  v < a ? 0 : v < a + b ? (v - a) / b : v < 2 * a + b ? 1 : v < 2 * a + 2 * b ? 1 - (v - 2 * a - b) / b : 0;
module thread(off, z0, z1) lathe(function(t, z) Rmin + off + th * tprof(z / P - t / 360), zlist(z0, z1, 0.25), 120);

// ---- parts ----
module body() {
  difference() {
    lathe(function(t, z) outer_r(t, z), zlist(0, H, dz), n);
    lathe(function(t, z) rin_at(z), zin, 96);                                    // chamber
    thread(clear, -1, Lt);                                                       // female thread
    translate([0, 0, -0.01]) cylinder(r1 = Rmax + clear + 1, r2 = Rmax + clear - 0.6, h = 1.6, $fn = 96); // entry chamfer
    for (p = hole_pts()) translate([p[0], p[1], 0]) {
      translate([0, 0, zap - 20]) cylinder(d = holes[1], h = 30, $fn = 32);                          // bore
      translate([0, 0, H - 1]) cylinder(d1 = holes[1], d2 = holes[1] + 2.2, h = 1.02, $fn = 32);     // countersink
    }
    intersection() {                                                             // 45 deg funnels under each hole
      cylinder(r = rcyl, h = H, $fn = 96);
      for (p = hole_pts()) translate([p[0], p[1], H - 3.4 - 12])
        cylinder(r1 = holes[1] / 2 + 12, r2 = holes[1] / 2, h = 12, $fn = 32);
    }
  }
  rt = base_r(H);                                                                // pearl rim on the crown
  np = floor(2 * PI * (rt - 1.5) / 2.7);
  for (i = [0:np - 1]) rotate(i * 360 / np) translate([rt - 1.5, 0, H]) sphere(d = 2.0, $fn = 16);
}
function hole_pts() = concat([[0, 0]], [for (i = [0:holes[0] - 2]) let(a = 90 + i * 360 / (holes[0] - 1)) holes[2] * [cos(a), sin(a)]]);

module cap() {
  rf = base_r(1);
  difference() {
    union() {
      lathe(function(t, z) rf - max(0, 0.6 - z) - max(0, z - (cap_t - 0.6)) + 0.45 * pow(0.5 + 0.5 * cos(40 * t), 2),
            zlist(0, cap_t, 0.2), n);                                            // knurled plinth, chamfered both edges
      intersection() {
        thread(0, cap_t - 0.01, cap_t + spig);
        cylinder(r1 = Rmax + spig, r2 = Rmax - 1.2, h = cap_t + spig, $fn = 96); // tapered lead-in at the tip
      }
    }
    translate([0, 0, 2]) cylinder(r = Rmin - 3, h = 30, $fn = 96);               // hollow spigot = more room inside
  }
}

module fit() { intersection() { body(); cylinder(r = 60, h = Lt + 3); } }        // 13 mm thread test ring

check_slope = max([for (z = zlist(0, H - 0.4, 0.2)) for (i = [0:3:n - 1]) let(t = i * 360 / n)
                   outer_r(t, z + 0.2) - outer_r(t, z)]) / 0.2;
check_in    = max([for (k = [0:len(zin) - 2]) rin[k] - rin[k + 1]]) / 0.5;
echo(kind = kind, H = H, max_outer_overhang_slope = check_slope, max_inner_ceiling_slope = check_in,
     min_wall_at_thread = base_r(Lt) - Rmax - clear, foot_d = 2 * base_r(1));

if (part == "body") body();
else if (part == "cap") cap();
else if (part == "fit") fit();
else if (part == "pair") { color("dimgray") translate([0, 0, cap_t]) body(); color("gray") cap(); }
else if (part == "cut") difference() { union() { translate([0, 0, cap_t]) body(); cap(); } translate([0, -100, -1]) cube(200); }
else if (part == "plate") echo("plate: use shakers_plate.scad");
