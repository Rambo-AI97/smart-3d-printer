// "Cathedral radio" phone dock, one phone. Compact: the cabinet hugs the phone.
// - gothic-arch backrest with a raised cabinet border (the radio silhouette)
// - lower cabinet: speaker-grille slots + a round dial ("BE HERE") on the front,
//   ribbed sides, small tray on top for rings / keys / earbuds
// - phone slot fits phones up to ~88 mm wide (with case), cases up to ~15 mm thick
// - USB-C plug pocket in the slot floor: park the plug (cable keeper) or leave it
//   tip-up and drop the phone on (dock). Shims (part="shim") raise it for thick cases.
// - v2 2026-11-08: arch 170 mm with sunburst fret above the phone, thin 7 mm back, no Qi pocket
// - v4 2026-11-09 (owner): pocket for his plug (rubber 13 x ~7 x 16 mm) 13.6 x 8 x 16.2 with a lead-in chamfer,
//   cable slit 6.5 (v2's 3.6 slit stopped the plug's strain relief), 10 mm back + 2 rear ribs,
//   speaker ducts: floor windows under the phone's bottom speakers -> ducts -> through the front grille
// - v5 2026-11-09 (owner "V2 it"): self-centring slot for the Nothing Phone 3 in a case (~80 wide):
//   83 mm slot with 45-deg side + front flares, so the phone slides onto the plug without looking
// part = "dock" | "shim"
part = "dock";

a   = 15;        // lean-back angle
Wb  = 100;       // overall width
H   = 170;       // backrest height above the slot floor (arch tip): tall enough that the arch + fret show above a phone
bt  = 10;        // backrest thickness (v4: 7 was flexy)
Hc  = 38;        // cabinet height
Dc  = 80;        // cabinet depth (front to back)
sd  = 8;         // slot depth below the cabinet top
slot_w = 83;     // v5: Nothing Phone 3 75.6 + case ~80; flares guide it in
ledge_d = 16;    // phone + case thickness
tray_d = 24;  tray_h = 12;  front_wall = 3;

// standard USB-C overmold, generous; plug drops in from the top
boot_w = 13.6;  boot_t = 8;  boot_len = 16.2;  cham = 1.5;   // v4: owner measured rubber 13 wide x ~7, 16 long, metal 6; flush with the floor, shims raise it
cable_w = 6.5;  port_off = 6;   // port centre in front of the phone's back face

pad_d = 71;  pad_u = 66;  skin = 1.2;   // Qi pad pocket (measure the pad you buy)

font = "Liberation Sans:style=Bold";
$fn = 72;

yb = front_wall + tray_d + front_wall + ledge_d;   // phone back plane at slot floor
zb = Hc - sd;
module frame() translate([0, yb, zb]) rotate([-a, 0, 0]) children();   // local: x, w(back), u(up)

// gothic arch: two arcs of radius R, spring line at H - rise
R = 60;
rise = sqrt(R * R - pow(R - Wb / 2, 2));
module arch2d(off = 0) offset(delta = off) union() {
  translate([0, -60]) square([Wb, H - rise + 60]);
  translate([0, H - rise]) intersection() {
    translate([R, 0]) circle(R, $fn = 160);
    translate([Wb - R, 0]) circle(R, $fn = 160);
    square([Wb, R]);
  }
}
module teardrop2d(d) hull() { circle(d = d); translate([0, d / 2 * 1.15]) rotate(45) square(d * 0.12, center = true); }

module cabinet() {
  linear_extrude(Hc) offset(6) offset(-6) square([Wb, Dc]);
}

module front_face() {   // dial raised on the front (y = 0 face)
  dz = Hc / 2;
  translate([Wb / 2, 0, dz]) rotate([90, 0, 0]) linear_extrude(1) {
    difference() { circle(d = 30); circle(d = 26.5); }
    for (i = [0 : 11]) rotate(i * 30) translate([0, 10.2]) square([i % 3 == 0 ? 1.4 : 0.8, i % 3 == 0 ? 3 : 2], center = true);
    text("BE HERE", size = 3.6, font = font, halign = "center", valign = "center");
  }
}

module grooves() {
  // grille on the front, left and right of the dial
  for (x = [9 : 4 : 31], s = [0, 1]) let(xx = s ? Wb - x : x)
    translate([xx - 0.8, -1, 6]) cube([1.6, 2.2, Hc - 12]);
  // ribbed sides
  for (y = [10 : 5 : Dc - 10], x = [-1, Wb - 1.2])
    translate([x, y - 0.8, 5]) cube([2.2, 1.6, Hc - 10]);
}

