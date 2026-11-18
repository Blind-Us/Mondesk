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
    def test_timeline_seek_accepts_arbitrary_time_without_timed_lyrics(self):
        b = Bridge()
        initial = {**state(lines=[]), 'playing': False}
        b.exchange({'state': initial})
        outcome = []
        def seek():
            try:
                b.action('seek_time', 'apple:123', 42)
                outcome.append(True)
            except Exception:
                outcome.append(False)
        worker = threading.Thread(target=seek); worker.start()
        commands = []
        deadline = time.monotonic() + 1
        while not commands and time.monotonic() < deadline:
            commands = b.exchange({'state': initial}); time.sleep(.01)
        self.assertTrue(commands)
        b.exchange({'state': {**initial, 'position': 42}, 'acks': [{'id': commands[0]['id'], 'ok': True}]})
        worker.join(2)
        self.assertEqual(outcome, [True])
        self.assertFalse(b.snapshot()['playing'])

    def test_resume_cannot_control_a_different_source(self):
        m = Module({'id': 'music'})
        m.last_media = {'browser_bridge': True, 'track': 'apple:123'}
        with patch('modules.apple_bridge.bridge.action') as control:
            with self.assertRaisesRegex(RuntimeError, '來源已變更'):
                m.action('toggle', track='youtube:123')
            control.assert_not_called()

    # ---- video mirror: frames flow only while a panel watches, and only for the current video ----
    def video(self, **extra):
        return {**state(track='youtube:abcdefghijk', lines=[]), 'source': 'YouTube', 'video': True, **extra}

    def test_mirror_frames_requested_only_while_watched(self):
        b = Bridge()
        b.exchange({'state': self.video()})
        self.assertFalse(b.want_frames())          # nobody watching: extension must not capture
        b.watch()
        self.assertTrue(b.want_frames())
        b.viewer_at -= 10                          # viewer closed the panel
        self.assertFalse(b.want_frames())

    def test_mirror_never_requested_for_music(self):
        b = Bridge()
        b.exchange({'state': state()})             # Apple Music song, no video
        b.watch()
        self.assertFalse(b.want_frames())

    def test_mirror_frame_must_match_current_video_and_be_jpeg(self):
        b = Bridge()
        b.exchange({'state': self.video()})
        jpeg = b'\xff\xd8\xff' + b'x' * 64
        b.put_frame('youtube:abcdefghijk', jpeg)
        self.assertEqual(b.watch()[1], jpeg)
        with self.assertRaises(ValueError):
            b.put_frame('youtube:OTHERVIDEOX', jpeg)   # stale tab / old video
        with self.assertRaises(ValueError):
            b.put_frame('youtube:abcdefghijk', b'<html>not an image')
        b.exchange({'state': self.video(track='youtube:zzzzzzzzzzz')})
        self.assertIsNone(b.watch()[1])               # never show the previous video's frame

    def test_youtube_ad_flag_passes_through(self):
        b = Bridge()
        b.exchange({'state': self.video(ad=True)})
        self.assertTrue(b.snapshot()['ad'])
        b.exchange({'state': self.video()})
        self.assertFalse(b.snapshot()['ad'])

    def test_mirror_status_is_whitelisted(self):
        b = Bridge()
        b.exchange({'state': self.video(mirror='hidden')})
        self.assertEqual(b.snapshot()['mirror'], 'hidden')
        b.exchange({'state': self.video(mirror='<img onerror=x>')})
        self.assertEqual(b.snapshot()['mirror'], '')

    def test_buttons_use_os_media_controls_not_the_tab(self):
        # a throttled, paused background tab answers late: play/pause must not depend on it
        m = Module({'id': 'music'})
        m.err, m.win_act = None, lambda name: calls.append(name)
        calls = []
        m.last_media = {'browser_bridge': True, 'track': 'youtube:abcdefghijk'}
        with patch('modules.apple_bridge.bridge.action') as tab, patch('modules.media.sys.platform', 'win32'):
            self.assertEqual(m.action('toggle', track='youtube:abcdefghijk'), 'toggle')
            tab.assert_not_called()
        self.assertEqual(calls, ['toggle'])

    def test_native_artwork_only_accepts_apple_https(self):
        b = Bridge()
        for url, expected in [('https://is1-ssl.mzstatic.com/image.jpg', True), ('http://is1-ssl.mzstatic.com/image.jpg', False), ('https://mzstatic.com.evil.test/x', False)]:
            b.exchange({'state': {**state(), 'art_url': url}})
            self.assertEqual(bool(b.snapshot()['art_url']), expected)

    def test_video_thumbnails_from_other_hosts_are_fetched_by_deskmon_not_loaded_by_the_panel(self):
        b = Bridge()
        video = {**state(track='bilibili:BV14uWC6bEz2', lines=[]), 'source': 'Bilibili', 'video': True}
        for url, expected in [('https://i0.hdslb.com/bfs/archive/a.jpg', True), ('http://i0.hdslb.com/a.jpg', False),
                              ('https://192.168.1.1/a.jpg', False), ('https://localhost/a.jpg', False), ('https://nas.local/a.jpg', False),
                              ('https://user:pw@i0.hdslb.com/a.jpg', False)]:
            b.exchange({'state': {**video, 'art_url': url}})
            snap = b.snapshot()
            self.assertEqual(snap['art_url'], '')                       # never handed to the panel as it is
            self.assertEqual(snap['art_remote'], url if expected else '')
        b.exchange({'state': {**state(), 'art_url': 'https://i0.hdslb.com/a.jpg'}})   # Apple Music: Apple's hosts only
        self.assertEqual(b.snapshot()['art_remote'], '')

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
        with patch('modules.apple_bridge.bridge', b), patch('modules.media._get_json') as external:
            self.assertEqual(m.poll()['source'], 'Apple Music')
            external.assert_not_called()
            b.updated -= 20
            m.err = 'OS fallback unavailable in this test'
            self.assertEqual(m.poll()['_status'], 'offline')

    def test_incremental_updates_keep_cached_lyrics(self):
        b = Bridge()
        b.exchange({'state': {**state(), 'lyrics_revision': 2}})
        delta = {k: v for k, v in state(position=12).items() if k not in ('lines', 'plain')}
        b.exchange({'state': delta})
        self.assertEqual(b.snapshot()['lines'], state()['lines'])
        self.assertEqual(b.snapshot()['lyrics_revision'], 2)

    def test_youtube_source_and_thumbnail_preserved(self):
        b = Bridge()
        b.exchange({'state': {**state(track='youtube:123', lines=[]), 'source': 'YouTube', 'video': True, 'art_url': 'https://i.ytimg.com/vi/123/hqdefault.jpg'}})
        m = Module({'id': 'music'})
        with patch('modules.apple_bridge.bridge', b):
            data = m.poll()
        self.assertEqual(data['source'], 'YouTube')
        self.assertTrue(data['video'])
        self.assertTrue(data['browser_bridge'])

    def test_os_fallback_when_browser_disconnected(self):
        m = Module({'id': 'music', 'apple_music_native': True})
        m.err = 'No native media runtime'
        with patch('modules.apple_bridge.bridge', Bridge()):
            self.assertEqual(m.poll()['message'], 'No native media runtime')



