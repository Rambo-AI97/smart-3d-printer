"""POST /api/cancel: localhost + cancel_from only, same effect as `p3d cancel`."""
import json, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer

from p3d import config
from p3d.web import server


def _post(port):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/cancel", data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _serve(monkeypatch, tmp_path, running, allow_local=True, state="printing"):
    c = config.Config({"cancel_from": []})
    monkeypatch.setattr(type(c), "state_dir", property(lambda s: tmp_path))
    monkeypatch.setattr(type(c), "stop", property(lambda s: tmp_path / "stop"))
    monkeypatch.setattr(config, "get", lambda: c)
    monkeypatch.setattr(config, "print_running", lambda: running)
    monkeypatch.setattr(config, "read_state", lambda: {"status": state})
    if not allow_local:
        monkeypatch.setattr(server.H, "client_address", ("203.0.113.9", 1), raising=False)
        orig = server.H.do_POST
        def do_POST(self):
            self.client_address = ("203.0.113.9", 1)
            return orig(self)
        monkeypatch.setattr(server.H, "do_POST", do_POST)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_nothing_running(monkeypatch, tmp_path):
    h = _serve(monkeypatch, tmp_path, running=False)
    assert _post(h.server_port) == (200, {"ok": "nothing to stop"})
    assert not (tmp_path / "stop").exists()
    h.shutdown()


def test_cancel_running(monkeypatch, tmp_path):
    h = _serve(monkeypatch, tmp_path, running=True)
    assert _post(h.server_port) == (200, {"ok": "cancel requested"})
    assert (tmp_path / "stop").exists()
    h.shutdown()


def test_other_ip_forbidden(monkeypatch, tmp_path):
    h = _serve(monkeypatch, tmp_path, running=True, allow_local=False)
    assert _post(h.server_port)[0] == 403
    assert not (tmp_path / "stop").exists()
    h.shutdown()


def test_cooldown_after_done_is_nothing(monkeypatch, tmp_path):
    h = _serve(monkeypatch, tmp_path, running=True, state="done")  # unit still active for the cooldown
    assert _post(h.server_port) == (200, {"ok": "nothing to stop"})
    assert not (tmp_path / "stop").exists()
    h.shutdown()
