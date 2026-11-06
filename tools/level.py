"""Measure the bed (G28 + G29), save the mesh (M500), show a colour map and what to adjust.

Usage: p3d level            probe now, cold (printer moves!)
       p3d level --hot 70   heat the bed to 70 C, settle 5 min, then probe (best: matches printing)
       p3d level --show     just show the mesh already saved in the printer
"""
import csv, pathlib, re, sys, time
import serial

PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
GOOD, OK = 0.30, 0.60  # mm span: good / usable


def talk(ser, cmd, wait=300):
    """Send one command, return all lines until 'ok'."""
    ser.write((cmd + "\n").encode())
    out, end = [], time.time() + wait
    while time.time() < end:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("ok"):
            return out
        if line:
            out.append(line)
            end = time.time() + wait  # still alive (busy/temps keep it going)
    raise RuntimeError(f"no 'ok' after {cmd}")


def parse_grid(lines):
    rows = []
    for l in lines:
        m = re.match(r"^\s*(\d+)\s+((?:[+-]\d+\.\d+\s*)+)$", l)
        if m:
            rows.append([float(v) for v in m.group(2).split()])
        elif rows and "Subdivided" in l:
            break
    return rows


def colour(v):
    # blue = low, green = flat, red = high
    if abs(v) < 0.1:
        c = 42
    elif v > 0:
        c = 43 if v < 0.3 else 41
    else:
        c = 46 if v > -0.3 else 44
    return f"\033[{c};30m {v:+.2f} \033[0m"


def report(grid):
    flat = [v for r in grid for v in r]
    span = max(flat) - min(flat)
    n = len(grid[0])
    left = sum(r[0] for r in grid) / len(grid)
    right = sum(r[-1] for r in grid) / len(grid)
    front = sum(grid[0]) / n
    back = sum(grid[-1]) / n
    print("\n  Bed map (mm, + = bed closer to nozzle). Seen from the front of the printer:\n")
    for i, r in enumerate(reversed(grid)):
        label = "back " if i == 0 else ("front" if i == len(grid) - 1 else "     ")
        print(f"  {label} " + "".join(colour(v) for v in r))
    print("        left" + " " * (n * 7 - 9) + "right\n")
    verdict = "GOOD" if span <= GOOD else ("OK" if span <= OK else "NEEDS WORK")
    print(f"  Span: {span:.2f} mm  ->  {verdict}   (good <= {GOOD}, usable <= {OK})")
    lr, fb = left - right, front - back
    if abs(lr) > 0.15:
        side = "left" if lr > 0 else "right"
        print(f"  Left/right: the {side} side is {abs(lr):.2f} mm higher -> raise the {side} end of the X gantry "
              f"(printer off, turn that Z screw by hand), then run p3d level again.")
    if abs(fb) > 0.15:
        side = "front" if fb > 0 else "back"
        print(f"  Front/back: the {side} is {abs(fb):.2f} mm higher (bed/Y-rail tilt; the auto mesh corrects up to ~0.5 mm).")
    if span <= GOOD:
        print("  Nothing to adjust. The saved mesh handles the rest.")
    return span


def save(grid, span):
    DATA.mkdir(exist_ok=True)
    p = DATA / "bed_mesh_log.csv"
    new = not p.exists()
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "span_mm", "grid_rows_front_to_back"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M"), round(span, 3), " | ".join(" ".join(f"{v:+.3f}" for v in r) for r in grid)])


def main(show_only=False, bed=0, soak_min=5):
    with serial.Serial(PORT, 115200, timeout=2, exclusive=True) as ser:
        time.sleep(3); ser.write(b"\n"); time.sleep(.5); ser.reset_input_buffer()
        if not show_only and bed:
            print(f"Heating bed to {bed} C and letting it settle {soak_min} min (a hot bed changes shape)...", flush=True)
            talk(ser, f"M190 S{bed}", wait=900)
            end = time.time() + soak_min * 60
            while time.time() < end:
                talk(ser, "M105")
                time.sleep(20)
        if not show_only:
            print("Homing and probing (about 2 minutes)...", flush=True)
            talk(ser, "G28")
            talk(ser, "G29", wait=600)
            talk(ser, "M500")  # keep the new mesh after power-off
            talk(ser, "G1 Z10 F600")
            if bed:
                talk(ser, "M140 S0")
        grid = parse_grid(talk(ser, "M420 V"))
    if not grid:
        sys.exit("No mesh found in the printer.")
    span = report(grid)
    if not show_only:
        save(grid, span)


if __name__ == "__main__":
    a = sys.argv[1:]
    main("--show" in a, int(a[a.index("--hot") + 1]) if "--hot" in a else 0)
