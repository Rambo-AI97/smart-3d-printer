// Axiom bed scraper v2 (2026-11-07). One PETG part, prints flat, no supports.
// Better than the honeycomb store scraper because:
//   - single-sided bevel: the bottom is the smooth bed-side face, so it lies flat on the PEI
//     and the edge goes UNDER the part instead of riding up onto it
//   - edge tapers to 0.8 mm (5 layers at 0.16) and is plastic: safe for the textured PEI
//   - sharp "pry corner" on the left to start under one corner, rounded right corner for sweeping
//   - raised offset handle (11 mm) keeps knuckles off the bed; thumb dish on the ramp to push down-and-in
//   - finger scallops on both sides, hang hole for a hook on the printer frame
// Coordinates: X = length (edge at x=0), Y = width, Z up, bottom flat on z=0.
// Export: p3d scad bed_scraper
blade_w   = 56;     // edge width
blade_len = 34;     // edge to start of the neck
edge_t    = 0.8;    // thickness at the very edge (v2: 0.5 curled up and was knocked loose)
blade_t   = 2.6;    // blade body thickness
bevel_len = 16;     // length of the bevel
handle_len = 95;
handle_w   = 28;
handle_h   = 11;
neck_len   = 16;
hang_d     = 8;
label      = "AXIOM";
$fn = 64;

module blade() {
  hull() {
    // edge: sharp left corner (pry point), rounded right corner
    translate([0, -blade_w/2, 0]) cube([0.4, blade_w - 4, edge_t]);
    translate([4, blade_w/2 - 4, 0]) cylinder(r = 4, h = edge_t);
    // bevel top, then full thickness
    translate([bevel_len, -blade_w/2 + 1, 0]) cube([blade_len - bevel_len, blade_w - 2, blade_t]);
  }
}

module handle_body() {
  r = 5.5;
  x0 = blade_len + neck_len; x1 = x0 + handle_len;
  hull() for (x = [x0 + r, x1 - r], y = [-handle_w/2 + r, handle_w/2 - r]) {
    translate([x, y, 0]) cylinder(r = r, h = handle_h - r);
    translate([x, y, handle_h - r]) sphere(r);
  }
}

module neck() {   // ramp from the blade up into the handle
  hull() {
    translate([blade_len - 6, -blade_w/2 + 6, 0]) cube([6, blade_w - 12, blade_t]);
    translate([blade_len + neck_len, -handle_w/2 + 1, 0]) cube([4, handle_w - 2, handle_h - 1]);
  }
}

module scraper() {
  x0 = blade_len + neck_len; x1 = x0 + handle_len;
  difference() {
    union() { blade(); neck(); handle_body(); }
    // thumb dish on the ramp
    translate([blade_len + neck_len + 6, 0, handle_h + 7]) sphere(r = 10);
    // finger scallops on both sides
    for (i = [0:3], s = [-1, 1])
      translate([x0 + 22 + i * 15, s * (handle_w/2 + 2.6), -1]) cylinder(r = 4.2, h = handle_h + 2);
    // hang hole
    translate([x1 - 10, 0, -1]) cylinder(d = hang_d, h = handle_h + 2);
    // debossed label on the flat top
    translate([x0 + 44, 0, handle_h - 0.6])
      linear_extrude(1) text(label, size = 6.5, halign = "center", valign = "center",
                              font = "Liberation Sans:style=Bold");
  }
}

scraper();
