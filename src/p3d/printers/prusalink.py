"""PrusaLink (Prusa MK4/MK4S/MK3.9/XL/Mini/Core One). printer_api_key = the PrusaLink API key."""
import pathlib
import urllib.parse

from .base import BackendError, HttpBackend, blank_status

MAP = {"PRINTING": "printing", "PAUSED": "paused", "ATTENTION": "paused", "FINISHED": "done", "STOPPED": "cancelled",
       "ERROR": "failed", "IDLE": "idle", "READY": "idle", "BUSY": "idle"}


class PrusaLinkBackend(HttpBackend):
    TYPE = "prusalink"
    CAPS = {"pause"}
    EXTS = (".gcode", ".bgcode")

    def start(self, path):
        self.check_file(path)
        p = pathlib.Path(path)
        self.req("PUT", "/api/v1/files/usb/" + urllib.parse.quote(p.name), body=p.read_bytes(), timeout=300,
                 headers={"Content-Type": "application/octet-stream", "Print-After-Upload": "?1", "Overwrite": "?1"})

    def status(self):
        s = self.get("/api/v1/status")
        pr, job = s.get("printer") or {}, s.get("job") or {}
        prog = job.get("progress")
        left = job.get("time_remaining")
        return blank_status(MAP.get(str(pr.get("state")).upper(), "idle"), progress=None if prog is None else prog / 100.0,
                            nozzle=pr.get("temp_nozzle"), bed=pr.get("temp_bed"), nozzle_target=pr.get("target_nozzle"),
                            bed_target=pr.get("target_bed"), elapsed_s=job.get("time_printing"),
                            left_s=left if left is not None and left >= 0 else None)

    def job_id(self):
        j = self.get("/api/v1/job", ok404=True)
        if not isinstance(j, dict) or "id" not in j:
            raise BackendError("prusalink: no job is running")
        return j["id"]

    def pause(self):
        self.req("PUT", f"/api/v1/job/{self.job_id()}/pause")

    def resume(self):
        self.req("PUT", f"/api/v1/job/{self.job_id()}/resume")

    def cancel(self):
        self.req("DELETE", f"/api/v1/job/{self.job_id()}")

    def ping(self):
        return self.get("/api/version")
