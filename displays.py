"""Connected screens, the resolutions each supports, and switching between them.

Windows: EnumDisplayDevices / EnumDisplaySettings / ChangeDisplaySettingsEx (ctypes)
Linux:   `xrandr`
Switching only happens when the user picks a mode on the settings page. The new mode is
applied temporarily and reverted automatically unless the user confirms, like Windows does.
"""
import re
import shutil
import subprocess
import sys
import threading
import uuid

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class DISPLAY_DEVICE(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                    ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                    ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

    class DEVMODE(ctypes.Structure):
        _fields_ = [("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                    ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                    ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                    ("dmPositionX", wintypes.LONG), ("dmPositionY", wintypes.LONG),
                    ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
                    ("dmColor", wintypes.SHORT), ("dmDuplex", wintypes.SHORT),
                    ("dmYResolution", wintypes.SHORT), ("dmTTOption", wintypes.SHORT),
                    ("dmCollate", wintypes.SHORT), ("dmFormName", wintypes.WCHAR * 32),
                    ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
                    ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
                    ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
                    ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
                    ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
                    ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
                    ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]

    user32 = ctypes.windll.user32

CDS_UPDATEREGISTRY, CDS_TEST = 0x1, 0x2
DM_PELSWIDTH, DM_PELSHEIGHT, DM_DISPLAYFREQUENCY = 0x80000, 0x100000, 0x400000
RESULTS = {0: "ok", 1: "需要重新開機才會生效", -1: "顯示卡拒絕這個設定", -2: "這個螢幕不支援此解析度",
           -3: "無法寫入設定", -4: "參數錯誤", -5: "參數錯誤", -6: "參數錯誤"}
_pending = {}
_lock = threading.RLock()


# ---------- listing ----------

def _windows():
    out, i = [], 0
    while True:
        adapter = DISPLAY_DEVICE(cb=ctypes.sizeof(DISPLAY_DEVICE))
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(adapter), 0):
            break
        i += 1
        if not adapter.StateFlags & 0x1:  # not part of the desktop
            continue
        monitor = DISPLAY_DEVICE(cb=ctypes.sizeof(DISPLAY_DEVICE))
        user32.EnumDisplayDevicesW(adapter.DeviceName, 0, ctypes.byref(monitor), 0)
        cur = DEVMODE(dmSize=ctypes.sizeof(DEVMODE))
        if not user32.EnumDisplaySettingsW(adapter.DeviceName, -1, ctypes.byref(cur)) or not cur.dmPelsWidth or not cur.dmPelsHeight:
            continue
        modes, k = {}, 0
        while True:
            dm = DEVMODE(dmSize=ctypes.sizeof(DEVMODE))
            if not user32.EnumDisplaySettingsW(adapter.DeviceName, k, ctypes.byref(dm)):
                break
            k += 1
            modes.setdefault((dm.dmPelsWidth, dm.dmPelsHeight), set()).add(dm.dmDisplayFrequency)
        out.append({
            "name": adapter.DeviceName.replace("\\\\.\\", ""),
            "monitor": monitor.DeviceString or "",
            "primary": bool(adapter.StateFlags & 0x4),
            "current": {"w": cur.dmPelsWidth, "h": cur.dmPelsHeight, "hz": cur.dmDisplayFrequency},
            "modes": [{"w": w, "h": h, "hz": sorted(hz)}
                      for (w, h), hz in sorted(modes.items(), key=lambda x: -x[0][0] * x[0][1])],
        })
    return out


def _linux():
    if not shutil.which("xrandr"):
        return []
    text = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5).stdout
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\S+) connected( primary)?", line)
        if m:
            cur = {"name": m.group(1), "monitor": "", "primary": bool(m.group(2)), "current": None, "modes": []}
            out.append(cur)
            continue
        m = re.match(r"^\s+(\d+)x(\d+)\S*\s+(.*)$", line)
        if cur and m:
            w, h, rest = int(m.group(1)), int(m.group(2)), m.group(3)
            hz = [round(float(x)) for x in re.findall(r"(\d+\.\d+)", rest)]
            cur["modes"].append({"w": w, "h": h, "hz": hz})
            if "*" in rest:
                cur["current"] = {"w": w, "h": h, "hz": hz[0] if hz else None}
        elif not line.startswith(" "):
            cur = None
    return out


