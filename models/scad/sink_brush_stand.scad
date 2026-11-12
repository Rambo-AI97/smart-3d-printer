// Free-standing dish brush stand V2 (no clip). Stands on the counter / sink ledge
// at the edge; the brush lies tilted 30 deg, head down and out over the basin.
// Drop the brush into both U cradles (flared lead-ins): it slides downhill until
// the handle's shoulder stops on the front fork, so it can't slip out. Its weight
// sits between the cradles, so the stand can't tip forward.
// Water runs down the handle toward the head and drips into the sink.
// Looks (pepper-shaker family): stepped diamond bands + bead lines on the spine and base, fluted back waist,
// waisted gothic spine with twin lancet windows + quatrefoil oculus under a
// recessed pointed arch, triquetra, stepped plinth base.
// Prints upright, base on the bed, no supports (all window tops are pointed).
// part = "print" (default) | "use" (with a ghost brush).
part = "print";

ang   = 30;     // brush tilt
hF    = 55;     // front cradle floor height (keeps the bristles above the counter)
span  = 95;     // front fork -> back cradle, along the brush
neckU = 16;     // front U (neck 13 mm measured; the 28 mm handle stops on it)
handU = 32;     // back U (handle 28 mm measured)
fin   = 8;      // spine thickness
rec   = 1.2;    // tracery arch recess per face
deb   = 0.8;    // debossed ornament depth
$fn = 48;

module lens(c1, c2, R) intersection() { translate(c1) circle(R); translate(c2) circle(R); }
module triquetra(d, w) {
  R = d / 2 / 1.155; c = [for (k = [0:2]) R / sqrt(3) * [cos(90 + 120 * k), sin(90 + 120 * k)]];
  for (k = [0:2]) difference() { lens(c[k], c[(k + 1) % 3], R); offset(-w) lens(c[k], c[(k + 1) % 3], R); }
  difference() { circle(d = d * 0.62); circle(d = d * 0.62 - 2 * w); }
}
// pointed (equilateral) arch: width w, straight sides up to h, apex above
module parch(w, h) {
  translate([-w / 2, 0]) square([w, h]);
  translate([0, h]) intersection() {
    translate([-w / 2, 0]) circle(w, $fn = 96); translate([w / 2, 0]) circle(w, $fn = 96);
    translate([-w / 2, 0]) square([w, w]);
  }
}
module quatrefoil(d) { for (a = [0:90:270]) rotate(a + 45) translate([d / 4, 0]) circle(d = d / 2, $fn = 32); circle(d = d / 2.2, $fn = 32); }

// brush frame: x along the brush toward the head, z=0 = the surface the brush rests on
module frame() translate([0, 0, hF]) rotate([0, ang, 0]) children();
function fw(x, z) = [x * cos(ang) + z * sin(ang), hF - x * sin(ang) + z * cos(ang)]; // frame -> world (x,z)

module rbox(a, b, r = 2) hull() for (x = [a[0] + r, b[0] - r], y = [a[1] + r, b[1] - r], z = [a[2] + r, b[2] - r])
  translate([x, y, z]) sphere(r, $fn = 16);
module block(x, w, t) rbox([x - t / 2, -w / 2, -10], [x + t / 2, w / 2, 12]);
module slice(x, t) rbox([x - t / 2, -fin / 2, -10], [x + t / 2, fin / 2, -5]);
module cradle(x, w, t) hull() { frame() block(x, w, t); translate([0, 0, -25]) frame() slice(x, t); }

// U cut with a flared lead-in at the top
module ucut(x, u, t) frame() translate([x - t, 0, 0]) {
  hull() {
    for (y = [-u / 2 + 3, u / 2 - 3]) translate([0, y, 3]) rotate([0, 90, 0]) cylinder(r = 3, h = 2 * t);
    translate([0, -u / 2, 8]) cube([2 * t, u, 0.1]);
  }
  hull() {
    translate([0, -u / 2, 8]) cube([2 * t, u, 0.1]);
    translate([0, -u / 2 - 4, 13]) cube([2 * t, u + 8, 6]);
  }
}

// base: stepped plinth
bx0 = -104; bx1 = 20; bw = 68;
module base2d(o = 0) offset(o) offset(10) offset(-10) translate([bx0, -bw / 2]) square([bx1 - bx0, bw]);
module plinth() {
  hull() { translate([0, 0, 0.6]) linear_extrude(2.4) base2d(); linear_extrude(0.6) base2d(-0.6); }   // anti elephant foot
  hull() { linear_extrude(3) base2d(-1); translate([0, 0, 3]) linear_extrude(0.01) base2d(-1); }
  hull() { linear_extrude(4.2) base2d(-4); linear_extrude(5) base2d(-5); }                            // upper step, chamfered
}

