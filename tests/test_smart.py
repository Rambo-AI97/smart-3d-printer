import json

import pytest

from conftest import commands
from p3d import config, ideas, insights, pause, printlog, runner, sender, spools
from p3d import gcode as G

# ---------- spools ----------

def test_spool_math():
    assert spools.job_grams("10", "done", 100) == 10
    assert spools.job_grams("10", "cancelled", 40) == 4
    assert spools.job_grams("10", "failed", None) == 0
    d = {"active": "", "spools": []}
    spools.add(d, "white", "PETG", 1000)
    assert d["active"] == "white" and spools.find(d, "WHITE")
    left, low = spools.deduct(d, "white", 950, "j")
    assert left == 50 and low
    assert spools.deduct(d, "white", 10)[1] is False
    ok, msg = spools.check(d, 60)
    assert not ok and "40" in msg
    with pytest.raises(ValueError):
        spools.add(d, "white", "petg", 5)
    spools.set_left(d, "white", 500)
    assert spools.check(d, 100) == (True, "")


def test_spool_deducted_and_logged_at_job_end(fake_printer, job):
    d = spools.load()
    spools.add(d, "s1", "petg", 100)
    spools.save(d)
    fake_printer()
    sender.main(str(job))
    assert spools.find(spools.load(), "s1")["left_g"] == 98.5
    row = printlog.rows()[-1]
    assert row["spool"] == "s1" and row["grams_used"] == "1.5"


def test_print_refused_when_spool_too_low(job, monkeypatch):
    d = spools.load()
    spools.add(d, "s1", "petg", 1)
    spools.save(d)
    monkeypatch.setattr(config, "print_running", lambda: False)
    with pytest.raises(runner.Refuse, match="spool"):
        runner.start(str(job))


# ---------- pause ----------

def test_pause_resume_commands():
    t = G.Tracker()
    for c in ["M83", "G1 X40 Y50 Z1.2 E1"]:
        t.feed(c)
    p = pause.pause_cmds(t, 220)
    assert p[0] == "M400" and "G1 Z11.2 F600" in p and p[-1].startswith("G1 X0 Y220")
    r = pause.resume_cmds(t, 225)
    assert r[0] == "M109 S225" and "G1 X40 Y50 F6000" in r and r.index("G1 X40 Y50 F6000") < r.index("G1 Z1.2 F600")
    assert pause.pause_cmds(G.Tracker()) is None
    t.feed("M82")
    assert "M82" in pause.resume_cmds(t)


def test_pause_due():
    assert pause.due(3, False, {3}) and pause.due(2, True, set()) and not pause.due(2, False, {3}) and not pause.due(0, True, set())


LAYER_JOB = """; total layer number: 2
; estimated printing time (normal mode) = 1m 0s
; total filament used [g] = 1.5
M83
;LAYER_CHANGE
;Z:0.2
G1 Z0.2
G1 X10 Y10 E1
;LAYER_CHANGE
;Z:0.4
G1 Z0.4
G1 X20 Y20 E1
"""


def test_sender_pauses_at_layer_and_resumes(fake_printer, tmp_path, monkeypatch):
    d = tmp_path / "data/jobs/j"
    d.mkdir(parents=True)
    g = d / "p.gcode"
    g.write_text(LAYER_JOB)
    fake_printer()
    pause.write_pause_at([2])
    real = sender.time.sleep
    calls = {"n": 0}

    def sleep(s):
        if config.read_state().get("status") == "paused":
            calls["n"] += 1
            config.get().resume.touch()
    monkeypatch.setattr(sender.time, "sleep", sleep)
    sent, orig = [], sender.Link.exchange
    monkeypatch.setattr(sender.Link, "exchange", lambda self, n, cmd: (sent.append(cmd), orig(self, n, cmd))[1])
    sender.main(str(g))
    monkeypatch.setattr(sender.time, "sleep", real)
    assert calls["n"] >= 1 and "G1 X0 Y220 F6000" in sent
    # layer 2 content comes after the pause block, all original lines still sent in order
    orig = commands(LAYER_JOB)
    assert all(c in sent for c in orig)
    assert sent.index("G1 X0 Y220 F6000") < sent.index("G1 Z0.4")
    s = json.loads(config.get().state.read_text())
    assert s["status"] == "done"
    rj = json.loads((d / "run.json").read_text())
    assert rj["layer_done"] == 1 and rj["z_done"] == 0.2
    assert pause.read_pause_at() == []


