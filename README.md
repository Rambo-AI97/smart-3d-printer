# smart-3d-printer

Slice and print on a Creality Ender-3 V3 SE (stock Marlin, USB) from the command line, so an AI assistant can run the printer.

```
p3d slice MODEL.stl [-q draft|standard|fine] [-f pla|petg] [--supports] [--brim]
p3d print jobs/<job>/<model>.gcode     # runs in the background (systemd user unit p3d-print)
p3d status                             # progress, temps
p3d cancel                             # heaters off, lift, park
p3d log                                # print history (data/, kept local)
p3d level [--show]                     # probe the bed + colour map with what to adjust (--show = no movement)
```

- `profiles/`: standalone Orca Slicer profiles built from Orca's stock V3 SE 0.4 presets (`python3 tools/flatten_profile.py`). Change settings here, not in the GUI.
- `sender.py`: streams G-code with line numbers and checksums, waits for each `ok`, resends lines Marlin asks for, and sends ntfy alerts.
- `printlog.py`: job log `data/print_log.csv` (each p3d job + past G-code found on this PC) and lifetime counters from the printer (`printlog.py stats`).
- `tools/probe.py`: read-only check of firmware, settings and temps.
- Legacy (2024, unsafe, don't use): `printer_comm.py`, `printer_test.py`, `log_print_data.py`, `ml_model.py`.

## Safety rules for the assistant
1. Never start a print without a human saying "print it" AND confirming the bed is clear.
2. The first print with new settings or a new filament is watched by a human.
