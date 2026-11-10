"""Add-to-queue, model library + background slice task, loaded-filament check. Temp dirs only (see conftest)."""
import json
import time

from p3d import runner, spools, config
from p3d.web import server
from test_queue_edit import call, serve


def mkjob(tmp_path, name, fil="PETG"):
    d = tmp_path / "data/jobs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.gcode").write_text("; total filament used [g] = 1.0\n" + "G1 X1\n" * 50000 + f"; filament_type = {fil}\n; end\n")
    return d


def test_add_validates_and_queues(tmp_path, monkeypatch):
    mkjob(tmp_path, "2026-a")
    h = serve(monkeypatch)
    assert call(h, "/api/queue/add", {"job": "2026-a"})[0] == 200
    assert [e["name"] for e in runner.q_load()] == ["2026-a"]
    for bad in ("../x", "..", "nope", "", "/etc"):
        assert call(h, "/api/queue/add", {"job": bad})[0] == 409
    assert len(runner.q_load()) == 1


def test_add_forbidden_remote(tmp_path, monkeypatch):
    mkjob(tmp_path, "2026-a")
    h = serve(monkeypatch, remote=True)
    assert call(h, "/api/queue/add", {"job": "2026-a"})[0] == 403
    assert call(h, "/api/models/slice", {"model": "x.stl"})[0] == 403
    assert runner.q_load() == []


def test_loaded_filament_and_gcode_type(tmp_path, monkeypatch):
    assert server.loaded_filament()["material"] == ""  # unknown, never guessed
    cfgf = tmp_path / "cfg/config.toml"
    cfgf.parent.mkdir(parents=True, exist_ok=True)
    cfgf.write_text('filament = "pla"\n')
    config.reset()
    assert server.loaded_filament() == {"material": "PLA", "source": "config"}
    d = spools.load()
    spools.add(d, "red", "petg", 1000)
    spools.save(d)
    assert server.loaded_filament()["material"] == "PETG"
    g = mkjob(tmp_path, "2026-a", "PLA") / "2026-a.gcode"
    assert server.gcode_filament(str(g)) == "PLA"
    runner.q_save(runner.q_add([], g))
    assert server.queue_view()[0]["sliced"] == "PLA"
    h = serve(monkeypatch)
    assert json.loads(call(h, "/api/state", method="GET")[1])["loaded_filament"]["material"] == "PETG"


def test_models_and_slice_task(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    (lib / "scad").mkdir(parents=True)
    (lib / "scad/cup.stl").write_text("x")
    (lib / "scad/cup.png").write_bytes(b"\x89PNG")
    (lib / "bare.stl").write_text("x")
    monkeypatch.setenv("P3D_MODELS_LIB", str(lib))
    h = serve(monkeypatch)
    m = json.loads(call(h, "/api/models", method="GET")[1])
    assert {(x["id"], x["picture"]) for x in m} == {("scad/cup.stl", True), ("bare.stl", False)}
    assert call(h, "/api/model.png?id=scad%2Fcup.stl", method="GET")[0] == 200
    assert call(h, "/api/model.png?id=..%2F..%2Fetc%2Fpasswd", method="GET")[0] == 404
    assert call(h, "/api/models/slice", {"model": "scad/cup.stl"})[0] == 409  # filament unknown
    assert call(h, "/api/models/slice", {"model": "../x.stl"})[0] == 409
    cfgf = tmp_path / "cfg/config.toml"
    cfgf.parent.mkdir(parents=True, exist_ok=True)
    cfgf.write_text('filament = "pla"\n')
    config.reset()
    seen = {}

    def fake(path, fil):
        seen["a"] = (path.name, fil)
        time.sleep(0.3)
        return mkjob(tmp_path, "2026-cup"), mkjob(tmp_path, "2026-cup") / "2026-cup.gcode"
    monkeypatch.setattr(server, "slice_start", lambda b, run=None, _o=server.slice_start: _o(b, run=fake))
    st, body = call(h, "/api/models/slice", {"model": "scad/cup.stl"})
    assert st == 202
    tid = json.loads(body)["task"]
    assert call(h, "/api/models/slice", {"model": "bare.stl"})[0] == 409  # one at a time
    for _ in range(50):
        t = json.loads(call(h, f"/api/tasks/{tid}", method="GET")[1])
        if t["state"] != "running":
            break
        time.sleep(0.1)
    assert t["state"] == "done" and t["n"] == 1 and seen["a"] == ("cup.stl", "pla")
    assert [e["name"] for e in runner.q_load()] == ["2026-cup"]
    assert call(h, "/api/tasks/nope", method="GET")[0] == 404


def test_slice_failure_reported(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "a.stl").write_text("x")
    monkeypatch.setenv("P3D_MODELS_LIB", str(lib))
    (tmp_path / "cfg").mkdir(exist_ok=True)
    (tmp_path / "cfg/config.toml").write_text('filament = "pla"\n')
    config.reset()

    def boom(path, fil):
        raise SystemExit("slice failed: bad mesh")
    tid = server.slice_start({"model": "a.stl"}, run=boom)
    for _ in range(50):
        if server._TASKS[tid]["state"] != "running":
            break
        time.sleep(0.05)
    assert server._TASKS[tid]["state"] == "error" and "bad mesh" in server._TASKS[tid]["msg"]
    assert runner.q_load() == []
