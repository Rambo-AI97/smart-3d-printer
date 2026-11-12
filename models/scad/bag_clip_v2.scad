// Bread bag clip V2 (2026-11-12): the hinged snap-latch chip clip at 60 mm. Replaces bag_slide_clip (too loose:
// a slide-on U cannot clamp). Fold the bag top flat, close the jaw, press the lip: it snaps and holds with preload.
// Research: print-in-place bag clips mostly fail at the hinge (same break point, even PETG 4 walls) or fuse at
// the hinge -> flex-loop hinge, no pin; printed open so nothing can fuse. Base: chip_clip.scad (idea #21).
// - Printed OPEN (top jaw 15 deg up) so the latch lip never overlaps the jaw; the round
//   flex loop is the hinge (no pin to wear out).
// - Ridge on the top jaw into a groove in the bottom jaw: bag is pinched in a zigzag, won't slide.
// - U-spring snap latch pulls the jaws 0.4 mm past the print gap (preload); flick the thumb tab out to open.
// - Rounded jaw tips (no bag snags), chamfered lip = press-to-close ramp.
// Prints flat (profile in XY, 10 mm tall): layers run along the loop, so the hinge flexes
// across strands, not between layers. PETG.
//   p3d slice chip_clip.stl --walls 4 --infill 40 --keep-orient
$fn = 72;
part = "one";      // "set" (60/90/120 + 90) | "one"
L    = 60;         // jaw length for part="one"
H    = 10;         // clip height (print Z)
T    = 4.5;        // jaw thickness
G    = 0.6;        // jaw gap as printed (closed pose)
pre  = 0.4;        // latch preload
w    = 1.7;        // hinge loop wall
th   = 15;         // print-open angle
ym   = T + G / 2;  // hinge centre height
yt   = 2 * T + G;  // top of top jaw (closed)

module bottom_jaw(L) {
  difference() {
    union() {
      square([L, T]);
      // U-spring latch: stub down, foot, long bar up (17 mm flex length, ~1.3 % strain)
      translate([L - 4, -6]) square([4, 6 + 0.01]);
      translate([L - 4, -6]) square([L + 2.2 - (L - 4), 2]);
      translate([L + 0.6, -6]) square([1.6, yt + 7.4]);
      // lip: 1.5 mm catch over the jaw tip, ramp on top = press to close
      polygon([[L - 1.5, yt - pre], [L + 2.2, yt - pre], [L + 2.2, yt + 1.4],
               [L + 0.6, yt + 1.4], [L - 1.5, yt]]);
      // thumb tab: flick out to open
      hull() {
        translate([L + 1.4, yt + 0.6]) circle(0.8);
        translate([L + 7, yt + 4.5]) circle(1.3);
      }
    }
    // V groove (bag zigzag)
    translate([8, T]) polygon([[0, 0.01], [L - 16, 0.01], [L - 17.2, -1.2], [1.2, -1.2]]);
  }
}

module top_jaw(L) {      // tip stays square on top (latch seat), rounded underneath
  difference() {
    union() {
      translate([0, T + G]) square([L, T]);
      translate([9, T + G]) polygon([[0.6, 0], [L - 18.6, 0], [L - 19.4, -0.9], [1.4, -0.9]]);
    }
    translate([L - 1.5, T + G - 0.01]) difference() { square(1.51); translate([0, 1.5]) circle(1.5); }
  }
}

module arc(r0, r1, a0, a1) {     // annulus sector, a0 -> a1 degrees
  n = 48;
  polygon(concat([for (i = [0:n]) let(a = a0 + (a1 - a0) * i / n) [r1 * cos(a), r1 * sin(a)]],
                 [for (i = [n:-1:0]) let(a = a0 + (a1 - a0) * i / n) [r0 * cos(a), r0 * sin(a)]]));
}

module clip2d(L) {
  translate([0, ym]) {
    arc(ym - w, ym, 90 + th, 270);                                   // flex loop / hang hole
    translate([0, -ym]) bottom_jaw(L);
    rotate(th) translate([0, -ym]) top_jaw(L);
    rotate(th) translate([-0.01, ym - w]) square([1.5, w]);         // loop -> top jaw joint
  }
}

module clip(L) linear_extrude(H) clip2d(L);

if (part == "one") clip(L);
else {
  // longest first; jaws open up, nested with 6 mm gaps
  Ls = [120, 90, 90, 60];
  for (i = [0:len(Ls) - 1]) translate([-60, -85 + i * 44, 0]) clip(Ls[i]);
}
