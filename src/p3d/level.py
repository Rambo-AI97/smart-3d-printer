"""Measure the bed (G28 + G29), save the mesh (M500), show a colour map and what to adjust.

Usage: p3d level                   probe now, cold (printer moves!)
       p3d level --hot 70          heat the bed to 70 C first (no wait if it's already hot; 2 min settle from cold)
       p3d level --hot 70 --adjust probe, show what to turn per corner, Enter = probe again, bed stays hot
       p3d level --soak N          settle minutes after heating (default 2)
       p3d level --show            just show the mesh already saved in the printer
"""
import csv, re, sys, time

from . import config
GOOD, OK = 0.30, 0.60  # mm span: good / usable
QUARTER = 0.175        # mm per 1/4 turn of an M4 bed screw (0.7 mm pitch)
TURN_HELP = ("  Which way:  TIGHTEN = corner goes DOWN (more gap),  LOOSEN = corner goes UP.\n"
             "    screw head on top (hex key from above): tighten = CLOCKWISE seen from above\n"
             "    knob under the bed: tighten = turn it so the knob climbs UP toward the bed")


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
    corners(grid)
    if span <= GOOD:
        print("  Nothing to adjust. The saved mesh handles the rest.")
    return span


def corners(grid):
    """Per-corner bed-screw instructions, relative to the average of the 4 corners."""
    c = {"back-left": grid[-1][0], "back-right": grid[-1][-1], "front-left": grid[0][0], "front-right": grid[0][-1]}
    ref = sum(c.values()) / 4
    todo = []
    for name, v in c.items():
        d = v - ref                                   # + = this corner is high -> lower it (tighten)
        q = round(abs(d) / QUARTER * 2) / 2           # quarter turns, to the nearest 1/8 turn
        if q < 0.5:
            continue
        from fractions import Fraction
        t = Fraction(int(q * 2), 8)                   # eighths of a turn
        whole, part = divmod(t, 1)
        amount = " ".join(x for x in (str(whole) if whole else "", str(part) if part else "") if x)
        what = "TIGHTEN (lower)" if d > 0 else "LOOSEN (raise)"
        todo.append(f"    {name:<12} {d:+.2f} mm  ->  {what} {amount} turn")
    print("\n  Bed screws (vs the corner average):")
    print("\n".join(todo) if todo else "    all four corners within 0.05 mm: leave them")
    print(TURN_HELP)


def save(grid, span):
    DATA = config.get().data
    DATA.mkdir(parents=True, exist_ok=True)
    p = DATA / "bed_mesh_log.csv"
    new = not p.exists()
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "span_mm", "grid_rows_front_to_back"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M"), round(span, 3), " | ".join(" ".join(f"{v:+.3f}" for v in r) for r in grid)])


def bed_temp(ser):
    for l in talk(ser, "M105") + [""]:
        m = re.search(r"B:\s*([\d.]+)", l)
        if m:
            return float(m.group(1))
    return 0.0


def probe(ser):
    print("Homing and probing (about 2 minutes)...", flush=True)
    talk(ser, "G28")
    talk(ser, "G29", wait=600)
    talk(ser, "M500")  # keep the new mesh after power-off
    grid = parse_grid(talk(ser, "M420 V"))
    present(ser)
    return grid


def present(ser):
    """Head up, bed forward: room to lift the plate off and reach the bed screws."""
    talk(ser, "G90")
    talk(ser, "G1 Z80 F900")
    talk(ser, f"G1 X0 Y{config.get().park_y} F3000")
    talk(ser, "M400")


def main(show_only=False, bed=0, soak_min=None, adjust=False):
    with config.open_serial(timeout=2) as ser:
        time.sleep(3); ser.write(b"\n"); time.sleep(.5); ser.reset_input_buffer()
        if show_only:
            grid = parse_grid(talk(ser, "M420 V"))
            if not grid:
                sys.exit("No mesh found in the printer.")
            report(grid)
            return
        try:
            if bed:
                now = bed_temp(ser)
                if now >= bed - 3 and soak_min is None:
                    print(f"Bed already at {now:.0f} C: probing now, no settle wait.", flush=True)
                else:
                    soak = 2 if soak_min is None else soak_min
                    print(f"Heating bed to {bed} C, then {soak} min settle (a hot bed changes shape)...", flush=True)
                    talk(ser, f"M190 S{bed}", wait=900)
                    end = time.time() + soak * 60
                    while time.time() < end:
                        talk(ser, "M105")
                        time.sleep(20)
            while True:
                grid = probe(ser)
                if not grid:
                    sys.exit("No mesh found in the printer.")
                span = report(grid)
                save(grid, span)
                if not adjust:
                    break
                try:
                    a = input("\nTurn the screws, then press Enter to check again (q + Enter = done): ")
                except EOFError:
                    break
                if a.strip().lower().startswith("q"):
                    break
                if bed:
                    talk(ser, f"M140 S{bed}")  # keep it hot between checks
        finally:
            if bed:
                talk(ser, "M140 S0")
                print("Bed heater off.")

if __name__ == "__main__":
    a = sys.argv[1:]
    main("--show" in a, int(a[a.index("--hot") + 1]) if "--hot" in a else 0, adjust="--adjust" in a)
