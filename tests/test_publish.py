import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from modules.apple_bridge import prepare_extension
from tools.package_desktop import build
from user_paths import ensure_user_config


class PublishTests(unittest.TestCase):
    def test_public_package_has_templates_but_no_user_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            output = build(Path(folder) / 'desktop.zip')
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('DeskMon/desktop.py', names)
                self.assertIn('DeskMon/user_paths.py', names)
                self.assertIn('DeskMon/web/printer-render.js', names)
                self.assertIn('DeskMon/apple-music-extension/video.js', names)
                self.assertNotIn('DeskMon/config.json', names)
                self.assertNotIn('DeskMon/apple-music-extension/config.js', names)
                self.assertFalse(any('/.venv/' in n or '/__pycache__/' in n for n in names))

    def test_extension_generated_only_next_to_user_config(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps({'modules': [{'id': 'music', 'type': 'media', 'pair_key': 'test-key'}]}))
            extension = prepare_extension(config, port=12345)
            self.assertEqual(extension, Path(folder) / 'browser-extension')
            generated = (extension / 'config.js').read_text(encoding='utf-8')
            self.assertIn('127.0.0.1:12345', generated)
            self.assertIn('test-key', generated)
            self.assertTrue((extension / 'video.js').exists())
            self.assertFalse((Path(folder) / '.apple-music-key').exists())

    def test_existing_user_config_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text('personal')
            template = Path(folder) / 'template.json'
            template.write_text('default')
            with patch('user_paths.user_config_path', return_value=config):
                ensure_user_config(template)
            self.assertEqual(config.read_text(), 'personal')
