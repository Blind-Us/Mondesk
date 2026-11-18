"""Builds the Mondesk application for the system this runs on: a folder with everything inside (Python,
every package, the modules, the pages, ffmpeg, the browser-extension template), then a zip of it.
Whoever downloads it unpacks and double-clicks; nothing to install, nothing to type.

Windows: not a PyInstaller .exe. Windows' "Smart App Control" refuses unsigned programs, and a
PyInstaller .exe is one. So the package carries the official embeddable Python from python.org
(python.exe / pythonw.exe are signed by the Python Software Foundation), the packages and our code,
and Mondesk.bat starts pythonw.exe with desktop.py: no console, nothing unsigned to start.

    python tools/build_app.py          ->  dist/Mondesk-windows.zip   (on Windows)
                                           dist/Mondesk-linux.tar.gz  (on Linux)

Windows: its own window (WebView2, part of Windows 10/11).
Linux:   no web view is bundled (it depends on each distribution's GTK/WebKit); the panel opens in the
         default browser instead.
One system cannot build the other's package; .github/workflows/release.yml builds both.
Needs: pip install -r requirements-desktop.txt pyinstaller
"""
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
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


# what the Windows package runs from source: the program, the pages, the pictures
APP_FILES = ["desktop.py", "server.py", "displays.py", "user_paths.py", "config.example.json", "LICENSE"]
APP_FOLDERS = ["modules", "web", "assets"]
DOTNET_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true"/>
  </runtime>
</configuration>
"""


def embeddable_python(work):
    """python.org's embeddable Python of the same version as the one running this build (so the
    wheels pip picks for this Python fit it), unpacked once into the build folder."""
    version = platform.python_version()
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
    name = f"python-{version}-embed-{arch}.zip"
    archive = work / name
    if not archive.exists():
        work.mkdir(parents=True, exist_ok=True)
        url = f"https://www.python.org/ftp/python/{version}/{name}"
        print("downloading", url, flush=True)
        with urllib.request.urlopen(url, timeout=120) as reply, open(archive, "wb") as out:
            shutil.copyfileobj(reply, out)
    return archive


def build_windows():
    """Mondesk/
         Mondesk.exe, Mondesk 示範模式.exe   Python's signed pythonw.exe under our name (tools/mondesk_launch.py)
         python3xx.dll, python3xx.zip, ...   the rest of the embeddable Python, which Mondesk.exe needs beside it
         runtime/                            Python's extension modules (.pyd) and their DLLs
         Lib/site-packages/                  the packages
         app/                                Mondesk itself
    No .bat: Smart App Control refuses scripts downloaded from the web."""
    work, dist = ROOT / "build", ROOT / "dist"
    folder = dist / NAME
    shutil.rmtree(folder, ignore_errors=True)
    app, runtime = folder / "app", folder / "runtime"
    with zipfile.ZipFile(embeddable_python(work)) as z:
        z.extractall(folder)
    # keep the top folder short: only what the .exe must have beside it stays there
    runtime.mkdir()
    for path in list(folder.iterdir()):
        if path.suffix == ".pyd" or path.name.startswith(("libcrypto", "libssl", "libffi", "libtommath", "sqlite3", "LICENSE", "build-details")):
            shutil.move(path, runtime / path.name)
    pythonw = folder / "pythonw.exe"
    for name in ("Mondesk.exe", "Mondesk 示範模式.exe"):
        shutil.copyfile(pythonw, folder / name)
        # .NET (the window, through pywebview) refuses DLLs marked "downloaded from the internet" unless the
        # program says these are its own: every file of a downloaded zip carries that mark
        (folder / f"{name}.config").write_text(DOTNET_CONFIG, encoding="utf-8")
    for name in ("pythonw.exe", "python.exe"):   # nothing to click by mistake: Mondesk.exe is the way in
        (folder / name).unlink()
    # the embeddable Python only looks where its ._pth file says: its library, its modules, the packages, Mondesk
    pth = next(folder.glob("python*._pth"))
    stdlib = [line for line in pth.read_text(encoding="utf-8").splitlines() if line.strip().endswith(".zip")]
    pth.write_text("\n".join(stdlib + ["runtime", r"Lib\site-packages", "app", "import site"]) + "\n", encoding="utf-8")
    packages = folder / "Lib" / "site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-warn-script-location",
                    "--target", str(packages), "-r", str(ROOT / "requirements-desktop.txt")], check=True)
    shutil.rmtree(packages / "bin", ignore_errors=True)   # the packages' console scripts: never used
    shutil.copyfile(ROOT / "tools" / "mondesk_launch.py", packages / "mondesk_launch.py")
    (packages / "mondesk-launch.pth").write_text("import mondesk_launch\n", encoding="utf-8")
    app.mkdir()
    for name in APP_FILES:
        shutil.copyfile(ROOT / name, app / name)
    skip = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in APP_FOLDERS:
        shutil.copytree(ROOT / name, app / name, ignore=skip)
    stage_extension(app)
    (folder / "README.txt").write_text(README_WINDOWS, encoding="utf-8")

    # the package must really start, the way a double click starts it: Mondesk.exe with nothing after it
    report = work / "self-test.json"
    report.unlink(missing_ok=True)
    env = {**__import__("os").environ, "MONDESK_SELF_TEST": str(report)}
    subprocess.run([str(folder / "Mondesk.exe")], env=env, check=True, timeout=180)
    result = json.loads(report.read_text(encoding="utf-8"))
    bad = [k for k, v in result.items() if v in (False, None, 0)] + [k for k in ("web", "settings", "icon") if result.get(k) != 200]
    if bad:
        raise SystemExit(f"packaged program failed its self-test: {result}")
    for path in folder.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)

    archive = dist / "Mondesk-windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, f"{NAME}/{path.relative_to(folder).as_posix()}")
    return archive, result


def build():
    if WINDOWS:
        return build_windows()
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
先看看長什麼樣子：點兩下「Mondesk 示範模式.exe」（全部是示範資料，不需要列印機或帳號，也不會存檔）
不用另外安裝 Python：這個資料夾裡就是 Python 官方的免安裝版，Mondesk.exe 是改了名字的 pythonw.exe（保留 Python 官方的數位簽章）。

設定：面板左上角的齒輪。每張卡片右上角的小齒輪只開那張卡的設定。
開機自動啟動、全螢幕：設定頁的「應用程式」。
Apple Music 歌詞、YouTube／B 站影片：需要瀏覽器擴充功能，設定頁「正在播放」裡有一步一步的安裝說明。

你的設定存在 %LOCALAPPDATA%\\DeskMon，不在這個資料夾裡；更新時直接換掉整個資料夾即可。
解壓縮後請整個資料夾一起保留，不要只拿出 Mondesk.exe。
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
