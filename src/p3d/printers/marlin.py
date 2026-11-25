"""USB Marlin: driven by sender.py (the streaming engine), not through this interface.

This class only declares the type and its capabilities; start/status/... are not used for Marlin.
"""
from .base import Backend, BackendError


class MarlinBackend(Backend):
    TYPE = "marlin"
    CAPS = {"pause", "gcode", "level", "pid", "probe", "calib", "recover"}
    LAYERS = True

    def _no(self, *_):
        raise BackendError("marlin printers are driven by p3d.sender over USB serial")

    start = status = pause = resume = cancel = ping = _no
