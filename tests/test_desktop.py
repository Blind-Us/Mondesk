"""The application around the pages (desktop.py): what it remembers and what the pages may ask of it."""
import json
import sys
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import desktop
import server


class FakeWindow:
    def __init__(self):
        self.x, self.y, self.width, self.height, self.toggled, self.shown = 40, 50, 800, 600, 0, 0

    def toggle_fullscreen(self): self.toggled += 1
    def restore(self): pass
    def show(self): self.shown += 1


class WindowMemoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = patch.object(desktop, 'window_file', lambda: self.folder / 'window.json')
        patcher.start(); self.addCleanup(patcher.stop)

    def test_first_start_uses_a_plain_window(self):
        self.assertEqual(desktop.load_window(), {'x': None, 'y': None, 'width': 960, 'height': 680, 'fullscreen': False})

    def test_place_and_size_come_back_and_nonsense_is_ignored(self):
        shell = desktop.Shell(window=FakeWindow())
        shell.remember()
        self.assertEqual(desktop.load_window(), {'x': 40, 'y': 50, 'width': 800, 'height': 600, 'fullscreen': False})
        (self.folder / 'window.json').write_text('{"x": 0, "y": 0, "width": 5, "height": 99999}', encoding='utf-8')
        self.assertEqual(desktop.load_window()['width'], 960)
        (self.folder / 'window.json').write_text('not json', encoding='utf-8')
        self.assertEqual(desktop.load_window()['width'], 960)

    def test_full_screen_is_remembered_and_keeps_the_place_to_return_to(self):
        window = FakeWindow()
        with patch.object(desktop, 'autostart_enabled', lambda: False):
            shell = desktop.Shell(window=window)
            shell.remember()
            state = shell.set({'fullscreen': True})
            window.x, window.y, window.width, window.height = 0, 0, 1920, 1080   # what a full-screen window reports
            shell.remember()
            self.assertEqual((state['fullscreen'], window.toggled), (True, 1))
            self.assertEqual(desktop.load_window(), {'x': 40, 'y': 50, 'width': 800, 'height': 600, 'fullscreen': True})
            shell.set({'fullscreen': True})                                       # already so: nothing happens
            self.assertEqual(window.toggled, 1)


class ShellTests(unittest.TestCase):
    def test_started_again_from_source_or_packaged(self):
        with patch.object(desktop, 'FROZEN', True), patch.object(sys, 'executable', r'C:\Apps\Mondesk\Mondesk.exe'):
            self.assertEqual(desktop.launch_command(), [r'C:\Apps\Mondesk\Mondesk.exe'])
        with patch.object(desktop, 'FROZEN', False):
            command = desktop.launch_command(['--demo'])
            self.assertTrue(command[1].endswith('desktop.py'))
            self.assertEqual(command[-1], '--demo')
        # the Windows package: Mondesk.exe (Python's signed pythonw.exe, renamed) starts Mondesk by itself
        exe = str(Path('/Apps/Mondesk/Mondesk.exe'))   # a path every system can read
        with patch.object(desktop, 'FROZEN', False), patch.object(sys, 'executable', exe):
            self.assertEqual(desktop.launch_command(), [exe])
            command = desktop.launch_command(['--demo'])
            self.assertEqual((command[0], command[-1]), (exe, '--demo'))
            self.assertTrue(command[1].endswith('desktop.py'))

    def test_autostart_goes_through_the_switch_only(self):
        calls = []
        with patch.object(desktop, 'set_autostart', lambda on: calls.append(on)), patch.object(desktop, 'autostart_enabled', lambda: bool(calls and calls[-1])):
            shell = desktop.Shell()
            self.assertEqual(shell.state()['autostart'], False)
            self.assertEqual(shell.set({'autostart': True})['autostart'], True)
            self.assertEqual(shell.set({})['autostart'], True)          # other requests leave it alone
            self.assertEqual(calls, [True])

    def test_show_without_a_window_opens_the_browser_again(self):
        opened = []
        with patch.object(desktop, 'autostart_enabled', lambda: False):
            desktop.Shell(opener=lambda: opened.append(1)).set({'action': 'show'})
        self.assertEqual(opened, [1])


class DesktopApiTests(unittest.TestCase):
    def setUp(self):
        self.app = server.App(demo=1.0)
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(self.app))
        Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.http.server_port}/api/desktop'
        self.addCleanup(lambda: (self.http.shutdown(), self.http.server_close(), self.app.hub.stop()))

    def post(self, body):
        return json.loads(urlopen(Request(self.url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'X-DeskMon': '1'}), timeout=5).read())

    def test_a_plain_server_says_it_is_not_the_application(self):
        self.assertEqual(json.loads(urlopen(self.url, timeout=5).read()), {'app': False})
        with self.assertRaises(HTTPError):
            self.post({'autostart': True})
        self.assertFalse(desktop.already_running(self.http.server_port))

    def test_a_second_start_finds_the_first_and_asks_it_to_come_forward(self):
        window = FakeWindow()
        with patch.object(desktop, 'autostart_enabled', lambda: False), patch.object(desktop, 'window_file', lambda: Path(tempfile.mkdtemp()) / 'w.json'):
            self.app.desktop = desktop.Shell(window=window)
            self.assertTrue(desktop.already_running(self.http.server_port))
        self.assertEqual(window.shown, 1)


if __name__ == '__main__':
    unittest.main()
