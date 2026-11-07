#!/usr/bin/env python3
"""Block private details from the public repo: LAN/tailnet IPs, home paths, secrets, personal names.

  python3 scripts/privacy_scan.py            scan all tracked + staged files (CI, pre-commit)
  python3 scripts/privacy_scan.py FILE...    scan these files
  python3 scripts/privacy_scan.py --history  scan every commit (added lines, author/committer emails, messages)
  python3 privacy_scan.py --repo PATH [--history]   scan another repo (hub copy: automation/public-repo/)

Personal names are stored as salted hashes (the list itself must not leak them). Add your own words,
one per line, to .privacy-blocklist (gitignored). A line ending in "privacy-ok" is skipped.
"""
import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if "--repo" in sys.argv:
    i = sys.argv.index("--repo")
    ROOT = pathlib.Path(sys.argv[i + 1]).expanduser().resolve()
    del sys.argv[i:i + 2]
NOREPLY = "users.noreply.github.com"
NAME_HASHES = {
    "69c9d2183fcf13e1",
    "cb021ac4a1d5e2a1",
    "2cf129dc9e1d2661",
    "4f964906ecd6a248",
    "80bb1dbda7d6a557",
    "25f9d3e8a5b49ec9",
}
PATTERNS = {
    "private/tailnet IP": r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))"
                          r"\.\d{1,3}\.\d{1,3}\b",
    "home path": r"/home/[a-z_][a-z0-9_-]*|/Users/[A-Za-z][\w-]*|C:\\Users\\",
    "personal hub path": r"second_brain",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    "AWS key": r"\bAKIA[0-9A-Z]{16}\b",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "ntfy token": r"\btk_[a-z0-9]{29}\b",
    "secret assignment": r"(?i)\b(?:password|passwd|secret|api_key|token)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]",
}
SKIP = {".png", ".jpg", ".jpeg", ".stl", ".glb", ".3mf", ".gcode", ".ico"}


def h(word):
    return hashlib.sha256(("p3d:" + word.lower()).encode()).hexdigest()[:16]


def blocked_hashes():
    hs = set(NAME_HASHES)
    extra = ROOT / ".privacy-blocklist"
    if extra.exists():
        hs |= {h(w.strip()) for w in extra.read_text().splitlines() if w.strip() and not w.startswith("#")}
    return hs


def files():
    out = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split("\n")
    return [ROOT / f for f in out if f and (ROOT / f).is_file()]


def rel(p):
    try:
        return p.resolve().relative_to(ROOT)
    except ValueError:
        return p.name


def scan(paths):
    hs, rx = blocked_hashes(), {k: re.compile(v) for k, v in PATTERNS.items()}
    hits = []
    for p in paths:
        p = pathlib.Path(p)
        if p.suffix.lower() in SKIP or p.name == "privacy_scan.py":
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.rstrip().endswith("privacy-ok"):
                continue
            for k, r in rx.items():
                if r.search(line):
                    hits.append(f"{rel(p)}:{i}: {k}")
            for w in set(re.findall(r"[A-Za-z]{3,}", line)):
                if h(w) in hs:
                    hits.append(f"{rel(p)}:{i}: personal name '{w}'")
    return hits


def line_hits(text, where, hs, rx):
    hits = []
    if text.rstrip().endswith("privacy-ok"):
        return hits
    for k, r in rx.items():
        if r.search(text):
            hits.append(f"{where}: {k}")
    for w in set(re.findall(r"[A-Za-z]{3,}", text)):
        if h(w) in hs:
            hits.append(f"{where}: personal name '{w}'")
    return hits


def scan_history():
    """Every commit: emails must be GitHub noreply, messages and added lines must be clean."""
    hs, rx = blocked_hashes(), {k: re.compile(v) for k, v in PATTERNS.items()}
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, errors="replace").stdout
    hits = []
    for line in git("log", "--all", "--format=%h%x00%ae%x00%ce").splitlines():
        c, ae, ce = line.split("\0")
        for e in {ae, ce} - {"noreply@github.com"}:
            if NOREPLY not in e:
                hits.append(f"commit {c}: email {e} (use the GitHub noreply address)")
    for c in git("rev-list", "--all").split():
        for ln in git("show", "-s", "--format=%B", c).splitlines():
            hits += line_hits(ln, f"commit {c[:7]} message", hs, rx)
        cur = "?"
        for ln in git("show", "--format=", "--unified=0", "--no-color", c).splitlines():
            if ln.startswith("+++ "):
                cur = ln[6:] if ln.startswith("+++ b/") else ln[4:]
            elif ln.startswith("+") and pathlib.Path(cur).suffix.lower() not in SKIP and not cur.endswith("privacy_scan.py"):
                hits += line_hits(ln[1:], f"commit {c[:7]} {cur}", hs, rx)
    return sorted(set(hits))


def main(argv):
    if "--history" in argv:
        hits = scan_history()
    else:
        hits = scan(argv or files())
    for x in hits:
        print(x)
    if hits:
        print(f"privacy scan: {len(hits)} problem(s). Remove them (or end the line with 'privacy-ok' if harmless).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
