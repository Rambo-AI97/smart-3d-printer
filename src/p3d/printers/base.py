"""Printer backends: one interface for USB Marlin and network printers (Klipper, OctoPrint, PrusaLink, Bambu LAN).

status() always returns the same dict so netsender can write the same state.json the Marlin sender writes:
  {state: printing|paused|done|failed|cancelled|idle, progress 0-1 or None, layer, nozzle, bed, nozzle_target,
   bed_target, elapsed_s, left_s}      (unknown values are None)
"""
import json
import urllib.error
import urllib.request
import uuid

TIMEOUT = 15
CAP_NAMES = {"pause", "gcode", "level", "pid", "probe", "calib", "recover"}
STATES = ("printing", "paused", "done", "failed", "cancelled", "idle")


class BackendError(Exception):
    """Printer unreachable or refused: the message is one readable line."""


def blank_status(state="idle", **kw):
    s = dict(state=state, progress=None, layer=None, nozzle=None, bed=None, nozzle_target=None, bed_target=None,
             elapsed_s=None, left_s=None)
    s.update(kw)
    return s


def multipart(fields, files):
    """Hand-made multipart/form-data. fields {name: str}, files {name: (filename, bytes)}. Returns (content_type, body)."""
    b = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (fn, data) in files.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                   "Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return f"multipart/form-data; boundary={b}", b"".join(out)


class Backend:
    TYPE = "base"
    CAPS = set()
    LAYERS = False          # status() reports the layer, so --pause-at-layer works
    EXTS = (".gcode",)      # file types start() accepts

    def __init__(self, config):
        self.cfg = config

    # ---- to implement ----
    def start(self, path):
        raise NotImplementedError

    def status(self):
        raise NotImplementedError

    def pause(self):
        raise NotImplementedError

    def resume(self):
        raise NotImplementedError

    def cancel(self):
        raise NotImplementedError

    def gcode(self, cmd):
        raise BackendError(f"sending G-code is not supported for {self.TYPE} printers")

    def ping(self):
        """Doctor check: raise BackendError if the printer does not answer."""
        raise NotImplementedError

    def close(self):
        pass

    # ---- shared ----
    def check_file(self, path):
        p = str(path)
        if not p.lower().endswith(self.EXTS):
            raise BackendError(f"{self.TYPE} printers need {' or '.join(self.EXTS)} files, got {p.rsplit('/', 1)[-1]}")


class HttpBackend(Backend):
    """Shared JSON-over-HTTP plumbing. Subclasses set auth headers in headers()."""

    def base(self):
        u = (getattr(self.cfg, "printer_url", "") or "").strip().rstrip("/")
        if not u:
            raise BackendError(f"set printer_url in the config for {self.TYPE} printers")
        if "://" not in u:
            u = "http://" + u
        return u

    def headers(self):
        k = getattr(self.cfg, "printer_api_key", "") or ""
        return {"X-Api-Key": k} if k else {}

    def req(self, method, path, body=None, headers=None, json_body=None, raw=False, timeout=TIMEOUT, ok404=False):
        url = self.base() + path
        h = dict(self.headers())
        if json_body is not None:
            body = json.dumps(json_body).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        r = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                data = resp.read()
                code = resp.status
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise BackendError(f"{self.TYPE}: access denied ({e.code}), check printer_api_key") from None
            if e.code == 404 and ok404:
                return None
            detail = ""
            try:
                detail = e.read(200).decode(errors="replace").strip().replace("\n", " ")
            except Exception:
                pass
            raise BackendError(f"{self.TYPE}: {method} {path} -> HTTP {e.code} {detail}".strip()) from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            why = getattr(e, "reason", e)
            raise BackendError(f"{self.TYPE}: cannot reach {self.base()} ({why})") from None
        if raw or not data or code == 204:
            return data
        try:
            return json.loads(data)
        except ValueError:
            return data

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, **kw):
        return self.req("POST", path, **kw)
