"""Small labelled preview sheets for a phone (remote clients can't load local image paths).

shot([job_dir | png, ...]) -> one JPG, <= ~100 KB: each tile = preview + name + time + grams.
"""
import json
import pathlib
import re
import time

from PIL import Image, ImageDraw, ImageFont

TILE = 360
OUT_DIR = pathlib.Path.home() / ".local/share/p3d/shots"


def _font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _info(item):
    """(png, title, subtitle) for a job dir, a gcode, an STL/scad name or a png."""
    p = pathlib.Path(item).expanduser()
    if p.suffix == ".gcode":
        p = p.parent
    if p.is_dir():
        png = p / "preview.png"
        name = re.sub(r"^\d{8}-\d{4}-", "", p.name)
        sub = ""
        g = next(p.glob("*.gcode"), None)
        if g:
            txt = g.read_text(errors="ignore")[-60000:]
            t = re.search(r"estimated printing time \(normal mode\) = (.+)", txt)
            w = re.search(r"total filament used \[g\] = ([\d.]+)", txt)
            sub = f"{t.group(1).strip() if t else '?'}  {w.group(1) + ' g' if w else ''}"
        warn = _warning(p)
        if warn:
            sub += "  ! " + warn[:40]
        return png, name, sub
    if p.suffix in (".stl", ".scad"):
        p = p.with_suffix(".png")
    return p, p.stem, ""


def _warning(job):
    try:
        plates = json.loads((job / "result.json").read_text()).get("sliced_plates", [])
        return "; ".join(x.get("warning_message", "") for x in plates if x.get("warning_message"))
    except (OSError, ValueError):
        return ""


def shot(items, out=None, tile=TILE):
    tiles = []
    for it in items:
        png, title, sub = _info(it)
        if not png.exists():
            raise SystemExit(f"no preview for {it} ({png})")
        im = Image.open(png).convert("RGB")
        im.thumbnail((tile, tile))
        t = Image.new("RGB", (tile, tile + 46), (24, 26, 30))
        t.paste(im, ((tile - im.width) // 2, 0))
        d = ImageDraw.Draw(t)
        d.text((8, tile + 4), title[:34], fill=(235, 235, 235), font=_font(17))
        d.text((8, tile + 25), sub[:48], fill=(160, 200, 255), font=_font(14))
        tiles.append(t)
    cols = min(len(tiles), 3)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile, rows * (tile + 46)), (24, 26, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * tile, (i // cols) * (tile + 46)))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(out) if out else OUT_DIR / f"shot-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    sheet.save(out, "JPEG", quality=78, optimize=True)
    return out
