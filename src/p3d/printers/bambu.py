"""Bambu Lab (X1/P1/A1/H2D) in LAN mode: implicit FTPS upload (port 990), MQTT over TLS (port 8883).

printer_url = the printer's IP or host name, bambu_serial, bambu_access_code (both on the printer's screen).
Needs a sliced .gcode.3mf. paho-mqtt is imported lazily: pip install 'p3d[bambu]'.
"""
import ftplib
import json
import pathlib
import socket
import ssl
import threading
import time

from .base import Backend, BackendError, blank_status

FTP_PORT, MQTT_PORT = 990, 8883
MAP = {"RUNNING": "printing", "PREPARE": "printing", "SLICING": "printing", "PAUSE": "paused", "FINISH": "done",
       "FAILED": "failed", "IDLE": "idle"}


class ImplicitFTPS(ftplib.FTP_TLS):
    """FTP over TLS from the first byte (port 990): wrap the control socket at connect, reuse the TLS session for data."""

    def connect(self, host="", port=0, timeout=-999, source_address=None):
        if host:
            self.host = host
        if port:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        self.sock = socket.create_connection((self.host, self.port), self.timeout, source_address=source_address)
        self.af = self.sock.family
        self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE   # the printer has a self-signed certificate
    return c


class BambuBackend(Backend):
    TYPE = "bambu"
    CAPS = {"pause", "gcode"}
    LAYERS = True
    EXTS = (".3mf",)

    def __init__(self, config):
        super().__init__(config)
        self.client = None
        self.report = {}
        self.got = threading.Event()
        self.connected = threading.Event()

    # ---- settings ----
    def host(self):
        h = (getattr(self.cfg, "printer_url", "") or "").strip()
        h = h.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        if not h:
            raise BackendError("set printer_url (the printer's IP) in the config for bambu printers")
        return h

    def serial(self):
        s = (getattr(self.cfg, "bambu_serial", "") or "").strip()
        if not s:
            raise BackendError("set bambu_serial in the config")
        return s

    def code(self):
        c = (getattr(self.cfg, "bambu_access_code", "") or "").strip()
        if not c:
            raise BackendError("set bambu_access_code in the config")
        return c

    # ---- upload ----
    def upload(self, path):
        p = pathlib.Path(path)
        ftp = ImplicitFTPS(context=_ctx())
        try:
            ftp.connect(self.host(), FTP_PORT, timeout=30)
            ftp.login("bblp", self.code())
            ftp.prot_p()
            with open(p, "rb") as f:
                ftp.storbinary(f"STOR {p.name}", f)
        except (OSError, ftplib.Error) as e:
            raise BackendError(f"bambu: FTPS upload to {self.host()}:{FTP_PORT} failed ({e})") from None
        finally:
            try:
                ftp.close()
            except Exception:
                pass

    # ---- mqtt ----
    def _paho(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise BackendError("install the bambu extra: pip install 'p3d[bambu]'") from None
        return mqtt

    def connect(self):
        if self.client is not None:
            return
        mqtt = self._paho()
        serial = self.serial()
        cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"p3d-{int(time.time())}")
        cl.username_pw_set("bblp", self.code())
        cl.tls_set_context(_ctx())
        cl.on_connect = lambda c, u, f, rc, *a: (c.subscribe(f"device/{serial}/report"), self.connected.set(),
                                                 self._push(c))
        cl.on_message = self._on_message
        try:
            cl.connect(self.host(), MQTT_PORT, keepalive=60)
        except OSError as e:
            raise BackendError(f"bambu: cannot reach {self.host()}:{MQTT_PORT} ({e})") from None
        cl.loop_start()
        self.client = cl
        if not self.connected.wait(15):
            self.close()
            raise BackendError(f"bambu: no MQTT answer from {self.host()}:{MQTT_PORT}, check bambu_access_code")

    def _push(self, c=None):
        (c or self.client).publish(f"device/{self.serial()}/request",
                                   json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

    def _on_message(self, _c, _u, msg):
        try:
            d = json.loads(msg.payload)
        except ValueError:
            return
        if isinstance(d.get("print"), dict):
            self.report.update(d["print"])
            self.got.set()

    def _send(self, body):
        self.connect()
        info = self.client.publish(f"device/{self.serial()}/request", json.dumps(body))
        try:
            info.wait_for_publish(10)
        except Exception:
            pass

    def close(self):
        cl, self.client = self.client, None
        self.connected.clear()
        if cl is not None:
            try:
                cl.loop_stop()
                cl.disconnect()
            except Exception:
                pass

    # ---- interface ----
    def start(self, path):
        p = pathlib.Path(path)
        if p.suffix.lower() == ".gcode":
            raise BackendError("bambu printers need a sliced .gcode.3mf (plain .gcode cannot be started over LAN); "
                               "slice for the Bambu machine so the job contains a .3mf")
        self.check_file(path)
        self._paho()   # fail early, before the upload
        self.upload(p)
        self.connect()
        self.report.clear()
        self.got.clear()
        self._send({"print": {"sequence_id": "0", "command": "project_file", "param": "Metadata/plate_1.gcode",
                              "project_id": "0", "profile_id": "0", "task_id": "0", "subtask_id": "0",
                              "subtask_name": p.stem, "url": f"ftp:///{p.name}", "bed_type": "auto", "timelapse": False,
                              "bed_leveling": True, "flow_cali": True, "vibration_cali": True, "layer_inspect": False,
                              "use_ams": False}})

    def status(self):
        self.connect()
        if not self.report:
            self.got.wait(10)
            if not self.report:
                self._push()
                self.got.wait(5)
        r = self.report
        if not r:
            raise BackendError("bambu: no status report from the printer")
        pct, left = r.get("mc_percent"), r.get("mc_remaining_time")
        return blank_status(MAP.get(str(r.get("gcode_state")).upper(), "idle"),
                            progress=None if pct is None else pct / 100.0, layer=r.get("layer_num"),
                            nozzle=r.get("nozzle_temper"), bed=r.get("bed_temper"), nozzle_target=r.get("nozzle_target_temper"),
                            bed_target=r.get("bed_target_temper"), left_s=None if left is None else left * 60)

    def pause(self):
        self._send({"print": {"command": "pause", "sequence_id": "0"}})

    def resume(self):
        self._send({"print": {"command": "resume", "sequence_id": "0"}})

    def cancel(self):
        self._send({"print": {"command": "stop", "sequence_id": "0"}})

    def gcode(self, cmd):
        self._send({"print": {"command": "gcode_line", "param": cmd + "\n", "sequence_id": "0"}})

    def ping(self):
        for port in (FTP_PORT, MQTT_PORT):
            try:
                socket.create_connection((self.host(), port), timeout=5).close()
            except OSError as e:
                raise BackendError(f"bambu: {self.host()}:{port} not reachable ({e})") from None
