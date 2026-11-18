"""Local, paired Chrome bridge. No Apple account credentials leave the browser."""
import json
import math
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent


MIRROR_STATES = ('', 'waiting', 'hidden', 'blocked')
MAX_FRAME = 2 * 1024 * 1024
VIEWER_TTL = 1.5  # seconds a viewer counts as watching after its last frame request (it asks every ~10 ms)


class Bridge:
    def __init__(self):
        self.lock = threading.Condition()
        self.state = None
        self.updated = 0
        self.commands = []
        self.pending = {}
        # video mirror: the extension copies frames from the playing tab only while a panel
        # is showing them; the original tab keeps playing (with its sound) untouched.
        self.frame = None
        self.frame_track = None
        self.frame_time = 0
        self.viewer_at = 0

    def want_frames(self):
        """True while a panel is showing the video, so the extension should send frames."""
        with self.lock:
            return bool(self.state and self.state.get('video')) and time.monotonic() - self.viewer_at < VIEWER_TTL

    def put_frame(self, track, jpeg):
        if not isinstance(jpeg, (bytes, bytearray)) or not 0 < len(jpeg) <= MAX_FRAME or jpeg[:3] != b'\xff\xd8\xff':
            raise ValueError('無效的影片畫面')
        with self.lock:
            if not self.state or self.state.get('track') != track:
                raise ValueError('影片已變更')
            self.frame, self.frame_track, self.frame_time = bytes(jpeg), track, time.monotonic()

    def watch(self):
        """Called by a viewer: marks the video as watched and returns (time, latest frame)."""
        with self.lock:
            self.viewer_at = time.monotonic()
            current = (self.state or {}).get('track')
            if self.frame and self.frame_track == current:
                return self.frame_time, self.frame
            return 0, None

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
            old = self.state
            if 'lines' not in state and old and old['track'] == state['track']:
                state = {**state, 'lines': old.get('lines'), 'plain': old.get('plain'), 'lyrics_revision': old.get('lyrics_revision')}
            self.state = {k: state.get(k) for k in ('track', 'title', 'artist', 'album', 'playing', 'position', 'duration', 'lines', 'plain')}
            self.state['lyrics_revision'] = state.get('lyrics_revision') if 'lines' in state else None
            self.state['source'] = state.get('source') if state.get('source') in ('Apple Music', 'YouTube', 'YouTube Music', 'Bilibili', 'Browser') else 'Apple Music'
            self.state['video'] = bool(state.get('video'))
            self.state['ad'] = bool(state.get('ad'))  # YouTube ad playing in the tab
            volume = state.get('volume')   # the video's own volume (0-100); None from pages that don't report it
            self.state['volume'] = round(volume) if isinstance(volume, (int, float)) and not isinstance(volume, bool) and 0 <= volume <= 100 else None
            # why frames can't be shown right now: tab in background / site blocks capture
            mirror = state.get('mirror')
            self.state['mirror'] = mirror if mirror in MIRROR_STATES else ''
            # which extension build is running in the tab (an old tab keeps old scripts until reloaded)
            ext = state.get('ext')
            self.state['ext'] = ext if isinstance(ext, str) and len(ext) <= 16 and ext.replace('.', '').isdigit() else ''
            diagnostic = data.get('diagnostic')
            self.state['native_diagnostic'] = diagnostic[:260] if isinstance(diagnostic, str) else ''
            art = state.get('art_url') or ''
            url = urlsplit(art) if isinstance(art, str) else urlsplit('')
            image_host = url.hostname or ''
            allowed_image = image_host.endswith('.mzstatic.com') or image_host.endswith('.ytimg.com') or image_host == 'i.ytimg.com' or image_host.endswith('.googleusercontent.com')
            clean = url.scheme == 'https' and not url.username and not url.password
            self.state['art_url'] = art if clean and allowed_image else ''
            # A video site's own thumbnail (Bilibili, other tabs) lives on any host and often refuses
            # requests that come from another page, so the panel never loads it directly: Mondesk
            # fetches it (see MediaModule.asset 'cover'). Only public https names, never an address.
            named = '.' in image_host and not image_host.replace('.', '').isdigit() and ':' not in image_host and not image_host.endswith(('.local', '.localhost', '.internal', '.lan'))
            self.state['art_remote'] = art if clean and named and not allowed_image and self.state['source'] != 'Apple Music' and len(art) <= 1000 else ''
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
            limit = 12 if (self.state or {}).get('playing') else 60
            if not self.state or time.monotonic() - self.updated > limit:
                return None
            result = dict(self.state)
            age = time.monotonic() - self.updated
        if result['playing']:
            result['position'] = min(result['duration'] or float('inf'), result['position'] + age)
        return result

    def action(self, name, track, position=None, value=None):
        state = self.snapshot()
        if not state or state['track'] != track:
            raise RuntimeError('播放器已斷線或播放來源已變更')
        if name == 'seek':
            if not state.get('lines') or not any(abs(row[0] - position) < .01 for row in state['lines']):
                raise ValueError('這句歌詞沒有 Apple Music 原生同步時間')
        if name == 'seek_time':
            from .media_seek import target_seconds
            position = target_seconds(position, state.get('duration'))
        command = {'id': secrets.token_hex(12), 'action': name, 'track': track, 'position': position}
        if name == 'volume':
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                raise ValueError('音量要在 0 到 100 之間')
            command['value'] = round(value)
        deadline = time.monotonic() + 7
        with self.lock:
            self.pending[command['id']] = None
            self.commands.append(command)
            try:
                while self.pending[command['id']] is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError(f"{state.get('source') or '播放器'} 未回應，請確認網頁仍開啟")
                    self.lock.wait(remaining)
                ack = self.pending[command['id']]
                if not ack.get('ok'):
                    raise RuntimeError(ack.get('error') or '播放器拒絕操作')
                actual = self.snapshot()
                if not actual or name in ('seek', 'seek_time') and actual['track'] != track:
                    raise RuntimeError('歌曲已變更')
                if name == 'seek' and (abs(actual['position'] - position) > 3 or not actual['playing']):
                    raise RuntimeError('Apple Music 尚未回報跳轉成功')
                if name == 'seek_time' and abs(actual['position'] - position) > 3:
                    raise RuntimeError('播放器尚未回報跳轉成功')
            finally:
                self.pending.pop(command['id'], None)
                self.commands = [c for c in self.commands if c['id'] != command['id']]


