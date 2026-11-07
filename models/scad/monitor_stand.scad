// HelloBaby HB6339 parent-unit kickstand (replacement, 2026-11-06). One part, no hardware.
// A flat plate with two pivot pins at the hinge end that snap into the sockets in the case.
// Measured: 22 mm wide, 56 mm tall. Everything marked GUESS needs calipers before the real print.
// Strength: prints FLAT, pins lie along the bed so filament lines run along each pin (bend-strong).
//   Pin undersides are trimmed flat to sit on the bed (no supports).
// Export: p3d scad monitor_stand        Fit test: p3d scad monitor_stand -D 'part="fit"'
part = "stand";      // "stand" | "fit" (3 short stands with pin_d -0.2 / 0 / +0.2)

w        = 22;       // plate width (between the pin shoulders)
h        = 56;       // plate length, hinge end to foot
t        = 3.0;      // GUESS plate thickness
pin_d    = 3.0;      // GUESS pivot pin diameter (measure the socket hole, subtract 0.2)
pin_len  = 2.0;      // GUESS how far each pin sticks out past the plate side
pin_y    = 3.0;      // GUESS pin centre distance from the hinge end
chamfer  = 0.9;      // lead-in on the pin tips so they snap in
notch_w  = 8;        // finger notch at the foot (0 = none)
slit_w   = 1.2;      // v2: relief slits like the original, so the pin arms flex inward to snap in
slit_len = 18;       // from the hinge end
arm_w    = 4;        // width of each flexing arm (pin side)
$fn = 64;

module tip(d) {      // chamfered pin = straight part + cone at the tip
  hull() {
    intersection() {
      translate([0, 0, t/2]) rotate([0, 90, 0]) cylinder(h = pin_len - chamfer, d = d);
      translate([0, -d, 0]) cube([pin_len, 2*d, t]);
    }
    intersection() {
      translate([0, 0, t/2]) rotate([0, 90, 0]) cylinder(h = pin_len, d = d - 2*chamfer);
      translate([0, -d, 0]) cube([pin_len, 2*d, t]);
    }
  }
}

module stand(d = pin_d, len = h) {
  difference() {
    // plate with rounded corners
    hull() for (x = [2, w-2], y = [2, len-2]) translate([x, y, 0]) cylinder(h = t, r = 2);
    if (notch_w > 0) translate([w/2, len + 1.5, -1]) cylinder(h = t + 2, r = notch_w/2);
    if (slit_w > 0) for (x = [arm_w, w - arm_w - slit_w])
      translate([x, -1, -1]) cube([slit_w, min(slit_len, len - 4) + 1, t + 2]);
  }
  translate([w, pin_y, 0]) tip(d);                         // right pin
  translate([0, pin_y, 0]) mirror([1, 0, 0]) tip(d);       // left pin
}

if (part == "stand") stand();
if (part == "fit")   // short stands (12 mm) just to test the snap, left to right: thin, nominal, thick
  for (i = [0:2]) translate([i * (w + 2*pin_len + 4), 0, 0]) stand(pin_d - 0.2 + 0.2*i, 12);
