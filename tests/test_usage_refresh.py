import unittest
from unittest.mock import patch
from modules.tokens import Module, Claude


class RefreshTests(unittest.TestCase):
    def module(self, official=False):
        m = Module({'id': 'claude', 'provider': 'claude', 'official_usage': official, 'glob': '/nonexistent/usage/*.jsonl'})
        m.start()
        return m

    def test_manual_refresh_queries_official_even_when_cached(self):
        m = self.module(True)
        m.provider._last = {'at': 1000, 'windows': [{'label': '5h', 'used_percent': 10}]}
        m.provider._next = 999999
        with patch('modules.tokens.time.time', return_value=2000), patch.object(Claude, '_query', return_value=[{'label': '5h', 'used_percent': 20}]) as query, patch('builtins.open', side_effect=OSError):
            self.assertEqual(m.action('refresh')['windows'][0]['used_percent'], 20)
            query.assert_called_once()

    def test_failure_keeps_last_good_usage(self):
        m = self.module(True)
        m.provider._last = {'at': 1000, 'windows': [{'label': '5h', 'used_percent': 10}]}
        m.provider._next = 999999
        with patch('modules.tokens.time.time', return_value=2000), patch.object(Claude, '_query', return_value=None):
            with self.assertRaisesRegex(RuntimeError, '保留上次資料'):
                m.action('refresh')
        self.assertEqual(m.provider._last['windows'][0]['used_percent'], 10)

    def test_local_mode_never_reads_official_account(self):
        m = self.module()
        with patch.object(Claude, '_query') as query:
            self.assertEqual(m.action('refresh')['provider'], 'claude')
            with self.assertRaisesRegex(RuntimeError, '剛剛已查詢'):
                m.action('refresh')
            query.assert_not_called()

class ExpiredLoginTests(unittest.TestCase):
    """The CLI's access token expires after hours; Mondesk must refresh it, not show 0%."""

    def setUp(self):
        import json, os, tempfile
        self.json, self.dir = json, tempfile.mkdtemp()
        self.cred = os.path.join(self.dir, '.credentials.json')
        p = patch.object(Claude, 'CRED', self.cred)
        p.start()
        self.addCleanup(p.stop)

    def write(self, **oauth):
        with open(self.cred, 'w', encoding='utf-8') as f:
            self.json.dump({'claudeAiOauth': {'accessToken': 'old', 'refreshToken': 'r1', 'scopes': ['x'], **oauth}, 'other': 1}, f)

    def test_expired_token_is_refreshed_and_saved_back(self):
        import time, urllib.request
        self.write(expiresAt=1000, refreshTokenExpiresAt=(time.time() + 86400) * 1000)
        calls = []

        class Resp:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return self.body

        def fake(req, timeout=0):
            calls.append((req.full_url, req.get_header('Authorization')))
            if 'oauth/token' in req.full_url:
                self.assertEqual(self.json.loads(req.data)['refresh_token'], 'r1')
                return Resp(b'{"access_token": "new", "refresh_token": "r2", "expires_in": 3600}')
            return Resp(b'{"five_hour": {"utilization": 42, "resets_at": "2099-01-01T00:00:00Z"}, "seven_day": {"utilization": 7}}')

        c = Claude()
        with patch.object(urllib.request, 'urlopen', fake):
            win = c._query()
        self.assertEqual([w['used_percent'] for w in win], [42, 7])
        self.assertEqual(calls[-1][1], 'Bearer new')
        with open(self.cred, encoding='utf-8') as f:
            saved = self.json.load(f)
        self.assertEqual((saved['claudeAiOauth']['accessToken'], saved['claudeAiOauth']['refreshToken']), ('new', 'r2'))
        self.assertEqual((saved['other'], saved['claudeAiOauth']['scopes']), (1, ['x']))  # rest of the file kept
        self.assertEqual(c.error, '')

    def test_dead_login_says_how_to_fix_instead_of_zero(self):
        self.write(expiresAt=1000, refreshTokenExpiresAt=1000)
        c = Claude()
        c.official = True
        c._last, c._next = None, 0
        with patch.object(Claude, 'CACHE', self.cred + '.cache'):
            out = c.extra()
        self.assertNotIn('windows', out)
        self.assertIn('/login', out['usage_error'])


class ResetWindowTests(unittest.TestCase):
    def test_window_past_its_reset_time_is_back_to_zero(self):
        from modules.tokens import _fresh
        self.assertEqual(_fresh({'label': '5h', 'used_percent': 90, 'resets_at': 100}, now=200)['used_percent'], 0)
        self.assertEqual(_fresh({'label': '5h', 'used_percent': 90, 'resets_at': 300}, now=200)['used_percent'], 90)
