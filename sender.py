"""Stream a G-code file to Marlin safely: line numbers + checksums, wait for 'ok', honour Resend.

Writes progress to state.json, stops cleanly when the STOP file appears, pings ntfy when done/failed.
Run via `p3d print`, not directly.
"""
import json, pathlib, subprocess, sys, time
import serial

ROOT = pathlib.Path(__file__).resolve().parent
STATE, STOP = ROOT / "state.json", ROOT / "STOP"
PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
NOTIFY = pathlib.Path.home() / ".local/bin/p3d-notify"
SILENCE_LIMIT = 300  # s with no reply at all → assume the link is dead
SAFE_STOP = ["M104 S0", "M140 S0", "M107", "G91", "G1 Z10 F600", "G90", "G1 X0 Y220 F3000", "M84"]


def notify(title, msg, tags="printer"):
    subprocess.run([str(NOTIFY), title, msg, tags], check=False)


def load(path):
    lines = []
    for raw in open(path, errors="replace"):
        cmd = raw.split(";", 1)[0].strip()
        if cmd:
            lines.append(cmd)
    return lines


def framed(n, cmd):
    body = f"N{n} {cmd}"
    cs = 0
    for ch in body.encode():
        cs ^= ch
    return f"{body}*{cs}\n".encode()


class Link:
    def __init__(self):
        self.ser = serial.Serial(PORT, 115200, timeout=1, exclusive=True)
        time.sleep(3)  # board resets on connect
        self.ser.write(b"\n")
        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.temps = ""
        self.exchange(0, "M110 N0")  # reset line numbering

    def exchange(self, n, cmd):
        """Send line n, block until 'ok'. Returns the next line number (earlier one if Marlin asks to resend)."""
        self.ser.write(framed(n, cmd))
        nxt, last = n + 1, time.time()
        while True:
            line = self.ser.readline().decode(errors="replace").strip()
            if not line:
                if time.time() - last > SILENCE_LIMIT:
                    raise RuntimeError(f"no reply for {SILENCE_LIMIT}s after: {cmd}")
                continue
            last = time.time()
            low = line.lower()
            if "T:" in line:
                self.temps = line.replace("ok", "").strip()
            if low.startswith(("resend", "rs:")):
                digits = "".join(ch for ch in line.split(":")[-1] if ch.isdigit())
                nxt = int(digits) if digits else n
            elif low.startswith("ok"):
                return nxt
            elif "kill" in low or "halted" in low or "heating failed" in low or "thermal runaway" in low:
                raise RuntimeError(f"printer error: {line}")

    def run(self, cmds, check_stop=False, on_progress=None):
        """Stream cmds as lines 1..len (renumbered from 0 first)."""
        self.exchange(0, "M110 N0")
        n = 1
        while n <= len(cmds):
            if check_stop and STOP.exists():
                raise KeyboardInterrupt(n)
            n = self.exchange(n, cmds[n - 1])
            if on_progress and n % 200 == 0:
                on_progress(n)
        if on_progress:
            on_progress(len(cmds))


def save(**kw):
    STATE.write_text(json.dumps(kw, indent=1))


def main(path):
    name = pathlib.Path(path).stem
    lines = load(path)
    total, t0 = len(lines), time.time()
    link = Link()
    save(file=name, status="printing", progress=0, started=time.ctime(t0))
    notify("Print started", name, "printer")

    def progress(i):
        save(file=name, status="printing", progress=round(100 * i / total, 1),
             elapsed_min=round((time.time() - t0) / 60, 1), temps=link.temps, started=time.ctime(t0))

    try:
        link.run(lines, check_stop=True, on_progress=progress)
        mins = round((time.time() - t0) / 60)
        save(file=name, status="done", progress=100, minutes=mins)
        notify("Print done", f"{name}: {mins} min", "white_check_mark")
    except KeyboardInterrupt as stop:
        link.run(SAFE_STOP)
        save(file=name, status="cancelled", at_line=stop.args[0] if stop.args else None, of=total)
        notify("Print cancelled", name, "stop_sign")
    except Exception as e:
        try:
            link.run(SAFE_STOP)
        except Exception:
            pass
        save(file=name, status="failed", error=str(e))
        notify("Print FAILED", f"{name}: {e}", "warning")
        raise
    finally:
        STOP.unlink(missing_ok=True)
        link.ser.close()


if __name__ == "__main__":
    main(sys.argv[1])
