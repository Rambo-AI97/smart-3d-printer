// Dog frisbee (2026-11-10, polished V1 = V2 built in). Supervised fetch only: retire it
// when it cracks or gets chewed (hard plastic splinters). TPU version = idea board.
// Prints TOP DOWN: flat flight face on the PEI (textured grip), rim grows up, no supports.
// Thick 6 mm rim with a rounded top + 45 deg inward catch lip (easy for a dog to pick up
// off flat ground, stiff, no sharp edge), 45 deg bed chamfer (no elephant-foot edge),
// 45 deg fillet where plate meets rim (no crack line). V2: bigger 4.5 mm leading-edge
// chamfer (smoother, less bite-edge), two 45-deg flight/stiffening rings under the plate
// (less flex and warp, steadier glide), 4 walls (chew), names in two lines in the centre
// raised 0.8 mm on the inside face (print top = readable), -D name="L1|L2" ("" = none).
//   p3d slice dog_frisbee.stl -f pla -q draft --walls 3 --infill 25 --brim --keep-orient
$fn = 160;
name  = "";     // raised on the underside, e.g. -D name="..."
D     = 190;    // diameter (bed 220, keeps 15 mm for the brim)
H     = 18;     // total height (plate + rim)
t     = 2.0;    // plate (>= 2 mm floor for big flat parts; rings stiffen it)
rim_w = 6;      // rim thickness
lip   = 3;      // inward catch lip
c     = 4.5;    // bed-edge chamfer (leading edge)
f     = 4;      // plate/rim fillet

R  = D / 2;
rr = rim_w / 2;
ri = R - rim_w;

module profile() {
    // plate
    polygon([[0, 0], [R - c, 0], [R, c], [R, t], [0, t]]);
    // rim with rounded top
    hull() {
        polygon([[ri, 0], [R - c, 0], [R, c], [R, H - rr], [ri, H - rr]]);
        translate([R - rr, H - rr]) circle(r = rr, $fn = 40);
    }
    // catch lip, 45 deg underside
    hull() {
        translate([R - rr, H - rr]) circle(r = rr, $fn = 40);
        translate([ri - lip + 1.2, H - 1.2]) circle(r = 1.2, $fn = 24);
        translate([ri, H - rr - lip - 1]) square(0.01);
    }
    // fillet plate -> rim
    polygon([[ri - f, t], [ri + 0.5, t], [ri + 0.5, t + f]]);
}

rotate_extrude($fn = 240) profile();

// flight / stiffening rings under the plate (45 deg sides, print fine)
rings = [42, 68]; rh = 1.4;
for (r = rings) rotate_extrude($fn = 240)
    polygon([[r - rh - 0.6, t - 0.01], [r + rh + 0.6, t - 0.01], [r + 0.6, t + rh], [r - 0.6, t + rh]]);

lines = split(name);
if (name != "")
    translate([0, 0, t - 0.01]) linear_extrude(0.8)
        for (i = [0 : len(lines) - 1])
            translate([0, (len(lines) - 1) * 8 - i * 16])
                text(lines[i], size = 11, font = "Liberation Sans:style=Bold",
                     halign = "center", valign = "center");

function split(s, i = 0, cur = "") =
    i >= len(s) ? [cur] :
    s[i] == "|" ? concat([cur], split(s, i + 1, "")) : split(s, i + 1, str(cur, s[i]));
