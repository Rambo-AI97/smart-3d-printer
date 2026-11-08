// Coffee kit: whole-bean scoop sized for one French press, + funnel.
// Scoop: level fill = full press; inner step ring marks 2/3 (smaller batch).
// Both print upright, no supports.
part = "both";            // "scoop" | "funnel" | "both"

// --- scoop: tune grams after weighing one level scoop ---
grams   = 50;             // beans for ~750 ml water (3 mugs, 1:15)
density = 0.37;           // g/ml whole beans (dark ~0.35, light ~0.40)
id      = 56;             // inner diameter (fits a jar mouth > 62 mm)
wall    = 2;
base    = 2;
vol_ml  = grams / density;
cup_h   = vol_ml * 1000 / (PI * pow(id / 2, 2));   // inner height, mm
h_23    = cup_h * 2 / 3;                           // 2/3 mark

// --- funnel ---
f_top = 110;  f_spout = 40;  f_cone_h = 45;  f_spout_h = 15;  f_wall = 1.6;

$fn = 96;
font = "Liberation Sans:style=Bold";

module scoop() {
  od = id + 2 * wall;
  difference() {
    cylinder(d = od, h = base + cup_h);
    translate([0, 0, base]) cylinder(d = id, h = cup_h + 1);
  }
  // 2/3 mark: thin ledge inside (sloped underside, prints without support)
  translate([0, 0, base + h_23 - 1.2]) difference() {
    cylinder(d = id + 0.1, h = 1.2);
    cylinder(d1 = id + 0.1, d2 = id - 2.4, h = 1.2);
  }
  // handle flat on the bed
  difference() {
    hull() {
      translate([od / 2 - 4, -8, 0]) cube([1, 16, 6]);
      translate([od / 2 + 70, 0, 0]) cylinder(d = 18, h = 6);
    }
    translate([od / 2 + 72, 0, -1]) cylinder(d = 6, h = 8);   // hang hole
  }
  translate([od / 2 + 32, 0, 6]) linear_extrude(0.8)
    text(str(grams, " g"), size = 7, font = font, halign = "center", valign = "center");
}

module funnel() {
  difference() {
    union() {
      cylinder(d = f_spout, h = f_spout_h);
      translate([0, 0, f_spout_h]) cylinder(d1 = f_spout, d2 = f_top, h = f_cone_h);
      translate([0, 0, f_spout_h + f_cone_h]) cylinder(d = f_top, h = 3);
    }
    translate([0, 0, -1]) cylinder(d = f_spout - 2 * f_wall, h = f_spout_h + 1.01);
    translate([0, 0, f_spout_h]) cylinder(d1 = f_spout - 2 * f_wall, d2 = f_top - 2 * f_wall, h = f_cone_h + 0.01);
    translate([0, 0, f_spout_h + f_cone_h]) cylinder(d = f_top - 2 * f_wall, h = 4);
  }
}

echo(str("scoop inner height ", cup_h, " mm, volume ", vol_ml, " ml"));
if (part != "funnel") scoop();
if (part != "scoop") translate([0, f_top / 2 + id / 2 + 12, 0]) funnel();