// spine profile in world (x, z)
ft = fw(0, -5); bk = fw(-span, -5);
module spine2d() offset(r = 6) offset(delta = -6) difference() {      // round the convex corners
  union() {
    offset(r = -14) offset(delta = 14) union() {                       // flared fillets into the base
      polygon([[bx0 + 6, 1], [bx1 - 6, 1], [10, ft[1]], ft, bk, [bk[0] - 8, bk[1] - 4]]);
      translate([bx0 + 2, 0]) square([bx1 - bx0 - 4, 5]);
    }
  }
  translate([-150, 54]) circle(70, $fn = 160);                         // waisted back
}
module window2d() translate([-50, 0]) parch(34, 20);                  // the recessed outer arch
module tracery2d() translate([-50, 0]) {
  for (s = [-1, 1]) translate([s * 8.5, 3]) parch(11, 17);            // twin lancets
  translate([0, 39]) quatrefoil(11);                                   // oculus
}
module onface(d) for (s = [-1, 1]) translate([0, s * (fin / 2 - d), 0]) rotate([90, 0, 0])
  linear_extrude(2 * d + 0.02, center = true) children();
module through() rotate([90, 0, 0]) linear_extrude(fin + 2, center = true) children();

// raised pattern on both spine faces
module onraise(h) for (s = [-1, 1]) translate([0, s * (fin / 2 + h / 2 - 0.01), 0]) rotate([90, 0, 0])
  linear_extrude(h + 0.02, center = true) children();
module local2d() translate([0, hF]) rotate(-ang) children();     // brush frame -> world (x,z)
module diamond(d) rotate(45) square(d / sqrt(2), center = true);
dp = 7.2;                                                         // diamond pitch
module diamondband(d) local2d() for (x = [-span + 13 : dp : -11]) translate([x, -12]) diamond(d);
module beadlines() local2d() for (z = [-7.6, -16.4]) translate([-span + 9, z - 0.7]) square([span - 16, 1.4]);
// base top: a diamond band with bead lines down each long side
module baseband(d, beads = true) for (sy = [-1, 1]) translate([0, sy * 22]) {
  for (x = [-93 : dp : 12]) translate([x, 0]) diamond(d);
  if (beads) for (y = [-4.4, 4.4]) translate([-97, y - 0.7]) square([111, 1.4]);
}

module stand() difference() {
  union() {
    plinth();
    rotate([90, 0, 0]) linear_extrude(fin, center = true) spine2d();
    cradle(0, neckU + 14, 12);
    cradle(-span, handU + 14, 14);
    // pepper-shaker patterns, raised
    onraise(0.6) intersection() { offset(-1.5) spine2d(); union() { diamondband(6.4); beadlines(); } }
    onraise(1.2) intersection() { offset(-1.5) spine2d(); diamondband(3.6); }                 // stepped facet
    translate([0, 0, 5 - 0.01]) { linear_extrude(0.6) baseband(6.4); linear_extrude(1.2) baseband(3.6, false); }
  }
  ucut(0, neckU, 12);
  ucut(-span, handU, 14);
  // tracery: recessed arch with a 2 mm raised frame, lancets + oculus cut through
  onface(rec) translate([0, 12]) difference() { offset(-2) window2d(); }
  through() translate([0, 12]) tracery2d();
  // fluted column on the back waist
  onface(deb) intersection() { offset(-2.5) spine2d(); for (i = [0:6]) translate([-97 + i * 4, 10]) offset(0.75) square([0.01, 34]); }
  // triquetra between the arch and the front fork
  onface(deb) translate([-21, 24]) triquetra(16, 1.4);
}

if (part == "use") {
  stand();
  %frame() {
    translate([0, 0, 6.5]) rotate([0, 90, 0]) cylinder(d = 13, h = 30);                       // neck
    translate([30, 0, 6.5]) rotate([0, 90, 0]) cylinder(d = 50, h = 12);                      // head
    translate([42, 0, 6.5]) rotate([0, 90, 0]) cylinder(d1 = 50, d2 = 62, h = 40);            // bristles
    translate([-6, 0, 7]) scale([1, 1, 0.5]) rotate([0, -90, 0]) cylinder(d = 28, h = 170);   // handle
  }
} else stand();
