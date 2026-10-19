"""Seek the real OS media session, never shift only the displayed lyrics."""
import asyncio,base64,json,math,subprocess,sys

def target_seconds(value,duration):
    if isinstance(value,bool): raise ValueError("無效的播放時間")
    value=float(value)
    if not math.isfinite(value) or value<0 or duration and duration>0 and value>duration:
        raise ValueError("無效的播放時間")
    return value

async def _native(snapshot,position):
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
    manager=await Manager.request_async()
    session=next((s for s in manager.get_sessions() if s.source_app_user_model_id==snapshot.get("session_id")),None)
    if session is None: raise RuntimeError("播放來源已變更")
    props=await session.try_get_media_properties_async()
    if props.title!=snapshot.get("title") or props.artist!=snapshot.get("artist"):
        raise RuntimeError("歌曲已變更，請重新點擊歌詞")
    if not await session.try_change_playback_position_async(round(position*10000000)):
        raise RuntimeError("這個播放器不支援跳轉")
    if not await session.try_play_async(): raise RuntimeError("播放器無法開始播放")

_PS=r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$await=[System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | select -First 1
function Await($op,$t){$task=$await.MakeGenericMethod($t).Invoke($null,@($op));$task.Wait(-1)|Out-Null;$task.Result}
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
$d=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__DATA__'))|ConvertFrom-Json
$mgr=Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$s=$mgr.GetSessions()|?{$_.SourceAppUserModelId -eq $d.session_id}|select -First 1
if(-not $s){throw 'Media source changed'}
$p=Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
if($p.Title -cne $d.title -or $p.Artist -cne $d.artist){throw 'Track changed'}
$ok=Await ($s.TryChangePlaybackPositionAsync([long][math]::Round($d.position*10000000))) ([bool])
if(-not $ok){throw 'Seek rejected'}
$playing=Await ($s.TryPlayAsync()) ([bool])
if(-not $playing){throw 'Play rejected'}
'{"ok":true}'
"""

def seek(snapshot,position):
    position=target_seconds(position,snapshot.get("duration"))
    absolute=position+snapshot.get("_seek_offset",0)
    if sys.platform=='win32':
        try: asyncio.run(_native(snapshot,absolute))
        except ImportError:
            data={k:snapshot.get(k,"") for k in ['session_id','title','artist']};data['position']=absolute
            payload=base64.b64encode(json.dumps(data).encode()).decode()
            result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',_PS.replace('__DATA__',payload)],capture_output=True,timeout=10,creationflags=0x08000000)
            if result.returncode or not json.loads(result.stdout.decode('utf-8-sig') or '{}').get('ok'):
                raise RuntimeError('播放器拒絕跳轉，或目前歌曲已切換')
    elif sys.platform.startswith('linux'):
        prefix=['playerctl','--player',snapshot['source']]
        title=subprocess.run(prefix+['metadata','xesam:title'],capture_output=True,text=True,timeout=3)
        if title.returncode or title.stdout.strip()!=snapshot['title']:raise RuntimeError('歌曲已變更')
        for args in [['position',str(absolute)],['play']]:
            result=subprocess.run(prefix+args,capture_output=True,timeout=4)
            if result.returncode:raise RuntimeError('這個播放器不支援跳轉')
    else:raise RuntimeError('這個系統尚未支援歌詞跳轉')
    return position
