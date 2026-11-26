# Command reference

`p3d --help` lists everything; `p3d <command> -h` explains one command. Commands marked *USB* need a Marlin printer on USB (they talk G-code to the firmware directly).


| Group | Command | What it does |
|---|---|---|
| Print | `p3d status [--json]` | current job, progress, temperatures |
| | `p3d print FILE.gcode` | print in the background (survives closing the terminal) |
| | `p3d print FILE --pause-at-layer N` | pause before layer N (magnets, colour swap); `--force` ignores a low spool |
| | `p3d pause [--at-layer N \| --remove-layer N \| --clear]` / `p3d resume` | host-side pause at a layer change (retract, lift, park, heaters stay on); `--remove-layer`/`--clear` cancel pending layer pauses mid-print |
| | `p3d cancel` | safe stop: heaters off, lift, park |
| | `p3d queue add JOB \| list \| remove N \| move N M \| next` | queue of approved jobs; `next` starts the head (refuses while printing or when the spool is short) |
| | `p3d wait layer\|done` | block until the first layer is down / the job ends (for scripts) |
| | `p3d retry` / `p3d cooldown` | reprint the newest logged job / after a print: wait until cool, motors off, alert |
| | `p3d web [--open]` | live dashboard URL (also for your phone) |
| | `p3d printers [WORDS]` | search the printers Orca has profiles for (e.g. `p3d printers bambu a1`) |
| Design | `p3d slice MODEL [-q draft\|standard\|fine] [-f pla\|petg] [--supports] [--brim]` | model → G-code |
| | `p3d scad NAME` / `p3d make NAME` | OpenSCAD part → STL + preview / → STL → slice → check |
| | `p3d sheet NAME\|FILE.stl` | 4-view design sheet (front/side/top/iso, mm, thinnest wall) before you slice |
| | `p3d build NAME` | Python (build123d) design `models/py/NAME.py` → STL → slice → check, see [Shape workflow](shapes.md) |
| | `p3d model FILE` / `p3d game PRESET` | any .glb/.obj/.fbx/.stl → solid printable STL (Blender); a Godot game model by preset |
| | `p3d inspect JOB_DIR\|FILE.gcode` | where the time and filament go, plus slice advice (brim, supports, heavy settings, placement, spool) |
| | `p3d pack NAME` | upload pack for Printables (STL, source, render) |
| | `p3d recover JOB [--from-layer N \| --z MM]` | continue a failed print from its last good layer (writes a job, never prints) |
| | `p3d addon MODEL --on-z MM [--x --y]` | slice a model to print on top of an existing part (writes a job, never prints) |
| Engineer | `p3d check MODEL.stl\|NAME [--multi]` | pre-slice gate (also runs inside `p3d make`, `--force` overrides): watertight, bodies, thin walls, empty layers, overhang, bed fit; PASS/WARN/FAIL |
| | `p3d stress NAME --load KG --section-at Z --arm MM` / `--fix-face -z --load-at X,Y,Z [--dir -z]` | beam/section stress from the real mesh vs PETG/PLA/TPU layer-line and in-plane strength, safety factor |
| | `p3d coupon NAME --z A..B \| --box x0,y0,z0,x1,y1,z1` | cut the critical slice and slice it as a tiny fit test (time, grams; never queued) |
| | `p3d orient MODEL [--load-dir X,Y,Z]` | score each stable face (supports, bed contact, height, strength), write the best `_oriented.stl`; `p3d make --auto-orient` |
| Calibrate *USB* | `p3d level [--hot 70]` | probe the bed, colour map, what to adjust |
| | `p3d calib temp\|retraction\|flow\|firstlayer` | make a calibration print |
| | `p3d pid` / `p3d probe` | PID-tune heaters / read-only firmware check |
| Data | `p3d log`, `p3d history`, `p3d rate` | job log, totals, ratings (issue tags print a concrete next step) |
| | `p3d import-history` | add past G-code files found on this PC to the log |
| | `p3d suggest`, `p3d stats` | recurring issues with fixes; success, rating, grams, hours per week and when settings changed |
| | `p3d spool add\|list\|use\|set` | filament spools; grams are deducted when a job ends (done = all, stopped = share printed) |
| | `p3d idea add\|list\|move\|done` | print ideas in a hand-editable `ideas.md` |
| Setup | `p3d setup`, `p3d doctor`, `p3d install-service` | first run, health check, background services |
| | `p3d install-cad`, `p3d update` | add the CAD/engineering libraries in their own venv; upgrade p3d |

