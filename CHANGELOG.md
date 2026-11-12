# Changelog

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