def test_sender_records_last_completed_layer_on_cancel(fake_printer, tmp_path):
    d = tmp_path / "data/jobs/j2"
    d.mkdir(parents=True)
    g = d / "p.gcode"
    g.write_text(LAYER_JOB)
    fake_printer()
    orig = sender.Link.exchange

    def ex(self, n, cmd):
        if cmd == "G1 X20 Y20 E1":
            config.get().stop.touch()
        return orig(self, n, cmd)
    sender.Link.exchange = ex
    try:
        sender.main(str(g))
    finally:
        sender.Link.exchange = orig
    s = json.loads(config.get().state.read_text())
    assert s["status"] == "cancelled" and s["layer_done"] == 1
    from p3d import recover
    assert recover.last_done_layer(d) == (1, "run.json")


# ---------- ideas ----------

def test_ideas_roundtrip_and_hand_edit():
    md = "# Print ideas\n## Idea\n- [#2] Tray #desk\n- hand added line\n## Planned\n- [#5] Stand | note: tall | model: a.scad\n## Dropped\n"
    items = ideas.parse(md)
    assert [(i["id"], i["status"]) for i in items] == [(2, "idea"), (6, "idea"), (5, "planned")]
    assert items[0]["tags"] == ["desk"] and items[2]["note"] == "tall" and items[2]["model"] == "a.scad"
    ideas.move(items, 6, "maybe")
    ideas.done(items, 2, "job1")
    again = ideas.parse(ideas.render(items))
    assert {i["id"]: i["status"] for i in again} == {2: "printed", 6: "maybe", 5: "planned"}
    assert [i for i in again if i["id"] == 2][0]["job"] == "job1"
    n = ideas.add(items, "New thing", "needs-thought", ["x"])
    assert n["id"] == 7 and "#x" in n["text"]
    with pytest.raises(ValueError):
        ideas.move(items, 99, "idea")
    with pytest.raises(ValueError):
        ideas.move(items, 2, "nope")


def test_ideas_file_next_to_data_dir(tmp_path):
    assert config.get().ideas == tmp_path / "ideas.md"
    items = []
    ideas.add(items, "x")
    ideas.save(items)
    assert ideas.load()[0]["text"] == "x"


# ---------- queue ----------

def test_queue_add_remove_and_refusals(job, monkeypatch):
    q = runner.q_add([], str(job.parent), "note")
    assert q[0]["name"] == "20260101-1200-cube" and q[0]["note"] == "note"
    runner.q_save(q)
    assert runner.q_load() == q
    assert runner.next_refusal([]) .startswith("the queue is empty")
    monkeypatch.setattr(config, "print_cancellable", lambda: True)
    assert "running" in runner.next_refusal(q)
    monkeypatch.setattr(config, "print_cancellable", lambda: False)
    assert runner.next_refusal(q) == ""
    with pytest.raises(runner.Refuse):
        runner.q_remove(q, 3)
    assert runner.q_remove(q, 1)["note"] == "note" and q == []


def test_queue_refuses_manual_z_jobs(job):
    (job.parent / "job.json").write_text(json.dumps({"manual_z": True}))
    with pytest.raises(runner.Refuse):
        runner.q_add([], str(job))


def test_queue_next_stops_cooldown_and_starts(job, monkeypatch):
    runner.q_save(runner.q_add([], str(job)))
    started, stopped = [], []
    state = {"running": True}
    config.write_state(status="done", job_id="old")
    monkeypatch.setattr(config, "print_running", lambda: state["running"])
    monkeypatch.setattr(runner, "start_unit", lambda u, a: started.append(u))
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: (stopped.append(a[0]), state.update(running=False))[0])
    runner.queue_next()
    assert started == ["p3d-print"] and stopped and runner.q_load() == []


