# Calibration record: Ender-3 V3 SE + PETG

Everything we tuned, what each test is for, and where the value lives.
Source of truth: `tools/flatten_profile.py` (`CALIBRATED`) → `profiles/*.json` (CLI) and the Orca GUI preset **PETG (Axiom)**.
Printer-side values are in the printer's EEPROM (`M503` shows them).

## Results

| Date | What | Value | Where |
|---|---|---|---|
| 2026-11-06 | Bed shape (mesh, probed hot at 70 °C) | span 0.69 mm, 4x4 mesh on | EEPROM (`p3d level --hot 70`) |
| 2026-11-06 | Hotend PID | P22.95 I2.09 D62.99 | EEPROM (M301) |
| 2026-11-06 | Bed PID | P89.29 I6.40 D829.88 | EEPROM (M304) |
| 2026-11-06 | First layer | all 5 squares stick; right side slightly far, OK | no change |
| 2026-11-06 | PETG nozzle temp | **235 °C**, first layer 240 °C | `CALIBRATED["petg"]` |
| 2026-11-06 | PETG bed temp | 70 °C (held with brim) | stock |
| | Retraction | _pending_ (stock 1.2 mm) | |
| | Flow | _pending_ (stock) | |

## Why each test, in order

Each test fixes one cause, so the order matters: later tests rely on earlier ones.

1. **Bed mesh (level).** The nozzle has to sit the same distance above the bed everywhere. The probe measures 16 points and the printer adjusts Z while it moves. We probe **hot** because steel bends when it heats: our bed moved 0.5–0.7 mm at 70 °C.
2. **PID tune.** PID is the controller that keeps a heater at its target temperature. The factory numbers overshoot and wobble. Tuned values hold the temperature steady, which gives steady flow and an even surface.
3. **First layer.** The first layer is about 80 % of print failures. The test prints five thin squares at the corners and centre. Rounded, separate lines mean the nozzle is too far; ridges or a see-through look mean too close; tearing means much too far.
4. **Temperature tower.** Hotter plastic flows and bonds better but strings and droops more. Each 10 mm block prints 5 °C cooler, and the engraved number is that block's temperature. We pick the coolest block that still has clean bridges and layers that won't snap. Ours was clean from 220 to 255 °C, so 235 °C leaves some margin.
5. **Retraction.** When the nozzle travels without printing, melted plastic leaks out and leaves strings. Retraction pulls the filament back first. Two pillars force a travel on every layer, and each 5 mm band uses a longer pull (0.2 → 1.6 mm). Pick the shortest band with no strings: too long wears the filament and leaves gaps.
6. **Flow.** Filament diameter and density vary by brand, so the slicer's estimate of how much plastic comes out is slightly off. Five squares at 90–110 % flow; the smoothest top (no gaps, no ridges) is the true value.

Later, if needed: pressure/corner sharpness (Linear Advance is not in this stock firmware), input shaping for ringing at speed.

## Lessons
- Calibration models need a wide base and a brim. Temp tower v1 stood on 5 mm legs and came off the bed.
- PETG: wash the PEI sheet with dish soap; probe hot; nozzle slightly far is safer than too close (PETG sticks very hard).
