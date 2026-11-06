#!/usr/bin/env python3
"""p3d: slice and print on the Ender-3 V3 SE from the command line.

  p3d status                         temps + current job
  p3d slice MODEL [-q draft|standard|fine] [-f pla|petg] [--supports] [--brim]
  p3d print FILE.gcode               start in the background (survives this terminal)
  p3d cancel                         safe stop: heaters off, lift, park
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
    print(final)
    print(f"time {info.get('estimated printing time (normal mode)')}, "
          f"{info.get('total filament used [g]')} g, layer {info.get('layer_height')} mm, "
          f"nozzle {info.get('nozzle_temperature')} / bed {info.get('bed_temperature')} C")


def cmd_print(a):
    g = pathlib.Path(a.gcode).expanduser().resolve()
    if running():
        sys.exit("a print is already running")
    STOP.unlink(missing_ok=True)
    # sg dialout: works before the user re-logs in after joining the group
    inner = f"exec {sys.executable} {shlex.quote(str(ROOT / 'sender.py'))} {shlex.quote(str(g))}"
    subprocess.run(["systemd-run", "--user", "--unit=p3d-print", "--collect",
                    "sg", "dialout", "-c", inner], check=True)
    print(f"started: {g.name}  (p3d status / p3d cancel)")


def cmd_cancel(_):
    STOP.touch()
    print("cancel requested; the sender will turn heaters off and park")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("slice"); s.add_argument("model")
    s.add_argument("-q", "--quality", default="standard", choices=["draft", "standard", "fine"])
    s.add_argument("-f", "--filament", default="pla", choices=["pla", "petg"])
    s.add_argument("--supports", action="store_true"); s.add_argument("--brim", action="store_true")
    s.set_defaults(fn=cmd_slice)
    s = sub.add_parser("print"); s.add_argument("gcode"); s.set_defaults(fn=cmd_print)
    sub.add_parser("cancel").set_defaults(fn=cmd_cancel)
    a = p.parse_args(); a.fn(a)
