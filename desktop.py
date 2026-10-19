import argparse
import json
import os
from pathlib import Path
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
import server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test', metavar='OUTPUT')
    args=parser.parse_args()
    if args.self_test:
        import modules.bambu, modules.media, modules.media_seek, modules.tokens
        import paho.mqtt.client
        import webview
        app=server.App(server.ROOT/'config.example.json')
        http=ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(app))
        threading.Thread(target=http.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{http.server_port}'
        result={'mqtt':True,'window':True,'modules':len(app.hub.modules),'web':urllib.request.urlopen(url).status,'settings':urllib.request.urlopen(url+'/settings.html').status}
        Path(args.self_test).write_text(json.dumps(result),encoding='utf-8')
        http.shutdown();app.hub.stop()
        return
    import webview
    home=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'DeskMon'
    home.mkdir(parents=True,exist_ok=True)
    config=home/'config.json'
    if not config.exists():
        config.write_bytes((server.ROOT/'config.example.json').read_bytes())
    app=server.App(config)
    ThreadingHTTPServer.allow_reuse_address=False
    http=ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(app))
    threading.Thread(target=http.serve_forever,daemon=True).start()
    webview.create_window('DeskMon',f'http://127.0.0.1:{http.server_port}',width=960,height=680,min_size=(640,480),background_color='#141419')
    try: webview.start(gui='edgechromium' if sys.platform=='win32' else None)
    finally: http.shutdown();http.server_close();app.hub.stop()

if __name__=='__main__':
    try: main()
    except Exception:
        import traceback
        folder=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'DeskMon'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'啟動失敗，詳細資訊已存入 DeskMon/error.log。','DeskMon',16)
        raise