class VideoVolumeTests(unittest.TestCase):
    def state(self, **extra):
        return {'state': {'track': 'youtube:abc', 'title': 't', 'playing': True, 'position': 1, 'duration': 60, 'video': True, **extra}}

    def test_the_tab_reports_its_own_volume_and_bad_values_are_dropped(self):
        from modules.apple_bridge import Bridge
        b = Bridge()
        b.exchange(self.state(volume=37.4))
        self.assertEqual(b.snapshot()['volume'], 37)
        for bad in (True, 'loud', -1, 101, None):
            b.exchange(self.state(volume=bad))
            self.assertIsNone(b.snapshot()['volume'])

    def test_volume_goes_to_the_tab_as_a_command_and_is_range_checked(self):
        import threading
        from modules.apple_bridge import Bridge
        b = Bridge()
        b.exchange(self.state(volume=80))
        for bad in (None, True, -5, 150, 'x'):
            with self.assertRaises(ValueError):
                b.action('volume', 'youtube:abc', value=bad)
        sent = {}
        def tab():   # the extension picks the command up and acknowledges it
            for _ in range(50):
                cmds = b.exchange(self.state(volume=80))
                if cmds:
                    sent.update(cmds[0])
                    b.exchange({**self.state(volume=25), 'acks': [{'id': cmds[0]['id'], 'ok': True}]})
                    return
                time.sleep(.02)
        threading.Thread(target=tab, daemon=True).start()
        b.action('volume', 'youtube:abc', value=25.4)
        self.assertEqual((sent['action'], sent['value'], sent['track']), ('volume', 25, 'youtube:abc'))
        self.assertEqual(b.snapshot()['volume'], 25)

if __name__ == '__main__':
    unittest.main()
