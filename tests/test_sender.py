import csv
import json

import pytest

from conftest import GCODE, commands
from p3d import config, sender


def state():
    return json.loads(config.get().state.read_text())


def test_streams_all_lines_and_writes_final_done(fake_printer, job):
    pr = fake_printer()
    sender.main(str(job))
    sent = [pr.got[n] for n in sorted(pr.got)]
    assert sent == ["M155 S5", *commands(GCODE), "M155 S0"]
    s = state()
    assert s["status"] == "done"
    assert s["ended_at"] and s["job_id"] == "20260101-1200-cube"
    assert s["progress"] == 100
    rows = list(csv.DictReader(open(config.get().data / "print_log.csv")))
    assert rows[-1]["status"] == "done" and rows[-1]["name"] == "cube"
    assert (config.get().data / "printer_stats.csv").exists()
    assert pr.closed


def test_resend_is_honoured(fake_printer, job):
    pr = fake_printer(resend_once={3, 5})
    sender.main(str(job))
    assert [pr.got[n] for n in sorted(pr.got)] == ["M155 S5", *commands(GCODE), "M155 S0"]
    assert pr.order == sorted(pr.order)  # every line accepted once, in order
    assert state()["status"] == "done"


def test_printer_error_gives_failed_state(fake_printer, job):
    fake_printer(error_at=4)
    with pytest.raises(RuntimeError):
        sender.main(str(job))
    s = state()
    assert s["status"] == "failed" and "Thermal Runaway" in s["error"] and s["ended_at"]


def test_stop_file_cancels_safely(fake_printer, job):
    pr = fake_printer()
    config.get().state_dir.mkdir(parents=True, exist_ok=True)
    config.get().stop.touch()
    sender.main(str(job))
    s = state()
    assert s["status"] == "cancelled" and s["ended_at"]
    assert "M104 S0" in pr.got.values() and "M84" in pr.got.values()  # heaters off, motors off
    assert not config.get().stop.exists()


def test_framed_checksum():
    assert sender.framed(1, "G28") == b"N1 G28*18\n"


def test_park_y_from_config(fake_printer):
    assert "G1 X0 Y220 F3000" in sender.safe_stop()


def test_cooldown_temp_reports_keep_final_state(fake_printer, job, monkeypatch):
    """Regression: M105 replies during the post-print cooldown used to rewrite the state as 'printing'."""
    from p3d import sender as snd
    monkeypatch.setattr(snd, "cooldown", lambda link, limit_min=60: link.run(["M105", "M105"]))
    clock = iter(range(1_000_000_000, 2_000_000_000, 7))  # every call 7 s later: no rate-limit skips
    monkeypatch.setattr(snd.time, "time", lambda: next(clock))
    fake_printer()
    snd.main(str(job))
    assert state()["status"] == "done"
