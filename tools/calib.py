"""Calibration prints: p3d calib temp|retraction|flow|firstlayer [-f pla|petg]

Each test = OpenSCAD model -> Orca slice (profiles + small overrides) -> G-code post-process.
Output: jobs/<stamp>-calib-<test>/calib-<test>.gcode (never sent to the printer from here).
"""
import json, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORCA = pathlib.Path.home() / "orca-slicer"
OPENSCAD = pathlib.Path.home() / ".local/bin/openscad"
FONT = "DejaVu Sans:style=Bold"
BED = 220
BASE_RETRACT = 1.2  # mm, profiles/machine.json retraction_length

# ---------- models (OpenSCAD) ----------

def temp_scad(temps):
    # Sturdy tower: 1 mm base plate, blocks 30x15 standing on two 10 mm-wide legs (10 mm bridge between),
    # 45 deg overhang fused along the whole right face. (v1 stood on two 5 mm legs and snapped off, 2026-11-06.)
    parts = ["translate([82,96,0]) cube([46,23,1]);  // base plate"]
    for i, t in enumerate(temps):
        z = 1 + 10 * i
        parts.append(f"""translate([90,100,{z}]) difference() {{
  union() {{ cube([30,15,10]);
    translate([30,15,4]) rotate([90,0,0]) linear_extrude(15) polygon([[0,0],[5,5],[0,5]]); }}  // 45 deg overhang
  translate([10,-1,-0.01]) cube([10,17,4.01]);       // 10 mm bridge (tunnel along Y)
  translate([15,0.8,7]) rotate([90,0,0]) linear_extrude(1) text("{t}", size=4.5, font="{FONT}", halign="center", valign="center");
}}""")
    return "\n".join(parts)


def retraction_scad(bands):
    h = 5 * bands
    return "\n".join(f"""translate([{x},110,0]) {{ cylinder(d=12,h=0.4,$fn=48); cylinder(d=8,h={h},$fn=48); }}"""
                     for x in (90, 130))


def flow_scad(flows):
    out = []
    for i, f in enumerate(flows):
        x = 31.5 + i * 33
        out.append(f"""translate([{x},97.5,0]) difference() {{ cube([25,25,2]);
  translate([12.5,4,1.4]) linear_extrude(1) text("{f}", size=5, font="{FONT}", halign="center"); }}""")
    return "\n".join(out)


def firstlayer_scad():
    return "\n".join(f"translate([{x-15},{y-15},0]) cube([30,30,0.2]);"
                     for x, y in ((100, 100), (40, 40), (160, 40), (40, 160), (160, 160)))

# ---------- post-processing ----------

def lines_with_z(lines):
    """yield (line, current_z); Orca marks layers as ';LAYER_CHANGE' then ';Z:<z>'."""
    z = None
    for ln in lines:
        m = re.match(r";Z:([\d.]+)", ln)
        if m:
            z = float(m.group(1))
        yield ln, z


