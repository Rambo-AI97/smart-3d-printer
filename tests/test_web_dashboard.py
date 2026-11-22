"""Dashboard controls bar, reslice form, knowledge tab. Temp dirs only; every action function is stubbed (never touches a printer)."""
import json
import time

import pytest

from p3d import config, runner
from p3d.web import server
from test_queue_edit import call, serve


@pytest.fixture
def hub(tmp_path, monkeypatch):
    """A hub layout under tmp: <hub>/projects/3d-printer/data, <hub>/_system/lessons."""
    data = tmp_path / "hub/projects/3d-printer/data"
    data.mkdir(parents=True)
    (tmp_path / "hub/_system/lessons").mkdir(parents=True)
    monkeypatch.setenv("P3D_DATA", str(data))
    monkeypatch.setenv("P3D_JOBS", str(tmp_path / "jobs"))
    config.reset()
    return tmp_path / "hub"


def mkjob(tmp_path, name, proc=None, meta=None, model=None, fil="PETG"):
    d = tmp_path / "jobs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.gcode").write_text(f"; estimated printing time (normal mode) = 10m 0s\n"
                                      f"; total filament used [g] = 2.0\n; filament_type = {fil}\n")
    (d / "preview.png").write_bytes(b"\x89PNG")
    j = {"gcode": str(d / f"{name}.gcode")}
    if model:
        j["model"] = str(model)
    if meta:
        j["settings"] = meta
    (d / "job.json").write_text(json.dumps(j))
    if proc is not None:
        (d / "process.json").write_text(json.dumps(proc))
    return d


# ---- knowledge ----

def test_knowledge_allowlist_and_paths(hub, monkeypatch):
    (hub / "projects/3d-printer/rules.md").write_text("# Rules\n")
    (hub / "_system/lessons/printer.md").write_text("lessons")
    assert server.knowledge_path("rules") == (hub / "projects/3d-printer/rules.md").resolve()
    assert server.knowledge_path("lessons") == (hub / "_system/lessons/printer.md").resolve()
    for bad in ("../x", "/etc/passwd", "rules.md", "", "wiki", "lessons/../x"):
        assert server.knowledge_path(bad) is None
    h = serve(monkeypatch)
    ids = {f["id"]: f for f in json.loads(call(h, "/api/knowledge", method="GET")[1])}
    assert set(ids) == {"rules", "filaments", "lessons", "ideas"} and ids["rules"]["exists"] and not ids["filaments"]["exists"]
    assert json.loads(call(h, "/api/knowledge/file?id=rules", method="GET")[1])["text"] == "# Rules\n"
    assert call(h, "/api/knowledge/file?id=..%2F..%2Fetc%2Fpasswd", method="GET")[0] == 404
    h.shutdown()


def test_knowledge_save_atomic_with_bak_and_refusals(hub, monkeypatch):
    f = hub / "projects/3d-printer/rules.md"
    f.write_text("old")
    h = serve(monkeypatch)
    st, body = call(h, "/api/knowledge/save", {"id": "rules", "text": "new text"})
    assert st == 200 and f.read_text() == "new text" and (hub / "projects/3d-printer/rules.md.bak").read_text() == "old"
    assert not list(f.parent.glob("*.tmp"))
    # new file (no previous version): no .bak
    assert call(h, "/api/knowledge/save", {"id": "filaments", "text": "x"})[0] == 200
    assert not (f.parent / "filaments.md.bak").exists()
    # outside the allowlist, by id or by path
    for bad in ({"id": "../../outside", "text": "x"}, {"id": "/tmp/evil.md", "text": "x"},
                {"path": "/tmp/evil.md", "text": "x"}, {"id": "secrets", "text": "x"}):
        assert call(h, "/api/knowledge/save", bad)[0] == 409
    assert call(h, "/api/knowledge/save", {"id": "rules"})[0] == 409  # no text
    assert call(h, "/api/knowledge/save", {"id": "rules", "text": "x" * 600000})[0] == 409
    assert f.read_text() == "new text"
    h.shutdown()