module dock() difference() {
  intersection() {
    union() {
      cabinet();
      frame() {
        translate([0, bt, 0]) rotate([90, 0, 0]) linear_extrude(bt) arch2d();               // backrest
        translate([0, 0, 0]) rotate([90, 0, 0]) linear_extrude(2.5)                          // cabinet border
          difference() { arch2d(); arch2d(-5); translate([0, -100]) square([Wb, 100 + 2]); }
      }
      front_face();
      for (x = [14, Wb - 20]) hull() {                    // rear ribs: cabinet top -> back of the backrest
        translate([x, Dc - 22, Hc - 1]) cube([6, 20, 1]);
        frame() translate([x, bt - 1, 70]) cube([6, 1, 1]);
      }
    }
    translate([-1, -5, 0]) cube([Wb + 2, 300, 300]);
  }
  grooves();
  // tray
  translate([0, 0, Hc - tray_h]) linear_extrude(tray_h + 1)
    translate([6, front_wall]) offset(4) offset(-4) square([Wb - 12, tray_d]);
  frame() {
    // phone slot
    translate([(Wb - slot_w) / 2, -ledge_d, 0]) cube([slot_w, ledge_d, 200]);
    hull() {   // lead-in flares: sides + front open up 45 deg toward the top of the cabinet
      translate([(Wb - slot_w) / 2, -ledge_d, 3]) cube([slot_w, ledge_d, 0.01]);
      translate([(Wb - slot_w) / 2 - 5, -ledge_d - 1.5, 8]) cube([slot_w + 10, ledge_d + 1.5, 0.01]);
      translate([(Wb - slot_w) / 2 - 5, -ledge_d - 1.5, 30]) cube([slot_w + 10, ledge_d + 1.5, 0.01]);
    }
    // plug pocket, top flush with the slot floor
    translate([Wb / 2 - boot_w / 2, -port_off - boot_t / 2, -boot_len]) cube([boot_w, boot_t, boot_len + 1]);
    hull() {   // lead-in chamfer
      translate([Wb / 2 - boot_w / 2, -port_off - boot_t / 2, -cham]) cube([boot_w, boot_t, 0.01]);
      translate([Wb / 2 - boot_w / 2 - cham, -port_off - boot_t / 2 - cham, 0]) cube([boot_w + 2 * cham, boot_t + 2 * cham, 1]);
    }
    // speaker windows in the slot floor, both sides of the plug, down into the ducts
    for (x = [12, Wb / 2 + boot_w / 2 + 3]) translate([x, -port_off - 4.5, -14]) cube([Wb / 2 - boot_w / 2 - 3 - 12, 9, 15]);
    // cable slit: from the pocket down and out the back, press the cable in
    translate([Wb / 2 - cable_w / 2, -port_off - cable_w / 2, -80]) cube([cable_w, 200, 80 - boot_len + 0.01]);
    // sunburst fretwork in the arch top (the part that shows above the phone), cut through
    translate([0, bt + 1, 0]) rotate([90, 0, 0]) linear_extrude(bt + 5) intersection() {
      arch2d(-9);
      translate([0, H - 45]) square([Wb, 200]);
      union() for (i = [-4 : 4]) translate([Wb / 2, H - rise - 20]) rotate(i * 11) translate([-1.3, 0]) square([2.6, 200]);
    }
  }
  // speaker ducts (45-deg gable roof: no supports), open to the front through the grille slots
  for (x0 = [10, Wb - 30]) {
    hull() {
      translate([x0, 3, 8]) cube([20, 42, 5]);
      translate([x0 + 9.5, 3, 8]) cube([1, 42, 15]);
    }
    for (xl = [13 : 4 : 29]) let(x = x0 < Wb / 2 ? xl : Wb - xl, top = 13 + 10 * (1 - abs(x - x0 - 10) / 10) - 1)
      translate([x - 0.8, -1, 9]) cube([1.6, 5, top - 9]);
  }
  // cable groove under the cabinet, out the back
  translate([Wb / 2 - (cable_w + 1) / 2, 20, -1]) cube([cable_w + 1, Dc, cable_w + 1.5]);
}

module shims() for (i = [0 : 2])
  translate([i * (boot_w + 4), 0, 0]) difference() {
    cube([boot_w - 0.4, boot_t - 0.4, i + 1]);
    translate([(boot_w - 0.4 - cable_w) / 2, -1, -1]) cube([cable_w, boot_t / 2 + 1, 5]);
  }

if (part == "dock") dock(); else shims();
