import json

import pytest

from p3d import cli, config


def run(capsys, *argv):
    try:
        cli.main(list(argv))
        code = 0
    except SystemExit as e:
        code = e.code
    out = capsys.readouterr()
    return code, out.out, out.err


def test_status_json_is_clean_json(capsys, monkeypatch):
    monkeypatch.setattr(cli, "print_running", lambda: False)
    config.write_state(status="printing", file="cube", job_id="j1")
    code, out, _ = run(capsys, "status", "--json")
    data = json.loads(out)  # nothing but JSON on stdout
    assert code == 0 and data["running"] is False and data["stale"] is True
    assert data["state"]["file"] == "cube"


def test_status_json_idle(capsys, monkeypatch):
    monkeypatch.setattr(cli, "print_running", lambda: False)
    code, out, _ = run(capsys, "status", "--json")
    assert json.loads(out) == {"running": False, "stale": False, "state": {"status": "idle"}}


def test_wait_ignores_previous_job_and_returns_on_final(capsys, monkeypatch):
    seq = iter([
        {"status": "printing", "job_id": "new"},
        {"status": "done", "job_id": "new", "ended_at": "2026-01-01T12:00:00"},
    ])
    config.write_state(status="queued", job_id="new")
    monkeypatch.setattr(cli, "read_state", lambda: next(seq, {"status": "done", "job_id": "new"}))
    monkeypatch.setattr(cli, "print_running", lambda: True)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    code, out, _ = run(capsys, "wait", "done", "--job", "new")
    assert code == 0 and "done" in out


def test_wait_does_not_return_for_old_final_state(capsys, monkeypatch):
    """An old job's 'done' must not end a wait for the new job."""
    states = iter([{"status": "done", "job_id": "old"}])
    monkeypatch.setattr(cli, "read_state", lambda: next(states, {"status": "failed", "job_id": "new", "error": "x"}))
    monkeypatch.setattr(cli, "print_running", lambda: True)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    code, out, err = run(capsys, "wait", "done", "--job", "new")
    assert "replaced" in str(code)  # old job id seen first -> treated as a different job, not 'done'


def test_wait_detects_dead_sender(capsys, monkeypatch):
    config.write_state(status="printing", job_id="j")
    monkeypatch.setattr(cli, "print_running", lambda: False)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    code, _, _ = run(capsys, "wait", "done", "--grace", "0")
    assert "without a final state" in str(code)


def test_help_is_grouped(capsys):
    code, out, _ = run(capsys, "--help")
    for g in ("Print:", "Design:", "Calibrate:", "Data:", "Setup:"):
        assert g in out
    for cmd in ("status", "slice", "doctor", "install-service"):
        assert f"  {cmd} " in out


@pytest.mark.parametrize("name", [n for cmds in cli.COMMANDS.values() for n, *_ in cmds])
def test_every_command_has_help(capsys, name):
    code, out, _ = run(capsys, name, "--help")
    assert code == 0 and out.strip()


def test_config_file_and_env(tmp_path, monkeypatch):
    config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_FILE.write_text('port = "/dev/ttyUSB9"\nweb_port = 9000\njobs_dir = "~/x-jobs"\n')
    monkeypatch.delenv("P3D_PORT")
    monkeypatch.delenv("P3D_JOBS", raising=False)
    config.reset()
    c = config.get()
    assert c.port == "/dev/ttyUSB9" and c.web_port == 9000
    assert str(c.jobs).endswith("x-jobs")
    assert c.data == tmp_path / "data"  # env P3D_DATA wins


def test_setup_yes_writes_config(capsys, monkeypatch):
    monkeypatch.setattr(config, "find_ports", lambda: ["/dev/serial/by-id/usb-fake"])
    monkeypatch.setattr(config, "find_orca", lambda: "")
    code, out, _ = run(capsys, "setup", "--yes")
    text = config.CONFIG_FILE.read_text()
    assert code == 0 and 'port = "/dev/serial/by-id/usb-fake"' in text
