// Edge cable clip (2026-11-10, polished V1 = V2 built in). Pushes onto a tabletop edge
// (no tape, no screws): spring C-clamp with 0.8 mm preload, chamfered jaw tips to slide on,
// grip ribs inside, 2 mm inner fillets (PLA corner strength). Snap-in channels on the outside
// hold the cables where they drop over the edge; the plugs can't pass, so they stay on top.
// Default: 26 mm edge, 2 thin cables (USB-C, monitor) + 1 x 12 mm extension cord.
// Prints LYING ON ITS SIDE (C profile flat) so layers run around the C: no supports.
//   p3d slice edge_cable_clip.stl -f pla --walls 4 --infill 40 --keep-orient
$fn = 64;
part  = "print";   // "print" | "use" (as mounted)
T     = 26;        // edge thickness (calipers)
pre   = 0.8;       // clamp preload
jaw   = 5;         // jaw thickness
top_d = 35;        // top jaw reach onto the table
bot_d = 10;        // bottom jaw reach under the top
gap_x = 3;         // clearance in front of the (rounded) edge
sp    = 6;         // spine thickness
small = 4.4;  small_in = 3.0;    // thin cable channel / snap opening
big   = 12.6; big_in   = 10.0;   // extension cord channel / snap opening
W     = 38;        // clip width along the edge
blk   = 16;        // channel block depth

G  = T - pre;            // jaw gap
x0 = gap_x;              // spine inner face
x1 = x0 + sp;            // spine outer face
x2 = x1 + blk;           // channel block front
zb = -jaw; zt = G + jaw; // overall z
chans = [[small, small_in, 6], [big, big_in, W / 2], [small, small_in, W - 6]];

module c_profile() {     // XZ profile, extruded along Y
    difference() {
        union() {
            translate([-top_d, G]) square([top_d + x1, jaw]);
            translate([x0, zb]) square([sp, zt - zb]);
            translate([-bot_d, zb]) square([bot_d + x1, jaw]);
            // inner fillets
            for (z = [G, 0]) translate([x0 - 2, z == G ? G - 2 : 0]) square(2);
        }
        for (z = [G - 2, 2]) translate([x0 - 2, z]) circle(r = 2);
        // chamfered jaw tips (slide-on lead-in)
        translate([-top_d, G]) rotate(45) square(2.2, center = true);
        translate([-bot_d, 0]) rotate(45) square(2.2, center = true);
    }
    // grip ribs
    for (x = [-top_d + 6 : 6 : x0 - 4]) translate([x, G - 0.4]) square([1, 0.41]);
    for (x = [-bot_d + 4 : 5 : x0 - 4]) translate([x, -0.01]) square([1, 0.41]);
}

module channel(d, opening) {   // XY cross-section, axis Z; teardrop to +Y
    union() {
        circle(d = d);
        rotate(45) square(d / 2);                          // 45 deg teardrop tip toward +Y
        translate([0, -opening / 2]) square([blk, opening]);  // snap slot to the front (+X)
    }
}

module clip() {
    difference() {
        union() {
            rotate([90, 0, 0]) translate([0, 0, -W]) linear_extrude(W) c_profile();
            // channel block on the spine, chamfered top/bottom
            hull() {
                translate([x1 - 0.01, 0, zb + 2]) cube([blk, W, zt - zb - 4]);
                translate([x1 - 0.01, 0, zb]) cube([0.01, W, zt - zb]);
            }
        }
        for (c = chans)
            translate([x2 - blk / 2 - (c[0] > 6 ? 0 : -2.5), c[2], zb - 1])
                linear_extrude(zt - zb + 2) mirror([0, 1]) channel(c[0], c[1]);   // tip to -Y = print up
        // lead-in chamfers on the snap slots
        for (c = chans)
            translate([x2, c[2], (zt + zb) / 2]) rotate(45)
                cube([(c[1] + 2) / 1.414, (c[1] + 2) / 1.414, zt - zb + 2], center = true);
    }
}

if (part == "use") clip();
else rotate([-90, 0, 0]) translate([0, -W, 0]) clip();   // edge-direction (Y) becomes print Z
