"""Network printer backends against fake local HTTP servers, plus netsender end to end (fake Moonraker)."""
import csv
import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from p3d import config, netsender, printers
from p3d.printers import BackendError
from p3d.printers.base import multipart
from conftest import GCODE


class Fake:
    """Local HTTP server. routes: {(METHOD, path-prefix): json-or-callable}; every request is recorded."""

    def __init__(self, routes):
        self.routes, self.log = routes, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def handle_any(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                outer.log.append((self.command, self.path, dict(self.headers), body))
                for (m, pre), resp in outer.routes.items():
                    if m == self.command and self.path.startswith(pre):
                        r = resp() if callable(resp) else resp
                        code = 200
                        if isinstance(r, tuple):
                            code, r = r
                        data = b"" if r is None else json.dumps(r).encode()
                        self.send_response(code)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = do_PUT = do_DELETE = handle_any

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def calls(self, method, prefix):
        return [x for x in self.log if x[0] == method and x[1].startswith(prefix)]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def serve():
    made = []

    def f(routes):
        s = Fake(routes)
        made.append(s)
        return s
    yield f
    for s in made:
        s.close()


def cfg(**kw):
    return types.SimpleNamespace(printer_url=kw.pop("url", ""), printer_api_key=kw.pop("key", ""), bambu_serial="", bambu_access_code="",
                                 **kw)


def mk(t, url, key=""):
    return printers.backend_class(t)(cfg(url=url, key=key))


# ---------- registry ----------

def test_registry_and_caps():
    assert printers.caps_for_type("marlin") == sorted({"pause", "gcode", "level", "pid", "probe", "calib", "recover"})
    for t in ("klipper", "octoprint", "prusalink", "bambu"):
        assert "level" not in printers.caps_for_type(t)
    assert "pause" in printers.caps_for_type("klipper")
    with pytest.raises(BackendError):
        printers.printer_type(cfg(printer_type="nope"))


def test_get_backend_by_config(tmp_path):
    config.get().raw["printer_type"] = "klipper"
    assert printers.get_backend().TYPE == "klipper"


def test_require_message():
    config.get().raw["printer_type"] = "octoprint"
    with pytest.raises(SystemExit) as e:
        printers.require("level")
    assert str(e.value) == "not available for octoprint printers (needs a USB Marlin connection)"
    config.get().raw["printer_type"] = "marlin"
    printers.require("level")


def test_multipart_shape():
    ct, body = multipart({"print": "true"}, {"file": ("a.gcode", b"G28\n")})
    b = ct.split("boundary=")[1].encode()
    assert b'name="print"\r\n\r\ntrue' in body and b'filename="a.gcode"' in body and body.endswith(b"--" + b + b"--\r\n")


def test_unreachable_is_one_line():
    b = mk("klipper", "http://127.0.0.1:1")
    with pytest.raises(BackendError) as e:
        b.status()
    assert "\n" not in str(e.value) and "cannot reach" in str(e.value)


# ---------- klipper ----------

def klipper_status(state="printing", prog=0.5, layer=3):
    return {"result": {"status": {
        "print_stats": {"state": state, "print_duration": 100.0, "info": {"current_layer": layer}},
        "virtual_sdcard": {"progress": prog}, "extruder": {"temperature": 214.9, "target": 215.0},
        "heater_bed": {"temperature": 60.0, "target": 60.0}}}}


def test_klipper(serve, job):
    s = serve({("POST", "/server/files/upload"): {"item": {}}, ("GET", "/printer/objects/query"): klipper_status(),
               ("POST", "/printer/print/pause"): {}, ("POST", "/printer/print/resume"): {},
               ("POST", "/printer/print/cancel"): {}, ("POST", "/printer/gcode/script"): {}, ("GET", "/server/info"): {"result": {}}})
    b = mk("klipper", s.url, key="sekret")
    b.start(job)
    m, p, h, body = s.calls("POST", "/server/files/upload")[0]
    assert h["X-Api-Key"] == "sekret" and h["Content-Type"].startswith("multipart/form-data")
    assert b'name="print"\r\n\r\ntrue' in body and b"G28 ; home" in body and b'filename="cube.gcode"' in body
    st = b.status()
    assert st["state"] == "printing" and st["progress"] == 0.5 and st["layer"] == 3 and st["nozzle"] == 214.9
    assert st["bed_target"] == 60.0 and st["elapsed_s"] == 100.0 and st["left_s"] == pytest.approx(100.0)
    b.pause(); b.resume(); b.cancel(); b.gcode("M104 S0")
    assert s.calls("POST", "/printer/print/pause") and s.calls("POST", "/printer/print/resume") and s.calls("POST", "/printer/print/cancel")
    assert "script=M104+S0" in s.calls("POST", "/printer/gcode/script")[0][1]
    b.ping()


@pytest.mark.parametrize("raw,want", [("complete", "done"), ("cancelled", "cancelled"), ("error", "failed"),
                                      ("standby", "idle"), ("paused", "paused")])
def test_klipper_state_map(serve, raw, want):
    s = serve({("GET", "/printer/objects/query"): klipper_status(raw)})
    assert mk("klipper", s.url).status()["state"] == want


def test_klipper_no_key_no_header(serve):
    s = serve({("GET", "/printer/objects/query"): klipper_status()})
    mk("klipper", s.url).status()
    assert "X-Api-Key" not in s.log[0][2]


def test_access_denied(serve):
    s = serve({("GET", "/printer/objects/query"): (401, {})})
    with pytest.raises(BackendError, match="access denied"):
        mk("klipper", s.url).status()


# ---------- octoprint ----------

def test_octoprint(serve, job):
    job_resp = {"state": "Printing", "progress": {"completion": 42.0, "printTime": 60, "printTimeLeft": 90}}
    pr = {"state": {"flags": {"printing": True, "operational": True}},
          "temperature": {"tool0": {"actual": 200.0, "target": 210.0}, "bed": {"actual": 55.0, "target": 60.0}}}
    s = serve({("POST", "/api/files/local"): (201, {}), ("GET", "/api/job"): job_resp, ("GET", "/api/printer"): pr,
               ("POST", "/api/job"): (204, None), ("POST", "/api/printer/command"): (204, None), ("GET", "/api/version"): {"api": "0.1"}})
    b = mk("octoprint", s.url, key="K")
    b.start(job)
    _, _, h, body = s.calls("POST", "/api/files/local")[0]
    assert h["X-Api-Key"] == "K" and b'name="select"\r\n\r\ntrue' in body and b'name="print"\r\n\r\ntrue' in body
    st = b.status()
    assert st["state"] == "printing" and st["progress"] == pytest.approx(0.42) and st["nozzle_target"] == 210.0
    assert st["elapsed_s"] == 60 and st["left_s"] == 90
    b.pause(); b.resume(); b.cancel(); b.gcode("M105")
    sent = [json.loads(x[3]) for x in s.calls("POST", "/api/job")]
    assert sent == [{"command": "pause", "action": "pause"}, {"command": "pause", "action": "resume"}, {"command": "cancel"}]
    assert json.loads(s.calls("POST", "/api/printer/command")[0][3]) == {"commands": ["M105"]}
    b.ping()


def test_octoprint_needs_key(serve, job):
    s = serve({})
    with pytest.raises(BackendError, match="printer_api_key"):
        mk("octoprint", s.url).start(job)


def test_octoprint_done_and_paused(serve):
    flags = {"state": {"flags": {"operational": True}}}
    s = serve({("GET", "/api/job"): {"state": "Operational", "progress": {"completion": 100.0}}, ("GET", "/api/printer"): flags})
    assert mk("octoprint", s.url, "K").status()["state"] == "done"
    s2 = serve({("GET", "/api/job"): {"state": "Paused", "progress": {"completion": 10.0}}, ("GET", "/api/printer"): flags})
    assert mk("octoprint", s2.url, "K").status()["state"] == "paused"


# ---------- prusalink ----------

def test_prusalink(serve, job):
    status = {"printer": {"state": "PRINTING", "temp_nozzle": 215.0, "target_nozzle": 215.0, "temp_bed": 60.0, "target_bed": 60.0},
              "job": {"id": 7, "progress": 25, "time_remaining": 600, "time_printing": 200}}
    s = serve({("PUT", "/api/v1/files/usb/"): (201, {}), ("GET", "/api/v1/status"): status, ("GET", "/api/v1/job"): {"id": 7},
               ("PUT", "/api/v1/job/7/"): (204, None), ("DELETE", "/api/v1/job/7"): (204, None), ("GET", "/api/version"): {}})
    b = mk("prusalink", s.url, "PK")
    b.start(job)
    m, p, h, body = s.calls("PUT", "/api/v1/files/usb/")[0]
    assert p == "/api/v1/files/usb/cube.gcode" and h["Print-After-Upload"] == "?1" and h["Overwrite"] == "?1"
    assert h["X-Api-Key"] == "PK" and body == job.read_bytes()
    st = b.status()
    assert st["state"] == "printing" and st["progress"] == 0.25 and st["left_s"] == 600 and st["elapsed_s"] == 200
    b.pause(); b.resume(); b.cancel()
    assert s.calls("PUT", "/api/v1/job/7/pause") and s.calls("PUT", "/api/v1/job/7/resume") and s.calls("DELETE", "/api/v1/job/7")
    b.ping()


@pytest.mark.parametrize("raw,want", [("FINISHED", "done"), ("STOPPED", "cancelled"), ("ERROR", "failed"), ("PAUSED", "paused"),
                                      ("IDLE", "idle")])
def test_prusalink_state_map(serve, raw, want):
    s = serve({("GET", "/api/v1/status"): {"printer": {"state": raw}}})
    assert mk("prusalink", s.url).status()["state"] == want


# ---------- bambu (ftplib + paho mocked) ----------

class FakeFTP:
    last = None

    def __init__(self, context=None):
        FakeFTP.last = self
        self.ops = []

    def connect(self, host, port, timeout=0):
        self.ops.append(("connect", host, port))

    def login(self, u, p):
        self.ops.append(("login", u, p))

    def prot_p(self):
        self.ops.append(("prot_p",))

    def storbinary(self, cmd, f):
        self.ops.append(("stor", cmd, f.read()))

    def close(self):
        pass


class FakeMqtt:
    last = None

    def __init__(self, *a, **k):
        FakeMqtt.last = self
        self.pub = []
        self.subs = []

    def username_pw_set(self, u, p):
        self.auth = (u, p)

    def tls_set_context(self, c):
        pass

    def connect(self, host, port, keepalive=60):
        self.addr = (host, port)

    def loop_start(self):
        self.on_connect(self, None, {}, 0)

    def subscribe(self, t):
        self.subs.append(t)

    def publish(self, topic, payload):
        self.pub.append((topic, json.loads(payload)))
        return types.SimpleNamespace(wait_for_publish=lambda t=None: None)

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def feed(self, **report):
        self.on_message(self, None, types.SimpleNamespace(payload=json.dumps({"print": report}).encode()))


@pytest.fixture
def paho(monkeypatch):
    from p3d.printers import bambu
    mod = types.ModuleType("paho.mqtt.client")
    mod.Client = FakeMqtt
    mod.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
    for n, m in (("paho", types.ModuleType("paho")), ("paho.mqtt", types.ModuleType("paho.mqtt")), ("paho.mqtt.client", mod)):
        monkeypatch.setitem(sys.modules, n, m)
    monkeypatch.setattr(bambu, "ImplicitFTPS", FakeFTP)
    return mod


def bambu_backend():
    c = cfg(url="192.0.2.5")
    c.bambu_serial, c.bambu_access_code = "SER123", "ACODE"
    return printers.backend_class("bambu")(c)


def test_bambu_refuses_plain_gcode(job):
    with pytest.raises(BackendError, match=r"\.gcode\.3mf"):
        bambu_backend().start(job)


def test_bambu_needs_paho(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "paho", None)
    f = tmp_path / "x.gcode.3mf"
    f.write_bytes(b"PK")
    with pytest.raises(BackendError, match=r"pip install 'p3d\[bambu\]'"):
        bambu_backend().start(f)


def test_bambu_start_status_controls(paho, tmp_path):
    f = tmp_path / "cube.gcode.3mf"
    f.write_bytes(b"PKdata")
    b = bambu_backend()
    b.start(f)
    ops = FakeFTP.last.ops
    assert ("connect", "192.0.2.5", 990) in ops and ("login", "bblp", "ACODE") in ops and ("stor", "STOR cube.gcode.3mf", b"PKdata") in ops
    m = FakeMqtt.last
    assert m.auth == ("bblp", "ACODE") and m.addr == ("192.0.2.5", 8883) and m.subs == ["device/SER123/report"]
    topic, msg = [p for p in m.pub if "print" in p[1]][0]
    assert topic == "device/SER123/request" and msg["print"]["command"] == "project_file"
    assert msg["print"]["param"] == "Metadata/plate_1.gcode" and msg["print"]["url"] == "ftp:///cube.gcode.3mf"
    assert msg["print"]["use_ams"] is False and msg["print"]["subtask_name"] == "cube.gcode"
    m.feed(gcode_state="RUNNING", mc_percent=40, mc_remaining_time=30, layer_num=12, nozzle_temper=220.0, bed_temper=60.0,
           nozzle_target_temper=220.0, bed_target_temper=60.0)
    st = b.status()
    assert st["state"] == "printing" and st["progress"] == 0.4 and st["left_s"] == 1800 and st["layer"] == 12 and st["bed"] == 60.0
    b.pause(); b.resume(); b.cancel()
    cmds = [p[1]["print"]["command"] for p in m.pub[-3:]]
    assert cmds == ["pause", "resume", "stop"] and m.pub[-1][1]["print"]["sequence_id"] == "0"
    for raw, want in (("PAUSE", "paused"), ("FINISH", "done"), ("FAILED", "failed"), ("IDLE", "idle")):
        m.feed(gcode_state=raw)
        assert b.status()["state"] == want


# ---------- netsender end to end (fake Moonraker) ----------

class MoonSim:
    """Fake Moonraker whose print advances one step per status poll."""

    def __init__(self, steps=3, layers=(1, 2, 3)):
        self.steps, self.i, self.layers = steps, 0, layers
        self.cancelled = self.paused = False

    def status(self):
        if self.cancelled:
            return klipper_status("cancelled", 0.3, 1)
        if self.paused:
            return klipper_status("paused", 0.5, self.layers[min(self.i, len(self.layers) - 1)])
        self.i += 1
        if self.i > self.steps:
            return klipper_status("complete", 1.0, self.layers[-1])
        return klipper_status("printing", self.i / (self.steps + 1), self.layers[min(self.i - 1, len(self.layers) - 1)])


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(netsender, "POLL", 0)
    monkeypatch.setattr(netsender.time, "sleep", lambda s: None)


def setup_moon(serve, sim):
    def stop(which):
        def f():
            setattr(sim, which, True)
            return {}
        return f
    s = serve({("POST", "/server/files/upload"): {"item": {}}, ("GET", "/printer/objects/query"): sim.status,
               ("POST", "/printer/print/cancel"): stop("cancelled"), ("POST", "/printer/print/pause"): stop("paused"),
               ("POST", "/printer/print/resume"): lambda: (setattr(sim, "paused", False), {})[1]})
    config.get().raw.update(printer_type="klipper", printer_url=s.url)
    return s


def test_netsender_done(serve, job, fast, monkeypatch):
    sim = MoonSim()
    s = setup_moon(serve, sim)
    from p3d import spools
    sp = spools.load()
    spools.add(sp, "red", "petg", 1000)
    spools.save(sp)
    notes = []
    monkeypatch.setattr(netsender, "notify", lambda *a, **k: notes.append(a[0]))
    assert netsender.main(str(job)) == 0
    assert s.calls("POST", "/server/files/upload")
    st = config.read_state()
    assert st["status"] == "done" and st["progress"] == 100 and st["file"] == "cube" and st["ended_at"] and st["job_id"] == job.parent.name
    for k in ("started", "minutes", "layer", "layer_done", "est_total_min", "grams", "job_dir", "total_layers", "spool"):
        assert k in st
    assert st["total_layers"] == 2 and float(st["grams"]) == 1.5 and st["spool"] == "red"
    assert notes == ["Print started", "Print done"]
    rows = list(csv.DictReader(open(config.get().data / "print_log.csv")))
    assert rows[-1]["name"] == "cube" and rows[-1]["status"] == "done"
    assert spools.load()["spools"][0]["left_g"] == pytest.approx(998.5)
    assert not config.get().stop.exists()


def test_netsender_running_state_fields(serve, job, fast, monkeypatch):
    sim = MoonSim(steps=2)
    setup_moon(serve, sim)
    seen = []
    orig = config.write_state
    monkeypatch.setattr(config, "write_state", lambda **kw: (seen.append(kw), orig(**kw))[1])
    netsender.main(str(job))
    live = [x for x in seen if x["status"] == "printing" and x.get("nozzle") is not None]
    assert live
    x = live[-1]
    for k in ("file", "status", "progress", "remaining_min", "elapsed_min", "eta", "z", "layer", "nozzle", "nozzle_target", "bed",
              "bed_target", "temps", "started", "updated", "layer_done", "z_done", "est_total_min", "total_layers", "job_id"):
        assert k in x, k
    assert x["nozzle_target"] == 215.0 and x["temps"].startswith("T:")


def test_netsender_cancel(serve, job, fast):
    sim = MoonSim(steps=1000)
    s = setup_moon(serve, sim)
    c = config.get()
    c.state_dir.mkdir(parents=True, exist_ok=True)
    orig = sim.status
    n = {"i": 0}

    def status():
        n["i"] += 1
        if n["i"] == 3:
            c.stop.touch()
        return orig()
    s.routes[("GET", "/printer/objects/query")] = status
    netsender.main(str(job))
    assert s.calls("POST", "/printer/print/cancel")
    assert config.read_state()["status"] == "cancelled"
    rows = list(csv.DictReader(open(c.data / "print_log.csv")))
    assert rows[-1]["status"] == "cancelled"
    assert not c.stop.exists()


def test_netsender_pause_resume_files(serve, job, fast):
    sim = MoonSim(steps=1000)
    s = setup_moon(serve, sim)
    c = config.get()
    c.state_dir.mkdir(parents=True, exist_ok=True)
    orig = sim.status
    n = {"i": 0}

    def status():
        n["i"] += 1
        if n["i"] == 3:
            c.pause.touch()
        if n["i"] == 6:
            c.resume.touch()
        if n["i"] == 10:
            c.stop.touch()
        return orig()
    s.routes[("GET", "/printer/objects/query")] = status
    netsender.main(str(job))
    assert s.calls("POST", "/printer/print/pause") and s.calls("POST", "/printer/print/resume")
    assert config.read_state()["status"] == "cancelled"


def test_netsender_pause_at_layer(serve, job, fast):
    from p3d import pause
    pause.write_pause_at([2])
    sim = MoonSim(steps=1000, layers=(1, 1, 2, 2, 3))
    s = setup_moon(serve, sim)
    c = config.get()
    orig = sim.status

    def status():
        if sim.paused and len(s.calls("POST", "/printer/print/pause")) == 1 and not s.calls("POST", "/printer/print/resume"):
            c.resume.touch()
        r = orig()
        if s.calls("POST", "/printer/print/resume"):
            c.stop.touch()
        return r
    s.routes[("GET", "/printer/objects/query")] = status
    netsender.main(str(job))
    assert len(s.calls("POST", "/printer/print/pause")) == 1 and s.calls("POST", "/printer/print/resume")
    assert pause.read_pause_at() == []


def test_netsender_refuses_pause_at_without_layers(serve, job, monkeypatch):
    from p3d import pause
    pause.write_pause_at([2])
    s = serve({})
    config.get().raw.update(printer_type="octoprint", printer_url=s.url, printer_api_key="K")
    monkeypatch.setattr(netsender, "notify", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="pause-at-layer"):
        netsender.main(str(job))
    assert config.read_state()["status"] == "failed" and not s.log


def test_netsender_upload_failure(job, monkeypatch):
    config.get().raw.update(printer_type="klipper", printer_url="http://127.0.0.1:1")
    monkeypatch.setattr(netsender, "notify", lambda *a, **k: None)
    with pytest.raises(BackendError):
        netsender.main(str(job))
    st = config.read_state()
    assert st["status"] == "failed" and "cannot start on the printer" in st["error"]


def test_netsender_ignores_stale_done(serve, job, fast):
    """A 'complete' left over from the previous job must not end this one before it was seen printing."""
    seq = iter([klipper_status("complete", 1.0)] * 3 + [klipper_status("printing", 0.5)] * 2 + [klipper_status("complete", 1.0)])
    s = serve({("POST", "/server/files/upload"): {}, ("GET", "/printer/objects/query"): lambda: next(seq)})
    config.get().raw.update(printer_type="klipper", printer_url=s.url)
    netsender.main(str(job))
    assert config.read_state()["status"] == "done"
    assert len(s.calls("GET", "/printer/objects/query")) == 6


def test_netsender_marlin_dispatch(monkeypatch):
    """sender.cli --queued hands over to netsender only for network printers."""
    from p3d import sender
    got = []
    monkeypatch.setattr(netsender, "cli", lambda argv: got.append(argv))
    config.get().raw["printer_type"] = "klipper"
    sender.cli(["--queued"])
    assert got == [["--queued"]]


# ---------- doctor, runner, web, cli ----------

def test_doctor_network(serve):
    from p3d import doctor
    s = serve({("GET", "/server/info"): {"result": {}}})
    config.get().raw.update(printer_type="klipper", printer_url=s.url)
    rows = {n: (lv, m) for lv, n, m in doctor.checks()}
    assert rows["printer"][0] == "ok" and "printer port" not in rows
    config.get().raw["printer_url"] = "http://127.0.0.1:1"
    rows = {n: (lv, m) for lv, n, m in doctor.checks()}
    assert rows["printer"][0] == "FAIL"


def test_runner_refuses_pause_at_for_octoprint(job):
    from p3d import runner
    config.get().raw["printer_type"] = "octoprint"
    with pytest.raises(runner.Refuse, match="pause-at-layer"):
        runner.start(job, pause_at=[3], force=True)


def test_runner_starts_netsender_unit(job, monkeypatch):
    from p3d import runner
    config.get().raw["printer_type"] = "klipper"
    got = []
    monkeypatch.setattr(runner.subprocess, "run", lambda cmd, **k: got.append(cmd))
    monkeypatch.setattr(runner, "service_dir", lambda: job.parent / "nounits")
    runner.start_unit("p3d-print", ["--queued"])
    assert "p3d.netsender" in " ".join(got[0])


def test_runner_accepts_3mf_for_bambu(tmp_path):
    from p3d import runner
    f = tmp_path / "a.gcode.3mf"
    f.write_bytes(b"PK")
    with pytest.raises(runner.Refuse):
        runner.resolve_gcode(f)
    config.get().raw["printer_type"] = "bambu"
    assert runner.resolve_gcode(f) == f


@pytest.mark.parametrize("cmd", ["level", "pid", "probe", "calib", "recover", "addon"])
def test_cli_refuses_marlin_only(cmd, capsys):
    from p3d import cli
    config.get().raw["printer_type"] = "klipper"
    argv = {"calib": ["calib", "temp"], "recover": ["recover", "x"], "addon": ["addon", "m.stl", "--on-z", "5"]}.get(cmd, [cmd])
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert "not available for klipper printers (needs a USB Marlin connection)" in str(e.value)


def test_web_printer_info_and_controls():
    from p3d.web import server
    assert server.printer_info()["type"] == "marlin" and "level" in server.printer_info()["caps"]
    config.get().raw["printer_type"] = "klipper"
    assert server.printer_info() == {"type": "klipper", "caps": ["gcode", "pause"]}
    c = server.controls()
    assert c["printer"]["type"] == "klipper" and not c["level"] and "not available" in c["why"]["level"]
    from p3d import runner
    with pytest.raises(runner.Refuse, match="not available"):
        server.level_start()
