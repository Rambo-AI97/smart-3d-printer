# Changelog

## Unreleased

(nothing yet)

## 2.0.0 (2026-11-25)

**Any printer**
- `p3d setup` asks which printer you have and searches Orca Slicer's 500+ machine profiles (`p3d printers WORDS`); bed size, max height, park and Z-home points come from the profile instead of being hard-coded.
- Network printers: Klipper (Moonraker), OctoPrint, PrusaLink and Bambu Lab LAN mode, next to USB Marlin. Same status, dashboard, log, spools and alerts; USB-only tools (level, PID, calibration, recover) say so. Bambu jobs are sliced to `.gcode.3mf`.
- New users default to PLA (`filament` in the config still wins).

**Install**
- One-line `install.sh`: uv, p3d with the CAD extra, Orca Slicer AppImage, serial access, setup, services, doctor. `p3d update`, `p3d install-cad`.
- Extras: `cad` (build123d, trimesh, manifold3d, shapely, ...), `bambu` (paho-mqtt), `all`.

**Engineering**
- `p3d check` / `stress` / `orient` / `coupon` take a build123d design (`.py`) directly. Negative option values work as typed (`--fix-face -x`).
- `examples/shelf_bracket.py`: a design to try `p3d sheet` on.

**Dashboard**
- Readable job names in the queue and tracker; upload slices with the loaded filament; round chart ticks; spool names fit.
- Stats: settings changes are compared per filament (switching PLA/PETG is not a change).

**Breaking: optional integrations are off by default.** `fridge_dir`, `fridge_done_cmd`, `event_cmd`, `knowledge_files`, `cad_python`, `shots_dir` (see config.example.toml). Design sheets and shots go to `<data_dir>/shots`.

## 1.1.x (after 1.1.0)

- Dashboard: upload a model from the phone (`POST /api/upload?name=`, raw body; .stl .3mf .obj .zip, 100 MB cap) or paste a Printables link (`POST /api/upload/link`, public GraphQL API, STL files only). Safe unzip, 3MF/OBJ converted to STL in pure Python, sliced PETG/standard into a model card (never queued or printed). Bed-mesh panel is collapsible (remembered) and capped in height.
- Slice advisor: `p3d inspect` prints an Advice section (brim for tall parts, supports, heavy settings on small parts, placement and bed mesh, filament vs spool, long prints). `p3d.advisor.advise(info)` for reuse.
  It also runs automatically after every `p3d slice`, `p3d queue add` and dashboard slice/reslice, so problems show before the preview (it caught a 50 mm part sliced without a brim on its first run).

## 1.1.0 (2026-11-12)

**Printing**
- Pause/resume on stock Marlin: host-side pause at the next layer change or a chosen layer (`--pause-at-layer`, `p3d pause --at-layer`), now also removable mid-print (`--remove-layer N`, `--clear`). A `PAUSE_NOTE.txt` in the job dir goes out with the pause alert.
- Print queue (`p3d queue add|list|remove|move|next`) that keeps each job's pause layers; `p3d retry`, `p3d cooldown`.
- Spools: grams deducted when a job ends, low-spool refusal, filament mismatch badge.
- `p3d recover` (continue a failed print from its last good layer) and `p3d addon` (print on top of a part). Both write a job and never print on their own.
- Bed step-down: PETG first layer 70 C then 60 C (PLA 60/55) on every plate variant.
- `p3d level`: live probe points, a minimal map, and plain Allen-key turns per corner.

**Dashboard**
- Controls bar on every tab: Pause, Resume, Stop, Start next, Retry, Check bed level, Last bed mesh, Cooldown.
- Tabs: Queue (reorder, pictures), Past prints, Models (slice and queue), Stats (success, rating, grams, hours, settings timeline), Ideas, Knowledge (edits a fixed allowlist of notes files).
- Reslice form (filament, quality, walls, infill, brim, supports, pause layer) with preview and Add to queue.
- Control API limited to localhost plus `control_from` / `cancel_from` addresses.

**Alerts and data**
- Loud alerts on a second ntfy topic (Priority 5, quiet hours), optional spoken line and quips; `p3d notify-test`.
- Settings snapshot per job; `p3d suggest` turns rating issue tags into next steps; `p3d idea` board.

**Models**
- Gallery in the README with 20 OpenSCAD sources: kitchen, baby, dog-walk, desk and printer-tool parts.

**Fixes**
- Tests no longer read the host's systemd, so a real print on the machine can't change results. Lint clean.

## 1.0.0 (2026-11-07)

First public release: `p3d setup/doctor/install-service`, slice, print, cancel, status, live dashboard, print log and ratings, calibration prints, Printables packs.
