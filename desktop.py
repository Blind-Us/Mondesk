"""Mondesk as an application: its own window instead of a browser tab, the server inside.

  * Started twice, the second one only brings the first one's window forward.
  * The window opens where it was closed: same screen, place, size, full screen or not.
  * "Start with the computer" is a switch on the settings page (see Shell.set).
  * --demo   every data source scripted: no printer, account, extension or key needed.
  * --browser (and Linux packages, which cannot carry a web view for every distribution):
    no window of its own; the panel opens in the default browser.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer

import server
from user_paths import ensure_user_config, user_config_path, user_data_dir

APP = 'Mondesk'
FROZEN = bool(getattr(sys, 'frozen', False))


def clean_child_environment(environ=os.environ, frozen=FROZEN, platform=sys.platform):
    """The Linux package's launcher points LD_LIBRARY_PATH at its own folder so this program finds the
    libraries it carries. Every program Mondesk starts (the browser through xdg-open, playerctl, pactl,
    brightnessctl, xrandr, Bambu Studio) would inherit it and load our copies of libssl, libz, ... instead
    of the system's own, which can crash them. The libraries are already loaded by now, so the variable
    goes back to what it was before the launcher touched it."""
    if not (frozen and platform.startswith('linux')):
        return
    for key in ('LD_LIBRARY_PATH',):
        original = environ.pop(key + '_ORIG', None)
        if original is not None:
            environ[key] = original
        else:
            environ.pop(key, None)


clean_child_environment()
ICON = server.ROOT / 'assets' / ('mondesk.ico' if sys.platform == 'win32' else 'mondesk.png')


def launch_command(extra=()):
    """How this program is started again (packaged: the executable; from source: python + this file)."""
    if FROZEN:
        return [sys.executable, *extra]
    python = Path(sys.executable)
    if python.stem.lower() == 'mondesk':
        # the Windows package: Mondesk.exe is Python's own signed pythonw.exe, renamed; started with nothing
        # after it, it runs Mondesk by itself (see tools/build_app.py, mondesk_launch.py)
        return [str(python), *extra] if not extra else [str(python), str(Path(__file__).resolve()), *extra]
    windowless = python.with_name('pythonw.exe')
    return [str(windowless if windowless.exists() else python), str(Path(__file__).resolve()), *extra]


# ---- start with the computer: only ever changed by the switch on the settings page ----
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
LINUX_ENTRY = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'autostart' / 'mondesk.desktop'


def autostart_supported():
    return sys.platform == 'win32' or sys.platform.startswith('linux')


def autostart_enabled():
    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return bool(winreg.QueryValueEx(key, APP)[0])
        except OSError:
            return False
    return LINUX_ENTRY.is_file()


def set_autostart(on):
    command = launch_command()
    if sys.platform == 'win32':
        import subprocess, winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try: winreg.DeleteValue(key, APP)
                except FileNotFoundError: pass
    elif sys.platform.startswith('linux'):
        if on:
            import shlex
            LINUX_ENTRY.parent.mkdir(parents=True, exist_ok=True)
            LINUX_ENTRY.write_text('[Desktop Entry]\nType=Application\nName=Mondesk\n'
                                   f'Exec={" ".join(shlex.quote(c) for c in command)}\nIcon={ICON}\nX-GNOME-Autostart-enabled=true\n', encoding='utf-8')
        else:
            LINUX_ENTRY.unlink(missing_ok=True)
    else:
        raise RuntimeError('這個系統不支援開機自動啟動')
    return autostart_enabled()


# ---- where the window was: remembered beside the settings ----
def window_file():
    return user_data_dir() / 'window.json'


def load_window():
    try:
        saved = json.loads(window_file().read_text(encoding='utf-8'))
        w, h = int(saved['width']), int(saved['height'])
        if not (320 <= w <= 10000 and 240 <= h <= 10000):
            raise ValueError
        return {'x': int(saved['x']), 'y': int(saved['y']), 'width': w, 'height': h, 'fullscreen': bool(saved.get('fullscreen'))}
    except (OSError, ValueError, KeyError, TypeError):
        return {'x': None, 'y': None, 'width': 960, 'height': 680, 'fullscreen': False}


class Shell:
    """What the pages may ask of the application (server.py: /api/desktop)."""

    def __init__(self, window=None, opener=None):
        self.window, self.opener = window, opener
        self.place = load_window()
        self.fullscreen = self.place['fullscreen']

    def state(self):
        return {'app': True, 'window': self.window is not None, 'fullscreen': self.fullscreen,
                'autostart': autostart_enabled(), 'autostart_supported': autostart_supported(), 'packaged': FROZEN}

    def set(self, request):
        if 'autostart' in request:
            set_autostart(bool(request['autostart']))
        if 'fullscreen' in request and self.window is not None and bool(request['fullscreen']) != self.fullscreen:
            self.window.toggle_fullscreen()
            self.fullscreen = not self.fullscreen
            self.remember()
        if request.get('action') == 'show':
            self.show()
        return self.state()

    def show(self):
        if self.window is None:
            if self.opener: self.opener()
            return
        try:
            self.window.restore(); self.window.show()
            if sys.platform == 'win32':   # Windows keeps a background program from taking the front: ask for it
                import ctypes
                handle = ctypes.windll.user32.FindWindowW(None, APP)
                if handle: ctypes.windll.user32.SetForegroundWindow(handle)
        except Exception:
            pass

    def remember(self, *_):
        """Called when the window moves, changes size or closes."""
        w = self.window
        if w is None:
            return
        try:
            if not self.fullscreen and w.width and w.height and w.width >= 320 and w.height >= 240:
                self.place.update(x=w.x, y=w.y, width=w.width, height=w.height)   # full screen keeps the place to return to
            window_file().write_text(json.dumps({**self.place, 'fullscreen': self.fullscreen}), encoding='utf-8')
        except Exception:
            pass


def already_running(port):
    """Ask a Mondesk on this port to come forward. True when one answered."""
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/desktop', data=b'{"action": "show"}',
                                         headers={'Content-Type': 'application/json', 'X-DeskMon': '1'})
        with urllib.request.urlopen(request, timeout=2) as response:
            return bool(json.loads(response.read()).get('app'))
    except Exception:
        return False


def self_test(output):
    import modules.bambu, modules.media, modules.media_seek, modules.tokens, modules.clock, modules.weather, modules.system, modules.companion
    import paho.mqtt.client
    window = True
    try: import webview
    except Exception: window = False     # Linux packages run in the browser
    app = server.App(demo=1.0)
    app.desktop = Shell()
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(app))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{http.server_port}'
    get = lambda path: urllib.request.urlopen(url + path, timeout=10)
    result = {'mqtt': True, 'window': window, 'modules': len(app.hub.modules), 'web': get('/').status, 'settings': get('/settings.html').status,
              'icon': get('/icon.svg').status, 'desktop': json.loads(get('/api/desktop').read()).get('app'),
              'extension': (server.ROOT / 'apple-music-extension' / 'manifest.json').is_file(), 'app_icon': ICON.is_file(),
              # programs Mondesk starts must not load the package's own libraries (see clean_child_environment)
              'child_env': not str(server.ROOT) in os.environ.get('LD_LIBRARY_PATH', '')}
    Path(output).write_text(json.dumps(result), encoding='utf-8')
    http.shutdown(); app.hub.stop()


def main():
    parser = argparse.ArgumentParser(prog=APP)
    parser.add_argument('--demo', action='store_true', help='scripted data for every source; nothing is saved')
    parser.add_argument('--browser', action='store_true', help='no window of its own: open the panel in the default browser')
    parser.add_argument('--self-test', metavar='OUTPUT')
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.self_test)

    # already open? then only bring that window forward (asked before anything is started here)
    config = None if args.demo else ensure_user_config(server.ROOT / 'config.example.json')
    try: port = int(json.loads(config.read_text(encoding='utf-8')).get('port', 9361)) if config else 9362   # the demo runs beside the real one
    except (OSError, ValueError, AttributeError): port = 9361
    if already_running(port):
        return
    app = server.App(demo=1.0) if args.demo else server.App(config)
    ThreadingHTTPServer.allow_reuse_address = False
    http = ThreadingHTTPServer(('127.0.0.1', port), server.make_handler(app))
    url = f'http://127.0.0.1:{http.server_port}'
    if config and any(m.get('type') == 'media' for m in app.hub.config.get('modules', [])):
        from modules.apple_bridge import prepare_extension
        prepare_extension(config, port=http.server_port)
        app.hub.config = json.loads(config.read_text(encoding='utf-8'))
    threading.Thread(target=http.serve_forever, daemon=True).start()

    webview = None
    if not args.browser and not sys.platform.startswith('linux'):
        try: import webview
        except Exception: webview = None
    try:
        if webview is None:
            app.desktop = Shell(opener=lambda: webbrowser.open(url))
            webbrowser.open(url)
            print(f'{APP}: {url}   (Ctrl+C to stop)', flush=True)
            threading.Event().wait()
        else:
            shell = app.desktop = Shell()
            place = shell.place
            window = shell.window = webview.create_window(APP, url, width=place['width'], height=place['height'], x=place['x'], y=place['y'],
                                                          fullscreen=place['fullscreen'], min_size=(480, 320), background_color='#141419')
            for name in ('moved', 'resized', 'closing'):
                event = getattr(window.events, name, None)
                if event is not None:
                    event += shell.remember
            kwargs = {'gui': 'edgechromium'} if sys.platform == 'win32' else {}
            if ICON.is_file() and sys.platform != 'win32':
                kwargs['icon'] = str(ICON)   # Windows takes the window icon from the executable
            webview.start(**kwargs)
    except KeyboardInterrupt:
        pass
    finally:
        http.shutdown(); http.server_close(); app.hub.stop()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        folder = user_config_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f'啟動失敗，詳細資訊已存入 {folder / "error.log"}', APP, 16)
        raise
