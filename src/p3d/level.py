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


def talk(ser, cmd, wait=300, live=None):
    """Send one command, return all lines until 'ok'. live(line) sees each line as it arrives."""
    ser.write((cmd + "\n").encode())
    out, end = [], time.time() + wait
    while time.time() < end:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("ok"):
            return out
        if line:
            out.append(line)
            if live:
                live(line)
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
    print("\n  Bed map (mm, + = bed closer to nozzle). Seen from the front of the printer:\n")
    for i, r in enumerate(reversed(grid)):
        label = "back " if i == 0 else ("front" if i == len(grid) - 1 else "     ")
        print(f"  {label} " + "".join(colour(v) for v in r))
    print("        left" + " " * (n * 7 - 9) + "right\n")
    verdict = "GOOD" if span <= GOOD else ("OK" if span <= OK else "NEEDS WORK")
    print(f"  Span: {span:.2f} mm  ->  {verdict}   (good <= {GOOD}, usable <= {OK})")
    corners(grid)
    return span


def corners(grid):
    """Exactly what to do with the Allen key at each of the 4 bed screws."""
    c = [("BACK-LEFT", grid[-1][0]), ("BACK-RIGHT", grid[-1][-1]), ("FRONT-LEFT", grid[0][0]), ("FRONT-RIGHT", grid[0][-1])]
    ref = sum(v for _, v in c) / 4
    from fractions import Fraction
    print("\n  WHAT TO TURN (Allen key from the top; clockwise = down):")
    for name, v in c:
        d = v - ref                                   # + = corner too high -> clockwise (down)
        eighths = round(abs(d) / QUARTER * 2)         # 1/8-turn steps
        if eighths == 0:
            print(f"    {name:<12} leave it")
            continue
        t = Fraction(eighths, 8)
        whole, part = divmod(t, 1)
        amount = " ".join(x for x in (str(whole) if whole else "", str(part) if part else "") if x)
        way = "CLOCKWISE" if d > 0 else "COUNTER-CLOCKWISE"
        print(f"    {name:<12} {amount} turn {way:<17} ({'too high' if d > 0 else 'too low'} by {abs(d):.2f} mm)")



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
    n = [0]
    def show(line):
        m = re.search(r"Bed X:\s*([-\d.]+)\s*Y:\s*([-\d.]+)\s*Z:\s*([-\d.]+)", line)
        if m:
            n[0] += 1
            print(f"  point {n[0]:>2}  X{float(m.group(1)):>5.0f} Y{float(m.group(2)):>5.0f}  Z {float(m.group(3)):+.3f}", flush=True)
    talk(ser, "G29", wait=600, live=show)
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
