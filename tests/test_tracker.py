"""Print tracker lifecycle + auto-close, verdict ping command, Fridge approvals, status.json. Temp dirs only; never ssh."""
import json
import os

import pytest

from p3d import config, fridge, printlog, runner, tracker


@pytest.fixture(autouse=True)
def fridge_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("P3D_FRIDGE", str(tmp_path / "fridge"))
    monkeypatch.setenv("P3D_JOBS", str(tmp_path / "jobs"))
    config.reset()
    return tmp_path / "fridge"


def mkjob(tmp_path, name, meta=None):
    d = tmp_path / "jobs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.gcode").write_text("; estimated printing time (normal mode) = 10m 0s\n; total filament used [g] = 2.0\n")
    if meta:
        (d / "job.json").write_text(json.dumps(meta))
    return d / f"{name}.gcode"


def test_lifecycle_and_autoclose(tmp_path):
    g = mkjob(tmp_path, "j1-cube", {"request": "7", "who": "Alex"})
    printlog.log_job(g, "done", 10)
    r = printlog.rows()[0]
    assert (r["state"], r["request"], r["who"]) == ("check", "7", "Alex")
    printlog.log_job(mkjob(tmp_path, "j2-bad"), "cancelled", 1)
    assert printlog.rows()[1]["state"] == "cancelled"
    closed = tracker.auto_close()
    assert [c["name"] for c in closed] == ["j1-cube"]
    r = printlog.rows()[0]
    assert (r["state"], r["verdict"], r["verdict_note"]) == ("passed", "pass", tracker.ASSUMED)
    assert printlog.rows()[1]["state"] == "cancelled"  # untouched
    assert tracker.auto_close() == []


def test_runner_start_autocloses(tmp_path, monkeypatch):
    printlog.log_job(mkjob(tmp_path, "j1-cube"), "done", 10)
    monkeypatch.setattr(runner, "start_unit", lambda *a, **k: None)
    runner.start(mkjob(tmp_path, "j2-next"))
    assert printlog.rows()[0]["state"] == "passed"


def test_verdict_fail_then_reprint_chain(tmp_path):
    printlog.log_job(mkjob(tmp_path, "v1-box"), "done", 10)
    r = tracker.set_verdict("last", "fail", "warping,stringing", "corner lifted")
    assert (r["state"], r["verdict_tags"], r["verdict_note"]) == ("failed", "warping,stringing", "corner lifted")
    assert [i["name"] for i in tracker.select("open")] == ["v1-box"]  # failed, nobody reprinted yet
    tracker.reopen("v1-box", "needs brim", new=str(mkjob(tmp_path, "v2-box").parent))
    printlog.log_job(mkjob(tmp_path, "v2-box"), "done", 10)
    v2 = printlog.rows()[1]
    assert v2["reprint_of"] == "v1-box"
    tracker.set_verdict("v2-box", "pass")
    its = {i["name"]: i for i in tracker.select("all")}
    assert its["v2-box"]["chain"] == [{"name": "v1-box", "state": "reopened"}]
    assert [i["name"] for i in tracker.select("open")] == []  # v1 has its reprint, v2 passed


def test_old_rows_and_rate_mapping(tmp_path):
    printlog.append({"date": "2026-01-01 10:00", "name": "old", "status": "done", "file": "/x/old.gcode"})
    assert tracker.state_of(printlog.rows()[0]) == "passed"
    printlog.log_job(mkjob(tmp_path, "j1-cube"), "done", 10)
    printlog.cmd_rate(2, None, None, "j1-cube")
    r = [x for x in printlog.rows() if x["name"] == "j1-cube"][0]
    assert (r["state"], r["verdict"], r["rating"]) == ("failed", "fail", "2")


def test_pass_with_request_builds_ssh_command_dry_run(tmp_path, monkeypatch, capsys):
    fridge.add_request(7, str(mkjob(tmp_path, "j1-cube").parent), "Alex", "Cube", shot=None)
    printlog.log_job(mkjob(tmp_path, "j1-cube"), "done", 10)
    sent = []
    monkeypatch.setattr(fridge, "notes_done", lambda n, text: sent.append((n, text)))
    tracker.set_verdict("last", "pass")
    assert sent[0][0] == "7"
    assert fridge.load_requests()[0]["state"] == "passed"
    cmd = fridge.notes_cmd(7, "Cube is \"done\"")
    assert cmd[:2] == ["ssh", "rambo"] and cmd[2].startswith("bash -lc ") and "rambo notes done 7" in cmd[2]
    monkeypatch.undo()
    assert fridge.notes_done(7, "x") == fridge.notes_cmd(7, "x")  # under pytest: built, printed, never run


def test_approvals_queue_once_and_change(tmp_path, fridge_dir):
    mkjob(tmp_path, "j1-cube")
    mkjob(tmp_path, "j2-hook")
    fridge.add_request(7, "j1-cube", "Alex", "Cube")
    fridge.add_request(8, "j2-hook", "Alex", "Hook")
    ap = [{"note": 7, "job": "j1-cube", "action": "approve", "by": "Alex", "text": "", "at": "2026-11-25T10:00:00"},
          {"note": 8, "job": "j2-hook", "action": "change", "by": "Alex", "text": "make it smaller", "at": "2026-11-25T10:01:00"}]
    (fridge_dir / "approvals.json").write_text(json.dumps(ap))
    assert len(fridge.process_approvals()) == 2
    assert fridge.process_approvals() == []  # duplicates ignored
    assert [e["name"] for e in runner.q_load()] == ["j1-cube"]
    reqs = {q["note"]: q for q in fridge.load_requests()}
    assert reqs["7"]["state"] == "queued"
    assert (reqs["8"]["state"], reqs["8"]["change_text"]) == ("change_asked", "make it smaller")
    ap.append({**ap[0], "at": "2026-11-25T11:00:00"})  # a new approve event for an already queued job: no second entry
    (fridge_dir / "approvals.json").write_text(json.dumps(ap))
    fridge.process_approvals()
    assert len(runner.q_load()) == 1
    assert not config.get().queue.exists()  # never auto-started


def test_status_json_atomic_and_content(tmp_path, fridge_dir, monkeypatch):
    mkjob(tmp_path, "j1-cube")
    printlog.log_job(mkjob(tmp_path, "j1-cube"), "done", 10)
    runner.q_save(runner.q_add([], mkjob(tmp_path, "j2-next").parent))
    fridge.write_status()
    s = json.loads((fridge_dir / "status.json").read_text())
    assert s["printer"]["state"] == "idle" and s["queue"][0]["name"] == "j2-next" and s["queue"][0]["grams"] == 2.0
    assert s["tracker"][0]["state"] == "check"
    assert not list(fridge_dir.glob("*.tmp"))
    calls = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (calls.append((str(a), str(b))), real(a, b))[1])
    fridge.write_status()
    assert calls[0][0].endswith("status.json.tmp") and calls[0][1].endswith("status.json")
