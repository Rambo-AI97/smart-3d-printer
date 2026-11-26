"""Filament change session: heat the nozzle, then extrude / retract on command, heater off when done.

Usage: p3d filament [--temp 240]      (default: print temp of the active spool's material)
Reads commands on stdin, one per line:  extrude MM | retract MM | done
Opens the serial port ONCE (opening it resets the board), so the nozzle stays hot between moves.
Heater off after `done`, end of input, an error, or 10 idle minutes. Refuses to move below 180 C.
"""
import re, select, sys, time

from . import config
from .level import talk

TEMPS = {"pla": 210, "petg": 240, "tpu": 225}
IDLE = 600
FEED = {"extrude": 180, "retract": 1200}   # mm/min: slow push in, fast pull out (unload)


def default_temp():
    try:
        from . import spools
        d = spools.load()
        s = next((s for s in d["spools"] if s["name"] == d["active"]), None)
        return TEMPS.get((s or {}).get("material", "").lower(), 240)
    except Exception:
        return 240


def say(msg):
    print(msg, flush=True)


def heat(ser, temp):
    say(f"heating nozzle to {temp} C")
    talk(ser, f"M104 S{temp}")
    end = time.time() + 600
    while time.time() < end:
        line = " ".join(talk(ser, "M105", wait=10))
        m = re.search(r"T:\s*([\d.]+)", line)
        t = float(m.group(1)) if m else 0
        say(f"  nozzle {t:.0f} / {temp} C")
        if t >= temp - 3:
            return
        time.sleep(2)
    raise RuntimeError("nozzle did not reach temperature in 10 minutes")


def move(ser, kind, mm):
    mm = max(1.0, min(float(mm), 120.0))
    e = mm if kind == "extrude" else -mm
    say(f"{kind} {mm:.0f} mm...")
    talk(ser, "M83")
    talk(ser, f"G1 E{e:.1f} F{FEED[kind]}", wait=120)
    talk(ser, "M400", wait=120)
    say(f"ready ({kind}ed {mm:.0f} mm)")


def main(temp=None):
    temp = int(temp or default_temp())
    if temp < 180 or temp > 260:
        sys.exit("temp must be 180..260 C")
    with config.open_serial(timeout=2) as ser:
        time.sleep(3); ser.write(b"\n"); time.sleep(.5); ser.reset_input_buffer()
        try:
            heat(ser, temp)
            say("ready: extrude / retract / done")
            last = time.time()
            while time.time() - last < IDLE:
                r, _, _ = select.select([sys.stdin], [], [], 5)
                if not r:
                    continue
                line = sys.stdin.readline()
                if not line:
                    break
                p = line.split()
                if not p:
                    continue
                if p[0] == "done":
                    break
                if p[0] in FEED:
                    move(ser, p[0], p[1] if len(p) > 1 else 10)
                    last = time.time()
                else:
                    say(f"unknown command: {p[0]}")
            else:
                say("idle 10 minutes")
        finally:
            for c in ("M104 S0", "M18 E"):
                try:
                    talk(ser, c, wait=10)
                except Exception:
                    pass
            say("heater off")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[a.index("--temp") + 1]) if "--temp" in a else None)
