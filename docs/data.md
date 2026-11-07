# Data recorded

Everything is plain CSV in the **data folder**: `~/.local/share/p3d` by default, or `data_dir` in
`~/.config/p3d/config.toml`, or the `P3D_DATA` environment variable. Point it at a synced folder to keep logs on another machine.

| Where | What |
|---|---|
| `~/.config/p3d/config.toml` | settings (`p3d setup`), see `config.example.toml` |
| `<data>/print_log.csv` | one row per job |
| `<data>/prints/<YYYYMMDD-HHMM>-<name>.csv` | one row every 30 s during a print |
| `<data>/printer_stats.csv` | the printer's lifetime counters (M78), after every print |
| `<data>/bed_mesh_log.csv` | every `p3d level` |
| `<data>/calibration.md` | your calibration results table (the dashboard's Calibration card reads it) |
| `<data>/jobs/<stamp>-<name>/` | sliced jobs: G-code, process.json, preview.png (`jobs_dir`) |
| `~/.local/state/p3d/state.json` | the current/last job (what `p3d status` and the dashboard show) |

New columns are appended at the end; old rows keep empty cells.

## print_log.csv

date, name, status, est_min, actual_min, grams, filament, layer_mm, nozzle_mm, source, file;
then started, ended, nozzle_set, bed_set, flow_ratio, retraction_mm, quality (draft/standard/fine/calib),
outer_speed (outer wall mm/s), max_nozzle, min_nozzle (lowest after layer 1 while heating: temperature dips),
avg_bed, layers, samples_file, rating (1-5), issues (tags), notes, model (source STL).
Slicer settings come from the G-code header; rating/issues/notes are set with `p3d rate`.

## prints/*.csv

time, elapsed_min, progress, remaining_min, z, layer, nozzle, nozzle_target, bed, bed_target.

## printer_stats.csv

date, prints, finished, failed, total_hours, longest_hours, filament_m.

## bed_mesh_log.csv

date, span_mm, grid_rows_front_to_back (0.30 mm span = good, 0.60 = usable).

## state.json (job lifecycle)

`p3d print` writes `queued` with a `job_id` (the job folder name). The sender then writes `printing`
every 5 s and always ends with a **final state**: `done`, `failed` (with `error`) or `cancelled`, plus `ended_at`.
`p3d wait done` returns only for the job that was current when it started (exit 0 = done, 1 = failed/cancelled).
If the state says `printing` but no sender runs, `p3d status` and the dashboard mark it **stale**.
`p3d status --json` prints only JSON: `{"running": bool, "stale": bool, "state": {...}}`.

Phone alerts (ntfy, if `ntfy_url` is set): print started, done, failed, cancelled, and "cool, safe to switch off".
