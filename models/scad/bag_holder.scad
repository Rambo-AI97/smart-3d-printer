// Poop-bag roll holder that rides on a dog leash.
// Tube stands upright on the bed (no supports): closed bottom, push-on cap,
// side slit to pull bags out, leash loop on the back (vertical channel).
// part = "both" | "body" | "cap"
part = "both";

roll_d = 33;     // MEASURE: bag roll diameter
roll_l = 57;     // MEASURE: bag roll length
leash_w = 25;    // MEASURE: leash webbing width
leash_t = 4;     // MEASURE: leash thickness

clear = 2;       // room around the roll
wall  = 2.4;
floor_t = 2;
fit   = 0.25;    // cap push-fit gap
slit_w = 5;

id = roll_d + 2 * clear;
od = id + 2 * wall;
h  = roll_l + clear + floor_t;
lip_h = 6;
loop_wall = 2.4;
$fn = 96;

module body() {
  difference() {
    union() {
      cylinder(d = od, h = h);
      // leash loop on the back: webbing threads through vertically
      lw = leash_w + 2;  lt = leash_t + 1;
      translate([-(lw / 2 + loop_wall), od / 2 - wall, 0])
        difference() {
          cube([lw + 2 * loop_wall, lt + loop_wall + wall, h * 0.6]);
          translate([loop_wall, wall, -1]) cube([lw, lt, h]);
        }
    }
    translate([0, 0, floor_t]) cylinder(d = id, h = h);
    // dispensing slit, front side
    translate([-slit_w / 2, -od, floor_t + 4]) cube([slit_w, od, h - floor_t - 8]);
    // finger hole in the floor to push the roll out
    translate([0, 0, -1]) cylinder(d = 14, h = floor_t + 2);
  }
}

module cap() {
  // flat top + plug that pushes into the tube
  cylinder(d = od, h = 2);
  difference() {
    cylinder(d = id - 2 * fit, h = 2 + lip_h);
    translate([0, 0, 2]) cylinder(d = id - 2 * fit - 2 * 1.6, h = lip_h + 1);
  }
  // small grip tab
  translate([od / 2 - 1, -4, 0]) cube([4, 8, 2]);
}

if (part == "body" || part == "both") body();
if (part == "cap" || part == "both") translate([od + 12, 0, 0]) cap();
