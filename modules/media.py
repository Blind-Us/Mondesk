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


def _download(url):
    try:
        return _ur.urlopen(_ur.Request(url, headers={"User-Agent": "DeskMon"}), timeout=8).read()
    except Exception:
        return None


def _sniff(b):
    return "image/png" if b[1:4] == b"PNG" else "image/jpeg"


# ---- lyrics (LRCLIB: free, synced LRC) ----
import json as _json
import re as _re
import urllib.parse as _up
import urllib.request as _ur

_LRC = _re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_NOISE = _re.compile(r"[\(\[（【『「].*?[\)\]）】』」]|official.*$|music video|mv|lyrics?|歌詞|動態歌詞", _re.I)


def _lrclib(path, params):
    url = f"https://lrclib.net/api/{path}?" + _up.urlencode(params)
    req = _ur.Request(url, headers={"User-Agent": "DeskMon (github.com/deskmon)"})
    try:
        return _json.load(_ur.urlopen(req, timeout=8))
    except Exception:
        return None


def _parse_lrc(text):
    lines = []
    for raw in (text or "").splitlines():
        stamps = _LRC.findall(raw)
        words = _LRC.sub("", raw).strip()
        if _CREDIT.match(words):
            continue  # drop credits before merging so they never swallow a lyric
        for m, sec in stamps:
            lines.append([int(m) * 60 + float(sec), words])
    offset=_re.search(r"\[offset:([+-]?\d+)\]",text or "",_re.I)
    if offset:
        for line in lines:line[0]=max(0,line[0]-int(offset.group(1))/1000)
    lines.sort(key=lambda l: l[0])
    merged = []
    for t, w in lines:
        if merged and abs(merged[-1][0] - t) < 0.01 and w:
            # bilingual files repeat the timestamp; keep it as one line + translation
            merged[-1].append(w)
        else:
            merged.append([t, w])
    return merged


_CREDIT = _re.compile(r"^\s*[^:：\s]{1,10}\s*[:：]")  # "作词：…", "Composer: …" credit lines


def _get_json(url, headers=None):
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 DeskMon", **(headers or {})})
    try:
        return _json.load(_ur.urlopen(req, timeout=8))
    except Exception:
        return None


def _kugou(title, artist, duration):
    """KuGou public song search + lyric download; best coverage for Chinese songs."""
    import base64
    main_artist=_re.split(r"&|、|,|/",artist or "")[0].strip()
    q = f"{main_artist} {title}".strip()
    r = _get_json("http://mobilecdn.kugou.com/api/v3/search/song?" + _up.urlencode(
        {"keyword": q, "page": 1, "pagesize": 10})) or {}
    songs = ((r.get("data") or {}).get("info")) or []
    cands = [{"name": x.get("songname", ""), "artists": [{"name": x.get("singername", "")}],
              "duration": (x.get("duration") or 0) * 1000, "raw": x} for x in songs]
    for c in _rank(cands, title, artist, duration)[:3]:
        x = c["raw"]
        s = _get_json("https://lyrics.kugou.com/search?" + _up.urlencode({
            "ver": 1, "man": "yes", "client": "pc", "hash": x["hash"],
            "duration": x["duration"] * 1000, "keyword": x.get("filename", "")})) or {}
        for cand in (s.get("candidates") or [])[:3]:
            d = _get_json("https://lyrics.kugou.com/download?" + _up.urlencode({
                "ver": 1, "client": "pc", "id": cand["id"], "accesskey": cand["accesskey"],
                "fmt": "lrc", "charset": "utf8"})) or {}
            try:
                lrc = base64.b64decode(d.get("content", "")).decode("utf-8", "replace")
            except Exception:
                continue
            if _LRC.search(lrc) and len([l for l in _parse_lrc(lrc) if l[1] and not _NOTICE.search(l[1])]) >= 3:
                return {"synced": _parse_lrc(lrc), "source": f"{x.get('singername')} — {x.get('songname')} (KuGou)"}
    return None


def _song_key(value):
    import unicodedata
    value=unicodedata.normalize("NFKC",value or "").casefold()
    try:
        from opencc import OpenCC
        value=OpenCC('t2s').convert(value)
    except ImportError:pass
    return ''.join(c for c in value if c.isalnum())


