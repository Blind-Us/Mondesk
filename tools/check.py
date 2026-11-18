"""One command that says whether this copy of Mondesk is healthy.

    check.bat            (Windows)      ./check.sh        (Linux / macOS)
    python tools/check.py [--quick]

1. Python version and the packages Mondesk needs (missing optional ones are only reported)
2. the whole Python test suite
3. the JavaScript tests, if Node.js is installed (set DESKMON_NODE to a node binary otherwise)
4. a demo server is started on a free port and its pages and API are fetched

No account, printer, browser extension or API key is needed, and nothing is written to your
settings. Exit code 0 = everything that could run passed.
"""
import argparse
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [("paho.mqtt.client", "paho-mqtt", "列印機監看")]
OPTIONAL = [("anthropic", "anthropic", "Agent 使用 Claude（固定句子與本機 AI 不需要）"),
            ("imageio_ffmpeg", "imageio-ffmpeg", "列印機機艙直播"),
            ("webview", "pywebview", "桌面視窗版（run-desktop）")]
if sys.platform == "win32":
    # Mondesk falls back to asking PowerShell when this can't load (e.g. Windows' app control
    # policy blocks the DLL, or a brand-new Python has no wheel yet): slower, but it works
    OPTIONAL += [("winrt.windows.media.control", "winrt-Windows.Media.Control",
                  "系統播放資訊改由 PowerShell 讀取，較慢（瀏覽器擴充功能的歌詞與影片不受影響）"),
                 ("pycaw", "pycaw", "音量控制"), ("monitorcontrol", "monitorcontrol", "螢幕亮度")]

results = []


def report(name, ok, detail=""):
    results.append((name, ok))
    mark = {True: "通過", False: "失敗", None: "略過"}[ok]
    print(f"[{mark}] {name}" + (f"：{detail}" if detail else ""), flush=True)


def packages():
    ok = sys.version_info >= (3, 10)
    report("Python 版本", ok, sys.version.split()[0] + ("" if ok else "（需要 3.10 以上）"))
    for module, pip_name, what in REQUIRED:
        try:
            importlib.import_module(module)
            report(f"套件 {pip_name}", True)
        except Exception as e:
            report(f"套件 {pip_name}", False, f"{what}需要它：pip install -r requirements.txt（{type(e).__name__}）")
    for module, pip_name, what in OPTIONAL:
        try:
            importlib.import_module(module)
        except Exception as e:
            blocked = "封鎖" in str(e) or "blocked" in str(e).lower()
            state = "已安裝，但被 Windows 的應用程式控制原則封鎖" if blocked else "沒安裝" if isinstance(e, ModuleNotFoundError) else "無法載入"
            report(f"選用套件 {pip_name}", None, f"{state}；只影響：{what}")


def python_tests():
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test*.py"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [line for line in run.stderr.strip().splitlines() if line.strip()]
    summary = next((line for line in reversed(tail) if line.startswith("Ran ")), "")
    report("Python 測試", run.returncode == 0, summary + ("" if run.returncode == 0 else "\n" + "\n".join(tail[-25:])))


def find_node():
    return os.environ.get("DESKMON_NODE") or shutil.which("node")


def js_tests():
    node = find_node()
    if not node:
        return report("JavaScript 測試", None, "找不到 Node.js（安裝 Node 18 以上，或設定 DESKMON_NODE 指向 node 執行檔）")
    files = sorted(str(p) for p in [*(ROOT / "tests").glob("*.cjs"), *(ROOT / "apple-music-extension").glob("test-*.cjs")])
    run = subprocess.run([node, "--test", *files], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = run.stdout + run.stderr
    count = {key: next((line.split()[-1] for line in out.splitlines() if line.strip().startswith(f"ℹ {key} ")
                        or line.strip().startswith(f"# {key} ")), "?") for key in ("tests", "pass", "fail")}
    detail = f"{count['pass']}/{count['tests']} 項通過"
    if run.returncode:
        detail += "\n" + "\n".join(line for line in out.splitlines() if "✖" in line or "not ok" in line)[:2000]
    report("JavaScript 測試", run.returncode == 0, detail)


def demo_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "server.py", "--demo", "--demo-speed", "10", "--port", str(port)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/state", timeout=1).read()
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError(proc.stderr.read().decode("utf-8", "replace")[-600:])
                time.sleep(0.25)
        else:
            raise RuntimeError("示範伺服器 15 秒內沒有回應")
        for page in ("/", "/settings.html", "/layout.js", "/layouts/focus.json", "/companion/kid/character.json"):
            assert urllib.request.urlopen(base + page, timeout=3).status == 200, page
        time.sleep(2.5)
        state = json.load(urllib.request.urlopen(base + "/api/state", timeout=3))
        bad = [m["id"] for m in state["modules"] if m["status"] in ("error", "starting")]
        assert state["demo"] and not bad, f"模組狀態異常：{bad}"
        types = {m["type"] for m in state["modules"]}
        assert {"bambu", "media", "tokens", "weather", "companion", "clock"} <= types, types
        diag = json.load(urllib.request.urlopen(base + "/api/diagnostics", timeout=3))
        assert diag["app"]["demo"] and diag["media"]["bridge"]
        # writes from another site (no X-DeskMon header) must be refused
        try:
            urllib.request.urlopen(urllib.request.Request(base + "/api/event", data=b'{"name":"timer_done"}'), timeout=3)
            raise AssertionError("沒有 X-DeskMon 標頭的寫入沒有被拒絕")
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code
        req = urllib.request.Request(base + "/api/event", data=b'{"name":"timer_done"}', headers={"X-DeskMon": "1"})
        assert json.load(urllib.request.urlopen(req, timeout=3))["ok"]
        for _ in range(40):  # the Companion (rule brain) says it within a couple of seconds
            events = json.load(urllib.request.urlopen(base + "/api/events", timeout=3))["events"]
            spoken = [e for e in events if e["name"] == "timer_done" and e["outcome"] == "spoken"]
            if spoken:
                break
            time.sleep(0.25)
        assert spoken, "計時結束事件沒有被角色說出來"
        report("示範伺服器", True, f"{len(state['modules'])} 個模組；事件 → 角色台詞「{spoken[0]['line']}」")
    except Exception as e:
        report("示範伺服器", False, f"{type(e).__name__}: {e}")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="skip the demo server")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import urllib.error  # noqa: F401  (used in demo_server)
    packages()
    python_tests()
    js_tests()
    if not args.quick:
        demo_server()
    failed = [name for name, ok in results if ok is False]
    skipped = [name for name, ok in results if ok is None]
    print()
    if failed:
        print("有項目失敗：" + "、".join(failed))
    else:
        print("可以執行的檢查全部通過。" + (f"（略過：{'、'.join(skipped)}）" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
