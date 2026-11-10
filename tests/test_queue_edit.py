"""Queue reorder/remove (runner + dashboard routes). All state lives in tmp dirs (see conftest)."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from p3d import config, runner
from p3d.web import server


def mkq(tmp_path, names):
    q = []
    for n in names:
        d = tmp_path / "data/jobs" / f"2026-{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{n}.gcode").write_text("; estimated printing time (normal mode) = 1h 5m 0s\n; total filament used [g] = 7.5\n; filament_type = PLA\n")
        (d / "preview.png").write_bytes(b"\x89PNG")
        q.append({"gcode": str(d / f"{n}.gcode"), "name": d.name, "note": "x", "added": "t", "extra": 1})
    runner.q_save(q)
    return q


def test_move_keeps_fields_and_is_atomic(tmp_path):
    mkq(tmp_path, ["a", "b", "c"])
    q = runner.q_load()
    runner.q_save(runner.q_move(q, 3, 1))
    q = runner.q_load()
    assert [e["name"] for e in q] == ["2026-c", "2026-a", "2026-b"] and q[0]["extra"] == 1
    assert not list(config.get().queue_file.parent.glob("*.tmp"))
    with pytest.raises(runner.Refuse):
        runner.q_move(q, 0, 1)
    with pytest.raises(runner.Refuse):
        runner.q_move(q, 1, 4)


def test_remove_bounds(tmp_path):
    mkq(tmp_path, ["a", "b"])
    q = runner.q_load()
    assert runner.q_remove(q, 1)["name"] == "2026-a"
    with pytest.raises(runner.Refuse):
        runner.q_remove(q, 5)


def serve(monkeypatch, remote=False):
    if remote:
        orig = server.H.do_POST

        def do_POST(self):
            self.client_address = ("203.0.113.9", 1)
            return orig(self)
        monkeypatch.setattr(server.H, "do_POST", do_POST)
    h = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    return h


def call(h, path, body=None, method="POST"):
    req = urllib.request.Request(f"http://127.0.0.1:{h.server_port}{path}", data=None if method == "GET" else json.dumps(body or {}).encode(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_routes(tmp_path, monkeypatch):
    mkq(tmp_path, ["a", "b", "c"])
    h = serve(monkeypatch)
    st, body = call(h, "/api/queue", method="GET")
    v = json.loads(body)
    assert st == 200 and v[0]["est_min"] == 65 and v[0]["grams"] == "7.5" and v[0]["job"] == "2026-a"
    assert call(h, "/api/queue/move", {"n": 1, "to": 3, "name": "2026-a"})[0] == 200
    assert [e["n"] and e["name"] for e in json.loads(call(h, "/api/queue", method="GET")[1])] == ["2026-b", "2026-c", "2026-a"]
    assert call(h, "/api/queue/move", {"n": 1, "to": 2, "name": "stale"})[0] == 409
    assert call(h, "/api/queue/move", {"n": "x"})[0] == 400
    assert call(h, "/api/queue/remove", {"n": 2, "name": "2026-c"})[0] == 200
    assert len(runner.q_load()) == 2
    assert call(h, "/api/job/2026-a/preview.png", method="GET")[0] == 200
    assert call(h, "/api/job/..%2f..%2fetc/preview.png", method="GET")[0] == 404


def test_routes_forbidden_remote(tmp_path, monkeypatch):
    mkq(tmp_path, ["a", "b"])
    h = serve(monkeypatch, remote=True)
    assert call(h, "/api/queue/move", {"n": 1, "to": 2})[0] == 403
    assert call(h, "/api/queue/remove", {"n": 1})[0] == 403
    assert len(runner.q_load()) == 2