def _rank(songs, title, artist, duration):
    """Reject other versions before scoring; compare title, performers and length."""
    from difflib import SequenceMatcher
    target=_song_key(_NOISE.sub('',title))
    artists=[_song_key(a) for a in _re.split(r'&|、|,|/| feat\.? | featuring ',artist or '',flags=_re.I) if a.strip()]
    variants=r'dj|remix|\brmx\b|伴奏|instrumental|live|翻唱|cover|降速|加速|混音|串烧|串燒|[01]\.[0-9]x'
    original_flags={m.group().casefold() for m in _re.finditer(variants,title,_re.I)}
    ranked=[]
    for row in songs:
        name=row.get('name','');performers=' '.join(a.get('name','') for a in row.get('artists',[]))
        flags={m.group().casefold() for m in _re.finditer(variants,name,_re.I)}
        if flags-original_flags:continue
        candidate=_song_key(_NOISE.sub('',name))
        similarity=SequenceMatcher(None,target,candidate).ratio()
        if similarity<.85:continue
        seconds=(row.get('duration') or 0)/1000
        delta=abs(seconds-duration) if duration and seconds else 0
        if duration and seconds and delta>max(8,duration*.025):continue
        people=_song_key(performers)
        same_artist=any(a in people or SequenceMatcher(None,a,people).ratio()>.7 for a in artists)
        if artists and not same_artist:continue
        ranked.append(((delta,-similarity),row))
    return [r for _,r in sorted(ranked,key=lambda pair:pair[0])]


def _netease(title, artist, duration):
    """NetEase Cloud Music public search + LRC; strong for Chinese songs."""
    h = {"Referer": "https://music.163.com"}
    r = _get_json("https://music.163.com/api/search/get?" + _up.urlencode(
        {"s": f"{title} {artist or ''}".strip(), "type": 1, "limit": 8}), h) or {}
    songs = _rank((r.get("result") or {}).get("songs") or [], title, artist, duration)
    for song in songs[:3]:
        l = _get_json(f"https://music.163.com/api/song/lyric?id={song['id']}&lv=1", h) or {}
        lrc = (l.get("lrc") or {}).get("lyric")
        if lrc and _LRC.search(lrc) and len([l for l in _parse_lrc(lrc) if l[1] and not _NOTICE.search(l[1])]) >= 3:
            names = "/".join(a["name"] for a in song.get("artists", []))
            return {"synced": _parse_lrc(lrc), "source": f"{names} — {song['name']} (NetEase)"}
    return None


_NOTICE = _re.compile(r"未经|未經|许可|許可|版权|版權|翻唱翻录|翻唱翻錄|音乐人|音樂人|QQ音乐|酷狗|网易云|網易雲|lrc by|歌词贡献", _re.I)


