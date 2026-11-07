"""p3d: slice, print and track a Marlin 3D printer from the command line."""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time

from . import __version__, config
from .config import FINAL, print_running, read_state


def cfg():
    return config.get()


# ===================== Print =====================

def cmd_status(a):
    s, run = read_state(), print_running()
    stale = s.get("status") in ("printing", "queued") and not run
    if a.json:
        print(json.dumps({"running": run, "stale": stale, "state": s}, indent=1))
        return
    st = s.get("status", "idle")
    print(f"{st}{' (STALE: sender not running, see journalctl --user -u p3d-print)' if stale else ''}: "
          f"{s.get('file') or 'no job'}")
    if st == "printing":
        print(f"  {s.get('progress')}%  layer {s.get('layer')}/{s.get('total_layers') or '?'}  z {s.get('z')}  "
              f"{s.get('remaining_min')} min left (ETA {s.get('eta')})")
    if s.get("ended_at"):
        print(f"  ended {s['ended_at'].replace('T', ' ')}  after {s.get('minutes')} min" +
              (f"  error: {s['error']}" if s.get("error") else ""))
    if s.get("nozzle") is not None:
        print(f"  nozzle {s.get('nozzle')}/{s.get('nozzle_target')} C  bed {s.get('bed')}/{s.get('bed_target')} C")
    if not run:
        config.reexec_with_dialout()
        try:
            with config.open_serial() as ser:
                time.sleep(2.5)
                ser.reset_input_buffer()
                ser.write(b"\nM105\n")
                time.sleep(1)
                lines = ser.read(500).decode(errors="replace").strip().splitlines()
                print("  printer now:", lines[-1] if lines else "no reply")
        except (Exception, SystemExit) as e:
            print("  printer not reachable:", e)


def service_dir():
    return config.XDG_CONFIG / "systemd/user"


def _start_unit(unit, args):
    """Run `python -m p3d.sender ARGS` as a systemd user service (survives the terminal)."""
    if (service_dir() / f"{unit}.service").exists():
        subprocess.run(["systemctl", "--user", "reset-failed", unit], capture_output=True)
        subprocess.run(["systemctl", "--user", "start", "--no-block", unit], check=True)
        return
    from .service import exec_line
    subprocess.run(["systemd-run", "--user", f"--unit={unit}", "--collect", *exec_line(args, split=True)], check=True)