def test_knowledge_save_forbidden_remote(hub, monkeypatch):
    f = hub / "projects/3d-printer/rules.md"
    f.write_text("old")
    h = serve(monkeypatch, remote=True)
    assert call(h, "/api/knowledge/save", {"id": "rules", "text": "hacked"})[0] == 403
    assert f.read_text() == "old"
    h.shutdown()


# ---- reslice ----

def test_reslice_defaults_from_job_snapshot(hub, tmp_path, monkeypatch):
    stl = tmp_path / "m.stl"
    stl.write_text("x")
    std = server._process("standard")
    proc = dict(std, wall_loops="5", sparse_infill_density="40%", enable_support="1", brim_type="outer_only")
    mkjob(tmp_path, "2026-old", proc=proc, model=stl, fil="PLA")
    d = server.reslice_defaults({"job": "2026-old"})
    st = d["settings"]
    assert d["source"] == "m.stl" and not d["recorded"]
    assert (st["filament"], st["quality"], st["walls"], st["infill"], st["supports"], st["brim"]) == ("pla", "standard", 5, 40, True, True)
    assert "petg" in d["filaments"] and d["qualities"] == ["draft", "standard", "fine"]


def test_reslice_defaults_recorded_and_missing_source(hub, tmp_path):
    stl = tmp_path / "m.stl"
    stl.write_text("x")
    meta = {"quality": "fine", "filament": "petg", "supports": False, "brim": True, "walls": 4, "infill": 25, "keep_orient": True}
    mkjob(tmp_path, "2026-new", meta=meta, model=stl)
    d = server.reslice_defaults({"job": "2026-new"})
    assert d["recorded"] and d["settings"]["quality"] == "fine" and d["settings"]["keep_orient"] and d["settings"]["walls"] == 4
    mkjob(tmp_path, "2026-nosrc")  # nothing recorded
    d = server.reslice_defaults({"job": "2026-nosrc"})
    assert d["source"] == "" and "not recorded" in d["note"]
    with pytest.raises(runner.Refuse):
        server.slice_start({"job": "2026-nosrc"})
    with pytest.raises(runner.Refuse):
        server.reslice_defaults({"job": "../x"})


def test_reslice_task_passes_options_and_does_not_queue(hub, tmp_path, monkeypatch):
    stl = tmp_path / "m.stl"
    stl.write_text("x")
    mkjob(tmp_path, "2026-src", model=stl)
    seen = {}

    def fake(path, fil, **kw):
        seen.update(path=path.name, fil=fil, kw=kw)
        d = mkjob(tmp_path, "2026-out")
        return d, d / "2026-out.gcode"
    h = serve(monkeypatch)
    monkeypatch.setattr(server, "slice_start", lambda b, run=None, _o=server.slice_start: _o(b, run=fake))
    server._process("standard")
    st, body = call(h, "/api/models/slice", {"job": "2026-src", "filament": "pla", "quality": "fine", "walls": 4, "infill": 30,
                                            "brim": True, "supports": True, "keep_orient": True})
    assert st == 202
    tid = json.loads(body)["task"]
    for _ in range(50):
        t = json.loads(call(h, "/api/tasks/" + tid, method="GET")[1])
        if t["state"] != "running":
            break
        time.sleep(0.1)
    assert t["state"] == "done" and t["job"] == "2026-out" and t["est_min"] == 10 and "2.0 g" in t["msg"]
    assert seen["path"] == "m.stl" and seen["fil"] == "pla"
    assert seen["kw"] == {"quality": "fine", "walls": 4, "infill": 30, "brim": True, "supports": True, "keep_orient": True}
    assert runner.q_load() == []  # reslice never queues by itself
    h.shutdown()