def post_temp(lines, temps, step_h=10, base=1.0):
    """M104 S<t> right after the ';Z:' line of the first layer of block 2..N."""
    out, done = [], set()
    for ln, z in lines_with_z(lines):
        out.append(ln)
        if ln.startswith(";Z:") and z is not None:
            i = int((z - base - 0.01) // step_h)
            if i > 0 and i not in done and abs(z - (base + i * step_h + 0.2)) < 1e-6:
                done.add(i)
                out.append(f"M104 S{temps[i]} ; calib: block {i+1}\n")
    assert done == set(range(1, len(temps))), f"temp blocks missing: {sorted(done)}"
    return out


def post_retraction(lines, lengths, band_h=5):
    """Scale every negative-E move (retract/wipe) and E-only positive move (unretract) per band."""
    out, started, band = [], False, 0
    for ln, z in lines_with_z(lines):
        if ln.startswith(";LAYER_CHANGE"):
            started = True
        elif ln.startswith("; filament end gcode"):
            started = False  # leave the end-of-print retract alone
        if z is not None and ln.startswith(";Z:"):
            band = min(int((z - 0.01) // band_h), len(lengths) - 1)
        if started and ln.startswith("G1 "):
            m = re.search(r" E(-?[\d.]+)", ln)
            if m:
                e = float(m.group(1))
                only_e = re.match(r"G1 E-?[\d.]+( F[\d.]+)?\s*(;.*)?$", ln)
                if e < 0 or (e > 0 and only_e):
                    ln = ln.replace(m.group(0), f" E{e * lengths[band] / BASE_RETRACT:.4f}", 1)
        out.append(ln)
    return out


def post_flow(lines, flows, x0=31.5, pitch=33):
    """Before the first extrusion in each square, set M221; reset at the end."""
    out, cur = [], None
    for ln in lines:
        m = re.match(r"G1 X([\d.]+) Y[\d.]+ E[\d.]+", ln)
        if m:
            i = round((float(m.group(1)) - x0 - 12.5) / pitch)
            if 0 <= i < len(flows) and i != cur and abs(float(m.group(1)) - (x0 + 12.5 + i * pitch)) <= 13:
                cur = i
                out.append(f"M221 S{flows[i]} ; calib: square {flows[i]}%\n")
        out.append(ln)
    out.append("M221 S100 ; calib: reset flow\n")
    return out

# ---------- tests ----------

def run(test, fil):
    pla = fil == "pla"
    proc, filament, post = {}, {}, (lambda l: l)
    brim = {"brim_type": "outer_only", "brim_width": "5"}
    if test == "temp":
        temps = list(range(230, 190, -5)) if pla else list(range(255, 215, -5))
        scad = temp_scad(temps)
        filament = {"nozzle_temperature": [str(temps[0])], "nozzle_temperature_initial_layer": [str(temps[0])]}
        post = lambda l: post_temp(l, temps)
        note = (f"Temperature tower, bottom block {temps[0]} C, top block {temps[-1]} C (1 mm base, then blocks of 10 mm, -5 C each).\n"
                "Judge per block: bridge over the tunnel (sagging/drooping), the 45 deg wedge on the right, "
                "stringing, surface gloss, layer bonding (snap a corner), legibility of the engraved number on the front.\n"
                "Pick the lowest temperature with a clean bridge and strong layers. The number is the temperature of that block.")
    elif test == "retraction":
        lengths = [round(0.2 * (i + 1), 1) for i in range(8)]
        scad = retraction_scad(len(lengths))
        post = lambda l: post_retraction(l, lengths)
        note = ("Two pillars 40 mm apart, one travel (retract) per layer. Bands of 5 mm height, bottom to top:\n"
                + "\n".join(f"  {5*i:2d}-{5*i+5:2d} mm : retraction {r} mm" for i, r in enumerate(lengths))
                + "\nLook for strings between the pillars. Pick the shortest retraction at which strings (nearly) disappear, "
                "and set it in the profile. If every band strings, lower temperature/dry the filament first; "
                "if the top bands show gaps/under-extrusion, the retraction is too long.")
    elif test == "flow":
        flows = [90, 95, 100, 105, 110]
        scad = flow_scad(flows)
        proc = {"sparse_infill_density": "100%"}
        post = lambda l: post_flow(l, flows)
        note = ("Five 25x25x2 squares, left to right flow 90 95 100 105 110 % (number engraved on top).\n"
                "Pick the smoothest top: too low shows gaps/lines between passes, too high shows ridges/blobs. "
                "Multiply the filament flow ratio by (picked/100).")
    elif test == "firstlayer":
        scad = firstlayer_scad()
        note = ("Single 0.2 mm layer: 5 squares (centre + 4 corners). Judge squish per square: "
                "lines should be flat, merged, no gaps; ridged/translucent = too close, rounded separate lines = too far. "
                "Compare corners to find tilt; adjust Z offset / re-level.")
    else:
        sys.exit("tests: temp retraction flow firstlayer")

    out = ROOT / "jobs" / (f"{time.strftime('%Y%m%d-%H%M')}-calib-{test}" + ("" if pla else "-petg"))
    out.mkdir(parents=True, exist_ok=True)
    (out / f"calib-{test}.scad").write_text(scad + "\n")
    stl = out / f"calib-{test}.stl"
    subprocess.run([str(OPENSCAD), "-o", str(stl), str(out / f"calib-{test}.scad")],
                   check=True, capture_output=True)
    pj, fj = out / "process.json", out / "filament.json"
    p = json.load(open(ROOT / "profiles/process-standard.json")); p.update(proc)
    if test != "firstlayer":
        p.update(brim)
    f = json.load(open(ROOT / f"profiles/filament-{fil}.json")); f.update(filament)
    pj.write_text(json.dumps(p)); fj.write_text(json.dumps(f))
    gdir = out / "slice"
    subprocess.run([str(ORCA), "--slice", "0", "--arrange", "0",  # keep the model's own X/Y
                    "--load-settings", f"{ROOT}/profiles/machine.json;{pj}",
                    "--load-filaments", str(fj), "--outputdir", str(gdir), str(stl)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    g = next(gdir.glob("*.gcode"), None)
    if not g:
        sys.exit("slice failed")
    final = out / f"calib-{test}.gcode"
    final.write_text("".join(post(g.read_text().splitlines(keepends=True))))
    meta = {}
    for ln in final.read_text().splitlines():
        m = re.match(r"; (estimated printing time \(normal mode\)|total filament used \[g\]) = (.*)", ln)
        if m:
            meta[m.group(1)] = m.group(2)
    print(final)
    print(f"time {meta.get('estimated printing time (normal mode)')}, {meta.get('total filament used [g]')} g")
    print(note)
    (out / "NOTE.txt").write_text(note + "\n")
