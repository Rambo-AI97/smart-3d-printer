"""Printer backends. get_backend(config) picks one by config `printer_type` (default "marlin")."""
import importlib

from .base import Backend, BackendError

TYPES = {"marlin": ("marlin", "MarlinBackend"), "klipper": ("klipper", "KlipperBackend"),
         "octoprint": ("octoprint", "OctoPrintBackend"), "prusalink": ("prusalink", "PrusaLinkBackend"),
         "bambu": ("bambu", "BambuBackend")}

__all__ = ["Backend", "BackendError", "TYPES", "get_backend", "printer_type", "caps_for", "require"]


def printer_type(config=None):
    from .. import config as cfgmod
    t = str(getattr(config or cfgmod.get(), "printer_type", "") or "marlin").strip().lower()
    if t not in TYPES:
        raise BackendError(f"unknown printer_type '{t}' (use {', '.join(TYPES)})")
    return t


def backend_class(t):
    mod, cls = TYPES[t]
    return getattr(importlib.import_module(f".{mod}", __name__), cls)


def get_backend(config=None):
    from .. import config as cfgmod
    config = config or cfgmod.get()
    return backend_class(printer_type(config))(config)


def caps_for(config=None):
    return sorted(backend_class(printer_type(config)).CAPS)


def caps_for_type(t):
    return sorted(backend_class(t).CAPS)


def require(cap, config=None):
    """SystemExit with a clear message when the configured printer type lacks `cap` (level, pid, probe, calib, recover)."""
    try:
        t = printer_type(config)
    except BackendError as e:
        raise SystemExit(str(e)) from None
    if cap not in backend_class(t).CAPS:
        raise SystemExit(f"not available for {t} printers (needs a USB Marlin connection)")
