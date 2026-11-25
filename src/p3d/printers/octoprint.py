"""OctoPrint (any printer behind it). Needs printer_api_key."""
import pathlib

from .base import BackendError, HttpBackend, blank_status, multipart


class OctoPrintBackend(HttpBackend):
    TYPE = "octoprint"
    CAPS = {"pause", "gcode"}

    def start(self, path):
        self.check_file(path)
        if not (getattr(self.cfg, "printer_api_key", "") or "").strip():
            raise BackendError("octoprint: set printer_api_key in the config")
        p = pathlib.Path(path)
        ct, body = multipart({"select": "true", "print": "true"}, {"file": (p.name, p.read_bytes())})
        self.post("/api/files/local", body=body, headers={"Content-Type": ct}, timeout=300)

    def status(self):
        job = self.get("/api/job")
        pr = self.get("/api/printer") or {}
        text = (job.get("state") or "").lower()
        prog = job.get("progress") or {}
        comp = prog.get("completion")
        flags = (pr.get("state") or {}).get("flags") or {}
        if flags.get("paused") or flags.get("pausing") or text.startswith("paus"):
            state = "paused"
        elif flags.get("printing") or text in ("printing", "starting", "resuming", "cancelling"):
            state = "printing"
        elif "error" in text or flags.get("error"):
            state = "failed"
        elif comp is not None and comp >= 100:
            state = "done"
        elif text.startswith("operational") or flags.get("operational"):
            state = "cancelled" if (comp or 0) > 0 else "idle"
        else:
            state = "idle"
        temp = pr.get("temperature") or {}
        tool, bed = temp.get("tool0") or {}, temp.get("bed") or {}
        return blank_status(state, progress=None if comp is None else comp / 100.0, nozzle=tool.get("actual"),
                            bed=bed.get("actual"), nozzle_target=tool.get("target"), bed_target=bed.get("target"),
                            elapsed_s=prog.get("printTime"), left_s=prog.get("printTimeLeft"))

    def pause(self):
        self.post("/api/job", json_body={"command": "pause", "action": "pause"})

    def resume(self):
        self.post("/api/job", json_body={"command": "pause", "action": "resume"})

    def cancel(self):
        self.post("/api/job", json_body={"command": "cancel"})

    def gcode(self, cmd):
        self.post("/api/printer/command", json_body={"commands": [cmd]})

    def ping(self):
        return self.get("/api/version")
