"""Render a PNG of a model with OpenSCAD for the dashboard: preview.make(stl, out_png)."""
import json, pathlib, shutil, subprocess, tempfile

from . import config


def make(stl, out_png):
    stl, out_png = pathlib.Path(stl).resolve(), pathlib.Path(out_png).resolve()
    scad_bin = config.get().scad
    if not stl.exists() or not scad_bin:
        return False
    with tempfile.TemporaryDirectory() as d:
        scad = pathlib.Path(d) / "p.scad"
        scad.write_text(f'import("{stl}");\n')
        cmd = [scad_bin, "-o", str(out_png), "--imgsize=400,400", "--viewall", "--autocenter",
               "--colorscheme=Tomorrow Night", str(scad)]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0 or not out_png.exists():
            r = subprocess.run(["xvfb-run", "-a", *cmd], capture_output=True, timeout=120) if shutil.which("xvfb-run") else r
    return out_png.exists()


def for_job(job_dir):
    """Ensure job_dir/preview.png exists (model from job.json, else an STL in the folder)."""
    job_dir = pathlib.Path(job_dir)
    png = job_dir / "preview.png"
    if png.exists():
        return png
    model = None
    jj = job_dir / "job.json"
    if jj.exists():
        model = json.load(open(jj)).get("model")
    if not model:
        model = next(iter(sorted(job_dir.glob("*.stl"))), None)
    return png if model and make(model, png) else None
