// Ornate slide-on bag clip (2026-11-12, V2 built in). Upside-down U like a bread tag but for any
// bag: fold or twist the bag top, push the clip down over it. No hinge, no latch, ~25 min on the Ender.
// - Prongs converge (0.9 mm gap at the root -> 0.45 at the tips; tighter fuses when printing): they spring apart on the bag.
// - Interlocking teeth inside: the bag runs in a zigzag and can't slide out.
// - Flared tips = lead-in, stress-relief hole at the root so the U flexes instead of cracking.
// - Head: Norse triquetra with a ring, tips welded into the ring + flared neck (load path, not decoration only) (house style, like the rattle); doubles as pull grip + hang loop.
// - Optional braid chevrons on the outer faces (braid_on; off = fast).
// Prints flat (profile in XY), no supports. PETG.
//   p3d slice bag_slide_clip.stl --walls 3 --infill 40 --keep-orient   (solid prongs)
$fn = 64;
braid_on = false;   // engraved braid on the outer faces: +10 min per clip
part = "one";     // "one" | "set" (4 on a plate)
H   = 8;          // clip height (print Z) = grip width on the bag
Lp  = 36;         // prong length
p   = 2.8;        // prong thickness
g0  = 0.9;        // gap at the root
g1  = 0.45;       // gap at the tips
th  = 0.7;        // tooth height
tp  = 4;          // tooth pitch
R   = 11;         // triquetra outer size
lw  = 1.8;        // knot line width

// prong i = -1 (left) / +1 (right). Both inner faces follow one zigzag centre line, so the gap
// is a wavy channel g1..g0 wide; the bag is bent around every tooth.
ix = function(y) (g1 + (g0 - g1) * y / Lp) / 2;
cz = function(k) (k % 2 == 0 ? 1 : -1) * th / 2;
n  = floor((Lp - 3) / (tp / 2));
module prong(i) {
  inner = [for (k = [1 : n]) let(y = 2 + k * tp / 2) [cz(k) + i * ix(y), y]];
  polygon(concat(
    [[i * (ix(0) + 1.4), 0], [i * ix(2), 2]],             // flared tip (lead-in)
    inner,
    [[i * ix(Lp), Lp], [i * (ix(Lp) + p), Lp], [i * (ix(0) + p), 0.8], [i * (ix(0) + p - 0.8), 0]]));
}

module vesica(r, d) intersection() { translate([-d, 0]) circle(r); translate([d, 0]) circle(r); }

module triquetra() {
  r = R * 0.62; d = R * 0.36;
  for (a = [90, 210, 330]) rotate(a) translate([R * 0.42, 0]) rotate(90)
    difference() { vesica(r, d); offset(-lw) vesica(r, d); }
  difference() { circle(R * 0.55); circle(R * 0.55 - lw); }
}

module profile() {
  difference() {
    union() {
      prong(-1); prong(1);
      // root block joining the prongs
      translate([-(g0 / 2 + p), Lp - 0.01]) square([g0 + 2 * p, 4]);
      // flared neck: spreads pull/twist load from the prongs into the ring
      polygon([[-(g0 / 2 + p), Lp + 0.5], [g0 / 2 + p, Lp + 0.5], [7, Lp + 4.6], [-7, Lp + 4.6]]);
      // neck + head
      translate([0, Lp + 3 + R]) {
        triquetra();
        difference() { circle(R + 0.6); circle(R + 0.6 - lw); }   // outer ring
        // welds: each knot tip fused into the ring over ~4 mm, not a tangent touch
        for (a = [90, 210, 330]) rotate(a) translate([R * 0.86, 0]) circle(d = 3.8);
      }
    }
    translate([0, Lp]) circle(d = 1.6);   // stress relief at the root of the slot
    translate([-g0 / 2, Lp - 1]) square([g0, 1]);
  }
}

// braid chevrons on an outer face (x = xo, facing +x if i = 1)
module braid(i) {
  xo = i * (g1 / 2 + p);
  for (y = [4 : 4.5 : Lp - 3], s = [-1, 1])
    translate([xo, y, H / 2]) rotate([0, 0, 0]) rotate([s * 40, 0, 0])
      cube([1.0, 0.8, H * 1.6], center = true);
}

module clip() {
  difference() {
    linear_extrude(H) profile();
    if (braid_on) { braid(-1); braid(1); }
    // keep the chevrons off the top/bottom edges
  }
}

if (part == "one") clip();
else for (i = [0:3]) translate([(i - 1.5) * 30, 0, 0]) clip();
