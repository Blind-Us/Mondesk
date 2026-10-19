"""Local, paired Chrome bridge. No Apple account credentials leave the browser."""
import json
import math
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent


class Bridge:
    def __init__(self):
        self.lock = threading.Condition()
        self.state = None
        self.updated = 0
        self.commands = []
        self.pending = {}

    def exchange(self, data):
        state = data.get('state')
        if not isinstance(state, dict) or not isinstance(state.get('track'), str):
            raise ValueError('無效的 Apple Music 狀態')
        for field in ('position', 'duration'):
            value = state.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('無效的播放時間')
        lines = state.get('lines') or []
        if not isinstance(lines, list) or len(lines) > 3000:
            raise ValueError('無效的歌詞')
        previous = -1
        for row in lines:
            if (not isinstance(row, list) or len(row) != 2 or not isinstance(row[1], str)
                    or isinstance(row[0], bool) or not isinstance(row[0], (int, float))
                    or not math.isfinite(row[0]) or row[0] < previous
                    or row[0] < 0 or state['duration'] and row[0] > state['duration']):
                raise ValueError('無效的原生歌詞時間')
            previous = row[0]
        with self.lock:
            self.state = {k: state.get(k) for k in ('track', 'title', 'artist', 'album', 'playing', 'position', 'duration', 'lines', 'plain')}
            diagnostic = data.get('diagnostic')
            self.state['native_diagnostic'] = diagnostic[:260] if isinstance(diagnostic, str) else ''
            art = state.get('art_url') or ''
            url = urlsplit(art) if isinstance(art, str) else urlsplit('')
            self.state['art_url'] = art if url.scheme == 'https' and (url.hostname or '').endswith('.mzstatic.com') and not url.username and not url.password else ''
            self.updated = time.monotonic()
            for ack in data.get('acks', []):
                if ack.get('id') in self.pending:
                    self.pending[ack['id']] = ack
            commands, self.commands = self.commands, []
            self.lock.notify_all()
            return commands

    def snapshot(self):
        with self.lock:
            # A paused, silent background tab gets throttled by Chrome and reports rarely;
            # a paused state doesn't change, so keep it much longer than a playing one.
            limit = 4 if (self.state or {}).get('playing') else 600
            if not self.state or time.monotonic() - self.updated > limit:
                return None
            result = dict(self.state)
            age = time.monotonic() - self.updated
        if result['playing']:
            result['position'] = min(result['duration'] or float('inf'), result['position'] + age)
        return result

    def action(self, name, track, position=None):
        state = self.snapshot()
        if not state or state['track'] != track:
            raise RuntimeError('Apple Music 已斷線或歌曲已變更')
        if name == 'seek':
            if not state.get('lines') or not any(abs(row[0] - position) < .01 for row in state['lines']):
                raise ValueError('這句歌詞沒有 Apple Music 原生同步時間')
        command = {'id': secrets.token_hex(12), 'action': name, 'track': track, 'position': position}
        deadline = time.monotonic() + 7
        with self.lock:
            self.pending[command['id']] = None
            self.commands.append(command)
            try:
                while self.pending[command['id']] is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError('Apple Music 未回應，請確認網頁仍開啟')
                    self.lock.wait(remaining)
                ack = self.pending[command['id']]
                if not ack.get('ok'):
                    raise RuntimeError(ack.get('error') or 'Apple Music 拒絕操作')
                actual = self.snapshot()
                if not actual or name == 'seek' and actual['track'] != track:
                    raise RuntimeError('歌曲已變更')
                if name == 'seek' and (abs(actual['position'] - position) > 3 or not actual['playing']):
                    raise RuntimeError('Apple Music 尚未回報跳轉成功')
            finally:
                self.pending.pop(command['id'], None)
                self.commands = [c for c in self.commands if c['id'] != command['id']]


bridge = Bridge()


def paired(headers, address, key):
    """The extension proves itself with the pairing key stored in config.json (media module)."""
    return (address in ('127.0.0.1', '::1') and bool(key)
            and secrets.compare_digest(headers.get('X-DeskMon-Key', ''), key))


def prepare_extension(config_path=ROOT / 'config.json', port=9361):
    """Create (or reuse) the pairing key in config.json and write the extension's config.js."""
    config = json.loads(config_path.read_text(encoding='utf-8'))
    media = next((m for m in config.get('modules', []) if m.get('type') == 'media'), None)
    if media is None:
        raise SystemExit('config.json 沒有 media 模組')
    old = ROOT / '.apple-music-key'  # migrate the old separate key file
    media['pair_key'] = media.get('pair_key') or (old.read_text().strip() if old.exists() else secrets.token_urlsafe(32))
    media['apple_music_native'] = True
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    if old.exists():
        old.unlink()
    ext = {'url': f'http://127.0.0.1:{port}/api/apple-music', 'key': media['pair_key']}
    (ROOT / 'apple-music-extension' / 'config.js').write_text('const DESKMON = ' + json.dumps(ext) + ';\n')


if __name__ == '__main__':
    prepare_extension()
    print('已配對（金鑰存於 config.json）：', ROOT / 'apple-music-extension')
