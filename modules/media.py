"""Now playing from the OS media session.

Windows: System Media Transport Controls (pip install winrt-Windows.Media.Control
         winrt-Windows.Foundation winrt-runtime)
Linux:   MPRIS via `playerctl`
macOS:   `nowplaying-cli` if installed
"""
import asyncio
import shutil
import subprocess
import sys
import threading
import time

from . import BaseModule


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def extension_version():
    """Version of the browser extension that ships with this Mondesk ('' if unknown)."""
    from pathlib import Path
    try:
        manifest = Path(__file__).resolve().parent.parent / "apple-music-extension" / "manifest.json"
        return str(_json.loads(manifest.read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError):
        return ""


def _secs(td):
    return td.total_seconds() if hasattr(td, "total_seconds") else td / 1e7


async def _windows():
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager)
    mgr = await Manager.request_async()
    sessions = list(mgr.get_sessions())
    # prefer a session that is actually playing
    cur = next((s for s in sessions if s.get_playback_info().playback_status == 4), None) \
        or mgr.get_current_session()
    if not cur:
        return None
    props = await cur.try_get_media_properties_async()
    tl = cur.get_timeline_properties()
    info = cur.get_playback_info()
    pos = _secs(tl.position)
    # SMTC position is a snapshot; extrapolate while playing
    if info.playback_status == 4 and hasattr(tl, "last_updated_time"):
        try:
            from datetime import datetime, timezone
            pos += (datetime.now(timezone.utc) - tl.last_updated_time).total_seconds()
        except Exception:
            pass
    return {
        "title": props.title, "artist": props.artist, "album": props.album_title,
        "playing": info.playback_status == 4,
        "position": max(0, pos), "duration": _secs(tl.end_time),
        "session_id": cur.source_app_user_model_id,
        "source": cur.source_app_user_model_id.split("!")[-1].replace(".exe", ""),
    }


# Fallback when winrt wheels are unavailable (e.g. brand-new Python): ask
# Windows PowerShell 5.1, which can reach WinRT natively.
_PS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$await = [System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | select -First 1
function Await($op, $t) { $task = $await.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$s = $mgr.GetSessions() | ? { $_.GetPlaybackInfo().PlaybackStatus -eq 'Playing' } | select -First 1
if (-not $s) { $s = $mgr.GetCurrentSession() }
if (-not $s) { '{}'; exit }
$p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
$t = $s.GetTimelineProperties()
$pos = $t.Position.TotalSeconds
$playing = $s.GetPlaybackInfo().PlaybackStatus -eq 'Playing'
if ($playing) { $pos += ([DateTimeOffset]::Now - $t.LastUpdatedTime).TotalSeconds }
@{ title=$p.Title; artist=$p.Artist; album=$p.AlbumTitle; playing=$playing; position=[math]::Max(0,$pos); duration=$t.EndTime.TotalSeconds; source=$s.SourceAppUserModelId; session_id=$s.SourceAppUserModelId } | ConvertTo-Json -Compress
"""


def _windows_ps():
    import json
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                         capture_output=True, timeout=8, creationflags=0x08000000).stdout
    d = json.loads(out.decode("utf-8", "replace") or "{}")
    if d.get("source"):
        d["source"] = d["source"].split("!")[-1].replace(".exe", "")
    return d or None


_PS_ACT = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$await = [System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | select -First 1
function Await($op, $t) { $task = $await.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$s = $mgr.GetSessions() | ? { $_.GetPlaybackInfo().PlaybackStatus -eq 'Playing' } | select -First 1
if (-not $s) { $s = $mgr.GetCurrentSession() }
if ($s) { Await ($s.__ACTION__()) ([bool]) }
"""

WIN_ACTIONS = {"toggle": "TryTogglePlayPauseAsync", "next": "TrySkipNextAsync", "prev": "TrySkipPreviousAsync"}
NIX_ACTIONS = {"toggle": "play-pause", "next": "next", "prev": "previous"}
MAC_ACTIONS = {"toggle": "togglePlayPause", "next": "next", "prev": "previous"}


async def _windows_action(name):
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager)
    mgr = await Manager.request_async()
    cur = next((s for s in mgr.get_sessions() if s.get_playback_info().playback_status == 4), None)         or mgr.get_current_session()
    if cur:
        fn = {"toggle": cur.try_toggle_play_pause_async, "next": cur.try_skip_next_async,
              "prev": cur.try_skip_previous_async}[name]
        return await fn()


def _windows_ps_action(name):
    script = _PS_ACT.replace("__ACTION__", WIN_ACTIONS[name])
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   capture_output=True, timeout=8, creationflags=0x08000000)


