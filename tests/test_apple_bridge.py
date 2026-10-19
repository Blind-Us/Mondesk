import threading
import time
import unittest
from modules.apple_bridge import Bridge
from modules.media import Module
from unittest.mock import patch


def state(track='apple:123', position=10, lines=None):
    return {'track': track, 'title': 'Song', 'artist': 'Artist', 'album': '',
            'position': position, 'duration': 200, 'playing': True,
            'lines': lines if lines is not None else [[10, 'First'], [30, 'Next']], 'plain': []}


class BridgeTests(unittest.TestCase):
    def test_native_artwork_only_accepts_apple_https(self):
        b = Bridge()
        for url, expected in [('https://is1-ssl.mzstatic.com/image.jpg', True), ('http://is1-ssl.mzstatic.com/image.jpg', False), ('https://mzstatic.com.evil.test/x', False)]:
            b.exchange({'state': {**state(), 'art_url': url}})
            self.assertEqual(bool(b.snapshot()['art_url']), expected)

    def test_missing_timing_never_seeks(self):
        b = Bridge()
        b.exchange({'state': state(lines=[])})
        with self.assertRaises(ValueError):
            b.action('seek', 'apple:123', 30)
        self.assertEqual(b.commands, [])

    def test_stale_track_rejected(self):
        b = Bridge()
        b.exchange({'state': state()})
        with self.assertRaises(RuntimeError):
            b.action('seek', 'apple:other', 30)

    def test_invalid_timing_rejected(self):
        for lines in ([[float('nan'), 'x']], [[300, 'x']], [[30, 'x'], [10, 'y']]):
            with self.assertRaises(ValueError):
                Bridge().exchange({'state': state(lines=lines)})

    def test_actual_player_position_required(self):
        for position, succeeds in ((30, True), (10, False)):
            b = Bridge()
            b.exchange({'state': state()})
            outcome = []
            def action():
                try:
                    b.action('seek', 'apple:123', 30)
                    outcome.append(True)
                except RuntimeError:
                    outcome.append(False)
            worker = threading.Thread(target=action)
            worker.start()
            deadline = time.monotonic() + 1
            commands = []
            while not commands and time.monotonic() < deadline:
                commands = b.exchange({'state': state()})
                time.sleep(.01)
            self.assertTrue(commands)
            b.exchange({'state': state(position=position), 'acks': [{'id': commands[0]['id'], 'ok': True}]})
            worker.join(2)
            self.assertEqual(outcome, [succeeds])

    def test_native_mode_does_not_lookup_external_lyrics(self):
        b = Bridge()
        b.exchange({'state': state()})
        m = Module({'id': 'music', 'apple_music_native': True})
        with patch('modules.apple_bridge.bridge', b), patch('modules.media.fetch_lyrics') as external:
            self.assertEqual(m.poll()['source'], 'Apple Music')
            external.assert_not_called()
            b.updated -= 10
            self.assertEqual(m.poll()['_status'], 'offline')


if __name__ == '__main__':
    unittest.main()
