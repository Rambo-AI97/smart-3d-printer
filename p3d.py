#!/usr/bin/env python3
"""p3d: slice and print on the Ender-3 V3 SE from the command line.

  p3d status                         temps + current job
  p3d slice MODEL [-q draft|standard|fine] [-f pla|petg] [--supports] [--brim]
  p3d print FILE.gcode               start in the background (survives this terminal)
  p3d web [--open]                   live dashboard on port 8765 (systemd user service p3d-web)
  p3d cancel                         safe stop: heaters off, lift, park
  p3d log                            print history
  p3d history                        totals, success rate, hours, grams, avg rating, last 5
  p3d rate [N] [--issues a,b] [--note "text"] [--job NAME]   rate the last print (no args: show it)
  p3d level [--show]                 probe the bed, save the mesh, show a colour map
  p3d calib temp|retraction|flow|firstlayer [-f pla|petg]   generate a calibration print (no printing)
"""
import argparse, json, pathlib, re, shlex, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
STATE = ROOT / "state.json"
STOP = ROOT / "STOP"
ORCA = pathlib.Path.home() / "orca-slicer"
PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"


def running():
    r = subprocess.run(["systemctl", "--user", "is-active", "p3d-print"], capture_output=True, text=True)
    return r.stdout.strip() in ("active", "activating")


def cmd_status(_):
    if STATE.exists():
        s = json.loads(STATE.read_text())
        print(json.dumps(s, indent=1))
    print("job running:", running())
    if not running():
        import serial
        with serial.Serial(PORT, 115200, timeout=1, exclusive=True) as ser:
            time.sleep(2.5)
            ser.reset_input_buffer()
            ser.write(b"\nM105\n")
            time.sleep(1)
            print(ser.read(500).decode(errors="replace").strip().splitlines()[-1])


