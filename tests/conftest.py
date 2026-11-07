import os
import re

import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own config/data/state dirs and no ntfy."""
    monkeypatch.setenv("P3D_CONFIG", str(tmp_path / "cfg/config.toml"))
    monkeypatch.setenv("P3D_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("P3D_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("P3D_NO_NOTIFY", "1")
    monkeypatch.setenv("P3D_PORT", "/dev/null-fake")
    from p3d import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "cfg/config.toml")
    config.reset()
    yield tmp_path
    config.reset()


class FakeMarlin:
    """Enough of Marlin's serial protocol: checksummed N-lines, ok, Resend, temps, M78."""

    def __init__(self, resend_once=(), error_at=None):
        self.out = []          # reply lines waiting to be read
        self.got = {}          # N -> command (last accepted)
        self.order = []        # accepted N in order
        self.resend_once = set(resend_once)
        self.error_at = error_at
        self.expect = 0
        self.closed = False

    # pyserial surface used by p3d
    def write(self, data):
        for raw in data.decode().splitlines():
            self._line(raw.strip())

    def readline(self):
        return (self.out.pop(0) + "\n").encode() if self.out else b""

    def read(self, n):
        s = "".join(x + "\n" for x in self.out)
        self.out = []
        return s.encode()[:n]

    def reset_input_buffer(self):
        self.out = []

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _line(self, raw):
        if not raw:
            return
        m = re.match(r"N(\d+) (.*)\*(\d+)$", raw)
        if not m:  # unframed (M78, M108...)
            if raw == "M78":
                self.out += ["echo:Stats: Prints: 5, Finished: 4, Failed: 1",
                             "echo:Stats: Total time: 0d 3h 0m 0s, Longest job: 0d 1h 0m 0s",
                             "echo:Stats: Filament used: 12.34m", "ok"]
            else:
                self.out.append("ok")
            return
        n, cmd, cs = int(m.group(1)), m.group(2), int(m.group(3))
        body = f"N{n} {cmd}"
        calc = 0
        for ch in body.encode():
            calc ^= ch
        assert calc == cs, f"bad checksum on {raw}"
        if cmd.startswith("M110"):
            self.expect = int(cmd.split("N")[-1]) + 1
            self.out.append("ok")
            return
        if n in self.resend_once:
            self.resend_once.discard(n)
            self.out += [f"Error:checksum mismatch, Last Line: {n - 1}", f"Resend: {n}", "ok"]
            return
        if n != self.expect:
            self.out += [f"Resend: {self.expect}", "ok"]
            return
        self.got[n] = cmd
        self.order.append(n)
        self.expect = n + 1
        if self.error_at is not None and n == self.error_at:
            self.out.append("Error:Thermal Runaway, system stopped! Heater_ID: 0")
            return
        if cmd.startswith(("M105", "M155")):
            self.out.append("ok T:25.0 /0.0 B:24.0 /0.0 @:0 B@:0")
        else:
            self.out.append("ok")


@pytest.fixture
def fake_printer(monkeypatch):
    """Patch p3d to talk to a FakeMarlin and skip real waits. Returns a factory."""
    from p3d import config, sender
    made = {}

    def factory(**kw):
        made["printer"] = FakeMarlin(**kw)
        monkeypatch.setattr(config, "open_serial", lambda timeout=1: made["printer"])
        return made["printer"]

    monkeypatch.setattr(sender.time, "sleep", lambda s: None)
    monkeypatch.setattr(sender, "cooldown", lambda link, limit_min=60: True)
    return factory


GCODE = """; total layer number: 2
; estimated printing time (normal mode) = 1m 0s
; total filament used [g] = 1.5
; filament_type = PETG
M73 P0 R1
G28 ; home
G1 Z0.2 F600
G1 X10 Y10 E1
M73 P50 R0
G1 Z0.4
G1 X20 Y20 E2
M73 P100 R0
"""


@pytest.fixture
def job(tmp_path):
    d = tmp_path / "data/jobs/20260101-1200-cube"
    d.mkdir(parents=True)
    g = d / "cube.gcode"
    g.write_text(GCODE)
    return g


def commands(gcode_text):
    return [ln.split(";", 1)[0].strip() for ln in gcode_text.splitlines() if ln.split(";", 1)[0].strip()]


os.environ.setdefault("TZ", "UTC")
