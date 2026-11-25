"""Settings and paths. One place, no hard-coded machine paths.

Order (first wins): environment (P3D_DATA, P3D_PORT, P3D_STATE_DIR, P3D_CONFIG) > ~/.config/p3d/config.toml > defaults.
Written by `p3d setup`; see config.example.toml.
"""
import glob
import json
import os
import re
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
    "printer_type": "marlin",  # marlin (USB serial) | klipper (Moonraker) | octoprint | prusalink | bambu (LAN mode)
    "printer_url": "",         # network printers: http://host[:port] (bambu: the printer's IP)
    "printer_api_key": "",     # Moonraker (optional), OctoPrint, PrusaLink API key
    "bambu_serial": "",        # Bambu: printer serial number
    "bambu_access_code": "",   # Bambu: LAN access code shown on the printer
    "orca_slicer": "",       # empty = search PATH and common places
    "openscad": "",
    "data_dir": "",          # print log + samples (default ~/.local/share/p3d)
    "jobs_dir": "",          # sliced jobs, G-code (default <data_dir>/jobs)
    "publish_dir": "",       # p3d pack output (default <data_dir>/publish)
    "models_dir": "",        # your .scad parts (default: ./models if it exists, else <data_dir>/models)
    "ntfy_url": "",          # e.g. https://ntfy.sh/my-printer-topic (empty = no phone alerts)
    "ntfy_token": "",
    "urgent_ntfy_url": "",   # 2nd topic for loud alerts (done/cool/failed/needs you), sent with Priority 5; empty = off
    "urgent_hours": [7, 22], # local hours [from, to) when urgent alerts may ring (quiet at night)
    "voice_url": "",         # webhook that speaks loud alerts on the phone (e.g. Home Assistant app TTS); POST {"text"}; empty = off
    "quips_file": "",        # funny lines for alerts: "[print_start]" / "[print_done]" / "[print_failed]" headers, one line each
    "web_port": 8765,
    "web_host": "0.0.0.0",
    "cancel_from": [],       # extra IPs allowed to POST /api/cancel (localhost always is), e.g. a home server
    "control_from": [],      # extra IPs allowed to POST the other control endpoints (pause, resume, queue, ideas); cancel_from counts too
    "ideas_file": "",        # print-ideas board (Markdown, hand-editable); default <data_dir>/../ideas.md
    "z_home_xy": [110, 110], # where the printer probes Z on G28 (bed centre on the Ender-3 V3 SE); used by recover/addon
    "z_home_margin": 12,     # mm kept clear around that point before a recover/add-on may use G28
    "fridge_dir": "",        # shared-notes link folder (status.json, requests.json, approvals.json); empty = feature off
    "fridge_done_cmd": "",   # run on a pass verdict for a linked request; {n} = note number, {text} = message (shell-quoted); empty = off
    "event_cmd": "",         # run per notification with {"title","msg","level","tags"} as JSON on stdin (log/webhook bridge); empty = off
    "knowledge_files": [],   # dashboard Knowledge tab: [{id = "rules", title = "Rules", path = "~/notes/rules.md"}]; empty = tab hidden
    "cad_python": "",        # python with build123d/trimesh/shapely when the cad extra is not installed in-process (see `p3d install-cad`)
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
    def queue(self):
        return self.state_dir / "next_job"

    @property
    def stop(self):
        return self.state_dir / "STOP"

    @property
    def pause(self):
        """Touch = pause at the next layer change; PAUSE_AT holds layer numbers to pause before; RESUME ends a pause."""
        return self.state_dir / "PAUSE"

    @property
    def resume(self):
        return self.state_dir / "RESUME"

    @property
    def pause_at(self):
        return self.state_dir / "pause_at.json"

    @property
    def spools_file(self):
        return self.data / "spools.json"

    @property
    def queue_file(self):
        return self.data / "print_queue.json"

    @property
    def ideas(self):
        v = self.raw.get("ideas_file")
        return pathlib.Path(v).expanduser() if v else self.data.parent / "ideas.md"

    @property
    def fridge(self):
        """Link folder, or None when the feature is off (no fridge_dir / P3D_FRIDGE)."""
        v = os.environ.get("P3D_FRIDGE") or self.raw.get("fridge_dir")
        return pathlib.Path(v).expanduser() if v else None

    @property
    def control_ips(self):
        return ["127.0.0.1", "::1", *self.raw.get("cancel_from", []), *self.raw.get("control_from", [])]

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

def urgent_allowed(now=None):
    """True inside urgent_hours (local time, [from, to))."""
    import datetime
    lo, hi = get().urgent_hours
    h = (now or datetime.datetime.now()).hour
    return lo <= h < hi


def quip(event, pick=None):
    """A random line under [event] in quips_file, or '' (no file / no such event). Never raises."""
    import random
    path = get().quips_file
    if not path:
        return ""
    lines, cur = {}, None
    try:
        for raw in pathlib.Path(path).expanduser().read_text().splitlines():
            t = raw.strip()
            if not t or t.startswith("#"):
                continue
            if t.startswith("[") and t.endswith("]"):
                cur = lines.setdefault(t[1:-1], [])
            elif cur is not None:
                cur.append(t)
    except OSError:
        return ""
    got = lines.get(event) or []
    return (pick or random.choice)(got) if got else ""