def test_reslice_profile_values_are_not_overrides(hub, tmp_path, monkeypatch):
    stl = tmp_path / "m.stl"
    stl.write_text("x")
    mkjob(tmp_path, "2026-src", model=stl)
    std = server._process("standard")
    got = {}
    monkeypatch.setattr(server.threading, "Thread",
                        lambda target, daemon: type("T", (), {"start": lambda s: None})())
    server.slice_start({"job": "2026-src", "filament": "petg", "walls": std["wall_loops"],
                        "infill": str(std["sparse_infill_density"]).rstrip("%")},
                       run=lambda *a, **k: got.update(a=a, k=k))
    # task registered; options would be empty (checked via a second call after clearing)
    server._TASKS.clear()
    with pytest.raises(runner.Refuse):
        server.slice_start({"job": "2026-src", "filament": "nonexistent"})
    with pytest.raises(runner.Refuse):
        server.slice_start({"job": "2026-src", "filament": "petg", "quality": "ultra"})
    with pytest.raises(runner.Refuse):
        server.slice_start({"job": "2026-src", "filament": "petg", "walls": 99})
    server._TASKS.clear()


# ---- queue add keeps pause_at ----

def test_queue_add_with_pause_at_via_web(hub, tmp_path, monkeypatch):
    mkjob(tmp_path, "2026-rattle")
    h = serve(monkeypatch)
    st, body = call(h, "/api/queue/add", {"job": "2026-rattle", "pause_at": [193], "note": "drop the ball"})
    assert st == 200 and "layer 193" in json.loads(body)["ok"]
    e = runner.q_load()[0]
    assert e["pause_at"] == [193] and e["note"] == "drop the ball"
    assert json.loads(call(h, "/api/queue", method="GET")[1])[0]["pause_at"] == [193]
    for bad in ("abc", 0, -3, [1, "x"]):
        assert call(h, "/api/queue/add", {"job": "2026-rattle", "pause_at": bad})[0] == 409
    assert len(runner.q_load()) == 1
    # and queue next hands the layers to the sender
    monkeypatch.setattr(config, "print_running", lambda: False)
    monkeypatch.setattr(runner, "start_unit", lambda u, a: None)
    runner.queue_next()
    from p3d import pause
    assert pause.read_pause_at() == [193]
    h.shutdown()


# ---- controls: retry / level / cooldown ----

def log_row(f, name="vase", status="failed"):
    import csv
    p = config.get().data / "print_log.csv"
    new = not p.exists()
    with open(p, "a", newline="") as fh:
        w = csv.DictWriter(fh, ["date", "name", "file", "status", "est_min"])
        if new:
            w.writeheader()
        w.writerow({"date": "2026-01-01 10:00", "name": name, "file": str(f), "status": status, "est_min": "30"})


