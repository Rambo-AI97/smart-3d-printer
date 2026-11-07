"""systemd user units for p3d: p3d-web (dashboard), p3d-print (one job), p3d-cooldown. `p3d install-service`."""
import os
import shlex
import shutil
import subprocess
import sys

from . import config

UNITS = {
    "p3d-web": ("p3d dashboard (read-only)", ["-m", "p3d", "web", "--foreground"], True),
    "p3d-print": ("p3d print job (started by p3d print)", ["-m", "p3d.sender", "--queued"], False),
    "p3d-cooldown": ("p3d cooldown watcher (started by p3d cooldown)", ["-m", "p3d.sender", "--cooldown"], False),
}


def unit_dir():
    return config.XDG_CONFIG / "systemd/user"


def needs_sg():
    """Run through `sg dialout` when the user is in dialout but a login session may not have it yet (harmless after)."""
    listed, _ = config.in_dialout_group()
    return listed and shutil.which("sg") is not None


def exec_line(args, split=False):
    """Command that runs `python -m p3d.sender ARGS` (or the given -m args) with serial access."""
    argv = [sys.executable, *(args if args and args[0] == "-m" else ["-m", "p3d.sender", *args])]
    if needs_sg():
        argv = [shutil.which("sg"), "dialout", "-c", "exec " + " ".join(shlex.quote(x) for x in argv)]
    return argv if split else " ".join(shlex.quote(x) for x in argv)


def render(name):
    desc, args, enabled = UNITS[name]
    env = "".join(f"Environment={k}={shlex.quote(os.environ[k])}\n"
                  for k in ("P3D_CONFIG", "P3D_DATA", "P3D_PORT") if os.environ.get(k))
    serial = name != "p3d-web"
    cmd = exec_line(args) if serial else " ".join(shlex.quote(x) for x in [sys.executable, *args])
    body = f"[Unit]\nDescription={desc}\n\n[Service]\nType=simple\n{env}ExecStart={cmd}\n"
    if enabled:
        body += "Restart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n"
    # print/cooldown never restart by themselves: a crashed print must not resume
    return body


def install(start=True):
    d = unit_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in UNITS:
        if name == "p3d-print" and config.print_running():
            print(f"skip {name}: a print is running (run again when it ends)")
            continue
        (d / f"{name}.service").write_text(render(name))
        print("wrote", d / f"{name}.service")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    if start:
        subprocess.run(["systemctl", "--user", "enable", "p3d-web"], capture_output=True)
        subprocess.run(["systemctl", "--user", "restart", "p3d-web"], check=False)
        print(f"dashboard: http://localhost:{config.get().web_port}  (p3d web shows the phone URL)")
    if shutil.which("loginctl"):
        r = subprocess.run(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger"],
                           capture_output=True, text=True)
        if "Linger=no" in r.stdout:
            print("tip: `loginctl enable-linger` keeps the dashboard and prints running after you log out")
