"""Klipper via the Moonraker HTTP API (Voron, Creality K1/K2, Sovol, Elegoo Neptune 4, Qidi, ...)."""
import pathlib
import urllib.parse

from .base import HttpBackend, blank_status, multipart

QUERY = "print_stats&virtual_sdcard&extruder&heater_bed&display_status"
MAP = {"printing": "printing", "paused": "paused", "complete": "done", "cancelled": "cancelled", "error": "failed",
       "standby": "idle"}


class KlipperBackend(HttpBackend):
    TYPE = "klipper"
    CAPS = {"pause", "gcode"}
    LAYERS = True

    def start(self, path):
        self.check_file(path)
        p = pathlib.Path(path)
        ct, body = multipart({"print": "true", "root": "gcodes"}, {"file": (p.name, p.read_bytes())})
        self.post("/server/files/upload", body=body, headers={"Content-Type": ct}, timeout=300)

    def status(self):
        r = self.get("/printer/objects/query?" + QUERY)
        st = (r.get("result") or {}).get("status") or {}
        ps, sd = st.get("print_stats") or {}, st.get("virtual_sdcard") or {}
        ex, hb = st.get("extruder") or {}, st.get("heater_bed") or {}
        prog = sd.get("progress")
        elapsed = ps.get("print_duration")
        left = None
        if prog and prog > 0.02 and elapsed:
            left = max(elapsed / prog - elapsed, 0)
        layer = (ps.get("info") or {}).get("current_layer")
        return blank_status(MAP.get(ps.get("state"), "idle"), progress=prog, layer=layer, nozzle=ex.get("temperature"),
                            bed=hb.get("temperature"), nozzle_target=ex.get("target"), bed_target=hb.get("target"),
                            elapsed_s=elapsed, left_s=left)

    def pause(self):
        self.post("/printer/print/pause")

    def resume(self):
        self.post("/printer/print/resume")

    def cancel(self):
        self.post("/printer/print/cancel")

    def gcode(self, cmd):
        self.post("/printer/gcode/script?" + urllib.parse.urlencode({"script": cmd}))

    def ping(self):
        return self.get("/server/info")
