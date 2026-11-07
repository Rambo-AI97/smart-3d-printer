"""Settings and paths. One place, no hard-coded machine paths.

Order (first wins): environment (P3D_DATA, P3D_PORT, P3D_STATE_DIR, P3D_CONFIG) > ~/.config/p3d/config.toml > defaults.
Written by `p3d setup`; see config.example.toml.
"""
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tomllib
import urllib.request

HOME = pathlib.Path.home()
PKG = pathlib.Path(__file__).resolve().parent
PROFILES = PKG / "profiles"
XDG_CONFIG = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
XDG_DATA = pathlib.Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
XDG_STATE = pathlib.Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state"))
CONFIG_FILE = pathlib.Path(os.environ.get("P3D_CONFIG", XDG_CONFIG / "p3d/config.toml"))
CONFIG_DIR = CONFIG_FILE.parent

DEFAULTS = {
    "port": "",              # empty = first /dev/serial/by-id/* device
    "baud": 115200,
    "orca_slicer": "",       # empty = search PATH and common places
    "openscad": "",
    "data_dir": "",          # print log + samples (default ~/.local/share/p3d)
    "jobs_dir": "",          # sliced jobs, G-code (default <data_dir>/jobs)
    "publish_dir": "",       # p3d pack output (default <data_dir>/publish)
    "models_dir": "",        # your .scad parts (default: ./models if it exists, else <data_dir>/models)
    "ntfy_url": "",          # e.g. https://ntfy.sh/my-printer-topic (empty = no phone alerts)
    "ntfy_token": "",
    "web_port": 8765,
    "web_host": "0.0.0.0",
    "park_y": 220,           # Y to park at on cancel (bed depth)
}


def _load():
    try:
        return tomllib.loads(CONFIG_FILE.read_text())
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"p3d: bad config {CONFIG_FILE}: {e}")


class Config:
    def __init__(self, raw=None):
        self.raw = {**DEFAULTS, **(_load() if raw is None else raw)}
        self.exists = CONFIG_FILE.exists()

    def __getattr__(self, k):
        try:
            return self.raw[k]
        except KeyError:
            raise AttributeError(k) from None

    def _path(self, env, key, default):
        v = os.environ.get(env) if env else None
        v = v or self.raw.get(key) or default
        return pathlib.Path(v).expanduser()

    @property
    def data(self):
        return self._path("P3D_DATA", "data_dir", XDG_DATA / "p3d")

    @property
    def jobs(self):
        return self._path("P3D_JOBS", "jobs_dir", self.data / "jobs")

    @property
    def publish(self):
        return self._path(None, "publish_dir", self.data / "publish")

    @property
    def models(self):
        here = pathlib.Path.cwd() / "models"
        return self._path(None, "models_dir", here if (here / "scad").is_dir() else self.data / "models")

    @property
    def state_dir(self):
        return self._path("P3D_STATE_DIR", None, XDG_STATE / "p3d")

    @property
    def state(self):
        return self.state_dir / "state.json"

    @property
    def stop(self):
        return self.state_dir / "STOP"

    @property
    def queue(self):
        return self.state_dir / "next_job"

    @property
    def profiles(self):
        """Your own flattened profiles (p3d profiles) win over the bundled Ender-3 V3 SE ones."""
        own = CONFIG_DIR / "profiles"
        return own if (own / "machine.json").exists() else PROFILES

    @property
    def port(self):
        return os.environ.get("P3D_PORT") or self.raw.get("port") or (find_ports() or [""])[0]

    @property
    def orca(self):
        return _tool(self.raw.get("orca_slicer")) or find_orca()

    @property
    def scad(self):
        return _tool(self.raw.get("openscad")) or shutil.which("openscad") or ""


def _tool(v):
    """Config value -> runnable path ('' if missing): expands ~, resolves bare names on PATH."""
    if not v:
        return ""
    p = os.path.expanduser(v)
    return p if os.path.isfile(p) and os.access(p, os.X_OK) else (shutil.which(v) or "")


def find_ports():
    return sorted(glob.glob("/dev/serial/by-id/*")) or sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def find_orca():
    for c in (shutil.which("orca-slicer"), shutil.which("OrcaSlicer"), HOME / "orca-slicer",
              *sorted(glob.glob(str(HOME / "Applications/*rca*licer*.AppImage"))),
              *sorted(glob.glob(str(HOME / "*rca*licer*.AppImage")))):
        if c and pathlib.Path(c).is_file() and os.access(c, os.X_OK):
            return str(c)
    return ""


_cfg = None


def get():
    global _cfg
    if _cfg is None:
        _cfg = Config()
    return _cfg


def reset():
    global _cfg
    _cfg = None


# ---------- notifications ----------

def notify(title, msg, tags="printer"):
    """ntfy push if ntfy_url is set. Never raises."""
    c = get()
    if os.environ.get("P3D_NO_NOTIFY") or not c.ntfy_url:
        return False
    req = urllib.request.Request(c.ntfy_url, data=msg.encode(), method="POST",
                                 headers={"Title": title, "Tags": tags})
    if c.ntfy_token:
        req.add_header("Authorization", f"Bearer {c.ntfy_token}")
    try:
        urllib.request.urlopen(req, timeout=10).close()
        return True
    except Exception:
        return False


# ---------- serial port access ----------

def in_dialout_group():
    """(listed in /etc/group, active in this process)."""
    import grp
    try:
        g = grp.getgrnam("dialout")
    except KeyError:
        return False, False
    user = os.environ.get("USER") or HOME.name
    return user in g.gr_mem, g.gr_gid in os.getgroups()


def reexec_with_dialout():
    """If the port isn't accessible yet because the group isn't active until next login, re-run under `sg dialout`."""
    port = get().port
    if not port or os.access(port, os.R_OK | os.W_OK) or os.environ.get("P3D_SG"):
        return
    listed, active = in_dialout_group()
    if listed and not active and shutil.which("sg"):
        import shlex
        env = dict(os.environ, P3D_SG="1")
        cmd = " ".join(shlex.quote(x) for x in [sys.executable, "-m", "p3d", *sys.argv[1:]])
        os.execvpe("sg", ["sg", "dialout", "-c", cmd], env)


def open_serial(timeout=1):
    import serial
    c = get()
    if not c.port:
        sys.exit("no printer port found: plug in USB, power on, then `p3d setup` or `p3d doctor`")
    return serial.Serial(c.port, c.baud, timeout=timeout, exclusive=True)


# ---------- state ----------

FINAL = ("done", "failed", "cancelled")


def read_state():
    try:
        return json.loads(get().state.read_text())
    except Exception:
        return {"status": "idle"}


def write_state(**kw):
    st = get().state
    st.parent.mkdir(parents=True, exist_ok=True)
    tmp = st.with_name(st.name + ".tmp")
    tmp.write_text(json.dumps(kw, indent=1))
    os.replace(tmp, st)


def unit_active(unit):
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip() in ("active", "activating")


def print_running():
    return unit_active("p3d-print")
