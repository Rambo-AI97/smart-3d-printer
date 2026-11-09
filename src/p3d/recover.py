"""`p3d recover JOB` (continue a failed/cancelled print) and `p3d addon MODEL.stl --on-z MM` (print on top of a part).

Both only WRITE a job (G-code + preview + INSTRUCTIONS.txt); they never start a print.

Z safety. The Ender-3 V3 SE finds Z by pressing the nozzle onto the bed at one point (default: the bed centre).
With a part on the bed that probe would land on the part and every height would be wrong (crash).
  - Part footprint known and clear of the probe point (+ margin): the job uses a normal G28.
  - Otherwise (default, and whenever the footprint is unknown): Z is never probed. You lower the nozzle by hand until it
    touches the top of the part; the job then declares that height with G92 Z, lifts 10 mm and homes X/Y only.
"""
import json
import pathlib
import re
import shutil
import time

from . import config, gcode

SAFE_LIFT = 6.0


def find_job(arg):
    p = pathlib.Path(arg).expanduser()
    if p.is_file() and p.suffix == ".gcode":
        return p.parent
    if p.is_dir():
        return p
    jobs = config.get().jobs
    if (jobs / arg).is_dir():
        return jobs / arg
    hits = sorted(jobs.glob(f"*{arg}*"))
    hits = [h for h in hits if h.is_dir()]
    if not hits:
        raise SystemExit(f"no job {arg} in {jobs}")
    return hits[-1]


def last_done_layer(job_dir):
    """Last completed layer: run.json next to the G-code, else the state file of that job, else the samples CSV."""
    try:
        v = json.loads((job_dir / "run.json").read_text()).get("layer_done")
        if v:
            return int(v), "run.json"
    except Exception:
        pass
    s = config.read_state()
    if s.get("job_id") == job_dir.name and s.get("layer_done"):
        return int(s["layer_done"]), "state"
    try:
        from . import printlog
        for r in reversed(printlog.rows()):
            if r.get("file", "").startswith(str(job_dir)) and r.get("samples_file"):
                import csv
                rows = list(csv.DictReader(open(printlog.data_dir() / r["samples_file"])))
                lay = [int(float(x["layer"])) for x in rows if x.get("layer")]
                if lay:
                    return max(lay[-1] - 1, 0), "samples"
    except Exception:
        pass
    return 0, ""


def new_job_dir(stem):
    c = config.get()
    out = c.jobs / f"{time.strftime('%Y%m%d-%H%M')}-{re.sub(r'[^A-Za-z0-9]+', '_', stem)}"
    n = 2
    while out.exists():
        out = out.with_name(out.name.split("~")[0] + f"~{n}")
        n += 1
    out.mkdir(parents=True)
    return out


def instructions(kind, auto_home, z_ref, box, point, margin, extra=()):
    L = [f"{kind}: read this before `p3d print`.", ""]
    if auto_home:
        L += [f"Z homing: AUTOMATIC. The part's footprint {tuple(round(v) for v in box)} stays {margin:.0f} mm clear of the Z probe",
              f"point {tuple(point)}, so a normal G28 is safe.",
              "1. Switch the printer on and raise the head by hand well above the part.",
              "2. Make sure nothing but the part is on the bed (the probe presses on whatever is at the centre)."]
    else:
        why = ("the part's footprint is unknown" if box is None else
               f"the part's footprint {tuple(round(v) for v in box)} covers the Z probe point {tuple(point)}")
        L += [f"Z homing: MANUAL (conservative), because {why}.",
              "The printer must NOT probe Z here: the probe would land on the part and every height would be wrong.",
              "1. Switch the printer on. Trim or scrape any blobs/strings off the top of the part so it is flat.",
              f"2. Lower the nozzle by hand (screen: Prepare > Move > Z, small steps) until it just touches the top of the part,",
              f"   a paper-thin gap. The job treats that surface as Z = {z_ref:g} mm.",
              "3. Do not move X/Y afterwards. Keep your hand near the power switch for the first minute."]
    L += list(extra)
    L += ["", "Then: p3d print JOB" + ("" if auto_home else " --confirm-z"),
          "UNTESTED on real hardware until the first run: watch the first minute (homing, prime, first layer), cancel with p3d cancel."]
    return "\n".join(L)


def write_job(out, name, lines, info, job_meta, instr, preview_from=None):
    g = out / f"{name}.gcode"
    g.write_text("\n".join(lines) + "\n")
    (out / "job.json").write_text(json.dumps({"gcode": str(g), **job_meta}))
    (out / "INSTRUCTIONS.txt").write_text(instr + "\n")
    if preview_from and (preview_from / "preview.png").exists():
        shutil.copy2(preview_from / "preview.png", out / "preview.png")
    else:
        try:
            from . import preview
            if job_meta.get("model"):
                preview.make(job_meta["model"], out / "preview.png")
        except Exception:
            pass
    return g


