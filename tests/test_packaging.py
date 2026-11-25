"""CAD lookup, install-cad plumbing, home-only integrations off by default. No network, no real installs."""
import json
import sys

import pytest

from p3d import cad, config, fridge


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    monkeypatch.delenv("P3D_FRIDGE", raising=False)
    monkeypatch.delenv("P3D_CAD_PYTHON", raising=False)
    monkeypatch.setattr(config, "XDG_DATA", tmp_path / "data")
    config.reset()
    yield
    config.reset()


def test_defaults_are_off():
    c = config.get()
    assert c.fridge is None and not fridge.enabled()
    assert fridge.load_requests() == [] and fridge.process_approvals() == [] and fridge.start_loop() is None
    assert c.raw["fridge_done_cmd"] == "" and c.raw["event_cmd"] == "" and c.raw["knowledge_files"] == []
    assert fridge.notes_done(3, "x") is None


def test_fridge_dir_from_config(tmp_path):
    (tmp_path / "config.toml").write_text(f'fridge_dir = "{tmp_path / "f"}"\n')
    config.reset()
    assert config.get().fridge == tmp_path / "f" and fridge.enabled()


def test_story_runs_event_cmd_only_outside_pytest(tmp_path, monkeypatch):
    out = tmp_path / "ev.json"
    sink = tmp_path / "sink.py"
    sink.write_text(f"import sys; open({str(out)!r}, 'w').write(sys.stdin.read())\n")
    (tmp_path / "config.toml").write_text(f'event_cmd = "{sys.executable} {sink}"\n')
    config.reset()
    config.story("Print failed", "boom", "printer")
    assert not out.exists()  # PYTEST_CURRENT_TEST is set
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    config.story("Print failed", "boom", "printer")
    assert json.loads(out.read_text()) == {"title": "Print failed", "msg": "boom", "level": "error", "tags": "printer"}
    (tmp_path / "config.toml").write_text('event_cmd = "/nonexistent/cmd"\n')
    config.reset()
    config.story("x", "y")  # never raises


def test_web_base_falls_back_to_lan_then_localhost(monkeypatch):
    monkeypatch.setattr(config.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(config, "lan_ip", lambda: "203.0.113.9")
    assert config.web_base() == f"http://203.0.113.9:{config.get().web_port}"
    monkeypatch.setattr(config, "lan_ip", lambda: "")
    assert config.web_base() == f"http://localhost:{config.get().web_port}"


def test_cad_lookup_order(tmp_path, monkeypatch):
    monkeypatch.setattr(cad, "importable", lambda *m: False)
    assert cad.find("build123d") == (None, None)
    with pytest.raises(SystemExit) as e:
        cad.python_for("build123d")
    assert "p3d install-cad" in str(e.value)
    default = cad.venv_python()
    default.parent.mkdir(parents=True)
    default.write_text("")
    assert cad.find("build123d") == ("venv", default)
    mine = tmp_path / "mine/python"
    mine.parent.mkdir()
    mine.write_text("")
    (tmp_path / "config.toml").write_text(f'cad_python = "{mine}"\n')
    config.reset()
    assert cad.find("x") == ("venv", mine)
    monkeypatch.setenv("P3D_CAD_PYTHON", str(default))
    assert cad.find("x") == ("venv", default)  # env beats config
    monkeypatch.setattr(cad, "importable", lambda *m: True)
    assert cad.find("x") == ("process", None)  # in-process beats both


def test_cad_requirements_cover_extra():
    reqs = " ".join(cad.requirements()).lower()
    for lib in ("build123d", "trimesh", "manifold3d", "shapely"):
        assert lib in reqs


def test_game_command_hidden_without_presets():
    from p3d import cli
    names = {n for cmds in cli.COMMANDS.values() for n, *_ in cmds}
    assert {"install-cad", "update", "model"} <= names
    assert ("game" in names) == (config.CONFIG_DIR / "presets.json").exists()


def test_setup_wizard_toml_roundtrips_lists():
    import tomllib
    from p3d import setup_wizard
    line = f"k = {setup_wizard.toml_value([{'id': 'a', 'path': '/x'}])}"
    assert tomllib.loads(line) == {"k": [{"id": "a", "path": "/x"}]}
