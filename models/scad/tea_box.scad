// Tea bag organizer: open-top box, cols x rows compartments. Wrapped tea bags
// (paper envelopes ~70 x 76 mm) stand upright, 2 cm sticks out to grab.
// Fits the 220 x 220 bed at 2 x 4. Prints as is, no supports.
cols = 2;  rows = 5;
cell_w = 75;      // envelope up to 70 mm + 5 mm
cell_d = 38;      // depth per row (~25 bags)
h      = 40;      // envelope ~76 tall -> top half visible
wall   = 1.2;  floor_t = 2.0;  r = 4;   // v2: 2 mm floor (v1 1.2 warped)
notch_w = 30;  notch_d = 18;    // finger dip in the front wall of each column
$fn = 48;

W = cols * cell_w + (cols + 1) * wall;
D = rows * cell_d + (rows + 1) * wall;

module rbox(x, y, z, rr) { linear_extrude(z) offset(rr) offset(-rr) square([x, y]); }

difference() {
  rbox(W, D, h, r);
  for (c = [0 : cols - 1], rr = [0 : rows - 1])
    translate([wall + c * (cell_w + wall), wall + rr * (cell_d + wall), floor_t])
      rbox(cell_w, cell_d, h, 1);
  // finger dips on the front edge, one per column
  for (c = [0 : cols - 1])
    translate([wall + c * (cell_w + wall) + cell_w / 2, -1, h - notch_d])
      rotate([-90, 0, 0]) hull() {
        cylinder(d = notch_w, h = wall + 2);
        translate([0, -notch_d - 5, 0]) cylinder(d = notch_w, h = wall + 2);
      }
}
echo(str("tea box ", W, " x ", D, " x ", h, " mm"));
