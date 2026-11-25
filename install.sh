#!/usr/bin/env bash
# p3d one-line installer (Linux).
#   curl -fsSL https://raw.githubusercontent.com/Rambo-AI97/smart-3d-printer/main/install.sh | bash
#   ... | bash -s -- --yes --no-orca        (flags: --yes, --no-orca, --no-setup)
# Safe to re-run: every step checks first. Env: P3D_SOURCE = another source to install (a local folder or git URL).
set -euo pipefail

YES=0 ORCA=1 SETUP=1
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --no-orca) ORCA=0 ;;
    --no-setup) SETUP=0 ;;
    -h|--help) sed -n '2,5p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --yes, --no-orca, --no-setup)" >&2; exit 2 ;;
  esac
done

SOURCE="${P3D_SOURCE:-git+https://github.com/Rambo-AI97/smart-3d-printer}"
step() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }

# Ask a yes/no question; reads from the terminal even when the script is piped. --yes answers yes.
confirm() {
  [ "$YES" = 1 ] && return 0
  if [ -r /dev/tty ] && : </dev/tty 2>/dev/null; then
    local a
    read -r -p "    $1 [Y/n] " a </dev/tty || return 1
    case "$a" in ""|y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
  fi
  return 1  # no terminal and no --yes: do not guess
}

[ "$(uname -s)" = Linux ] || { echo "p3d's installer supports Linux only." >&2; exit 1; }
[ "$(id -u)" -ne 0 ] || note "running as root: p3d is meant to be installed for a normal user."
command -v curl >/dev/null 2>&1 || { echo "curl is required (sudo apt install curl)." >&2; exit 1; }

export PATH="$HOME/.local/bin:$PATH"

step "1/6 uv (installs p3d and Python 3.12 in an isolated environment)"
if command -v uv >/dev/null 2>&1; then
  note "uv already installed: $(uv --version)"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  command -v uv >/dev/null 2>&1 || { echo "uv installed but not on PATH; open a new shell and re-run." >&2; exit 1; }
fi

step "2/6 p3d with the CAD libraries (p3d[all])"
uv tool install --python 3.12 --force "p3d[all] @ ${SOURCE}"
command -v p3d >/dev/null 2>&1 || note "p3d is in $(uv tool dir --bin 2>/dev/null || echo "$HOME/.local/bin"): add it to PATH (uv tool update-shell)."

step "3/6 Orca Slicer (the slicer p3d drives)"
find_orca() {
  command -v orca-slicer 2>/dev/null || command -v OrcaSlicer 2>/dev/null || true
  local f
  for f in "$HOME"/Applications/*rca*licer*.AppImage "$HOME"/*rca*licer*.AppImage "$HOME/orca-slicer"; do
    if [ -f "$f" ] && [ -x "$f" ]; then echo "$f"; return 0; fi
  done
}
install_orca() {
  local id="" ver="" want api asset url dest
  # shellcheck disable=SC1091
  if [ -r /etc/os-release ]; then id=$(. /etc/os-release; echo "${ID:-}"); ver=$(. /etc/os-release; echo "${VERSION_ID:-}"); fi
  want="2404"
  case "$id:$ver" in ubuntu:22.*|linuxmint:21*|debian:11*) want="2204" ;; esac
  api=$(curl -fsSL https://api.github.com/repos/OrcaSlicer/OrcaSlicer/releases/latest) || { note "could not reach the GitHub API; install Orca by hand: https://github.com/OrcaSlicer/OrcaSlicer/releases"; return 0; }
  url=$(printf '%s' "$api" | grep -o '"browser_download_url": *"[^"]*\.AppImage"' | sed 's/.*"\(http[^"]*\)"/\1/' || true)
  asset=$(printf '%s\n' "$url" | grep -i "ubuntu.*${want}\|${want}" | head -n1 || true)
  [ -n "$asset" ] || asset=$(printf '%s\n' "$url" | head -n1)
  [ -n "$asset" ] || { note "no AppImage in the latest Orca release; install it by hand: https://github.com/OrcaSlicer/OrcaSlicer/releases"; return 0; }
  dest="$HOME/Applications"
  mkdir -p "$dest"
  note "downloading $(basename "$asset") to $dest"
  curl -fL --progress-bar -o "$dest/$(basename "$asset").part" "$asset"
  mv "$dest/$(basename "$asset").part" "$dest/$(basename "$asset")"
  chmod +x "$dest/$(basename "$asset")"
  note "installed $dest/$(basename "$asset")"
}
if [ "$ORCA" = 0 ]; then
  note "skipped (--no-orca)"
elif [ -n "$(find_orca)" ]; then
  note "found: $(find_orca)"
else
  install_orca
fi
if [ "$ORCA" = 1 ] && ! ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'; then
  note "AppImages need libfuse2 (Ubuntu/Debian: sudo apt install libfuse2t64 or libfuse2; Arch: sudo pacman -S fuse2)."
fi

step "4/6 serial port access (the printer's USB port needs your user in a group)"
GROUP="dialout"
getent group dialout >/dev/null 2>&1 || GROUP="uucp"
if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$GROUP"; then
  note "you are in the $GROUP group"
elif ! getent group "$GROUP" >/dev/null 2>&1; then
  note "no dialout/uucp group on this system; skipping"
else
  note "you are not in the $GROUP group. The command is: sudo usermod -aG $GROUP $USER   (then log out and in)"
  if confirm "Run it now?"; then
    sudo usermod -aG "$GROUP" "$USER" && note "added; log out and in once for it to apply"
  fi
fi

if [ "$SETUP" = 0 ]; then
  step "5/6 and 6/6 skipped (--no-setup)"
  note "later: p3d setup && p3d install-service && p3d doctor"
  exit 0
fi

step "5/6 p3d setup (finds the port and the slicer, writes the config)"
if [ "$YES" = 1 ]; then
  p3d setup --yes
elif [ -r /dev/tty ] && : </dev/tty 2>/dev/null; then
  p3d setup </dev/tty
else
  p3d setup --yes
fi

step "6/6 dashboard service and health check"
p3d install-service || note "service not installed (no systemd user session?). Run it later: p3d install-service"
p3d doctor || true

printf '\nDone. Next: plug in and switch on the printer, then p3d slice my-part.stl. Update later with: p3d update\n'
