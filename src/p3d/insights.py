"""Learning from the log: next-step advice per issue tag, recurring issues, settings-change timeline, weekly stats.
All pure functions over print_log rows (dicts of strings)."""
import datetime

ADVICE = {
    "stringing": "p3d calib retraction (and dry the spool if it is damp)",
    "adhesion": "clean the bed with IPA, then p3d level --hot 70",
    "first-layer": "p3d level --hot 70, then p3d calib firstlayer",
    "warping": "re-slice with --brim and a floor >= 2 mm; keep big parts off drafts; clean the bed",
    "layer-shift": "check belts and pulley grub screws; slow the travel speed; look for a snagging cable",
    "blobs": "p3d calib retraction; dry the filament; check the seam setting",
    "under-extrusion": "p3d calib flow (raise the ratio); check for a partial clog or damp filament",
    "over-extrusion": "p3d calib flow (lower the ratio)",
    "supports": "re-slice with other support settings (tree vs none); p3d inspect shows the support share",
    "spaghetti": "p3d level --hot 70, p3d calib firstlayer; use --brim for tall or thin parts",
    "other": "add a note: p3d rate --note \"...\"",
}
TRACKED = ["layer_mm", "nozzle_set", "nozzle_first", "bed_first", "bed_other", "outer_speed", "inner_speed", "travel_speed",
           "walls", "infill", "infill_pattern", "retraction_mm", "flow_ratio"]
LABEL = {"layer_mm": "layer", "nozzle_set": "nozzle", "nozzle_first": "nozzle L1", "bed_first": "bed L1", "bed_other": "bed",
         "outer_speed": "outer speed", "inner_speed": "inner speed", "travel_speed": "travel", "walls": "walls",
         "infill": "infill", "infill_pattern": "pattern", "retraction_mm": "retraction", "flow_ratio": "flow"}
PRINTED = ("done", "failed", "cancelled")


def tags(row):
    return [t.strip() for t in (row.get("issues") or "").split(",") if t.strip()]


def next_steps(issue_tags):
    return [(t, ADVICE.get(t, ADVICE["other"])) for t in issue_tags]


def printed(rows):
    return [r for r in rows if r.get("status") in PRINTED]


def recurring(rows, last=10, min_count=2):
    """[(tag, count, advice)] for tags seen in at least min_count of the last `last` printed jobs, most frequent first."""
    cnt = {}
    for r in printed(rows)[-last:]:
        for t in set(tags(r)):
            cnt[t] = cnt.get(t, 0) + 1
    return [(t, n, ADVICE.get(t, ADVICE["other"])) for t, n in sorted(cnt.items(), key=lambda kv: -kv[1]) if n >= min_count]


def settings_of(row):
    return tuple((k, (row.get(k) or "").strip()) for k in TRACKED)


def settings_changes(rows):
    """[{date, name, changes: ['bed 70 -> 60', ...]}] each time the tracked settings differ from the job before.
    Jobs without a snapshot (older rows) are skipped for comparison; empty values never count as a change.
    Compared per filament: switching PLA <-> PETG is not a settings change (each material keeps its own baseline)."""
    out, prev_by = [], {}
    for r in printed(rows):
        cur = {k: v for k, v in settings_of(r) if v}
        if not cur:
            continue
        mat = (r.get("filament") or "").strip().lower()
        prev = prev_by.get(mat)
        if prev is not None:
            ch = [f"{LABEL[k]} {prev.get(k, '?')} -> {cur[k]}" for k in TRACKED if k in cur and cur[k] != prev.get(k, cur[k])]
            if ch:
                out.append({"date": r["date"], "name": r["name"], "changes": [f"{mat.upper()}: {c}" for c in ch] if mat else ch})
        prev_by[mat] = {**(prev or {}), **cur}
    return out


def since_last_change(rows):
    """Issue rate (issues per rated job) before vs after the latest settings change, or None."""
    ch = settings_changes(rows)
    if not ch:
        return None
    d = ch[-1]["date"]
    pr = [r for r in printed(rows) if (r.get("issues") or r.get("rating"))]
    before, after = [r for r in pr if r["date"] < d], [r for r in pr if r["date"] >= d]
    if not before or not after:
        return None
    rate = lambda rs: round(sum(len(tags(r)) for r in rs) / len(rs), 2)
    return {"date": d, "before": rate(before), "after": rate(after), "n_before": len(before), "n_after": len(after)}


def week_of(date_str):
    try:
        d = datetime.date.fromisoformat((date_str or "")[:10])
    except ValueError:
        return None
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def weekly(rows):
    """Per ISO week: jobs, done, success %, avg rating, grams (as used), hours."""
    w = {}
    for r in printed(rows):
        k = week_of(r.get("date"))
        if not k:
            continue
        x = w.setdefault(k, {"week": k, "n": 0, "done": 0, "ratings": [], "grams": 0.0, "hours": 0.0})
        x["n"] += 1
        x["done"] += r["status"] == "done"
        if (r.get("rating") or "").isdigit():
            x["ratings"].append(int(r["rating"]))
        x["grams"] += f(r.get("grams_used")) or (f(r.get("grams")) if r["status"] == "done" else 0.0)
        x["hours"] += f(r.get("actual_min")) / 60
    out = []
    for k in sorted(w):
        x = w[k]
        out.append({"week": k, "n": x["n"], "done": x["done"], "success": round(100 * x["done"] / x["n"]),
                    "rating": round(sum(x["ratings"]) / len(x["ratings"]), 2) if x["ratings"] else None,
                    "grams": round(x["grams"], 1), "hours": round(x["hours"], 2)})
    return out


def issue_counts(rows):
    c = {}
    for r in printed(rows):
        for t in tags(r):
            c[t] = c.get(t, 0) + 1
    return c


def cmd_suggest(rows, out=print):
    rec = recurring(rows)
    if not rec:
        out("no issue has repeated in the last 10 jobs. Tag problems with p3d rate N --issues ...")
    for t, n, adv in rec:
        out(f"{t} x{n} (last 10 jobs): {adv}")
    s = since_last_change(rows)
    if s:
        out(f"settings last changed {s['date'][:10]}: issues per rated job {s['before']} before ({s['n_before']} jobs) -> "
            f"{s['after']} after ({s['n_after']} jobs)")


def cmd_stats(rows, out=print):
    pr = printed(rows)
    if not pr:
        return out("no printed jobs yet")
    wk = weekly(rows)
    out(f"{len(pr)} jobs, success {round(100 * sum(r['status'] == 'done' for r in pr) / len(pr))}%")
    for x in wk[-6:]:
        bar = "#" * round(x["success"] / 10)
        out(f"  week {x['week']}  {x['n']:2} jobs  {x['success']:3}% {bar:10}  rating {x['rating'] or '-':>4}  "
            f"{x['grams']:6.0f} g  {x['hours']:5.1f} h")
    ic = issue_counts(rows)
    if ic:
        out("issues: " + ", ".join(f"{k} {v}" for k, v in sorted(ic.items(), key=lambda kv: -kv[1])))
    for c in settings_changes(rows)[-5:]:
        out(f"  {c['date'][:10]} settings changed ({c['name']}): " + "; ".join(c["changes"]))
    cmd_suggest(rows, out)
