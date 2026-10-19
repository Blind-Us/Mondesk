"""Read one camera frame without publishing any MQTT messages."""
import json
import subprocess
from pathlib import Path
from urllib.parse import quote


def main():
    from imageio_ffmpeg import get_ffmpeg_exe
    config = json.loads((Path(__file__).resolve().parent.parent / 'config.json').read_text(encoding='utf-8'))
    spec = next(m for m in config['modules'] if m['type'] == 'bambu')
    url = f"rtsps://bblp:{quote(spec['access_code'], safe='')}@{spec['ip']}:322/streaming/live/1"
    args = [get_ffmpeg_exe(), '-loglevel', 'error', '-rtsp_transport', 'tcp', '-timeout', '8000000',
            '-i', url, '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1']
    try:
        result = subprocess.run(args, capture_output=True, timeout=14, creationflags=0x08000000 if __import__('sys').platform == 'win32' else 0)
    except subprocess.TimeoutExpired:
        print('camera_probe: timeout after 14 seconds')
        return
    error = result.stderr.decode('utf-8', 'replace')
    for private in (url, spec['access_code'], quote(spec['access_code'], safe=''), spec['ip']):
        error = error.replace(private, '[redacted]')
    print(json.dumps({'returncode': result.returncode, 'jpeg_received': result.stdout.startswith(b'\xff\xd8'), 'error': error[:1800]}, ensure_ascii=True))


if __name__ == '__main__':
    main()
