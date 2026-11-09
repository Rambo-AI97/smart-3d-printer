"""POST /api/pause, /api/resume, /api/ideas, /api/queue/next: same access rules as /api/cancel."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from p3d import config
from p3d.web import server


def serve(monkeypatch, remote=False):
    monkeypatch.setattr(config, "print_running", lambda: True)
    if remote:
        orig = server.H.do_POST

        def do_POST(self):
            self.client_address = ("203.0.113.9", 1)
            return orig(self)
        monkeypatch.setattr(server.H, "do_POST", do_POST)
    h = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    return h


def post(h, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{h.server_port}{path}", data=json.dumps(body or {}).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_pause_then_resume(monkeypatch):
    h = serve(monkeypatch)
    config.write_state(status="printing")
    assert post(h, "/api/pause")[0] == 200 and config.get().pause.exists()
    config.write_state(status="paused")
    assert post(h, "/api/resume") == (200, {"ok": "resume requested"}) and config.get().resume.exists()
    h.shutdown()


def test_ideas_add_and_move(monkeypatch):
    h = serve(monkeypatch)
    code, r = post(h, "/api/ideas", {"action": "add", "text": "Tray #desk"})
    assert code == 200 and r["items"][0]["id"] == 1
    assert post(h, "/api/ideas", {"action": "move", "id": 1, "status": "planned"})[1]["items"][0]["status"] == "planned"
    assert post(h, "/api/ideas", {"action": "move", "id": 9, "status": "planned"})[0] == 400
    h.shutdown()


def test_queue_next_empty_is_409(monkeypatch):
    h = serve(monkeypatch)
    assert post(h, "/api/queue/next")[0] == 409
    h.shutdown()


def test_control_forbidden_from_other_ip(monkeypatch):
    h = serve(monkeypatch, remote=True)
    for p in ("/api/pause", "/api/resume", "/api/ideas", "/api/queue/next"):
        assert post(h, p, {"action": "add", "text": "x"})[0] == 403
    assert not config.get().pause.exists()
    h.shutdown()
