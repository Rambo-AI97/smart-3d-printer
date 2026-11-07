import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def scan(tmp_path, text):
    f = tmp_path / "x.py"
    f.write_text(text)
    return subprocess.run([sys.executable, str(ROOT / "scripts/privacy_scan.py"), str(f)], capture_output=True, text=True)


def test_blocks_tailnet_ip_and_home_path(tmp_path):
    assert scan(tmp_path, 'URL = "http://' + "100." + '71.1.2:8090"\n').returncode == 1
    assert scan(tmp_path, 'P = "/' + 'home/someone/x"\n').returncode == 1
    assert scan(tmp_path, 'KEY = "ghp_' + "a" * 36 + '"\n').returncode == 1


def test_allows_normal_code(tmp_path):
    assert scan(tmp_path, 'URL = "http://localhost:8765"\nV = "1.2.3.4"\n').returncode == 0


def test_repo_is_clean():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/privacy_scan.py")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
