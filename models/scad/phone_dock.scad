// Phone dock, N bays. Each bay does all three:
//  1 cable keeper: the USB-C plug parks in a pocket in the ledge, cable can't fall.
//  2 drop-on dock: plug sits tip-up in that pocket, the phone drops onto it.
//  3 wireless: a pocket behind the backrest takes a round Qi pad (add later).
// Any phone/case: wide bays, deep ledge, plug height set with shims (part="shim").
// part = "dock" | "shim"
part = "dock";

bays   = 2;
bay_w  = 90;       // fits phones up to ~85 mm wide with case
a      = 15;       // lean-back angle
H      = 120;      // backrest height above the ledge
bt     = 11.5;     // backrest thickness (holds the Qi pad)
ledge_h = 26;      // ledge depth below the phone (holds the plug)
ledge_d = 16;      // phone + case thickness room
lip_t  = 3;  lip_h = 7;

// USB-C plug (MEASURE with caliper: boot width, thickness, length w/o metal)
boot_w = 11.5;  boot_t = 7;  boot_len = 20;
cable_w = 3.6;  // slit: a bit under the cable so it snaps in
port_off = 6;   // port centre from the phone's back face (phone/2 + case)

// Qi pad (MEASURE): round, diameter / thickness
pad_d = 71;  pad_t = 9;  pad_u = 68;  skin = 1.2;

$fn = 64;
W  = bays * bay_w;
z0 = ledge_h * cos(a) + bt * sin(a);
back_y = -(H * sin(a) + bt * cos(a)) - 6;   // foot reaches behind the top: no tipping
front_y = (ledge_d + lip_t) * cos(a) + 2;

module frame() translate([0, 0, z0]) rotate([a, 0, 0]) children();

module body() {
  intersection() {
    union() {
      frame() {
        translate([0, -bt, -ledge_h]) cube([W, bt, ledge_h + H]);             // backrest
        translate([0, 0, -ledge_h]) cube([W, ledge_d + lip_t, ledge_h]);      // ledge
        translate([0, ledge_d, 0]) cube([W, lip_t, lip_h]);                    // lip
      }
      // fill under the ledge down to the bed
      hull() {
        frame() translate([0, 0, -ledge_h]) cube([W, ledge_d + lip_t, 1]);
        translate([0, 0, 0]) cube([W, front_y, 1]);
      }
      translate([0, back_y, 0]) cube([W, front_y - back_y, 8]);               // foot (8: grooves under it)
    }
    translate([-1, -500, 0]) cube([W + 2, 1000, 500]);
  }
}

module bay_cuts(cx) {
  frame() {
    // plug pocket, top flush with the ledge
    translate([cx - boot_w / 2, port_off - boot_t / 2, -boot_len]) cube([boot_w, boot_t, boot_len + 1]);
    // cable channel down from the pocket, and a front slit to press the cable in
    translate([cx - cable_w / 2, port_off - cable_w / 2, -ledge_h - 60]) cube([cable_w, ledge_d + lip_t + 10, ledge_h + 60 - boot_len + 0.01]);
    // Qi pad pocket from the back, teardrop top (prints without support)
    translate([cx, -skin, pad_u]) rotate([90, 0, 0]) linear_extrude(bt) hull() {
      circle(d = pad_d);
      translate([0, pad_d / 2 * 1.2]) rotate(45) square(pad_d / 2 * 0.2, center = true);
    }
    // pad cable groove down the back
    translate([cx - 5, -bt - 1, -ledge_h - 60]) cube([10, 6, pad_u + 60]);
  }
  // groove under the foot: both cables run out the back
  translate([cx - (cable_w + 1) / 2, back_y - 1, -1]) cube([cable_w + 1, front_y - back_y + 2, cable_w + 1.5]);
  translate([cx - 5, back_y - 1, -1]) cube([10, 30, 5.5]);
}

module dock() difference() {
  body();
  for (i = [0 : bays - 1]) bay_cuts(bay_w / 2 + i * bay_w);
}

// shims: drop under the plug to raise it for thick cases (1, 2, 3 mm)
module shims() for (i = [0 : 2])
  translate([i * (boot_w + 4), 0, 0]) difference() {
    cube([boot_w - 0.4, boot_t - 0.4, i + 1]);
    translate([(boot_w - 0.4 - cable_w) / 2, -1, -1]) cube([cable_w, boot_t / 2 + 1, 5]);
  }

if (part == "dock") dock(); else shims();
