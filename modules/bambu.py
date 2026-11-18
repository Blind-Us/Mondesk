"""Bambu Lab printer over LAN MQTT (passive subscription by default).

Works with Wi-Fi + cloud mode left on; needs printer IP, serial and the LAN
access code shown on the printer. Requires `pip install paho-mqtt`.
"""
import json
import hashlib
import ssl
import subprocess
import threading
import time
from collections import deque

from . import BaseModule

STAGES = {
    "IDLE": "待機", "PREPARE": "準備中", "RUNNING": "列印中", "PAUSE": "已暫停",
    "FINISH": "已完成", "FAILED": "失敗", "SLICING": "切片中",
}


def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v


class Module(BaseModule):
    type = "bambu"
    default_interval = 2

    def __init__(self, spec):
        super().__init__(spec)
        self.report = {}
        self.connected = False
        self.last_msg = 0
        self.err = None
        self.started_at = time.time()
        self.lock = threading.Lock()
        from .printer_assets import Camera
        self.camera = Camera(spec)
        self.preview_image = None
        self.preview_key = None
        self.preview_loaded_key = None
        self.preview_version = ''
        self.preview_retry = 0
        self.preview_busy = False
        self.objects=[]
        self.skip_enabled=False
        self.command_replies={}
        self.command_lock=threading.Lock()
        self.control_enabled = bool(spec.get('control_enabled', False))
        # which print commands the panel may send; anything else is refused
        self.control_actions = set(spec.get('control_actions') or ("pause", "resume", "stop", "skip_objects"))
        self.control_blocked = False
        self.last_command_error = None
        self.diagnostics = deque(maxlen=30)
        self.pending_command = None

    def start(self):
        if not (self.spec.get("ip") and self.spec.get("serial") and self.spec.get("access_code")):
            self.err = "尚未填入 IP、序號和 LAN 存取碼（設定頁 → 列印機）"
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.err = "缺少套件：pip install paho-mqtt"
            return
        serial = self.spec["serial"]
        try:
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:  # paho < 2
            c = mqtt.Client()
        c.username_pw_set("bblp", self.spec["access_code"])
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # printer uses a self-signed cert
        c.tls_set_context(ctx)

        def on_connect(cl, _userdata, _flags, reason, *_extra):
            failed = getattr(reason, "is_failure", None)
            if failed is None:
                failed = reason != 0
            if failed:
                self.connected = False
                self.err = "印表機拒絕登入，請確認 LAN 存取碼與連線權限"
                return
            self.connected, self.err = True, None
            cl.subscribe(f"device/{serial}/report")
            # Passive by default: even query commands can be rejected by firmware.
            if self.spec.get('request_full_status', False):
                cl.publish(f"device/{serial}/request",
                       json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))

        def on_disconnect(*_a):
            self.connected = False

        def on_connect_fail(*_a):
            self.connected = False
            self.err = "無法連到印表機，請確認 IP、電源與同一區域網路"

        def on_message(_cl, _u, msg):
            try:
                payload = json.loads(msg.payload)
            except ValueError:
                return
            self._handle_payload(payload)

        c.on_connect, c.on_disconnect, c.on_message = on_connect, on_disconnect, on_message
        c.on_connect_fail = on_connect_fail
        c.reconnect_delay_set(2, 30)
        c.connect_async(self.spec["ip"], 8883, keepalive=30)
        c.loop_start()
        self.client = c

    def _handle_payload(self, payload):
        if not isinstance(payload, dict):
            return
        with self.lock:
            for section, reply in payload.items():
                if not isinstance(reply, dict):
                    continue
                error = self._reply_error(reply)
                if error:
                    event = {'time': time.time(), 'section': section,
                             'command': str(reply.get('command', ''))[:80],
                             'sequence_id': str(reply.get('sequence_id', ''))[:40],
                             'err_code': reply.get('err_code'), 'message': error}
                    self.diagnostics.append(event)
                    self.last_command_error = event
                    if self._verification_error(reply):
                        self.control_blocked = True
                pending = self.pending_command
                # Some firmware returns sequence 0 for a rejected command.
                if (section == 'print' and pending and reply.get('command') == pending[1]
                        and (str(reply.get('sequence_id')) == pending[0]
                             or error and str(reply.get('sequence_id')) == '0')):
                    self.command_replies[pending[0]] = reply
            report = payload.get('print')
            if isinstance(report, dict) and report.get('command') in (None, 'push_status'):
                deep_merge(self.report, report)
                self.last_msg = time.time()

    @staticmethod
    def _verification_error(reply):
        try:
            code = int(str(reply.get('err_code', 0)), 0)
        except (TypeError, ValueError):
            code = 0
        return 84033543 <= code <= 84033548

    @classmethod
    def _reply_error(cls, reply):
        code = reply.get('err_code')
        if code not in (None, 0, '0', ''):
            if cls._verification_error(reply):
                return f'MQTT 指令驗證失敗（{code}）；已停用面板控制，請使用 Bambu Studio／Handy'
            return f'印表機回報指令錯誤（{str(code)[:40]}）'
        if str(reply.get('result', '')).lower() in ('fail', 'failed', 'error'):
            return '印表機拒絕操作：' + str(reply.get('reason') or reply.get('result'))[:120]
        return None

    def stop(self):
        self.camera.stop()
        c = getattr(self, "client", None)
        if c:
            c.disconnect()
            c.loop_stop()

    @staticmethod
    def _focus_studio():
        """Bring an already-running Bambu Studio to the front. True if one was found."""
        import shutil, sys
        if sys.platform != "win32":
            # X11/XWayland: wmctrl can activate a window by its class
            return bool(shutil.which("wmctrl")) and subprocess.run(
                ["wmctrl", "-x", "-a", "bambu-studio"], capture_output=True).returncode == 0
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        # system code page output (e.g. cp950): the fields we need are ASCII, ignore the rest
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq bambu-studio.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, creationflags=0x08000000).stdout.decode("ascii", "ignore")
        pids = {int(line.split('","')[1]) for line in out.splitlines() if line.lower().startswith('"bambu-studio.exe"')}
        if not pids:
            return False
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # its main window: visible, top-level (no owner) and has a title
            n = user32.GetWindowTextLengthW(hwnd)
            if pid.value in pids and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4) and n:
                title = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, title, n + 1)
                found.append((hwnd, title.value))
            return True
        user32.EnumWindows(each, 0)
        if not found:
            return True  # running but still starting up / no window yet: don't launch another
        # several windows: prefer one with a project open over an empty "未命名 / Untitled" one
        hwnd = min(found, key=lambda w: w[1].startswith(("未命名", "Untitled")))[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Windows only lets the foreground app hand over focus; borrow it by attaching input
        fg = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        me = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(me, fg, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(me, fg, False)
        return True

    def _open_studio(self):
        """Focus Bambu Studio if it is running, otherwise launch it. Never talks to the printer."""
        import os, shutil, sys
        if self._focus_studio():
            return {"opened": True, "focused": True}
        custom = self.spec.get("studio_path")
        # Only ever launch Bambu Studio itself: a changed config must not run other programs.
        if custom and (os.path.basename(custom).lower() not in ("bambu-studio.exe", "bambu-studio", "bambustudio.exe")
                       or not os.path.isfile(custom)):
            raise RuntimeError("studio_path 必須指向 Bambu Studio 主程式（bambu-studio）")
        if sys.platform == "win32":
            candidates = [custom, os.path.join(os.environ.get("ProgramFiles", ""), "Bambu Studio", "bambu-studio.exe"),
                          os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Bambu Studio", "bambu-studio.exe")]
            exe = next((p for p in candidates if p and os.path.isfile(p)), None)
            if not exe:
                raise RuntimeError("找不到 Bambu Studio，請在設定填入 studio_path")
            subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=0x00000008 | 0x00000200)  # detached
        else:
            cmd = [custom] if custom else (["bambu-studio"] if shutil.which("bambu-studio") else
                  ["flatpak", "run", "com.bambulab.BambuStudio"] if shutil.which("flatpak") else None)
            if not cmd:
                raise RuntimeError("找不到 Bambu Studio，請在設定填入 studio_path")
            subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened": True}

    def action(self, name, objects=None, job=None):
        if name == "open_studio":
            return self._open_studio()
        if name == "camera":
            with self.lock: report = dict(self.report)
            self.camera.start(report)
            return {"ready":bool(self.camera.frame), "message":self.camera.error}
        if name not in ("pause", "resume", "stop", "skip_objects"):
            raise ValueError("不支援的操作")
        if name not in self.control_actions:
            raise RuntimeError("這個操作未開放，請在設定中允許")
        if not self.control_enabled or self.control_blocked:
            raise RuntimeError('面板目前僅接收狀態；MQTT 控制尚未驗證相容，請使用 Bambu Studio／Handy 操作')
        with self.lock: stage=self.report.get("gcode_state")
        if not self.connected or time.time()-self.last_msg>30:
            raise RuntimeError("印表機連線中斷，無法送出操作")
        allowed = ("PAUSE",) if name == "resume" else ("RUNNING","PREPARE") if name == "pause" else ("RUNNING","PREPARE","PAUSE")
        if stage not in allowed:
            raise RuntimeError("列印狀態已變更，請重新操作")
        if not self.command_lock.acquire(blocking=False):raise RuntimeError("上一個操作仍在等待印表機回覆")
        try:
            command={"sequence_id":str(time.time_ns()%1000000000),"command":name}
            if name in ('pause', 'resume', 'stop'):
                command['param'] = ''
            if name=="skip_objects":
                if job!=str(abs(hash(self.preview_key))):raise RuntimeError("列印任務已變更，請重新選擇")
                if not self.skip_enabled:raise RuntimeError("此切片未啟用物件標記，無法跳過物件；下次切片需啟用標記物件")
                valid={o['id'] for o in self.objects if not o.get('skipped')}
                if not isinstance(objects,list) or not objects or any(type(x) is not int or x not in valid for x in objects):raise ValueError("請選擇有效物件")
                command['obj_list']=sorted(set(objects)|{o['id'] for o in self.objects if o.get('skipped')}|set(self.report.get('s_obj') or []))
            sequence=command['sequence_id']
            with self.lock:
                self.pending_command = (sequence, name)
            msg=self.client.publish(f"device/{self.spec['serial']}/request",json.dumps({"print":command}),qos=1)
            msg.wait_for_publish(timeout=5)
            if not msg.is_published():raise RuntimeError("指令未送出，請確認連線")
            expected={"pause":{"PAUSE"},"resume":{"RUNNING"},"stop":{"FINISH","FAILED","IDLE"}}.get(name,set())
            for _ in range(24):
                time.sleep(.5)
                with self.lock:
                    reply=self.command_replies.pop(sequence,None)
                    current=self.report.get('gcode_state')
                    skipped=set(self.report.get('s_obj') or [])
                if reply and self._reply_error(reply):
                    raise RuntimeError(self._reply_error(reply))
                if self.control_blocked:
                    raise RuntimeError('印表機回報 MQTT 驗證失敗，已停止控制操作')
                if current in expected or (name=='skip_objects' and set(objects)<=skipped):return {"confirmed":True}
            raise RuntimeError("印表機未確認操作成功，請檢查印表機畫面與區域網路控制權限")
        finally:
            with self.lock:
                self.pending_command = None
                self.command_replies.clear()
            self.command_lock.release()

    def _preview(self,key,report):
        try:
            from .printer_assets import preview
            def received(objects,enabled):
                if key==self.preview_key:self.objects=objects;self.skip_enabled=enabled
            image=preview(self.spec,report,received)
            if image and key == self.preview_key:
                with self.lock:
                    self.preview_image = image
                    self.preview_loaded_key = key
                    self.preview_version = hashlib.sha256(image).hexdigest()[:20]
        except Exception:pass
        finally:self.preview_busy=False

    def stream_frame(self):
        """Latest camera frame for the MJPEG stream; reading it keeps the camera alive."""
        self.camera.last_request=time.time()
        return self.camera.sampled, self.camera.frame

    def asset(self,name):
        if name == "preview" and self.preview_image:return self.preview_image,"image/png"
        if name == "camera":
            self.camera.last_request=time.time()
            # Studio's relay refreshes slowly (often 10-40 s): keep showing the latest frame
            if self.camera.frame and time.time()-self.camera.sampled<120:return self.camera.frame,"image/jpeg"
        return None

    def poll(self):
        with self.lock:
            diagnostics = {'control_enabled': self.control_enabled and not self.control_blocked,
                           'control_actions': sorted(self.control_actions),
                           'command_error': self.last_command_error,
                           'diagnostics': list(self.diagnostics)}
        if self.err:
            return {"_status": "offline", "message": self.err, **diagnostics}
        with self.lock:
            r = dict(self.report)
        if not self.connected or not r:
            elapsed = time.time() - self.started_at
            message = "連線中…" if elapsed < 12 else ("已連線但未收到狀態，請確認序號與印表機區域網路權限" if self.connected else "無法連到印表機，請確認 IP、電源與同一區域網路")
            if self.last_command_error:
                message = self.last_command_error['message']
            return {"_status": "offline", "message": message, **diagnostics}
        key=(r.get("subtask_name"),r.get("gcode_file"),r.get("task_id"))
        if self.preview_key and (not key[0] or key[0] == self.preview_key[0]):
            key = tuple(value if value not in (None, '') else old for value, old in zip(key, self.preview_key))
        if key!=self.preview_key:self.preview_key=key;self.preview_retry=0;self.objects=[];self.skip_enabled=False
        if key[0] and self.preview_loaded_key != key and not self.preview_busy and time.time()>self.preview_retry:
            self.preview_busy=True;self.preview_retry=time.time()+60
            preview_report = {**r, 'subtask_name': key[0], 'gcode_file': key[1], 'task_id': key[2]}
            threading.Thread(target=self._preview,args=(key,preview_report),daemon=True).start()
        stage = r.get("gcode_state", "IDLE")
        remain = r.get("mc_remaining_time")  # minutes
        ams = []
        for unit in (r.get("ams") or {}).get("ams", []):
            for tray in unit.get("tray", []):
                if tray.get("tray_type"):
                    ams.append({"type": tray.get("tray_type"),
                                "color": "#" + (tray.get("tray_color") or "888888FF")[:6]})
        return {
            "_status": "ok" if stage in ("RUNNING", "PREPARE") else "idle",
            "objects":self.objects,
            **diagnostics,
            "print_error": r.get('print_error'),
            "mc_print_error_code": r.get('mc_print_error_code'),
            "hms": r.get('hms') or [],
            "skip_enabled":self.skip_enabled,
            "preview": bool(self.preview_image),
            "preview_version": self.preview_version,
            "job_version": str(abs(hash(self.preview_key))),
            "preview_pending": self.preview_loaded_key != self.preview_key,
            "model": self.spec.get("model", ""),
            "stage": stage,
            "stage_label": STAGES.get(stage, stage),
            "file": r.get("subtask_name") or r.get("gcode_file") or "",
            "progress": r.get("mc_percent"),
            "remaining_min": remain,
            "eta": time.time() + remain * 60 if isinstance(remain, (int, float)) else None,
            "layer": r.get("layer_num"),
            "total_layers": r.get("total_layer_num"),
            "nozzle": r.get("nozzle_temper"),
            "nozzle_target": r.get("nozzle_target_temper"),
            "bed": r.get("bed_temper"),
            "bed_target": r.get("bed_target_temper"),
            "chamber": r.get("chamber_temper"),
            "speed_level": r.get("spd_lvl"),
            "ams": ams,
            "stale": time.time() - self.last_msg > 60,
        }