## How the smart parts work

- **Engineer tools** (`p3d.eng`): need trimesh/shapely/manifold3d (the `cad` extra, included in `p3d[all]`); used in-process if installed, else run in the venv from `p3d install-cad` (or the Python in `P3D_CAD_PYTHON` / config `cad_python`), and skipped with a message if neither exists.
- **Slice advisor:** runs after every `p3d slice`, `p3d queue add` and dashboard (re)slice, and at the end of `p3d inspect`; it flags problems before you print (tall part without brim, support-heavy or unused supports, heavy walls/infill on a small part, off-centre or bad-mesh placement, filament vs active spool, long fine prints); thresholds are constants in `advisor.py`, `advise(info)` is reusable.
- **Bed step-down:** the first layer gets a hotter bed, the rest a cooler one (Ender defaults: PETG 70 then 60 C, PLA 60 then 55); set in `flatten_profile.py`, applied to every printer.
- **Pause/resume** works on stock Marlin: the sender stops at a layer boundary, retracts, lifts and parks; resume returns, primes and carries on. The dashboard and the ntfy message have Pause/Resume buttons (POST `/api/pause`, `/api/resume`).
- **Recover / add-on** (*USB*): many printers (e.g. the Ender-3 V3 SE) probe Z with the nozzle at one point (config `z_home_xy`, default bed centre). If the part's footprint covers that point, or is unknown, the generated job never probes Z: you lower the nozzle onto the part top by hand and the job declares that height (`G92 Z`), then homes X/Y only. If the footprint is known and clear (+ `z_home_margin`), it uses a normal `G28`. Both write `INSTRUCTIONS.txt` next to the G-code and need `p3d print --confirm-z`. Untested on hardware until watched once.
- **Stats:** every job stores a settings snapshot (layer height, temperatures incl. the bed step-down, speeds, walls, infill, retraction, profile hash); the dashboard Stats tab charts success and rating by week, issues, grams and hours, spool levels and a settings-change timeline.
- **Dashboard controls:** a bar on every tab with Pause, Resume, Stop, Start next, Retry last print (`p3d retry`), Check bed level (one `p3d level --hot 70` probe as a background task, colour map when done; refused while a print runs or cools), Last bed mesh and Cooldown. Queue, history and model cards have a Reslice form (filament, quality, walls, infill, brim, supports, keep orientation, optional pause at layer N with a note); the result shows time, grams and a preview with Add to queue. The Knowledge tab renders and edits the hub's rules, filament guide, printer lessons and ideas files (fixed allowlist, atomic save, `.bak` of the previous version). All writes are limited to `control_from` addresses.
- **Control endpoints** (`/api/cancel`, `pause`, `resume`, `queue/next`, `ideas`) accept localhost plus the addresses in `cancel_from` / `control_from` in the config. The queue lives in `print_queue.json` and spools in `spools.json` in the data dir; the ideas board is `ideas.md` next to it (`ideas_file` to move it).
- **Loud alerts**: set `urgent_ntfy_url` to a second ntfy topic your phone lets through silent mode. Print done, printer cool, failed/cancelled, paused, still warm, not started and spool low also go there with `Priority: 5`, only between `urgent_hours` (default `[7, 22]`, local time). Set `quips_file` (lines under `[print_start]`, `[print_done]`, `[print_failed]`) to put a funny line above the facts. Test with `p3d notify-test --dry-run` (prints, sends nothing) or `p3d notify-test`.