bridge = Bridge()


def paired(headers, address, key):
    """The extension proves itself with the pairing key stored in config.json (media module)."""
    return (address in ('127.0.0.1', '::1') and bool(key)
            and secrets.compare_digest(headers.get('X-DeskMon-Key', ''), key))


def prepare_extension(config_path=None, port=9361, output_dir=None):
    """Create (or reuse) the pairing key in config.json and write the extension's config.js."""
    from user_paths import user_config_path
    import shutil
    config_path = Path(config_path) if config_path else user_config_path()
    output_dir = Path(output_dir) if output_dir else config_path.parent / 'browser-extension'
    output_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding='utf-8'))
    media = next((m for m in config.get('modules', []) if m.get('type') == 'media'), None)
    if media is None:
        raise SystemExit('config.json 沒有 media 模組')
    media['pair_key'] = media.get('pair_key') or secrets.token_urlsafe(32)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    for source in (ROOT / 'apple-music-extension').iterdir():
        if source.is_file() and source.name != 'config.js' and source.suffix != '.cjs':
            shutil.copyfile(source, output_dir / source.name)
    icons = ROOT / 'apple-music-extension' / 'icons'
    if icons.is_dir():
        shutil.copytree(icons, output_dir / 'icons', dirs_exist_ok=True)
    ext = {'url': f'http://127.0.0.1:{port}/api/apple-music', 'key': media['pair_key']}
    (output_dir / 'config.js').write_text('const DESKMON = ' + json.dumps(ext) + ';\n', encoding='utf-8')
    return output_dir


if __name__ == '__main__':
    print('已配對（金鑰存於使用者設定）：', prepare_extension())