def test_queue_next_keeps_pause_layers(job, monkeypatch):
    # a queued ball-pause job (rattle) must still pause: queue next used to drop pause_at
    runner.q_save(runner.q_add([], str(job), "", [193]))
    monkeypatch.setattr(config, "print_running", lambda: False)
    monkeypatch.setattr(runner, "start_unit", lambda u, a: None)
    runner.queue_next()
    from p3d import pause
    assert pause.read_pause_at() == [193]


def test_queue_next_refuses_while_printing(job, monkeypatch):
    runner.q_save(runner.q_add([], str(job)))
    config.write_state(status="printing", job_id="x")
    monkeypatch.setattr(config, "print_running", lambda: True)
    with pytest.raises(runner.Refuse):
        runner.queue_next()
    assert len(runner.q_load()) == 1


def test_manual_z_job_needs_confirm(job, monkeypatch):
    (job.parent / "job.json").write_text(json.dumps({"manual_z": True}))
    monkeypatch.setattr(config, "print_running", lambda: False)
    with pytest.raises(runner.Refuse, match="confirm-z"):
        runner.start(str(job))


# ---------- insights ----------

def R(date, status="done", issues="", rating="", **kw):
    return {"date": date, "name": "j" + date, "status": status, "issues": issues, "rating": rating, **kw}


def test_advice_and_recurring():
    assert "calib retraction" in dict(insights.next_steps(["stringing"]))["stringing"]
    assert "level --hot 70" in insights.ADVICE["first-layer"] and "calib flow" in insights.ADVICE["under-extrusion"]
    rows = [R("2026-11-01 10:00", issues="stringing"), R("2026-11-02 10:00", issues="stringing,blobs"), R("2026-11-03 10:00")]
    rec = insights.recurring(rows)
    assert [(t, n) for t, n, _ in rec] == [("stringing", 2)]


def test_settings_changes_and_before_after():
    rows = [R("2026-11-01 10:00", bed_first="70", bed_other="70", issues="adhesion", rating="2"),
            R("2026-11-02 10:00", bed_first="70", bed_other="70", issues="adhesion", rating="3"),
            R("2026-11-03 10:00", bed_first="70", bed_other="60", rating="5"),
            R("2026-11-04 10:00", bed_first="70", bed_other="60", rating="5"),
            R("2026-11-05 10:00")]  # no snapshot: not a change
    ch = insights.settings_changes(rows)
    assert len(ch) == 1 and ch[0]["changes"] == ["bed 70 -> 60"] and ch[0]["name"] == "j2026-11-03 10:00"
    s = insights.since_last_change(rows)
    assert s["before"] == 1.0 and s["after"] == 0.0


def test_weekly():
    rows = [R("2026-11-02 10:00", rating="4", grams="10", actual_min="60"),
            R("2026-11-03 10:00", status="failed", grams_used="5", actual_min="30"),
            R("2026-11-10 10:00", grams="1")]
    w = insights.weekly(rows)
    assert w[0]["week"] == "2026-11-02" and w[0]["success"] == 50 and w[0]["grams"] == 15 and w[0]["hours"] == 1.5 and w[0]["rating"] == 4
    assert len(w) == 2


def test_rate_prints_next_step(job, capsys):
    printlog.log_job(str(job), "done", 5)
    printlog.cmd_rate(2, "stringing,first-layer")
    out = capsys.readouterr().out
    assert "next step for stringing: p3d calib retraction" in out and "level --hot 70" in out


def test_snapshot_columns_in_log(tmp_path):
    g = tmp_path / "x.gcode"
    g.write_text("; CONFIG_BLOCK_START\n; wall_loops = 3\n; curr_bed_type = Cool Plate\n; cool_plate_temp = 60\n"
                 "; cool_plate_temp_initial_layer = 70\n; sparse_infill_density = 15%\n; travel_speed = 200\n; CONFIG_BLOCK_END\n")
    i = printlog.gcode_info(g)
    assert (i["bed_first"], i["bed_other"], i["walls"], i["infill"], i["travel_speed"]) == ("70", "60", "3", "15%", "200")
    assert len(i["profile_hash"]) == 8
