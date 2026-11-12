"""Host-side pause/resume for stock Marlin (no firmware pause needed).

The sender stops streaming at a layer boundary, retracts, lifts Z and parks; heaters stay on.
Resume moves back over the part, lowers, un-retracts + a small prime and carries on.
Control files in the state dir: PAUSE (pause at the next layer), pause_at.json (layers to pause before), RESUME.
"""
import json

from . import config
from .gcode import Z_MAX, _fmt

RETRACT, LIFT, PRIME = 2.0, 10.0, 0.5


def pause_cmds(pos, park_y=220, retract=RETRACT, lift=LIFT):
    """Commands that park the head. None if the position is not known yet (nothing printed)."""
    if pos.z is None:
        return None
    return ["M400", "M83", f"G1 E-{_fmt(retract)} F2400", "G90",
            f"G1 Z{_fmt(min(pos.z + lift, Z_MAX))} F600", f"G1 X0 Y{_fmt(park_y)} F6000"]


def resume_cmds(pos, nozzle=0.0, retract=RETRACT, prime=PRIME):
    """Commands that return to where the pause started and pick the print up again."""
    c = []
    if nozzle and nozzle > 150:
        c.append(f"M109 S{_fmt(nozzle)}")
    c += ["G90", "M83"]
    if pos.x is not None and pos.y is not None:
        c.append(f"G1 X{_fmt(pos.x)} Y{_fmt(pos.y)} F6000")
    c.append(f"G1 Z{_fmt(pos.z)} F600")
    c.append(f"G1 E{_fmt(retract + prime)} F300")
    if pos.abs_e:  # the file used absolute E: put the counter back
        c += ["M82", f"G92 E{_fmt(pos.e)}"]
    return c


# ---- control files (CLI, web API and sender all use these) ----

def read_pause_at():
    try:
        return sorted({int(x) for x in json.loads(config.get().pause_at.read_text())})
    except Exception:
        return []


def write_pause_at(layers):
    c = config.get()
    c.state_dir.mkdir(parents=True, exist_ok=True)
    if layers:
        c.pause_at.write_text(json.dumps(sorted({int(x) for x in layers})))
    else:
        c.pause_at.unlink(missing_ok=True)


def request_pause(at_layers=None):
    """Pause at the next layer change, or before each layer in at_layers. Returns a message."""
    c = config.get()
    c.state_dir.mkdir(parents=True, exist_ok=True)
    if at_layers:
        write_pause_at(read_pause_at() + list(at_layers))
        return "will pause before layer " + ", ".join(str(x) for x in read_pause_at())
    c.pause.touch()
    return "pause requested: the print stops at the next layer change"


def remove_pause_layers(layers=None):
    """Drop pending layer pauses (all when layers is None). The running sender re-reads the file at each layer change."""
    left = [] if layers is None else [x for x in read_pause_at() if x not in {int(y) for y in layers}]
    write_pause_at(left)
    return "pending layer pauses: " + (", ".join(str(x) for x in left) or "none")


def request_resume():
    c = config.get()
    if not config.read_state().get("status") == "paused":
        return "not paused"
    c.resume.touch()
    return "resume requested"


def due(layer, pause_file_exists, at_layers):
    """Should the sender pause before starting this layer?"""
    return bool(layer) and (pause_file_exists or layer in at_layers)