def cmd_slice(a):
    model = pathlib.Path(a.model).expanduser().resolve()
    stamp = time.strftime("%Y%m%d-%H%M")
    out = JOBS / f"{stamp}-{re.sub(r'[^A-Za-z0-9]+', '_', model.stem)}"
    n = 2
    while out.exists():  # two slices in the same minute
        out = out.with_name(out.name.split("~")[0] + f"~{n}"); n += 1
    out.mkdir(parents=True)
    proc = json.load(open(ROOT / f"profiles/process-{a.quality}.json"))
    if a.supports:
        proc["enable_support"] = "1"
    if a.brim:
        proc["brim_type"] = "outer_only"
    pj = out / "process.json"
    pj.write_text(json.dumps(proc))
    cmd = [str(ORCA), "--slice", "0", "--arrange", "1", "--orient", "1",
           "--load-settings", f"{ROOT}/profiles/machine.json;{pj}",
           "--load-filaments", f"{ROOT}/profiles/filament-{a.filament}.json",
           "--outputdir", str(out), str(model)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = json.load(open(out / "result.json"))
    g = next(out.glob("*.gcode"), None)
    if res.get("return_code") != 0 or not g:
        sys.exit(f"slice failed: {res.get('error_string')}")
    final = out / f"{model.stem}.gcode"
    g.rename(final)
    info = {}
    for line in open(final, errors="replace"):
        m = re.match(r"; (estimated printing time \(normal mode\)|total filament used \[g\]|layer_height|nozzle_temperature|bed_temperature) = (.*)", line)
        if m:
            info.setdefault(m.group(1), m.group(2))
        elif line.startswith("M190 S"):
            info.setdefault("bed_temperature", line.split()[1][1:])
    (out / "job.json").write_text(json.dumps({"model": str(model), "gcode": str(final)}))
    try:
        import preview
        preview.make(model, out / "preview.png")
    except Exception:
        pass
    print(final)
    print(f"time {info.get('estimated printing time (normal mode)')}, "
          f"{info.get('total filament used [g]')} g, layer {info.get('layer_height')} mm, "
          f"nozzle {info.get('nozzle_temperature')} / bed {info.get('bed_temperature')} C")


def cmd_print(a):
    g = pathlib.Path(a.gcode).expanduser().resolve()
    if running():
        sys.exit("a print is already running")
    STOP.unlink(missing_ok=True)
    try:
        import preview
        preview.for_job(g.parent)
    except Exception:
        pass
    # sg dialout: works before the user re-logs in after joining the group
    inner = f"exec {sys.executable} {shlex.quote(str(ROOT / 'sender.py'))} {shlex.quote(str(g))}"
    subprocess.run(["systemd-run", "--user", "--unit=p3d-print", "--collect",
                    "sg", "dialout", "-c", inner], check=True)
    print(f"started: {g.name}  (p3d status / p3d cancel)")


def cmd_log(_):
    import printlog
    r = printlog.rows()
    done = [x for x in r if x["status"] in ("done", "failed", "cancelled")]
    print(f"{len(r)} jobs logged ({len(done)} printed through p3d)")
    for x in r[-15:]:
        print(f"{x['date'][:10]}  {x['status']:9} {x['name'][:34]:34} {x['grams'] or '-':>6} g  {x['actual_min'] or x['est_min'] or '-':>7} min")
    if printlog.STATS.exists():
        print("printer lifetime:", open(printlog.STATS).read().strip().splitlines()[-1])


def cmd_rate(a):
    import printlog
    printlog.cmd_rate(a.rating, a.issues, a.note, a.job)


def cmd_history(_):
    import printlog
    printlog.cmd_history()


def cmd_level(a):
    if running():
        sys.exit("a print is running")
    sys.path.insert(0, str(ROOT / "tools"))
    import level
    level.main(a.show, a.hot)


def cmd_calib(a):
    sys.path.insert(0, str(ROOT / "tools"))
    import calib
    calib.run(a.test, a.filament)


def cmd_web(a):
    urls = ["http://localhost:8765", "http://<tailscale-ip>:8765"]
    r = subprocess.run(["systemctl", "--user", "is-active", "p3d-web"], capture_output=True, text=True)
    if r.stdout.strip() != "active":
        subprocess.run(["systemctl", "--user", "start", "p3d-web"], check=False)
    print("\n".join(urls))
    if a.open:
        subprocess.Popen(["xdg-open", urls[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_cancel(_):
    STOP.touch()
    print("cancel requested; the sender will turn heaters off and park")


MODELS = ROOT / "models"


def _to_stl(src, out, length, flat=0.0, thicken=None, voxel=None):
    """Blender headless: model -> solid STL + preview PNG (tools/model/to_stl.py)."""
    cmd = ["blender", "-b", "-P", str(ROOT / "tools/model/to_stl.py"), "--", str(src), str(out),
           "--length", str(length), "--flat", str(flat), "--png", str(out.with_suffix(".png"))]
    if thicken: cmd += ["--thicken", str(thicken)]
    if voxel: cmd += ["--voxel", str(voxel)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("SIZE_MM", "PREVIEW"))]
    if r.returncode or not lines:
        sys.exit("blender failed:\n" + (r.stdout + r.stderr)[-1500:])
    print("\n".join(lines)); print("stl:", out)


def cmd_model(a):
    src = pathlib.Path(a.src).expanduser().resolve()
    out = pathlib.Path(a.out).expanduser().resolve() if a.out else MODELS / src.stem / (src.stem + ".stl")
    out.parent.mkdir(parents=True, exist_ok=True)
    _to_stl(src, out, a.length, a.flat, a.thicken, a.voxel)


def cmd_game(a):
    presets = json.loads((MODELS / "presets.json").read_text())
    if a.name not in presets:
        sys.exit("presets: " + ", ".join(k for k in presets if not k.startswith("_")))
    c = presets[a.name]
    d = MODELS / a.name; d.mkdir(parents=True, exist_ok=True)
    glb = d / (a.name + ".glb")
    env = dict(__import__("os").environ, GD_SCRIPT=c["script"], GD_ARGS=json.dumps(c.get("args", [])),
               GD_HIDE=c.get("hide", ""), GD_DROP_THIN=str(c.get("drop_thin", 0)), OUT=str(glb))
    r = subprocess.run(["godot", "--headless", "--path", str(pathlib.Path(c["game"]).expanduser()),
                        "-s", str(ROOT / "tools/model/godot_export.gd")], env=env, capture_output=True, text=True, timeout=300)
    if "EXPORT" not in r.stdout:
        sys.exit("godot export failed:\n" + (r.stdout + r.stderr)[-1500:])
    _to_stl(glb, d / (a.name + ".stl"), a.length or c.get("length", 85), c.get("flat", 0.0), c.get("thicken"), c.get("voxel"))
    if c.get("note"): print("note:", c["note"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("slice"); s.add_argument("model")
    s.add_argument("-q", "--quality", default="standard", choices=["draft", "standard", "fine"])
    s.add_argument("-f", "--filament", default="petg", choices=["pla", "petg"])
    s.add_argument("--supports", action="store_true"); s.add_argument("--brim", action="store_true")
    s.set_defaults(fn=cmd_slice)
    s = sub.add_parser("print"); s.add_argument("gcode"); s.set_defaults(fn=cmd_print)
    s = sub.add_parser("web", help="dashboard URL (starts the service if needed)"); s.add_argument("--open", action="store_true")
    s.set_defaults(fn=cmd_web)
    sub.add_parser("cancel").set_defaults(fn=cmd_cancel)
    sub.add_parser("log").set_defaults(fn=cmd_log)
    s = sub.add_parser("rate", help="rate the last print (1-5, issue tags, note)")
    s.add_argument("rating", nargs="?", type=int); s.add_argument("--issues"); s.add_argument("--note")
    s.add_argument("--job", help="job name instead of the last one"); s.set_defaults(fn=cmd_rate)
    sub.add_parser("history", help="summary of all prints").set_defaults(fn=cmd_history)
    s = sub.add_parser("level", help="probe the bed and show the map (--show: no probing)")
    s.add_argument("--show", action="store_true")
    s.add_argument("--hot", type=int, default=0, metavar="BED_C", help="heat the bed first (70 for PETG, 55 for PLA)")
    s.set_defaults(fn=cmd_level)
    s = sub.add_parser("calib", help="generate a calibration print")
    s.add_argument("test", choices=["temp", "retraction", "flow", "firstlayer"])
    s.add_argument("-f", "--filament", default="petg", choices=["pla", "petg"]); s.set_defaults(fn=cmd_calib)
    s = sub.add_parser("model", help="any .glb/.obj/.fbx/.stl -> solid printable STL + preview")
    s.add_argument("src"); s.add_argument("-o", "--out"); s.add_argument("--length", type=float, default=85, help="longest side mm")
    s.add_argument("--flat", type=float, default=0.0, help="cut this fraction of the height off for a flat base")
    s.add_argument("--thicken", type=float); s.add_argument("--voxel", type=float); s.set_defaults(fn=cmd_model)
    s = sub.add_parser("game", help="export a code-built game model by preset (models/presets.json) -> STL")
    s.add_argument("name"); s.add_argument("--length", type=float); s.set_defaults(fn=cmd_game)
    a = p.parse_args(); a.fn(a)
