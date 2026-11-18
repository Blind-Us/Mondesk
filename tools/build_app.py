"""Builds the Mondesk application for the system this runs on: a folder with everything inside (Python,
every package, the modules, the pages, ffmpeg, the browser-extension template), then a zip of it.
Whoever downloads it unpacks and double-clicks; nothing to install, nothing to type.

    python tools/build_app.py          ->  dist/Mondesk-windows.zip   (on Windows)
                                           dist/Mondesk-linux.tar.gz  (on Linux)

Windows: its own window (WebView2, part of Windows 10/11).
Linux:   no web view is bundled (it depends on each distribution's GTK/WebKit); the panel opens in the
         default browser instead.
One system cannot build the other's package; .github/workflows/release.yml builds both.
Needs: pip install -r requirements-desktop.txt pyinstaller
"""
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = sys.platform == "win32"
NAME = "Mondesk"


def stage_extension(folder):
    """The extension as it ships: no tests, and never a config.js (that holds one user's pairing key)."""
    target = folder / "apple-music-extension"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for source in (ROOT / "apple-music-extension").iterdir():
        if source.is_file() and source.name != "config.js" and source.suffix != ".cjs":
            shutil.copyfile(source, target / source.name)
    shutil.copytree(ROOT / "apple-music-extension" / "icons", target / "icons")
    return target


def build():
    import PyInstaller.__main__
    from PyInstaller.utils.hooks import collect_submodules
    work, dist = ROOT / "build", ROOT / "dist"
    stage = work / "stage"
    shutil.rmtree(dist / NAME, ignore_errors=True)
    extension = stage_extension(stage)
    sep = ";" if WINDOWS else ":"
    data = [(ROOT / "web", "web"), (extension, "apple-music-extension"), (ROOT / "assets", "assets"),
            (ROOT / "config.example.json", "."), (ROOT / "LICENSE", ".")]
    # modules are loaded by name from the settings (importlib), so PyInstaller cannot see them by itself
    hidden = collect_submodules("modules") + ["displays", "user_paths", "paho.mqtt.client"]
    if WINDOWS:
        hidden += ["winrt.windows.media.control", "winrt.windows.foundation", "winrt.windows.foundation.collections",
                   "winrt.windows.storage.streams", "pycaw.pycaw", "comtypes.stream", "monitorcontrol"]
    args = [str(ROOT / "desktop.py"), "--name", NAME, "--noconfirm", "--clean", "--windowed",
            "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
            "--icon", str(ROOT / "assets" / ("mondesk.ico" if WINDOWS else "mondesk.png")),
            "--collect-data", "imageio_ffmpeg", "--collect-submodules", "anthropic",
            "--exclude-module", "tkinter", "--exclude-module", "PIL", "--exclude-module", "PyInstaller"]
    if not WINDOWS:
        args += ["--exclude-module", "webview"]
    for source, target in data:
        args += ["--add-data", f"{source}{sep}{target}"]
    for name in hidden:
        args += ["--hidden-import", name]
    PyInstaller.__main__.run(args)

    folder = dist / NAME
    exe = folder / (NAME + ".exe" if WINDOWS else NAME)
    # a demo anyone can start with a double click: scripted data, no printer or account needed
    if WINDOWS:
        (folder / "Mondesk 示範模式.bat").write_text('@echo off\r\nstart "" "%~dp0Mondesk.exe" --demo\r\n', encoding="utf-8")
    else:
        demo = folder / "mondesk-demo.sh"
        demo.write_text('#!/bin/sh\nexec "$(dirname "$0")/Mondesk" --demo\n', encoding="utf-8")
        demo.chmod(0o755)
    (folder / "README.txt").write_text(README_WINDOWS if WINDOWS else README_LINUX, encoding="utf-8")

    # the packaged program must really start: every module, the pages, the icon, the extension template
    report = work / "self-test.json"
    report.unlink(missing_ok=True)
    try:
        subprocess.run([str(exe), "--self-test", str(report)], check=True, timeout=180)
    except OSError as error:
        # Windows "Smart App Control" refuses programs without a signature, on the machine that built them too.
        # The package is still made; it just could not be tried here (the release workflow tries it on GitHub).
        if getattr(error, "winerror", None) != 4551:
            raise
        result = {"untested": "this computer's application control policy blocks unsigned programs"}
    else:
        result = json.loads(report.read_text(encoding="utf-8"))
        bad = [k for k, v in result.items() if k != "window" and v in (False, None, 0)] + [k for k in ("web", "settings", "icon") if result.get(k) != 200]
        if bad or (WINDOWS and not result.get("window")):
            raise SystemExit(f"packaged program failed its self-test: {result}")

    if WINDOWS:
        archive = dist / "Mondesk-windows.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    z.write(path, f"{NAME}/{path.relative_to(folder).as_posix()}")
    else:
        archive = dist / "Mondesk-linux.tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            t.add(folder, arcname=NAME)
    return archive, result


README_WINDOWS = """Mondesk

開啟：點兩下 Mondesk.exe
先看看長什麼樣子：點兩下「Mondesk 示範模式.bat」（全部是示範資料，不需要列印機或帳號，也不會存檔）

設定：面板左上角的齒輪。每張卡片右上角的小齒輪只開那張卡的設定。
開機自動啟動、全螢幕：設定頁的「應用程式」。
Apple Music 歌詞、YouTube／B 站影片：需要瀏覽器擴充功能，設定頁「正在播放」裡有一步一步的安裝說明。

你的設定存在 %LOCALAPPDATA%\\DeskMon，不在這個資料夾裡；更新時直接換掉整個資料夾即可。
第一次開啟時 Windows 可能顯示「Windows 已保護您的電腦」：這個程式沒有購買簽章，按「其他資訊」→「仍要執行」。
如果顯示的是「智慧型應用程式控制已封鎖」，那台電腦不允許任何沒有簽章的程式，請改用原始碼版（GitHub 頁面有說明）。
"""

README_LINUX = """Mondesk

Start:      ./Mondesk          (opens the panel in your browser; keep it running)
Demo first: ./mondesk-demo.sh  (scripted data: no printer or account needed, nothing is saved)

Settings: the gear at the top left of the panel.
Your settings live in ~/.config/DeskMon, not in this folder.
The volume card and "now playing" from the system need Windows; everything else works the same.
"""


if __name__ == "__main__":
    archive, result = build()
    print(f"{archive}  ({archive.stat().st_size / 1e6:.0f} MB)  self-test: {result}")