def _junk(line, title):
    t, text = line[0], line[1]
    if _NOTICE.search(text):
        return True
    # "歌名-歌手" / "歌手 - 歌名" header near the start
    head = t < 30 and ("-" in text or "－" in text)
    return head and len(set(_NOISE.sub("", title)) & set(text)) >= max(1, len(set(title)) // 2)


LYRIC_SOURCES = ("lrclib",)  # default: only the open LRCLIB API; KuGou/NetEase are opt-in


def fetch_lyrics(title, artist, album, duration, sources=LYRIC_SOURCES):
    sources = set(sources or ())
    ly = _fetch_lrclib(title, artist, album, duration) if "lrclib" in sources else None
    if not ly or not ly.get("synced"):
        # untimed lyrics can't follow the song: look for a synced version first
        clean = " ".join(_NOISE.sub(" ", title.replace("《", " ").replace("》", " ")).split())
        ly = (("kugou" in sources and _kugou(clean, artist, duration))
              or ("netease" in sources and _netease(clean, artist, duration)) or ly)
    if ly and ly.get("synced"):
        ly["synced"] = [l for l in ly["synced"]
                        if not _CREDIT.match(l[1]) and not _junk(l, title)]
    return ly


def _title_queries(title):
    import unicodedata
    text=unicodedata.normalize("NFKC",title or "")
    clean=" ".join(_NOISE.sub(" ",text).split())
    no_year=_re.sub(r"\s+(?:19|20)\d{2}\s*$","",clean)
    variants=[clean,no_year]
    variants += [p.strip() for p in _re.split(r"[~〜～/|]",no_year) if len(p.strip())>2]
    variants += [_re.sub(r"[~〜～/|]"," ",no_year)]
    return list(dict.fromkeys(v.strip() for v in variants if v.strip()))[:5]


def _fetch_lrclib(title, artist, album, duration):
    import unicodedata
    from difflib import SequenceMatcher
    def normalized(value):return "".join(c for c in unicodedata.normalize("NFKC",value or "").casefold() if c.isalnum())
    def convert(hit):
        source=f"{hit.get('artistName','')} — {hit.get('trackName','')}"
        if hit.get("syncedLyrics"):
            return {"synced":_parse_lrc(hit["syncedLyrics"]),"source":source}
        if hit.get("plainLyrics"):return {"plain":hit["plainLyrics"].splitlines(),"source":source}
    params={"track_name":title,"artist_name":artist}
    if duration:params["duration"]=round(duration)
    hit=_lrclib("get",params) if title and artist else None
    if hit and (hit.get("syncedLyrics") or hit.get("plainLyrics")):return convert(hit)
    target_artist=normalized(artist)
    candidates={}
    variants=_title_queries(title)
    queries=list(dict.fromkeys([f"{v} {artist}".strip() for v in variants]+variants))
    for query in queries:
        result=_lrclib("search",{"q":query})
        if result is None:result=_lrclib("search",{"q":query})
        for row in result or []:
            if not isinstance(row,dict):continue
            if _re.search(r"instrumental|伴奏|カラオケ|off\s*vocal",row.get("trackName", ""),_re.I) and not _re.search(r"instrumental|伴奏|カラオケ|off\s*vocal",title,_re.I):continue
            name=normalized(row.get("trackName"));performer=normalized(row.get("artistName"))
            title_score=max((SequenceMatcher(None,normalized(v),name).ratio() for v in variants),default=0)
            artist_score=SequenceMatcher(None,target_artist,performer).ratio() if target_artist else 1
            if target_artist and artist_score<.55:continue
            if title_score<.45:continue
            delta=abs((row.get("duration") or duration or 0)-(duration or row.get("duration") or 0))
            if duration and delta>max(12,duration*.04):continue
            if not (row.get("syncedLyrics") or row.get("plainLyrics")):continue
            candidates[row.get("id",(name,performer))]=(row,(delta, -artist_score,-title_score))
        if any(r.get("syncedLyrics") for r,_ in candidates.values()):break
    if not candidates:return None
    ranked=sorted(candidates.values(),key=lambda pair:(not bool(pair[0].get("syncedLyrics")),pair[1]))
    return convert(ranked[0][0])


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
        if self.spec.get('apple_music_native'):
            return self._apple_poll()
        if self.err:
            return {"_status": "offline", "message": self.err}
        if sys.platform == "win32":
            np = self.win()
        elif sys.platform == "darwin":
            np = _mac()
        else:
            np = _linux()
        if not np or not np.get("title"):
            return {"_status": "idle", "message": "目前沒有播放"}
        key = f"{np.get('title')}|{np.get('artist')}"
        if key != getattr(self, "art_key", None):
            self.art_key, self.art, self.lyrics, self.lyrics_state = key, None, None, "loading"
            self.meta, self.first_dur = {}, np.get("duration")
            self.lyric_attempts, self.lyric_retry_at = 0, 0
            # where the (possibly playlist-wide) clock stood when this track began;
            # unknown for the track already playing when DeskMon started
            self.base = np.get("position") if getattr(self, "seen_change", False) else None
            self.seen_change = True
            threading.Thread(target=self._load_meta, args=(key, dict(np)), daemon=True).start()
        if self.lyrics_state == "none" and self.lyric_attempts < 3 and time.time() >= self.lyric_retry_at:
            self.lyrics_state = "loading"
            threading.Thread(target=self._retry_lyrics,args=(key,dict(np)),daemon=True).start()
        np["duration"] = max(0.0, float(np.get("duration") or 0))
        raw_position = np.get("position",0)
        self._fix_timeline(np)
        np["duration"] = max(0.0, float(np.get("duration") or 0))
        if self.art:
            np["art"] = abs(hash(key)) % 10**9
        np["lyrics"] = self.lyrics_state
        np["track"] = abs(hash(key)) % 10**9
        np["progress"] = round(np["position"] / np["duration"] * 100) if np.get("duration") else None
        np["_status"] = "ok" if np["playing"] else "idle"
        np["sampled"] = time.time()
        self.last_media = {**np, "_seek_offset": raw_position - np.get("position",0)}
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
        if not lines:
            # Apple has no timing for this song: look up synced lyrics elsewhere and time them
            # with Apple's (accurate) playback position. Apple's own synced lyrics always win.
            if getattr(self, 'fallback_track', None) != data['track']:
                self.fallback_track, self.fallback = data['track'], None
                threading.Thread(target=self._apple_fallback, args=(dict(data),), daemon=True).start()
            if self.fallback and self.fallback.get('synced'):
                self.lyrics = self.fallback
        # Include lyric revision so opening the native panel refreshes an already-open view.
        revision = abs(hash(_json.dumps([self.lyrics, data.get('native_diagnostic')], ensure_ascii=False)))
        data.update(source='Apple Music', lyrics='ok' if self.lyrics else 'native_missing',
                    lyrics_revision=revision, sampled=time.time(),
                    progress=round(data['position'] / data['duration'] * 100) if data['duration'] else None)
        data['_status'] = 'ok' if data['playing'] else 'idle'
        self.last_media = dict(data)
        return data

    def _apple_fallback(self, data):
        try:
            ly = fetch_lyrics(data.get('title'), data.get('artist'), data.get('album'), data.get('duration'), self.spec.get('lyrics_sources', LYRIC_SOURCES))
        except Exception:
            ly = None
        if ly and ly.get('synced') and self.fallback_track == data['track']:
            ly['source'] = (ly.get('source') or '') + '（Apple Music 無同步時間，改用外部歌詞）'
            self.fallback = ly

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
        # 1) real length (fixes broken timelines, helps pick the right lyrics version)
        try:
            meta = itunes_lookup(np.get("title"), np.get("artist"), np.get("album"))
        except Exception:
            meta = {}
        if key != self.art_key:
            return
        self.meta = meta
        reported = np.get("duration") or 0
        length = reported if 0 < reported < 1200 else meta.get("length") or reported
        # 2) lyrics
        try:
            ly = fetch_lyrics(np.get("title"), np.get("artist"), np.get("album"), length, self.spec.get("lyrics_sources", LYRIC_SOURCES))
        except Exception:
            ly = None
        if key == self.art_key:
            self.lyrics, self.lyrics_state = ly, "ok" if ly else "none"
            self.lyric_attempts += 1
            self.lyric_retry_at = time.time() + 30
        # 3) cover: system thumbnail, unless a browser only gave its own icon
        try:
            data = _windows_art() if sys.platform == "win32" else _linux_art() if not sys.platform == "darwin" else None
        except Exception:
            data = None
        src = (np.get("source") or "").lower()
        if (not data or (any(b in src for b in BROWSERS) and _sniff(data) == "image/png" and len(data) < 40000))                 and meta.get("art_url"):
            data = _download(meta["art_url"]) or data
        if data and key == self.art_key:
            self.art = data

    def _retry_lyrics(self,key,np):
        try:ly=fetch_lyrics(np.get("title"),np.get("artist"),np.get("album"),np.get("duration") or (self.meta or {}).get("length"),self.spec.get("lyrics_sources",LYRIC_SOURCES))
        except Exception:ly=None
        if key == self.art_key:
            self.lyrics,self.lyrics_state=ly,"ok" if ly else "none"
            self.lyric_attempts+=1
            self.lyric_retry_at=time.time()+30

    def asset(self, name):
        if name == "lyrics":
            ly = getattr(self, "lyrics", None)
            return (_json.dumps(ly or {}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        return (self.art, _sniff(self.art)) if getattr(self, "art", None) else None

    def action(self, name, position=None, track=None):
        if self.spec.get('apple_music_native'):
            from .apple_bridge import bridge
            from .media_seek import target_seconds
            snapshot = getattr(self, 'last_media', None)
            if not snapshot:
                raise RuntimeError('Apple Music 尚未連接')
            if name not in ('seek', 'toggle', 'prev', 'next'):
                raise ValueError(name)
            if name != 'seek' and not self.err:
                # Use the OS media controls (same path as keyboard media keys). Chrome serves
                # them even when it throttles a paused background Apple Music tab, which made
                # the extension miss commands after a few minutes of pause.
                if sys.platform == 'win32':
                    self.win_act(name)
                elif sys.platform == 'darwin':
                    _run(['nowplaying-cli', MAC_ACTIONS[name]])
                else:
                    _run(['playerctl', NIX_ACTIONS[name]])
                return name
            if name == 'seek':
                position = target_seconds(position, snapshot.get('duration'))
            bridge.action(name, track if name == 'seek' else snapshot['track'], position)
            return self._apple_poll() if name == 'seek' else name
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
