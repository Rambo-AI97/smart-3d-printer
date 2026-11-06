"""PID-tune the hotend and bed, save to EEPROM. Usage: p3d pid [--hotend 220] [--bed 60]"""
import re, sys, time
import serial
from level import PORT, talk


def tune(ser, heater, temp):
    label = "hotend" if heater == 0 else "bed"
    print(f"Tuning {label} at {temp} C (8 cycles, a few minutes)...", flush=True)
    out = talk(ser, f"M303 E{heater} S{temp} C8 U1", wait=900)
    vals = [l for l in out if re.search(r"Kp|M30[14]|PID Autotune finished|failed", l, re.I)]
    for l in vals:
        print("  ", l)
    if any("fail" in l.lower() for l in out):
        raise SystemExit(f"{label} autotune failed")


def main(hotend=220, bed=60):
    with serial.Serial(PORT, 115200, timeout=2, exclusive=True) as ser:
        time.sleep(3); ser.write(b"\n"); time.sleep(.5); ser.reset_input_buffer()
        try:
            talk(ser, "M106 S255")  # part fan on, like during a print
            tune(ser, 0, hotend)
            talk(ser, "M106 S0")
            tune(ser, -1, bed)
            talk(ser, "M500")
            print("Saved. New values:")
            for l in talk(ser, "M503"):
                if "M301" in l or "M304" in l:
                    print("  ", l.replace("echo:", "").strip())
        finally:
            for c in ("M104 S0", "M140 S0", "M106 S0"):
                talk(ser, c)


if __name__ == "__main__":
    args = sys.argv[1:]
    get = lambda k, d: int(args[args.index(k) + 1]) if k in args else d
    main(get("--hotend", 220), get("--bed", 60))
