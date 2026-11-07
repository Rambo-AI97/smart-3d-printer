# smart-3d-printer

Slice and print on a Creality Ender-3 V3 SE (stock Marlin, USB) from the command line, so an AI assistant can run the printer.

```
p3d slice MODEL.stl [-q draft|standard|fine] [-f pla|petg] [--supports] [--brim]
p3d print jobs/<job>/<model>.gcode     # runs in the background (systemd user unit p3d-print)
p3d status                             # progress, temps
p3d cancel                             # heaters off, lift, park
p3d log                                # print history (logs live in ~/.local/share/p3d)
p3d rate [1-5] [--issues stringing,adhesion] [--note "text"] [--job NAME]   # rate the last print (no args: show it)
p3d history                            # totals, success rate, hours, grams, avg rating, last 5
p3d level [--show]                     # probe the bed + colour map with what to adjust (--show = no movement)
```

- Live dashboard: `p3d web [--open]` -> http://localhost:8765 (phone: `http://<this-pc-tailscale-ip>:8765`; `p3d web` prints it). Read-only page with model preview, progress, time left, ETA, layer/Z, nozzle/bed temps chart, recent prints. Runs as systemd user service `p3d-web` (`web/server.py`, stdlib only). `sender.py` writes `state.json` every 5 s (M73 progress, Z, layers, M155 temps); `preview.py` renders `preview.png` per job with OpenSCAD.
- `profiles/`: standalone Orca Slicer profiles built from Orca's stock V3 SE 0.4 presets (`python3 tools/flatten_profile.py`). Change settings here, not in the GUI.
- `sender.py`: streams G-code with line numbers and checksums, waits for each `ok`, resends lines Marlin asks for, and sends ntfy alerts.
- `printlog.py`: job log `~/.local/share/p3d/print_log.csv` (family hub, syncs to the home server) (each p3d job + past G-code found on this PC) and lifetime counters from the printer (`printlog.py stats`).
- `tools/calib.py` (`p3d calib`; OpenSCAD model -> Orca slice -> G-code post-process, firmware has no Linear Advance):
  - `temp`: 8-block tower, PLA 230->195 / PETG 255->220 in -5 C steps (bottom = hottest), number engraved on the front, bridge + 45 deg overhang per block; ~1 h 15 min.
  - `retraction`: two pillars 40 mm apart, 5 mm bands with retraction 0.2 -> 1.6 mm (bottom to top); read stringing per band; ~25 min.
  - `flow`: five 25x25x2 squares at 90/95/100/105/110 % (`M221`), pick the smoothest top; ~22 min.
  - `firstlayer`: one 0.2 mm layer, 5 squares (centre + 4 corners) to judge squish and tilt; ~4 min.
- `tools/probe.py`: read-only check of firmware, settings and temps.
- Legacy (2024, unsafe, don't use): `printer_comm.py`, `printer_test.py`, `log_print_data.py`, `ml_model.py`.

## Data we record
All in `~/.local/share/p3d/` (override `P3D_DATA`); new columns are appended at the end, old rows keep empty cells.
- `print_log.csv` (one row per job): date, name, status, est_min, actual_min, grams, filament, layer_mm, nozzle_mm, source, file; then started, ended, nozzle_set, bed_set, flow_ratio, retraction_mm, quality (draft/standard/fine/calib), outer_speed (outer wall mm/s), max_nozzle, min_nozzle (lowest after layer 1 while heating: temp dips), avg_bed, layers, samples_file, rating (1-5), issues (tags), notes, model (source STL). Slicer settings come from the G-code header comments; rating/issues/notes are set with `p3d rate`.
- `prints/<YYYYMMDD-HHMM>-<name>.csv` (one per print, row every 30 s + end): time, elapsed_min, progress, remaining_min, z, layer, nozzle, nozzle_target, bed, bed_target.
- `printer_stats.csv`: date, prints, finished, failed, total_hours, longest_hours, filament_m (M78 lifetime counters, appended after every print and by `printlog.py stats`).
- `bed_mesh_log.csv`: date, span_mm, grid_rows_front_to_back (every `p3d level`; 0.30 good, 0.60 usable).
- Dashboard "History" tab charts all of it (`/api/history`, `/api/print/<file>`); the Calibration card is read from `CALIBRATION.md`.

## Safety rules for the assistant
1. Never start a print without a human saying "print it" AND confirming the bed is clear.
2. The first print with new settings or a new filament is watched by a human.
