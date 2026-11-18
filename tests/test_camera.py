import time
import unittest
from unittest.mock import Mock, patch
from modules.printer_assets import Camera


class CameraTests(unittest.TestCase):
    def test_failed_connection_backoff_preserves_error(self):
        camera = Camera({})
        camera.error = '攝影機 TLS 連線中斷'
        camera.retry_after = time.time() + 10
        with patch('modules.printer_assets.threading.Thread') as worker:
            camera.start({})
            worker.assert_not_called()
        self.assertEqual(camera.error, '攝影機 TLS 連線中斷')

    def test_live_worker_not_restarted(self):
        camera = Camera({})
        camera.worker = Mock(is_alive=lambda: True)
        with patch('modules.printer_assets.threading.Thread') as worker:
            camera.start({})
            worker.assert_not_called()


class CameraSourceTests(unittest.TestCase):
    SPEC = {'ip': '10.0.0.5', 'access_code': 'a b/c'}

    def test_lan_source_skips_certificate_check_and_escapes_the_code(self):
        with patch('modules.printer_assets.studio_stream', return_value=None):
            ways = Camera(self.SPEC).sources({})
        self.assertEqual([w[0] for w in ways], ['lan'])
        args = ways[0][1]
        self.assertEqual(args[args.index('-tls_verify') + 1], '0')       # the printer's certificate is self-signed
        self.assertLess(args.index('-tls_verify'), args.index('-i'))     # an input option: it must come before -i
        self.assertEqual(args[-1], 'rtsps://bblp:a%20b%2Fc@10.0.0.5:322/streaming/live/1')

    def test_studio_first_then_lan_and_the_setting_picks_one(self):
        with patch('modules.printer_assets.studio_stream', return_value='x.sdp'), patch('modules.printer_assets.studio_port', return_value=5004):
            self.assertEqual([w[0] for w in Camera(self.SPEC).sources({})], ['studio', 'lan'])
            self.assertEqual([w[0] for w in Camera({**self.SPEC, 'camera_source': 'lan'}).sources({})], ['lan'])
            self.assertEqual([w[0] for w in Camera({**self.SPEC, 'camera_source': 'studio'}).sources({})], ['studio'])
            self.assertEqual([w[0] for w in Camera(self.SPEC).sources({'ipcam': {'rtsp_url': 'disable'}})], ['studio'])
        with patch('modules.printer_assets.studio_stream', return_value=None):
            self.assertEqual(Camera(self.SPEC).sources({'ipcam': {'rtsp_url': 'disable'}}), [])
            self.assertEqual(Camera({}).sources({}), [])

    def test_the_second_way_is_tried_when_the_first_gives_no_picture(self):
        camera = Camera(self.SPEC)
        camera.last_request = time.time()
        def watch(ffmpeg, source, rtp_port, errors):
            if rtp_port is None:
                camera.frame = b'\xff\xd8\xff\xd9'
        with patch('modules.printer_assets.studio_stream', return_value='x.sdp'), patch('modules.printer_assets.studio_port', return_value=5004), \
                patch.object(camera, 'watch', side_effect=watch):
            camera.run({})
        self.assertEqual((camera.tried, camera.source, camera.error), (['studio', 'lan'], 'lan', ''))


if __name__ == '__main__':
    unittest.main()
