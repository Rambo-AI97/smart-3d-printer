"""Measure the bed (G28 + G29), save the mesh (M500), show a colour map and what to adjust.

Usage: p3d level                   probe now, cold (printer moves!)
       p3d level --hot 70          heat the bed to 70 C first (no wait if it's already hot; 2 min settle from cold)
       p3d level --hot 70 --adjust probe, show what to turn per corner, Enter = probe again, bed stays hot
       p3d level --soak N          settle minutes after heating (default 2)
       p3d level --show            just show the mesh already saved in the printer
"""
import csv, re, signal, sys, time

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


class Stopped(Exception):
    pass


_last_temp = [0.0]
def temp_line(line):
    """Print the bed temperature while heating (at most every 2 s): '  bed 55.2 / 70 C'."""
    m = re.search(r"B:\s*([\d.]+)\s*/\s*([\d.]+)", line)
    if m and time.time() - _last_temp[0] >= 2:
        _last_temp[0] = time.time()
        print(f"  bed {float(m.group(1)):.1f} / {float(m.group(2)):.0f} C", flush=True)


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


def turns(grid):
    """[(corner, action, delta_mm)] for the 4 bed screws; grid rows front to back. action e.g. '3/8 turn CLOCKWISE'."""
    from fractions import Fraction
    c = [("BACK-LEFT", grid[-1][0]), ("BACK-RIGHT", grid[-1][-1]), ("FRONT-LEFT", grid[0][0]), ("FRONT-RIGHT", grid[0][-1])]
    ref = sum(v for _, v in c) / 4
    out = []
    for name, v in c:
        d = v - ref                                   # + = corner too high -> clockwise (down)
        eighths = round(abs(d) / QUARTER * 2)         # 1/8-turn steps
        if eighths == 0:
            out.append((name, "leave it", d))
            continue
        whole, part = divmod(Fraction(eighths, 8), 1)
        amount = " ".join(x for x in (str(whole) if whole else "", str(part) if part else "") if x)
        out.append((name, f"{amount} turn {'CLOCKWISE' if d > 0 else 'COUNTER-CLOCKWISE'}", d))
    return out


def corners(grid):
    """Exactly what to do with the Allen key at each of the 4 bed screws."""
    print("\n  WHAT TO TURN (Allen key from the top; clockwise = down):")
    for name, action, d in turns(grid):
        if action == "leave it":
            print(f"    {name:<12} leave it")
        else:
            print(f"    {name:<12} {action:<27} ({'too high' if d > 0 else 'too low'} by {abs(d):.2f} mm)")


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
    """Current bed temperature. The 'ok' line itself carries the temps on Marlin, so read it too; retry (first reply after connect can be empty)."""
    for _ in range(5):
        ser.write(b"M105\n")
        end = time.time() + 5
        while time.time() < end:
            l = ser.readline().decode(errors="replace")
            m = re.search(r"B:\s*([\d.]+)", l)
            if m:
                t, stop = float(m.group(1)), time.time() + 2
                while not l.startswith("ok") and time.time() < stop:   # eat the trailing 'ok' so the next command lines up
                    l = ser.readline().decode(errors="replace")
                return t
        time.sleep(0.5)
    return 0.0


def probe(ser):
    print("Homing...", flush=True)
    talk(ser, "G28")
    print("Probing 16 points (about 2 minutes)...", flush=True)
    n = [0]
    def show(line):
        m = re.search(r"X:\s*([-\d.]+)\s*Y:\s*([-\d.]+)\s*Z:\s*([-\d.]+)", line) if "Bed" in line or "Probe" in line else None
        if m:
            n[0] += 1
            print(f"  point {n[0]:>2}  X{float(m.group(1)):>5.0f} Y{float(m.group(2)):>5.0f}  Z {float(m.group(3)):+.3f}", flush=True)
    talk(ser, "G29 V3", wait=600, live=show)   # V3: firmware reports every probed point (Bed X: Y: Z:)
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
        def stop(*_):
            ser.write(b"M108\n")   # emergency parser: break a heat-up wait now
            raise Stopped()
        signal.signal(signal.SIGTERM, stop)
        try:
            if bed:
                now = bed_temp(ser)
                if now >= bed - 3 and soak_min is None:
                    print(f"Bed already at {now:.0f} C: probing now, no settle wait.", flush=True)
                elif now >= bed - 20 and soak_min is None:
                    print(f"Bed still warm ({now:.0f} C) from the last print: topping up to {bed} C, no settle wait.", flush=True)
                    talk(ser, f"M190 S{bed}", wait=900)
                else:
                    soak = 2 if soak_min is None else soak_min
                    print(f"Heating bed to {bed} C, then {soak} min settle (a hot bed changes shape)...", flush=True)
                    talk(ser, f"M190 S{bed}", wait=900, live=temp_line)
                    end = time.time() + soak * 60
                    while time.time() < end:
                        b = bed_temp(ser)
                        print(f"  settle {int(end - time.time())}s left, bed {b:.1f} C", flush=True)
                        time.sleep(10)
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
        except Stopped:
            ser.write(b"M140 S0\n")   # queued: runs right away, or after the probe pass the firmware is finishing
            print("Stopped. Bed heater off (a probe pass already running finishes first, up to 2 min).", flush=True)
            sys.exit(3)
        finally:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            if bed:
                try:
                    talk(ser, "M140 S0", wait=10)
                except Exception:
                    ser.write(b"M140 S0\n")
                print("Bed heater off.")

if __name__ == "__main__":
    a = sys.argv[1:]
    main("--show" in a, int(a[a.index("--hot") + 1]) if "--hot" in a else 0, adjust="--adjust" in a)
