"""Read-only printer probe: firmware, settings, temps. Sends no motion or heat commands."""
import sys, time

import serial

from . import config


def main(port=None):
    PORT = port or config.get().port
    if not PORT:
        sys.exit("no serial port found (is the printer plugged in and on?)")
    for baud in (115200, 250000):
        try:
            s = serial.Serial(PORT, baud, timeout=1)
        except serial.SerialException as e:
            sys.exit(f"Cannot open {PORT}: {e}")
        time.sleep(3)              # board resets on connect
        s.reset_input_buffer()
        out = []
        for cmd in ("M115", "M503", "M105"):  # firmware info, saved settings, temps
            s.write((cmd + "\n").encode())
            end = time.time() + 4
            while time.time() < end:
                line = s.readline().decode(errors="replace").strip()
                if line:
                    out.append(line)
                    if line.startswith("ok"):
                        break
        s.close()
        if any("FIRMWARE" in l or l.startswith("ok") for l in out):
            print(f"# baud {baud}")
            print("\n".join(out))
            break
    else:
        print("No sensible reply at 115200 or 250000. Is the printer powered on?")
