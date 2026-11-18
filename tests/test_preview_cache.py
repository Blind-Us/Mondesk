import unittest
from unittest.mock import patch
from modules.bambu import Module


class PreviewCacheTests(unittest.TestCase):
    def printer(self):
        m = Module({'id': 'printer'})
        m.connected = True
        m.report = {'gcode_state': 'RUNNING', 'subtask_name': 'Model', 'gcode_file': 'plate_1.gcode', 'task_id': '1'}
        with patch('modules.bambu.threading.Thread'):
            m.poll()
        m.preview_busy = False
        with patch('modules.printer_assets.preview', return_value=b'image-one'):
            m._preview(m.preview_key, m.report)
        return m

    def test_progress_changes_never_fetch_preview_again(self):
        m = self.printer()
        version = m.preview_version
        with patch('modules.bambu.threading.Thread') as thread:
            for progress in (10, 20, 30):
                m.report['mc_percent'] = progress
                self.assertEqual(m.poll()['preview_version'], version)
            thread.assert_not_called()

    def test_transient_empty_task_fields_keep_image_and_identity(self):
        m = self.printer()
        key = m.preview_key
        m.report.update(subtask_name='', gcode_file='', task_id=None)
        with patch('modules.bambu.threading.Thread') as thread:
            self.assertTrue(m.poll()['preview'])
            self.assertEqual(m.preview_key, key)
            thread.assert_not_called()

    def test_new_task_keeps_old_preview_until_replacement_succeeds(self):
        m = self.printer()
        old_version = m.preview_version
        m.report['task_id'] = '2'
        with patch('modules.bambu.threading.Thread'):
            result = m.poll()
        self.assertTrue(result['preview'])
        self.assertTrue(result['preview_pending'])
        self.assertEqual(result['preview_version'], old_version)
        with patch('modules.printer_assets.preview', return_value=None):
            m._preview(m.preview_key, m.report)
        self.assertEqual(m.preview_image, b'image-one')
        with patch('modules.printer_assets.preview', return_value=b'image-two'):
            m._preview(m.preview_key, m.report)
        self.assertNotEqual(m.preview_version, old_version)
        self.assertFalse(m.poll()['preview_pending'])

    def test_old_task_worker_never_replaces_new_task_image(self):
        m = self.printer()
        old_key = m.preview_key
        m.preview_key = ('Other', 'plate_2.gcode', '2')
        with patch('modules.printer_assets.preview', return_value=b'stale'):
            m._preview(old_key, m.report)
        self.assertEqual(m.preview_image, b'image-one')

    def test_same_picture_in_a_new_job_keeps_the_same_cache_url(self):
        m = self.printer()
        version = m.preview_version
        m.preview_key = ('Other', 'plate_2.gcode', '2')
        with patch('modules.printer_assets.preview', return_value=b'image-one'):
            m._preview(m.preview_key, m.report)
        self.assertEqual(m.preview_version, version)