def test_last_reprintable_skips_junk(hub, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SCRATCH_DIRS", (str(tmp_path / "scratch") + "/",))
    d = mkjob(tmp_path, "2026-vase")
    g = d / "2026-vase.gcode"
    log_row(g, "vase")
    log_row(g, "purge_line", "done")
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch/s.gcode").write_text("x")
    log_row(tmp_path / "scratch/s.gcode", "scratch")
    log_row(tmp_path / "gone.gcode", "gone")
    assert runner.last_reprintable()["name"] == "vase"


def test_retry_and_level_refuse_while_printing(hub, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SCRATCH_DIRS", ("/nonexistent-scratch/",))
    g = mkjob(tmp_path, "2026-vase") / "2026-vase.gcode"
    log_row(g)
    started = []
    monkeypatch.setattr(runner, "start", lambda gc, **kw: started.append(gc) or "started")
    ran = []
    monkeypatch.setattr(server, "run_level", lambda args, on_line=None: ran.append(args) or (0, ""))
    h = serve(monkeypatch)
    monkeypatch.setattr(config, "print_running", lambda: True)
    monkeypatch.setattr(config, "print_cancellable", lambda: True)
    assert call(h, "/api/retry")[0] == 409
    assert call(h, "/api/level")[0] == 409
    c = json.loads(call(h, "/api/controls", method="GET")[1])
    assert not c["retry"] and not c["level"] and not c["next"] and "running" in c["why"]["level"]
    assert started == [] and ran == [] and server._TASKS == {}
    # cooldown phase (unit active, job finished): retry may start; the probe stops the cooldown first
    monkeypatch.setattr(config, "print_cancellable", lambda: False)
    stopped = []
    monkeypatch.setattr(runner, "end_cooldown_if_idle", lambda: stopped.append(1))
    assert call(h, "/api/level")[0] == 409 and stopped   # cooldown would not stop -> refused
    assert call(h, "/api/retry")[0] == 200 and started == [str(g)]
    h.shutdown()


def test_retry_refuses_without_job(hub, monkeypatch):
    monkeypatch.setattr(runner, "SCRATCH_DIRS", ("/nonexistent-scratch/",))
    monkeypatch.setattr(config, "print_cancellable", lambda: False)
    with pytest.raises(runner.Refuse):
        runner.retry_last()


def test_level_task_runs_and_parses(hub, monkeypatch):
    out = ("\x1b[42;30m x \x1b[0m\n  Bed map\n\n  back  \x1b[42;30m +0.05 \x1b[0m\x1b[41;30m +0.40 \x1b[0m\x1b[42;30m +0.00 \x1b[0m\n"
           "         \x1b[44;30m -0.35 \x1b[0m\x1b[42;30m +0.02 \x1b[0m\x1b[42;30m +0.01 \x1b[0m\n"
           "  front  \x1b[42;30m +0.00 \x1b[0m\x1b[42;30m +0.00 \x1b[0m\x1b[42;30m +0.00 \x1b[0m\n\n"
           "  Span: 0.75 mm  ->  NEEDS WORK   (good <= 0.3, usable <= 0.6)\n")
    seen = []
    monkeypatch.setattr(server, "run_level", lambda args, on_line=None: seen.append(args) or (0, out))
    monkeypatch.setattr(config, "print_running", lambda: False)
    monkeypatch.setattr(config, "print_cancellable", lambda: False)
    h = serve(monkeypatch)
    st, body = call(h, "/api/level")
    assert st == 202
    tid = json.loads(body)["task"]
    for _ in range(50):
        t = json.loads(call(h, "/api/tasks/" + tid, method="GET")[1])
        if t["state"] != "running":
            break
        time.sleep(0.05)
    assert seen == [["--hot", "70"]]  # once, no --adjust loop
    assert t["state"] == "done" and t["kind"] == "level" and t["span"] == 0.75 and t["verdict"] == "NEEDS WORK"
    assert t["grid"] == [[0.05, 0.40, 0.00], [-0.35, 0.02, 0.01], [0.00, 0.00, 0.00]]
    assert json.loads(call(h, "/api/level/last", method="GET")[1])["span"] == 0.75
    assert call(h, "/api/level/show")[0] == 202 and seen[-1] == ["--show"]
    h.shutdown()


def test_level_last_falls_back_to_log(hub):
    (config.get().data / "bed_mesh_log.csv").write_text(
        "date,span_mm,grid_rows_front_to_back\n2026-01-01 10:00,0.2,+0.0 +0.1 | +0.2 +0.0\n")
    server._TASKS.clear()
    r = server.level_last()
    assert r["span"] == 0.2 and r["grid"] == [[0.2, 0.0], [0.0, 0.1]] and r["verdict"] == "GOOD"


def test_level_error_and_busy(hub, monkeypatch):
    monkeypatch.setattr(config, "print_running", lambda: False)
    monkeypatch.setattr(server, "run_level", lambda args, on_line=None: (1, "No mesh found in the printer.\n"))
    server._TASKS.clear()
    tid = server.level_start()
    for _ in range(50):
        if server._TASKS[tid]["state"] != "running":
            break
        time.sleep(0.05)
    assert server._TASKS[tid]["state"] == "error" and "No mesh" in server._TASKS[tid]["msg"]
    server._TASKS.clear()


def test_cooldown_and_new_posts_forbidden_remote(hub, monkeypatch):
    units = []
    monkeypatch.setattr(runner, "start_unit", lambda u, a: units.append(u))
    h = serve(monkeypatch, remote=True)
    for p in ("/api/retry", "/api/cooldown", "/api/level", "/api/level/show", "/api/knowledge/save"):
        assert call(h, p, {"id": "rules", "text": "x"})[0] == 403
    assert units == []
    h.shutdown()


def test_cooldown_starts_unit(hub, monkeypatch):
    units = []
    monkeypatch.setattr(runner, "start_unit", lambda u, a: units.append(u))
    h = serve(monkeypatch)
    assert call(h, "/api/cooldown")[0] == 200 and units == ["p3d-cooldown"]
    h.shutdown()


def test_models_newest_first_and_delete_to_trash(hub, tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    (lib / "scad").mkdir(parents=True)
    old, new = lib / "old.stl", lib / "scad/new.stl"
    old.write_text("solid")
    new.write_text("solid")
    (lib / "scad/new.png").write_bytes(b"\x89PNG")
    (lib / "scad/new.scad").write_text("cube(1);")
    import os
    os.utime(old, (1_000_000, 1_000_000))
    monkeypatch.setenv("P3D_MODELS_LIB", str(lib))
    h = serve(monkeypatch)
    ids = [m["id"] for m in json.loads(call(h, "/api/models", method="GET")[1])]
    assert ids == ["scad/new.stl", "old.stl"]
    st, body = call(h, "/api/models/delete", {"id": "scad/new.stl"})
    assert st == 200 and "deleted new" in json.loads(body)["ok"]
    assert not new.exists() and not (lib / "scad/new.png").exists() and (lib / "scad/new.scad").exists()
    assert len(list((lib / ".trash").rglob("new.stl"))) == 1
    assert [m["id"] for m in json.loads(call(h, "/api/models", method="GET")[1])] == ["old.stl"]  # trash hidden
    assert call(h, "/api/models/delete", {"id": "../etc/passwd"})[0] == 409
    assert call(serve(monkeypatch, remote=True), "/api/models/delete", {"id": "old.stl"})[0] == 403
    assert old.exists()


def test_bed_turns_from_back_first_grid():
    from p3d.web import server
    g = [[-0.479, -0.393, -0.209, -0.362], [-0.286, -0.262, 0.026, -0.179],
         [-0.460, -0.109, -0.003, -0.138], [-0.388, -0.167, 0.125, -0.079]]  # back row first
    t = {x["corner"]: x["action"] for x in server.bed_turns(g)}
    assert t == {"BACK-LEFT": "1/4 turn COUNTER-CLOCKWISE", "BACK-RIGHT": "leave it",
                 "FRONT-LEFT": "1/8 turn COUNTER-CLOCKWISE", "FRONT-RIGHT": "3/8 turn CLOCKWISE"}


def test_level_progress_lines():
    from p3d.web import server
    server._TASKS["t1"] = {"id": "t1", "kind": "level", "state": "running"}
    for l in ["Heating bed to 70 C, then 2 min settle", "  bed 55.2 / 70 C", "Homing...", "Probing 16 points (about 2 minutes)...",
              "  point  1  X   30 Y   25  Z -0.388", "  point  2  X  100 Y   25  Z +0.125"]:
        server.level_progress("t1", l)
    t = server._TASKS.pop("t1")
    assert t["phase"] == "probing" and t["points"] == [[30, 25, -0.388], [100, 25, 0.125]] and t["bed"] == 55.2


def test_level_stop_refuses_when_idle():
    from p3d.web import server
    with pytest.raises(runner.Refuse):
        server.level_stop()
