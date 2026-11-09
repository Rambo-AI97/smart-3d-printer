"""Loud (urgent) alerts: second topic, Priority 5, quiet hours. No network, no printer."""
import datetime

import pytest

from p3d import config, sender


@pytest.fixture
def posts(monkeypatch):
    monkeypatch.delenv("P3D_NO_NOTIFY", raising=False)
    sent = []

    class Resp:
        def close(self):
            pass

    def fake_urlopen(req, timeout=10):
        sent.append({"url": req.full_url, "title": req.get_header("Title"), "prio": req.get_header("Priority")})
        return Resp()

    monkeypatch.setattr(config.urllib.request, "urlopen", fake_urlopen)
    config._cfg = config.Config({"ntfy_url": "http://ntfy.test/normal", "urgent_ntfy_url": "http://ntfy.test/loud"})
    return sent


def at(h):
    return datetime.datetime(2026, 11, 9, h, 30)


def test_urgent_daytime_goes_to_both(posts):
    assert config.notify("Print done", "x", urgent=True, now=at(12))
    assert [p["url"] for p in posts] == ["http://ntfy.test/normal", "http://ntfy.test/loud"]
    assert posts[0]["prio"] is None and posts[1]["prio"] == "5"


@pytest.mark.parametrize("h", [22, 23, 0, 6])
def test_urgent_quiet_hours_normal_only(posts, h):
    config.notify("Print done", "x", urgent=True, now=at(h))
    assert [p["url"] for p in posts] == ["http://ntfy.test/normal"]


@pytest.mark.parametrize("h", [7, 21])
def test_urgent_window_edges(posts, h):
    config.notify("Print done", "x", urgent=True, now=at(h))
    assert len(posts) == 2


def test_not_urgent_never_loud(posts):
    config.notify("Print started", "x", now=at(12))
    assert [p["url"] for p in posts] == ["http://ntfy.test/normal"]


def test_no_loud_topic_configured(posts):
    config._cfg = config.Config({"ntfy_url": "http://ntfy.test/normal"})
    config.notify("Print done", "x", urgent=True, now=at(12))
    assert len(posts) == 1


def test_dry_run_sends_nothing(posts, monkeypatch, capsys):
    monkeypatch.setenv("P3D_NOTIFY_DRYRUN", "1")
    assert config.notify("Print done", "x", urgent=True, now=at(12))
    assert posts == []
    assert "P5 Print done" in capsys.readouterr().err


def test_which_alerts_are_loud(monkeypatch):
    """Done/cool/failed/cancelled/paused/warm/not-started/spool-low are urgent; started/resumed are not."""
    import inspect
    import re
    from p3d import runner, spools
    src = "\n".join(inspect.getsource(m) for m in (sender, runner, spools))
    calls = re.findall(r'notify\(\s*"([^"]+)"(.*?)\)\s*$', src, re.M | re.S)
    loud = {t for t, rest in calls if "urgent=True" in rest}
    assert {"Print done", "Printer cool", "Print FAILED", "Print cancelled", "Print paused",
            "Printer still warm", "Print NOT started", "Spool low"} <= loud
    assert not loud & {"Print started", "Print resumed", "Queued print started"}


def test_quip_goes_above_facts(posts, tmp_path):
    f = tmp_path / "quips.txt"
    f.write_text("# c\n[print_done]\nDing. Not a real ding.\n[print_failed]\nOops.\n")
    config._cfg = config.Config({"ntfy_url": "http://ntfy.test/normal", "quips_file": str(f)})
    bodies = []
    orig = config._post
    config._post = lambda url, t, m, *a, **k: bodies.append(m) or True
    try:
        config.notify("Print done", "desk: 81 min", quip_event="print_done", now=at(12))
        config.notify("Print done", "x", quip_event="nope", now=at(12))
    finally:
        config._post = orig
    assert bodies == ["Ding. Not a real ding.\n\ndesk: 81 min", "x"]


def test_quip_missing_file_is_silent():
    config._cfg = config.Config({"quips_file": "/nonexistent/q.txt"})
    assert config.quip("print_done") == ""