def cmd_print(a):
    c = cfg()
    g = pathlib.Path(a.gcode).expanduser().resolve()
    if g.is_dir():
        g = next(g.glob("*.gcode"), g)
    if g.suffix != ".gcode" or not g.exists():
        sys.exit(f"not a G-code file: {g}")
    if print_running():
        sys.exit("a print is already running (p3d status)")
    c.stop.unlink(missing_ok=True)
    try:
        from . import preview
        preview.for_job(g.parent)
    except Exception:
        pass
    c.state_dir.mkdir(parents=True, exist_ok=True)
    c.queue.write_text(str(g))
    config.write_state(status="queued", file=g.stem, job_id=g.parent.name, job_dir=str(g.parent),
                       queued_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _start_unit("p3d-print", ["--queued"])
    print(f"started: {g.name}  (job {g.parent.name}; p3d status / p3d wait done / p3d cancel)")


def cmd_cancel(_):
    c = cfg()
    if not print_running():
        print("no print running")
        return
    c.state_dir.mkdir(parents=True, exist_ok=True)
    c.stop.touch()
    print("cancel requested: the sender turns heaters off, lifts and parks")


def cmd_wait(a):
    target = a.job or read_state().get("job_id")
    if not target:
        sys.exit("no job to wait for (start one with p3d print)")
    dead_since = None
    while True:
        s = read_state()
        if s.get("job_id") == target:
            if s.get("status") in FINAL:
                print(f"job ended: {s['status']} at {s.get('ended_at')}" + (f" ({s['error']})" if s.get("error") else ""))
                sys.exit(0 if s["status"] == "done" else 1)
            if a.until == "layer" and s.get("layer"):
                print(f"layer {s['layer']}: nozzle {s.get('nozzle')} C, bed {s.get('bed')} C, {s.get('progress')}%")
                return
        elif s.get("job_id"):
            sys.exit(f"job {target} was replaced by {s['job_id']}")
        if print_running():
            dead_since = None
        else:
            dead_since = dead_since or time.time()
            if time.time() - dead_since > a.grace:
                sys.exit(f"the sender stopped without a final state for {target} (journalctl --user -u p3d-print)")
        time.sleep(a.interval)


def cmd_cooldown(_):
    _start_unit("p3d-cooldown", ["--cooldown"])
    print("cooldown watcher started: after the print, heaters off, wait until cool, motors off, ntfy")


def cmd_web(a):
    c = cfg()
    if a.foreground:
        from .web import server
        print(f"http://localhost:{c.web_port}")
        server.main()
        return
    urls = [f"http://localhost:{c.web_port}"]
    try:  # LAN/Tailscale address for phones, found at run time (never hard-coded)
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split()
        if ip:
            urls.append(f"http://{ip[0]}:{c.web_port}")
    except (OSError, subprocess.SubprocessError):
        pass
    if not config.unit_active("p3d-web"):
        if not (service_dir() / "p3d-web.service").exists():
            sys.exit("dashboard service not installed: p3d install-service  (or p3d web --foreground)")
        subprocess.run(["systemctl", "--user", "start", "p3d-web"], check=False)
    print("\n".join(urls))
    if a.open:
        subprocess.Popen(["xdg-open", urls[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ===================== Design =====================

def _need(tool, path):
    if not path:
        sys.exit(f"{tool} not found: install it, then p3d setup (p3d doctor shows what's missing)")
    return path


def cmd_slice(a):
    c = cfg()
    orca = _need("Orca Slicer", c.orca)
    model = pathlib.Path(a.model).expanduser().resolve()
    if not model.exists():
        sys.exit(f"no such model: {model}")
    stamp = time.strftime("%Y%m%d-%H%M")
    out = c.jobs / f"{stamp}-{re.sub(r'[^A-Za-z0-9]+', '_', model.stem)}"
    n = 2
    while out.exists():  # two slices in the same minute
        out = out.with_name(out.name.split("~")[0] + f"~{n}")
        n += 1
    out.mkdir(parents=True)
    prof = c.profiles
    proc = json.load(open(prof / f"process-{a.quality}.json"))
    if a.supports:
        proc["enable_support"] = "1"
    if a.brim:
        proc["brim_type"] = "outer_only"
    if a.walls:  # strong parts: more perimeters matter more than infill
        proc["wall_loops"] = str(a.walls)
        proc["top_shell_layers"] = proc["bottom_shell_layers"] = str(max(5, a.walls))
    if a.infill:
        proc["sparse_infill_density"] = f"{a.infill}%"
        proc["sparse_infill_pattern"] = "gyroid"
    pj = out / "process.json"
    pj.write_text(json.dumps(proc))
    cmd = [orca, "--slice", "0", "--arrange", "1", "--orient", "0" if a.keep_orient else "1",
           "--load-settings", f"{prof}/machine.json;{pj}",
           "--load-filaments", f"{prof}/filament-{a.filament}.json",
           "--outputdir", str(out), str(model)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        res = json.load(open(out / "result.json"))
    except FileNotFoundError:
        res = {"return_code": -1, "error_string": "Orca wrote no result.json"}
    g = next(out.glob("*.gcode"), None)
    if res.get("return_code") != 0 or not g:
        sys.exit(f"slice failed: {res.get('error_string')}")
    final = out / f"{model.stem}.gcode"
    g.rename(final)
    info = {}
    for line in open(final, errors="replace"):
        m = re.match(r"; (estimated printing time \(normal mode\)|total filament used \[g\]|layer_height|"
                     r"nozzle_temperature|bed_temperature) = (.*)", line)
        if m:
            info.setdefault(m.group(1), m.group(2))
        elif line.startswith("M190 S"):
            info.setdefault("bed_temperature", line.split()[1][1:])
    (out / "job.json").write_text(json.dumps({"model": str(model), "gcode": str(final)}))
    try:
        from . import preview
        preview.make(model, out / "preview.png")
    except Exception:
        pass
    print(final)
    print(f"time {info.get('estimated printing time (normal mode)')}, "
          f"{info.get('total filament used [g]')} g, layer {info.get('layer_height')} mm, "
          f"nozzle {info.get('nozzle_temperature')} / bed {info.get('bed_temperature')} C")


def _scad_src(name):
    src = pathlib.Path(name).expanduser()
    if src.exists():
        return src
    return cfg().models / "scad" / (name if name.endswith(".scad") else name + ".scad")


def cmd_scad(a):
    scad = _need("OpenSCAD", cfg().scad)
    src = _scad_src(a.file)
    if not src.exists():
        sys.exit(f"no {src}")
    out = src.with_suffix(".stl")
    defs = [x for d in (a.D or []) for x in ("-D", d)]
    r = subprocess.run([scad, *defs, "-o", str(out), str(src)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-1500:])
    view = [x for d in (a.view or []) for x in ("-D", d)]
    subprocess.run([scad, *defs, *view, "--imgsize=900,700", "--viewall", "--autocenter",
                    "-o", str(out.with_suffix(".png")), str(src)], capture_output=True)
    print("stl:", out)
    print("preview:", out.with_suffix(".png"))


def cmd_pack(a):
    """Printables pack: STL, .scad, render.png, starter pack.json. Never overwrites pack.json or photo_*."""
    import csv
    from . import printlog
    scad = _need("OpenSCAD", cfg().scad)
    src = _scad_src(a.model.removesuffix(".scad"))
    if not src.exists():
        sys.exit(f"no {src}")
    name = src.stem
    out = cfg().publish / (a.dir or name.replace("_", "-"))
    out.mkdir(parents=True, exist_ok=True)
    defs = ["-D", f'part="{a.part}"'] if a.part else []
    stl = out / (name + ".stl")
    r = subprocess.run([scad, *defs, "-o", str(stl), str(src)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-1500:])
    shutil.copy2(src, out / src.name)
    subprocess.run([scad, *defs, "--render", "--imgsize=1200,900", "--colorscheme=Tomorrow",
                    "--viewall", "--autocenter", "-o", str(out / "render.png"), str(src)], capture_output=True)
    pj = out / "pack.json"
    if pj.exists():
        print("pack.json kept")
    else:
        row = None
        if printlog.log_file().exists():
            for r_ in csv.DictReader(printlog.log_file().open()):
                if r_.get("name") == name and r_.get("status") == "done":
                    row = r_
        lines = []
        if row:
            mins = row.get("actual_min") or row.get("est_min") or "?"
            lines = [f"- {row.get('filament', 'PETG')}, {row.get('layer_mm', '0.2')} mm layers, "
                     f"{row.get('nozzle_mm', '0.4')} mm nozzle",
                     f"- Nozzle {row.get('nozzle_set', '')} C, bed {row.get('bed_set', '')} C",
                     f"- About {mins} min, {row.get('grams', '?')} g"]
        pack = {"title": name.replace("_", " ").title(), "summary": "", "category": "",
                "tags": [t for t in name.lower().split("_") if t][:10], "ai_assisted": True,
                "license": "Creative Commons — Attribution — Share Alike",
                "description": "Print settings (tested):\n" + "\n".join(lines) if lines else "",
                "model_files": [stl.name, src.name],
                "images": sorted(p.name for p in out.glob("photo_*.jpg")) + ["render.png"]}
        pj.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n")
        print("starter pack.json written (fill title/summary/category/description)")
    print("pack:", out)


def cmd_inspect(a):
    """What's in a G-code: time, grams, sequence, filament share per feature, support by height."""
    import collections
    g = pathlib.Path(a.gcode).expanduser()
    if g.is_dir():
        g = next(g.glob("*.gcode"))
    feat, sup, head = collections.Counter(), collections.Counter(), {}
    t, z = None, 0.0
    for line in open(g, errors="replace"):
        if line.startswith(";TYPE:"):
            t = line[6:].strip()
        elif line.startswith(";Z:"):
            z = float(line[3:])
        elif line.startswith("G1") and " E" in line and t:
            m = re.search(r" E([\d.]+)", line)
            if m:
                feat[t] += float(m.group(1))
                if t.startswith("Support"):
                    sup[int(z // 5) * 5] += float(m.group(1))
        elif line.startswith("; ") and " = " in line:
            k, v = line[2:].split(" = ", 1)
            if k in ("estimated printing time (normal mode)", "total filament used [g]", "print_sequence",
                     "max_z_height", "nozzle_temperature", "wall_loops", "sparse_infill_density", "support_type"):
                head.setdefault(k, v.strip())
        elif line.startswith("; max_z_height"):
            head.setdefault("max_z_height", line.split(":")[-1].strip())
    for k, v in head.items():
        print(f"{k}: {v}")
    tot = sum(feat.values()) or 1
    print("filament by feature:", ", ".join(f"{k} {100 * v / tot:.0f}%" for k, v in feat.most_common(8)))
    if sup:
        print("support by height:", ", ".join(f"{k}-{k + 5}mm {100 * v / tot:.0f}%" for k, v in sorted(sup.items())))


def _to_stl(src, out, length, flat=0.0, thicken=None, voxel=None):
    """Blender headless: model -> solid STL + preview PNG (p3d/model/to_stl.py)."""
    blender = _need("Blender", shutil.which("blender"))
    cmd = [blender, "-b", "-P", str(config.PKG / "model/to_stl.py"), "--", str(src), str(out),
           "--length", str(length), "--flat", str(flat), "--png", str(out.with_suffix(".png"))]
    if thicken:
        cmd += ["--thicken", str(thicken)]
    if voxel:
        cmd += ["--voxel", str(voxel)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("SIZE_MM", "PREVIEW"))]
    if r.returncode or not lines:
        sys.exit("blender failed:\n" + (r.stdout + r.stderr)[-1500:])
    print("\n".join(lines))
    print("stl:", out)


def cmd_model(a):
    src = pathlib.Path(a.src).expanduser().resolve()
    out = pathlib.Path(a.out).expanduser().resolve() if a.out else cfg().models / src.stem / (src.stem + ".stl")
    out.parent.mkdir(parents=True, exist_ok=True)
    _to_stl(src, out, a.length, a.flat, a.thicken, a.voxel)


def cmd_game(a):
    import os
    pf = config.CONFIG_DIR / "presets.json"
    if not pf.exists():
        sys.exit(f"no presets: write {pf} (format: docs/game-models.md)")
    presets = json.loads(pf.read_text())
    if a.name not in presets:
        sys.exit("presets: " + ", ".join(k for k in presets if not k.startswith("_")))
    c = presets[a.name]
    d = cfg().models / a.name
    d.mkdir(parents=True, exist_ok=True)
    glb = d / (a.name + ".glb")
    env = dict(os.environ, GD_SCRIPT=c["script"], GD_ARGS=json.dumps(c.get("args", [])),
               GD_HIDE=c.get("hide", ""), GD_DROP_THIN=str(c.get("drop_thin", 0)), OUT=str(glb))
    godot = _need("Godot", shutil.which("godot"))
    r = subprocess.run([godot, "--headless", "--path", str(pathlib.Path(c["game"]).expanduser()),
                        "-s", str(config.PKG / "model/godot_export.gd")], env=env, capture_output=True, text=True,
                       timeout=300)
    if "EXPORT" not in r.stdout:
        sys.exit("godot export failed:\n" + (r.stdout + r.stderr)[-1500:])
    _to_stl(glb, d / (a.name + ".stl"), a.length or c.get("length", 85), c.get("flat", 0.0), c.get("thicken"),
            c.get("voxel"))
    if c.get("note"):
        print("note:", c["note"])


# ===================== Calibrate =====================

def _idle_port():
    if print_running():
        sys.exit("a print is running")
    config.reexec_with_dialout()


def cmd_level(a):
    _idle_port()
    from . import level
    level.main(a.show, a.hot)


def cmd_calib(a):
    _need("Orca Slicer", cfg().orca)
    _need("OpenSCAD", cfg().scad)
    from . import calib
    calib.run(a.test, a.filament)


def cmd_pid(a):
    _idle_port()
    from . import pid
    pid.main(a.hotend, a.bed)


def cmd_probe(_):
    _idle_port()
    from . import probe
    probe.main()


def cmd_profiles(_):
    from . import flatten_profile
    flatten_profile.main()


# ===================== Data =====================

def cmd_log(_):
    from . import printlog
    r = printlog.rows()
    done = [x for x in r if x["status"] in FINAL]
    print(f"{len(r)} jobs logged ({len(done)} printed through p3d)  [{printlog.log_file()}]")
    for x in r[-15:]:
        print(f"{x['date'][:10]}  {x['status']:9} {x['name'][:34]:34} {x['grams'] or '-':>6} g  "
              f"{x['actual_min'] or x['est_min'] or '-':>7} min")
    if printlog.stats_file().exists():
        print("printer lifetime:", printlog.stats_file().read_text().strip().splitlines()[-1])


def cmd_rate(a):
    from . import printlog
    printlog.cmd_rate(a.rating, a.issues, a.note, a.job)


def cmd_history(_):
    from . import printlog
    printlog.cmd_history()


def cmd_stats(_):
    _idle_port()
    from . import printlog
    printlog.cmd_stats()


def cmd_import(_):
    from . import printlog
    printlog.cmd_import()


# ===================== Setup =====================

def cmd_setup(a):
    from . import setup_wizard
    setup_wizard.run(defaults=a.yes)


def cmd_doctor(a):
    from . import doctor
    sys.exit(doctor.run(quiet=a.quiet))


def cmd_install_service(a):
    from . import service
    service.install(start=not a.no_start)


# ===================== parser =====================

def A(*flags, **kw):
    return (flags, kw)


QUAL = A("-q", "--quality", default="standard", choices=["draft", "standard", "fine"])
FIL = A("-f", "--filament", default="petg", choices=["pla", "petg"])

COMMANDS = {
    "Print": [
        ("status", cmd_status, "current job, progress and temperatures",
         [A("--json", action="store_true", help="machine-readable {running, stale, state}, nothing else")]),
        ("print", cmd_print, "start printing a G-code file in the background",
         [A("gcode", help="FILE.gcode or a job folder")]),
        ("cancel", cmd_cancel, "safe stop: heaters off, lift, park", []),
        ("wait", cmd_wait, "block until the current job's first layer or its end (exit 0 = done)",
         [A("until", choices=["layer", "done"]), A("--job", help="job id (default: the current one)"),
          A("--interval", type=float, default=5, help=argparse.SUPPRESS),
          A("--grace", type=float, default=15, help=argparse.SUPPRESS)]),
        ("cooldown", cmd_cooldown, "after the current print: wait until cool, motors off, ntfy", []),
        ("web", cmd_web, "the live dashboard (prints its URLs, starts the service)",
         [A("--open", action="store_true", help="open in the browser"),
          A("--foreground", action="store_true", help="run the server here instead of the service")]),
    ],
    "Design": [
        ("slice", cmd_slice, "STL/3MF -> G-code with the bundled Orca profiles",
         [A("model"), QUAL, FIL, A("--supports", action="store_true"), A("--brim", action="store_true"),
          A("--walls", type=int, help="perimeters (strong parts: 5-6)"),
          A("--infill", type=int, help="percent, gyroid"),
          A("--keep-orient", action="store_true", help="don't auto-rotate (part already laid out for strength)")]),
        ("scad", cmd_scad, "OpenSCAD part -> STL + preview PNG",
         [A("file", help="NAME in models/scad, or a path"), A("-D", action="append", help="param=value (repeat)"),
          A("--view", action="append", help="extra -D only for the preview, e.g. 'part=\"assembly\"'")]),
        ("model", cmd_model, "any .glb/.obj/.fbx/.stl -> solid printable STL (Blender)",
         [A("src"), A("-o", "--out"), A("--length", type=float, default=85, help="longest side mm"),
          A("--flat", type=float, default=0.0, help="cut this fraction of the height off for a flat base"),
          A("--thicken", type=float), A("--voxel", type=float)]),
        ("game", cmd_game, "Godot game model by preset -> STL (~/.config/p3d/presets.json)",
         [A("name"), A("--length", type=float)]),
        ("inspect", cmd_inspect, "G-code breakdown: time, grams, feature share, supports", [A("gcode")]),
        ("pack", cmd_pack, "Printables upload pack: STL, .scad, render, pack.json",
         [A("model"), A("--part"), A("--dir", help="folder name (default: model with - for _)")]),
    ],
    "Calibrate": [
        ("level", cmd_level, "probe the bed, save the mesh, show a colour map",
         [A("--show", action="store_true", help="show the saved mesh, no probing"),
          A("--hot", type=int, default=0, metavar="BED_C", help="heat the bed first (70 PETG, 55 PLA)")]),
        ("calib", cmd_calib, "make a calibration print: temp, retraction, flow, firstlayer",
         [A("test", choices=["temp", "retraction", "flow", "firstlayer"]), FIL]),
        ("pid", cmd_pid, "PID-tune hotend and bed, save to EEPROM",
         [A("--hotend", type=int, default=220), A("--bed", type=int, default=60)]),
        ("probe", cmd_probe, "read-only check: firmware, settings, temps", []),
        ("profiles", cmd_profiles, "rebuild the Orca CLI profiles from Orca's presets", []),
    ],
    "Data": [
        ("log", cmd_log, "the job log (last 15)", []),
        ("history", cmd_history, "totals, success rate, hours, grams, rating, last 5", []),
        ("rate", cmd_rate, "rate the last print 1-5 with issue tags and a note (no args: show it)",
         [A("rating", nargs="?", type=int), A("--issues", help="comma list, e.g. stringing,adhesion"),
          A("--note"), A("--job", help="job name instead of the last one")]),
        ("stats", cmd_stats, "save the printer's lifetime counters (M78)", []),
        ("import-history", cmd_import, "add past G-code files found on this PC to the log", []),
    ],
    "Setup": [
        ("setup", cmd_setup, "first-run wizard: port, slicer, OpenSCAD, ntfy -> config file",
         [A("-y", "--yes", action="store_true", help="accept detected defaults, no questions")]),
        ("doctor", cmd_doctor, "check port, permissions, slicer, profiles, services; says how to fix",
         [A("-q", "--quiet", action="store_true", help="only problems")]),
        ("install-service", cmd_install_service, "write the systemd user units (web, print, cooldown)",
         [A("--no-start", action="store_true", help="write the units but don't start the dashboard")]),
    ],
}


def build():
    width = max(len(n) for cmds in COMMANDS.values() for n, *_ in cmds)
    epilog = "\n".join(f"{g}:\n" + "\n".join(f"  {n:<{width}}  {h}" for n, _, h, _ in cmds) + "\n"
                       for g, cmds in COMMANDS.items())
    p = argparse.ArgumentParser(prog="p3d", formatter_class=argparse.RawDescriptionHelpFormatter,
                                description=__doc__, usage="p3d <command> [options]   (p3d <command> -h for details)",
                                epilog=epilog + "\nNew here? p3d setup, then p3d doctor.")
    p.add_argument("--version", action="version", version=f"p3d {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="<command>", help=argparse.SUPPRESS)
    sub.required = True
    for cmds in COMMANDS.values():
        for name, fn, help_, args in cmds:
            sp = sub.add_parser(name, description=help_)
            for flags, kw in args:
                sp.add_argument(*flags, **kw)
            sp.set_defaults(fn=fn)
    return p


def main(argv=None):
    a = build().parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
