// Fit-test C-clips: one per inner diameter, each with a numbered tab.
// Snap them on the bar; the one that grips without forcing wins.
// p3d scad fit_rings -D 'sizes=[30,31,32,33,34]' -D height=8
sizes = [30, 31, 32, 33, 34];  // inner diameters, mm
wall = 2.4;                    // ring thickness (6 lines of 0.4)
height = 8;                    // ring height
gap = 0.72;                    // opening as a fraction of the diameter (snap-on)
$fn = 96;

module clip(d) {
  r = d / 2;
  difference() {
    union() {
      cylinder(h = height, r = r + wall);
      // label tab opposite the opening
      translate([-(r + wall + 9), -5, 0]) cube([10, 10, height]);
    }
    translate([0, 0, -1]) cylinder(h = height + 2, r = r);
    // opening on +X
    translate([0, -gap * d / 2, -1]) cube([r + wall + 1, gap * d, height + 2]);
    // number engraved on the tab top
    translate([-(r + wall + 4), 0, height - 0.8])
      linear_extrude(1) text(str(d), size = 4.5, halign = "center", valign = "center",
                             font = "Liberation Sans:style=Bold");
  }
}

for (i = [0 : len(sizes) - 1])
  translate([(i % 3) * 58, floor(i / 3) * 52, 0]) clip(sizes[i]);
