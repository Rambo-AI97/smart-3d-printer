# Fridge link

Plain JSON files in one folder (config `fridge_dir`, env `P3D_FRIDGE`; empty = the whole link is off; point it at a synced folder to share it). **One writer per file.** All times are local ISO `YYYY-MM-DDTHH:MM:SS`. p3d refreshes its files about every 30 s (in the `p3d-web` service) and on events (print start/end, verdict, request).

| File | Writer | Reader |
|---|---|---|
| `status.json` | p3d | Fridge |
| `requests.json` | p3d | Fridge |
| `shots/*.jpg` | p3d | Fridge |
| `approvals.json` | Fridge | p3d |

All p3d writes are atomic (tmp file + rename), so a reader never sees half a file. Missing or unreadable files: treat as empty.

## status.json

```json
{
  "schema": 1,
  "updated": "2026-11-25T16:00:24",
  "printer": {"state": "idle|printing|paused", "job": "cube-v2" , "percent": 42.0, "minutes_left": 31,
              "nozzle": 241.5, "nozzle_target": 240, "bed": 79.8, "bed_target": 80},
  "spool": {"name": "Black PETG 1kg", "grams_left": 812.0},
  "queue": [{"n": 1, "name": "20261125-1200-hook", "minutes": 74.0, "grams": 18.5, "request": "7"}],
  "tracker": [{"name": "cube-v2", "state": "check", "verdict": "", "date": "2026-11-25 15:10", "request": "7", "who": "Alex"}]
}
```

- `printer.*` other than `state` is `null` while idle. `state` is `idle` when nothing runs (also when the dashboard service sees a dead sender).
- `queue` is the print queue in order; `request` is the Fridge note number or `""`.
- `tracker` = the last 10 non-queued tracker items, newest first. `state`: `printing | check | passed | failed | cancelled | reopened`. `verdict`: `pass | fail | ""`.

## requests.json

```json
{"updated": "2026-11-25T15:00:00", "requests": [
  {"note": "7", "who": "Alex", "title": "Hook for the dog leashes", "job": "20261125-1200-hook",
   "shot": "note-7-20261125-1200-hook.jpg", "time": 74.0, "grams": 18.5,
   "state": "awaiting_ok", "reprint_of": "", "updated": "2026-11-25T15:00:00"}
]}
```

- `note`: Fridge note number (string). `job`: job folder name (the key used in `approvals.json`). `shot`: file in `shots/` (may be `""`). `time`: estimated minutes; `grams`: estimated filament.
- `state`: `awaiting_ok` (shot made, waiting for Alex/the owner) -> `approved` -> `queued` -> `printing` -> `check` (finished, waiting for a verdict) -> `passed | failed`. Side states: `change_asked` (a change was requested; p3d adds `change_text`, `change_by`), and a cancelled print goes back to `approved`. `approved` with an `error` field means p3d could not queue it (the text says why).
- A new version of a design is a new request entry with the same `note` and a new `job`; `reprint_of` names the earlier job.
- `verdict_note` appears once there is a verdict.

Created with `p3d request add NOTE JOB --who Alex --title "..."` (makes the shot with `p3d shot` and copies it to `shots/`).

## approvals.json (the Fridge writes)

A JSON array, append-only is fine; p3d remembers processed entries, so old ones are ignored.

```json
[{"note": 7, "job": "20261125-1200-hook", "action": "approve", "by": "Alex", "text": "", "at": "2026-11-25T15:30:00"},
 {"note": 8, "job": "20261125-1300-box",  "action": "change",  "by": "Alex", "text": "make it 5 mm taller", "at": "2026-11-25T15:31:00"}]
```

- `action`: `approve` or `change`. An entry is identified by `note|job|action|at`: **`at` must differ for each new decision** (write a fresh timestamp).
- `approve`: p3d adds the job to the print queue (same as `p3d queue add`) and sets the request to `queued`. It **never starts a print**; the owner starts the queue.
- `change`: request becomes `change_asked`, `text` is stored as `change_text`.

## Verdicts

After a print, the owner (or the dashboard Tracker tab) gives a verdict. On `pass` for a job linked to a Fridge note, p3d runs your `fridge_done_cmd` (a command template; `{n}` = note number, `{text}` = the plain-words message, both shell-quoted for you, e.g. `fridge_done_cmd = "notes-cli done {n} {text}"`) so the note is ticked and the requester gets a ping. Empty (the default) = no command. It never runs under pytest or `P3D_NOTES_DRYRUN`. Starting the next print without a verdict closes the previous job as `passed` ("assumed pass: plate cleared for next print"); this does not ping.

## Dashboard embed

`http://<this-pc>:8765/?embed=1&tab=tracker` (tabs: `live`, `queue`, `models`, `past`, `tracker`, `requests`, `charts`, `history`, `ideas`, `knowledge`). `embed=1` hides the page header and the opaque edges for use in an iframe. The Pass/Fail buttons need the viewing device in `control_from`.
Read-only JSON: `/api/tracker`, `/api/requests`, shots at `/api/request/shot/<file>`.
