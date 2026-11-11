// Plate for shakers.scad: render the 4 STLs first (openscad -D kind=.. -D part=body|cap).
view = "plate";   // "plate" | "pair" | "cut"
module pb() import("shakers_pepper_body.stl"); module pc() import("shakers_pepper_cap.stl");
module sb() import("shakers_salt_body.stl");   module sc() import("shakers_salt_cap.stl");
if (view == "plate") {
  translate([-30, 32, 0]) pb(); translate([32, 32, 0]) sb();
  translate([-30, -30, 0]) pc(); translate([32, -30, 0]) sc();
} else {
  difference() {
    union() { translate([-32, 0, 4]) pb(); translate([-32, 0, 0]) pc(); translate([32, 0, 4]) sb(); translate([32, 0, 0]) sc(); }
    if (view == "cut") translate([-100, -200, -1]) cube([200, 200, 200]);
  }
}