def _post(url, title, msg, tags, actions=None, priority=None):
    c = get()
    req = urllib.request.Request(url, data=msg.encode(), method="POST",
                                 headers={"Title": title, "Tags": tags})
    if actions:
        req.add_header("Actions", actions)
    if priority:
        req.add_header("Priority", str(priority))
    if c.ntfy_token:
        req.add_header("Authorization", f"Bearer {c.ntfy_token}")
    if os.environ.get("P3D_NOTIFY_DRYRUN"):
        print(f"[dry-run ntfy] {url} P{priority or 3} {title}: {msg}", file=sys.stderr)
        return True
    try:
        urllib.request.urlopen(req, timeout=10).close()
        return True
    except Exception:
        return False


def notify(title, msg, tags="printer", actions=None, urgent=False, now=None, quip_event=None):
    """ntfy push if ntfy_url is set. Never raises. actions: ntfy action-button string, e.g. 'http, Resume, URL, method=POST'.
    urgent=True (done, cool, failed, needs attention) also posts to urgent_ntfy_url with Priority 5, only inside urgent_hours.
    quip_event: put a funny line from quips_file above the facts (same line on both topics).
    P3D_NOTIFY_DRYRUN=1 prints instead of sending."""
    c = get()
    if os.environ.get("P3D_NO_NOTIFY"):
        return False
    story(title, msg, tags)
    q = quip(quip_event) if quip_event else ""
    if q:
        msg = f"{q}\n\n{msg}"
    ok = _post(c.ntfy_url, title, msg, tags, actions) if c.ntfy_url else False
    if urgent and urgent_allowed(now):
        if c.urgent_ntfy_url:
            ok = _post(c.urgent_ntfy_url, title, msg, tags, actions, priority=5) or ok
        if c.voice_url:
            ok = speak(spoken(title, msg, q)) or ok
    return ok


def story(title, msg, tags="printer"):
    """Hand one event to `event_cmd` (JSON on stdin: title, msg, level, tags). Never raises; off in dry-run and under pytest."""
    if os.environ.get("P3D_NOTIFY_DRYRUN") or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        cmd = get().raw.get("event_cmd")
        if not cmd:
            return
        import shlex
        t = title.lower()
        level = "error" if ("fail" in t or "not started" in t) else "warn" if tags in ("warning", "stop_sign") else "info"
        subprocess.run([os.path.expanduser(x) for x in shlex.split(cmd)], timeout=15, capture_output=True, text=True,
                       input=json.dumps({"title": title, "msg": msg, "level": level, "tags": tags}))
    except Exception:
        return


def spoken(title, msg, q=""):
    """Short line for text-to-speech: title, first fact sentence (job names readable), then the quip."""
    fact = msg[len(q):].strip() if q and msg.startswith(q) else msg
    fact = re.split(r"(?<=[.!?])\s|\n", fact.replace("_", " "))[0].strip()
    fact = re.sub(r"\s*Rate it:.*$", "", fact)
    parts = [title.rstrip(".") + "."] + ([fact] if fact else []) + ([q] if q else [])
    return " ".join(parts)[:240]


def speak(text):
    """POST {"text": ...} to voice_url (phone TTS). Never raises. P3D_NOTIFY_DRYRUN=1 prints instead."""
    url = get().voice_url
    if not url:
        return False
    if os.environ.get("P3D_NOTIFY_DRYRUN"):
        print(f"[dry-run voice] {text}", file=sys.stderr)
        return True
    import json
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    import time
    for attempt in range(3):  # one missed POST = silent phone (2026-11-09 cancel): retry, and say why in the journal
        try:
            urllib.request.urlopen(req, timeout=15).close()
            return True
        except Exception as e:
            print(f"p3d voice: attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(3)
    return False


def desktop_notify(title, msg):
    """notify-send on this PC (best effort)."""
    if os.environ.get("P3D_NO_NOTIFY") or not shutil.which("notify-send"):
        return
    try:
        subprocess.run(["notify-send", title, msg], timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def lan_ip():
    """This machine's LAN address via a UDP socket trick (no packet is sent), or ''."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("192.0.2.1", 9))
            ip = sk.getsockname()[0]
        return "" if ip.startswith("127.") else ip
    except OSError:
        return ""


def reach_ip():
    """Address phones can use: Tailscale if present, else the LAN address, else ''."""
    try:
        ip = (subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split() or [""])[0]
    except (OSError, subprocess.SubprocessError):
        ip = ""
    return ip or lan_ip()


def web_base():
    """Dashboard URL for ntfy action buttons: Tailscale address, else the LAN address, else localhost (found at run time)."""
    return f"http://{reach_ip() or 'localhost'}:{get().web_port}"


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


def print_cancellable():
    """A job is printing or heating (not just the post-print cooldown, which keeps p3d-print active)."""
    return print_running() and read_state().get("status") not in ("done", "cancelled", "failed")
