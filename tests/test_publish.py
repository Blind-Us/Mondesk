import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from modules.apple_bridge import prepare_extension
from tools.build_app import stage_extension
from user_paths import ensure_user_config


class PublishTests(unittest.TestCase):
    def test_released_extension_has_no_pairing_key_and_no_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            extension = stage_extension(Path(folder))
            names = {p.relative_to(extension).as_posix() for p in extension.rglob('*') if p.is_file()}
            self.assertIn('video.js', names)
            self.assertIn('manifest.json', names)
            self.assertIn('icons/icon128.png', names)
            self.assertNotIn('config.js', names)
            self.assertFalse(any(n.endswith('.cjs') for n in names))

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