_PS_ART = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$await = [System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | select -First 1
function Await($op, $t) { $task = $await.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStreamWithContentType,Windows.Storage.Streams,ContentType=WindowsRuntime]
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$s = $mgr.GetSessions() | ? { $_.GetPlaybackInfo().PlaybackStatus -eq 'Playing' } | select -First 1
if (-not $s) { $s = $mgr.GetCurrentSession() }
if (-not $s) { exit }
$p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
if (-not $p.Thumbnail) { exit }
$st = Await ($p.Thumbnail.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
[void][Windows.Storage.Streams.IInputStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$asStream = [System.IO.WindowsRuntimeStreamExtensions].GetMethods() | ? { $_.Name -eq 'AsStreamForRead' -and $_.GetParameters().Count -eq 1 } | select -First 1
$net = $asStream.Invoke($null, @($st))
$ms = New-Object IO.MemoryStream; $net.CopyTo($ms); $buf = $ms.ToArray()
[Convert]::ToBase64String($buf)
"""


def _windows_art():
    import base64
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_ART],
                         capture_output=True, timeout=10, creationflags=0x08000000).stdout.strip()
    return base64.b64decode(out) if out else None


def _linux_art():
    url = _run(["playerctl", "metadata", "mpris:artUrl"])
    if not url:
        return None
    import urllib.parse, urllib.request
    if url.startswith("file://"):
        with open(urllib.parse.unquote(url[7:]), "rb") as f:
            return f.read()
    return urllib.request.urlopen(url, timeout=5).read()


BROWSERS = ("chrome", "msedge", "edge", "firefox", "brave", "opera", "vivaldi", "arc")


def itunes_lookup(title, artist, album):
    """Song metadata from Apple's public iTunes Search API (no account): real length + cover URL."""
    term = " ".join(filter(None, [title, artist]))
    alb = (album or "").replace(" - Single", "").replace(" - EP", "").strip()
    for country in ("TW", "US", "JP"):
        r = _get_json("https://itunes.apple.com/search?" + _up.urlencode(
            {"term": term, "entity": "song", "limit": 8, "country": country})) or {}
        res = [x for x in r.get("results") or [] if "伴奏" not in x.get("trackName", "")]
        best = next((x for x in res if alb and alb in x.get("collectionName", "")), None) or (res[0] if res else None)
        if best:
            return {"length": (best.get("trackTimeMillis") or 0) / 1000 or None,
                    "art_url": (best.get("artworkUrl100") or "").replace("100x100bb", "600x600bb") or None}
    return {}


def _download(url, limit=None):
    try:
        with _ur.urlopen(_ur.Request(url, headers={"User-Agent": "Mozilla/5.0 Mondesk"}), timeout=8) as r:
            if limit is None:
                return r.read()
            body = r.read(limit + 1)
            return body if len(body) <= limit else None
    except Exception:
        return None


def _image_type(b):
    """MIME type of a picture by its first bytes, or None when it isn't one."""
    if b[:3] == b"\xff\xd8\xff": return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    if b[:6] in (b"GIF87a", b"GIF89a"): return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "image/webp"
    if b[4:12] in (b"ftypavif", b"ftypavis"): return "image/avif"
    return None


def _sniff(b):
    return "image/png" if b[1:4] == b"PNG" else "image/jpeg"


# ---- helpers for the iTunes lookup (cover art + real song length) ----
import json as _json
import urllib.parse as _up
import urllib.request as _ur


def _get_json(url, headers=None):
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 Mondesk", **(headers or {})})
    try:
        return _json.load(_ur.urlopen(req, timeout=8))
    except Exception:
        return None


def _linux():
    fmt = "{{status}}\t{{title}}\t{{artist}}\t{{album}}\t{{position}}\t{{mpris:length}}\t{{playerName}}"
    out = _run(["playerctl", "metadata", "--format", fmt])
    if not out:
        return None
    st, title, artist, album, pos, length, player = (out.split("\t") + [""] * 7)[:7]
    return {
        "title": title, "artist": artist, "album": album, "playing": st == "Playing",
        "position": int(pos or 0) / 1e6, "duration": int(length or 0) / 1e6, "source": player,
    }


def _mac():
    out = _run(["nowplaying-cli", "get", "title", "artist", "album", "elapsedTime", "duration", "playbackRate"])
    lines = (out.splitlines() + [""] * 6)[:6]
    if not lines[0] or lines[0] == "null":
        return None
    f = lambda v: float(v) if v not in ("", "null") else 0
    return {"title": lines[0], "artist": lines[1], "album": lines[2], "position": f(lines[3]),
            "duration": f(lines[4]), "playing": f(lines[5]) > 0, "source": ""}


class Module(BaseModule):
    type = "media"
    default_interval = 2

    def start(self):
        self.err = None
        if sys.platform == "win32":
            try:
                import winrt.windows.media.control  # noqa: F401
                self.win = lambda: asyncio.run(_windows())
                self.win_act = lambda a: asyncio.run(_windows_action(a))
            except ImportError:
                self.win = _windows_ps
                self.win_act = _windows_ps_action
        elif sys.platform.startswith("linux") and not shutil.which("playerctl"):
            self.err = "請安裝 playerctl（sudo apt install playerctl）"
        elif sys.platform == "darwin" and not shutil.which("nowplaying-cli"):
            self.err = "請安裝 nowplaying-cli（brew install nowplaying-cli）"

    def poll(self):
        from .apple_bridge import bridge
        browser = bridge.snapshot()
        if browser and browser.get('playing'):
            return self._apple_poll()
        if self.err:
            if browser:
                return self._apple_poll()
            return {"_status": "offline", "message": self.err}
        if sys.platform == "win32":
            np = self.win()
        elif sys.platform == "darwin":
            np = _mac()
        else:
            np = _linux()
        if browser and (not np or not np.get('playing') or np.get('title') == browser.get('title')):
            return self._apple_poll()
        if not np or not np.get("title"):
            return {"_status": "idle", "message": "目前沒有播放"}
        key = (np.get('source'), np.get('session_id'), np.get('title'), np.get('artist'), np.get('album'))
        if key != getattr(self, "art_key", None):
            self.art_key, self.art, self.lyrics = key, None, None
            self.meta, self.first_dur = {}, np.get("duration")
            # where the (possibly playlist-wide) clock stood when this track began;
            # unknown for the track already playing when Mondesk started
            self.base = np.get("position") if getattr(self, "seen_change", False) else None
            self.seen_change = True
            threading.Thread(target=self._load_meta, args=(key, dict(np)), daemon=True).start()
        np["duration"] = max(0.0, float(np.get("duration") or 0))
        raw_position = np.get("position",0)
        self._fix_timeline(np)
        np["duration"] = max(0.0, float(np.get("duration") or 0))
        if self.art:
            np["art"] = abs(hash(key)) % 10**9
        np["lyrics"] = "unavailable"
        np['browser_bridge'] = False
        np["track"] = abs(hash(key)) % 10**9
        np["progress"] = round(np["position"] / np["duration"] * 100) if np.get("duration") else None
        np["_status"] = "ok" if np["playing"] else "idle"
        np["sampled"] = time.time()
        self.last_media = {**np, "_seek_offset": raw_position - np.get("position",0)}
        self.last_media['browser_bridge'] = False
        return np

    def _apple_poll(self):
        from .apple_bridge import bridge
        data = bridge.snapshot()
        if not data:
            self.lyrics = None
            self.last_media = None
            return {'_status': 'offline', 'message': '請連接 Chrome 的 Apple Music 擴充功能'}
        lines, plain = data.pop('lines', None), data.pop('plain', None)
        # The page sometimes reports a frame without lyrics; once Apple gave synced lines for
        # this track, keep them so the view never flips to another source's timing.
        kept = getattr(self, 'apple_lines', None)
        if lines:
            self.apple_lines = (data['track'], lines)
        elif kept and kept[0] == data['track']:
            lines = kept[1]
        self.lyrics ={'source': 'Apple Music', 'synced': lines} if lines else ({'source': 'Apple Music', 'plain': plain} if plain else None)
        # Include lyric revision so opening the native panel refreshes an already-open view.
        revision = abs(hash(_json.dumps([self.lyrics, data.get('native_diagnostic')], ensure_ascii=False)))
        source = data.get('source') or 'Apple Music'
        data.update(source=source, browser_bridge=True, lyrics='ok' if self.lyrics else 'native_missing' if source == 'Apple Music' else 'unavailable',
                    lyrics_revision=revision, sampled=time.time(),
                    progress=round(data['position'] / data['duration'] * 100) if data['duration'] else None)
        remote = data.pop('art_remote', '')
        self.cover_url = remote
        if remote and not data.get('art_url'):
            import zlib
            data['art_url'] = f"/api/asset/{self.id}/cover?v={zlib.crc32(remote.encode())}"
        data['_status'] = 'ok' if data['playing'] else 'idle'
        # Chrome keeps running the extension it loaded until "Reload" is pressed on
        # chrome://extensions, so a Mondesk update alone doesn't reach the browser: say so
        expected = extension_version()
        data['ext_expected'] = expected
        data['ext_outdated'] = bool(expected) and data.get('ext') != expected
        self.last_media = dict(data)
        return data

    def _fix_timeline(self, np):
        """Apple Music web reports a playlist-wide clock: 'position' counts up across tracks
        and 'duration' moves with it. Detect that (duration changes mid-track, or is longer
        than the real song) and rebuild the in-track position."""
        dur, pos = np.get("duration") or 0, np.get("position") or 0
        length = max(0.0,float((getattr(self,"meta",None) or {}).get("length") or 0))
        if dur <= 0:
            np["duration"] = length or 0
            return
        drifting = self.first_dur and abs(dur - self.first_dur) > 2
        if not drifting:
            return
        if self.base is not None:
            np["position"] = max(0.0, pos - self.base)
        elif length:
            np["position"] = max(0.0, length - (dur - pos))  # best guess for a track joined midway
        np["position"] = min(np["position"], length or np["position"])
        np["duration"] = length or 0
        np["timeline_estimated"] = self.base is None

    def _load_meta(self, key, np):
        # 1) real length (fixes broken browser timelines)
        try:
            meta = itunes_lookup(np.get("title"), np.get("artist"), np.get("album"))
        except Exception:
            meta = {}
        if key != self.art_key:
            return
        self.meta = meta
        # 2) cover: system thumbnail, unless a browser only gave its own icon
        try:
            data = _windows_art() if sys.platform == "win32" else _linux_art() if not sys.platform == "darwin" else None
        except Exception:
            data = None
        src = (np.get("source") or "").lower()
        if (not data or (any(b in src for b in BROWSERS) and _sniff(data) == "image/png" and len(data) < 40000))                 and meta.get("art_url"):
            data = _download(meta["art_url"]) or data
        if data and key == self.art_key:
            self.art = data

    def stream_frame(self):
        """Latest mirrored video frame for /api/stream/<id>; asking marks the video as watched,
        which tells the browser extension to keep sending frames."""
        from .apple_bridge import bridge
        return bridge.watch()

    def asset(self, name):
        if name == "lyrics":
            ly = getattr(self, "lyrics", None)
            return (_json.dumps(ly or {}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        if name == "cover":
            # the thumbnail of the video the browser is playing, fetched here (see apple_bridge art_remote)
            url = getattr(self, "cover_url", "")
            if not url:
                return None
            if getattr(self, "cover_cache", (None,))[0] != url:
                body = _download(url, limit=4 * 1024 * 1024)
                self.cover_cache = (url, body if body and _image_type(body) else None)
            body = self.cover_cache[1]
            return (body, _image_type(body)) if body else None
        return (self.art, _sniff(self.art)) if getattr(self, "art", None) else None

    def action(self, name, position=None, track=None, value=None):
        if name == 'side_screen':
            # the extension moves the video tab to the side screen, fullscreen (again: back)
            snapshot = getattr(self, 'last_media', None) or {}
            if not snapshot.get('browser_bridge'):
                raise RuntimeError('在影片分頁按 Alt+Shift+D 送到副螢幕')
            from .apple_bridge import bridge
            bridge.action('side-screen', track if track is not None else snapshot['track'])
            return name
        if (getattr(self, 'last_media', None) or {}).get('browser_bridge'):
            from .apple_bridge import bridge
            from .media_seek import target_seconds
            snapshot = getattr(self, 'last_media', None)
            if not snapshot:
                raise RuntimeError('播放器尚未連接')
            if track is not None and track != snapshot.get('track'):
                raise RuntimeError('播放來源已變更，請稍後再試')
            if name == 'volume':
                # the volume of the video in the tab itself (video page on the panel); the system volume is untouched
                bridge.action('volume', track if track is not None else snapshot['track'], value=value)
                return name
            if name not in ('seek', 'seek_time', 'toggle', 'prev', 'next'):
                raise ValueError(name)
            if name not in ('seek', 'seek_time') and not self.err:
                # OS media controls (same path as keyboard media keys): Chrome serves them even
                # when it throttles a paused background tab, which made the extension miss
                # commands after a few minutes of pause. The extension is only the fallback.
                if sys.platform == 'win32':
                    self.win_act(name)
                elif sys.platform == 'darwin':
                    _run(['nowplaying-cli', MAC_ACTIONS[name]])
                else:
                    _run(['playerctl', NIX_ACTIONS[name]])
                return name
            if name in ('seek', 'seek_time'):
                position = target_seconds(position, snapshot.get('duration'))
            bridge.action(name, track if track is not None else snapshot['track'], position)
            return self._apple_poll() if name in ('seek', 'seek_time') else name
        if name == "seek":
            from .media_seek import seek
            snapshot = getattr(self,"last_media",None)
            if not snapshot or track != snapshot.get("track"):
                raise RuntimeError("歌曲已變更，請重新點擊歌詞")
            target = seek(snapshot,position)
            for attempt in range(5):
                time.sleep(.4)
                data = self.poll()
                if data.get("track") != track:
                    raise RuntimeError("歌曲已變更，請重新點擊歌詞")
                if abs(data.get("position",-100)-target)<4:
                    return data
            raise RuntimeError("播放器未回報跳轉成功，字幕會繼續跟隨實際播放")
        if name not in WIN_ACTIONS:
            raise ValueError(name)
        if self.err:
            raise RuntimeError(self.err)
        if sys.platform == "win32":
            self.win_act(name)
        elif sys.platform == "darwin":
            _run(["nowplaying-cli", MAC_ACTIONS[name]])
        else:
            _run(["playerctl", NIX_ACTIONS[name]])
        return name
