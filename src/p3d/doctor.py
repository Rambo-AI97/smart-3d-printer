"""`p3d doctor`: check everything p3d needs and say how to fix each problem."""
import json
import os
import sys
import urllib.request

from . import config, service

OK, WARN, FAIL = "ok", "warn", "FAIL"
MARK = {OK: "✓", WARN: "!", FAIL: "✗"}


def checks():
    c = config.get()
    yield (OK, "config", str(config.CONFIG_FILE)) if c.exists else \
        (WARN, "config", "no config file, using defaults -> run `p3d setup`")

    if sys.version_info < (3, 11):
        yield FAIL, "python", f"{sys.version.split()[0]} is too old -> Python 3.11 or newer"
    try:
        import serial  # noqa: F401
        yield OK, "pyserial", serial.__version__
    except ImportError:
        yield FAIL, "pyserial", "missing -> reinstall p3d (pipx install --force ...)"

    port = c.port
    if not port:
        yield FAIL, "printer port", "no USB serial device -> plug in the printer, power it on, check the cable"
    elif not os.path.exists(port):
        yield FAIL, "printer port", f"{port} not present -> printer off/unplugged, or wrong `port` in the config"
    else:
        yield OK, "printer port", port
        real = os.path.realpath(port)
        listed, active = config.in_dialout_group()
        if os.access(real, os.R_OK | os.W_OK):
            yield OK, "port permission", f"read/write {real}"
        elif listed and not active:
            yield OK, "port permission", "via `sg dialout` (automatic) until your next login"
        else:
            yield FAIL, "port permission", f"no access to {real} -> `sudo usermod -aG dialout $USER`, then log out and in"

    orca = c.orca
    if orca:
        yield OK, "Orca Slicer", orca
    else:
        yield FAIL, "Orca Slicer", "not found -> install the AppImage from github.com/SoftFever/OrcaSlicer/releases, " \
            "then `p3d setup` (or set orca_slicer in the config)"
    yield (OK, "OpenSCAD", c.scad) if c.scad else \
        (WARN, "OpenSCAD", "not found (needed for scad, calib, previews) -> `sudo apt install openscad`")

    prof = c.profiles
    bad = []
    for f in ["machine.json"] + [f"process-{q}.json" for q in ("draft", "standard", "fine")] + \
             [f"filament-{f}.json" for f in ("pla", "petg")]:
        try:
            json.loads((prof / f).read_text())
        except Exception:
            bad.append(f)
    yield (FAIL, "profiles", f"broken/missing in {prof}: {', '.join(bad)} -> `p3d profiles`") if bad else \
        (OK, "profiles", ("your own: " if prof != config.PROFILES else "bundled Ender-3 V3 SE: ") + str(prof))

    for label, d in (("data dir", c.data), ("jobs dir", c.jobs), ("state dir", c.state_dir)):
        try:
            d.mkdir(parents=True, exist_ok=True)
            t = d / ".p3d-write-test"
            t.write_text("x")
            t.unlink()
            yield OK, label, str(d)
        except OSError as e:
            yield FAIL, label, f"{d} not writable ({e.strerror}) -> fix the folder or change it in the config"

    ud = service.unit_dir()
    missing, stale = [], []
    for name in service.UNITS:
        f = ud / f"{name}.service"
        if not f.exists():
            missing.append(name)
        elif sys.executable not in f.read_text():
            stale.append(name)
    if missing:
        yield FAIL, "services", f"not installed: {', '.join(missing)} -> `p3d install-service`"
    elif stale:
        yield WARN, "services", f"{', '.join(stale)} point to another Python -> `p3d install-service`"
    else:
        yield OK, "services", f"{', '.join(service.UNITS)} in {ud}"

    url = f"http://127.0.0.1:{c.web_port}/api/state"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            json.loads(r.read())
        yield OK, "dashboard", f"http://localhost:{c.web_port} answers" + \
            ("" if config.unit_active("p3d-web") else " (not the p3d-web service)")
    except Exception:
        yield FAIL, "dashboard", f"nothing on port {c.web_port} -> `p3d install-service` " \
            "(logs: journalctl --user -u p3d-web)"

    s = config.read_state()
    running = config.print_running()
    if s.get("status") in ("printing", "queued") and not running:
        yield WARN, "job state", f"{s.get('file')} says {s['status']} but no sender runs (crashed?) -> " \
            "journalctl --user -u p3d-print; the next p3d print resets it"
    else:
        yield OK, "job state", ("printing " if running else "") + f"{s.get('file') or '-'}: {s.get('status', 'idle')}"

    yield (OK, "ntfy", "phone alerts on") if c.ntfy_url else \
        (WARN, "ntfy", "no phone alerts (optional) -> set ntfy_url via `p3d setup`")


def run(quiet=False):
    worst = OK
    for level, name, msg in checks():
        if level == FAIL or (level == WARN and worst == OK):
            worst = level
        if quiet and level == OK:
            continue
        print(f" {MARK[level]} {name:<16} {msg}")
    print({OK: "all good", WARN: "works; see ! lines", FAIL: "fix the ✗ lines, then run p3d doctor again"}[worst])
    return 1 if worst == FAIL else 0


if __name__ == "__main__":
    sys.exit(run())
