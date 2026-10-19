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


if __name__ == '__main__':
    unittest.main()