def list_displays():
    try:
        return _windows() if sys.platform == "win32" else _linux()
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}"}]


# ---------- switching ----------

def _win_change(name, w, h, flags, hz=None):
    device = "\\\\.\\" + name
    current = DEVMODE(dmSize=ctypes.sizeof(DEVMODE))
    if not user32.EnumDisplaySettingsW(device, -1, ctypes.byref(current)):
        return -4
    candidates, k = [], 0
    while True:
        dm = DEVMODE(dmSize=ctypes.sizeof(DEVMODE))
        if not user32.EnumDisplaySettingsW(device, k, ctypes.byref(dm)):
            break
        k += 1
        if dm.dmPelsWidth == w and dm.dmPelsHeight == h and (hz is None or dm.dmDisplayFrequency == hz):
            candidates.append(dm)
    if not candidates:
        return -2
    mode = min(candidates, key=lambda m: (m.dmBitsPerPel != current.dmBitsPerPel, abs(m.dmDisplayFrequency - current.dmDisplayFrequency)))
    mode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY | 0x40000
    return user32.ChangeDisplaySettingsExW(device, ctypes.byref(mode), None, flags, None)


def _apply(name, mode, save=False, test=False):
    if sys.platform == "win32":
        code = _win_change(name, mode["w"], mode["h"], CDS_TEST if test else CDS_UPDATEREGISTRY if save else 0, mode.get("hz"))
        return {"ok": code == 0, "message": RESULTS.get(code, str(code))}
    if test or save:
        return {"ok": True, "message": "ok"}
    args = ["xrandr", "--output", name, "--mode", f"{mode['w']}x{mode['h']}"]
    if mode.get("hz"):
        args += ["--rate", str(mode["hz"])]
    result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    return {"ok": result.returncode == 0, "message": "ok" if result.returncode == 0 else "顯示服務拒絕切換解析度"}


def _expire(name, change_id):
    with _lock:
        pending = _pending.get(name)
        if not pending or pending["id"] != change_id:
            return
        _pending.pop(name)
        _apply(name, pending["before"])


def set_mode(name, w=0, h=0, step="test", timeout=15, change_id=None):
    """Only switch a supported small secondary screen. An expired trial cannot be kept."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name or "") or step not in {"test", "try", "keep", "revert"}:
        raise ValueError("無效的顯示器或操作")
    with _lock:
        if step in {"keep", "revert"}:
            pending = _pending.get(name)
            if not pending or pending["id"] != change_id:
                return {"ok": False, "message": "試用已到期或已還原，請重新試用解析度。"}
            result = _apply(name, pending["mode"], save=True) if step == "keep" else _apply(name, pending["before"])
            if result["ok"]:
                _pending.pop(name)
                pending["timer"].cancel()
            return result
        w, h = int(w), int(h)
        displays = _windows() if sys.platform == "win32" else _linux()
        display = next((d for d in displays if d.get("name") == name), None)
        if not display or not display.get("current"):
            return {"ok": False, "message": "找不到已連接的小螢幕"}
        if display.get("primary") or not any(m["w"] == 960 and m["h"] == 640 for m in display["modes"]):
            return {"ok": False, "message": "只允許切換支援 960×640 的副螢幕，主螢幕不會變動。"}
        if not any(m["w"] == w and m["h"] == h for m in display["modes"]):
            return {"ok": False, "message": "小螢幕沒有回報支援這個解析度"}
        if name in _pending:
            return {"ok": False, "message": "已有試用中的解析度，請先保留或還原。"}
        mode = {"w": w, "h": h}
        checked = _apply(name, mode, test=True)
        if step == "test" or not checked["ok"]:
            return checked
        applied = _apply(name, mode)
        if not applied["ok"]:
            return applied
        ticket = uuid.uuid4().hex
        timer = threading.Timer(timeout, _expire, args=(name, ticket))
        timer.daemon = True
        _pending[name] = {"id": ticket, "before": dict(display["current"]), "mode": mode, "timer": timer}
        timer.start()
        return {"ok": True, "message": "已試用，15 秒內未保留會還原", "change_id": ticket}


if __name__ == "__main__":
    import json
    print(json.dumps(list_displays(), indent=2, ensure_ascii=False))