def cmd_recover(a):
    c = config.get()
    src_dir = find_job(a.job)
    src = next(iter(sorted(src_dir.glob("*.gcode"))), None)
    if not src:
        raise SystemExit(f"no G-code in {src_dir}")
    raw = src.read_text(errors="replace").splitlines()
    cmds, layer_at, layer_z, total = gcode.parse(raw)
    how = "given"
    if a.from_layer is not None:
        keep = a.from_layer
    elif a.z is not None:
        keep = gcode.last_layer_at_or_below(layer_z, a.z)
    else:
        keep, how = last_done_layer(src_dir)
        if not keep:
            raise SystemExit("no recorded layer for this job: give --from-layer N (last good layer) or --z MM (its top height)")
    if not 1 <= keep < total:
        raise SystemExit(f"last good layer must be 1..{total - 1} (file has {total} layers)")
    box = gcode.footprint(cmds, upto=keep, layer_at=layer_at)
    point = tuple(c.z_home_xy)
    auto = gcode.z_home_ok(box, point, c.z_home_margin)
    prime_ok = box is None or box[0] > 14
    lines, info = gcode.build_recover(raw, keep, auto, prime_ok=prime_ok)
    out = new_job_dir(src.stem + f"_recover_L{keep + 1}")
    name = f"{src.stem}_recover_L{keep + 1}"
    title = f"RECOVER {src.stem}: continue at layer {info['layer']} (last good layer {keep}, top z {info['z_ref']:g}, from {how})"
    prime_txt = "line on the left bed edge" if prime_ok else "air purge near the corner: pull the blob off the nozzle"
    instr = instructions(title,
                         auto, info["z_ref"], box, point, c.z_home_margin,
                         extra=["", "Filament left for this job is about {:.0f}% of the original.".format(100 * info["share"]),
                                "Prime: " + prime_txt])
    meta = {"model": json.loads((src_dir / "job.json").read_text()).get("model", "") if (src_dir / "job.json").exists() else "",
            "recover_of": src_dir.name, "from_layer": keep, "manual_z": not auto}
    g = write_job(out, name, lines, info, meta, instr, preview_from=src_dir)
    print(g)
    print()
    print(instr)


def cmd_addon(a):
    from . import cli
    c = config.get()
    model = pathlib.Path(a.model).expanduser().resolve()
    proc_extra = {"brim_type": "no_brim", "skirt_loops": "0", "elefant_foot_compensation": "0",
                  "initial_layer_line_width": "0.42"}
    out, g_sliced = cli.slice_model(model, a.quality, a.filament, proc_extra=proc_extra, keep_orient=True, tag="addon")[:2]
    raw = g_sliced.read_text(errors="replace").splitlines()
    cmds, layer_at, layer_z, total = gcode.parse(raw)
    if not total:
        raise SystemExit("slice has no layers")
    top = max(layer_z.values())
    if a.on_z + top > 240:
        raise SystemExit(f"on-z {a.on_z} + model height {top:.1f} is over the 240 mm limit")
    first = next(i for i, r in enumerate(raw) if r.startswith(";LAYER_CHANGE"))
    tail = max(i for i, r in enumerate(raw) if r.startswith(";TYPE:Custom"))
    t = gcode.Tracker()
    for r in raw[:first]:
        if gcode.strip(r):
            t.feed(gcode.strip(r))
    nozzle, bed = t.nozzle or 240.0, t.bed or 70.0
    body = gcode.shift_all(raw[first:tail], a.x, a.y, a.on_z)
    end = gcode.shift_all(raw[tail:], 0, 0, a.on_z)
    bcmds, blayer, _, _ = gcode.parse(body)
    box = gcode.footprint(bcmds, layer_at=blayer)
    point = tuple(c.z_home_xy)
    pb = None
    if a.part_bbox:
        pb = tuple(float(v) for v in a.part_bbox.split(","))
        if len(pb) != 4:
            raise SystemExit("--part-bbox X0,Y0,X1,Y1 (mm)")
    auto = gcode.z_home_ok(pb, point, c.z_home_margin) if pb else False
    foot = pb or box
    prime_ok = foot is None or foot[0] > 14
    head = [r for r in raw[:first] if r.startswith(";") or r.startswith(("M201", "M203"))]
    hdr = gcode.start_header(nozzle, bed, a.on_z, auto, prime_ok, return_z=a.on_z + SAFE_LIFT,
                             comment="p3d add-on")
    lines = head + [f"; p3d add-on at z {a.on_z:g}, offset x {a.x:g} y {a.y:g}"] + hdr + ["G90", "M83", "G92 E0"] + body + end
    name = f"{model.stem}_addon_z{a.on_z:g}"
    title = f"ADD-ON {model.stem} on top of an existing part at z {a.on_z:g} mm (offset x {a.x:g}, y {a.y:g} from the bed centre)"
    hint = "" if pb else " (Pass --part-bbox X0,Y0,X1,Y1 to allow automatic homing if the part is far from the bed centre.)"
    instr = instructions(title,
                         auto, a.on_z, pb, point, c.z_home_margin,
                         extra=["", f"The add-on's own footprint is {tuple(round(v) for v in box)}; "
                                "the part under it must be at least that big.",
                                "No brim, no skirt, no elephant-foot squish: the first layer lands on the part's top surface.",
                                "Put the part back in the SAME place it was printed, or give its x/y offset with --x/--y, "
                                "and make sure it cannot move." + hint])
    meta = {"model": str(model), "manual_z": not auto, "addon_z": a.on_z}
    g = write_job(out, name, lines, {}, meta, instr)
    g_sliced.unlink(missing_ok=True)  # the plain slice must not be printable by accident
    print(g)
    print()
    print(instr)
