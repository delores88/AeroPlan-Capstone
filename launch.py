#!/usr/bin/env python3
"""Start AeroPlan locally with an exclusive workspace lock."""
import argparse, logging, sys, threading, webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from app.server import Application,LocalServer

def lock_workspace(folder):
    stream=(folder/'.running.lock').open('a+b')
    stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
    try:
        if sys.platform=='win32':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError('This workspace is already open in AeroPlan.')
    return stream

def main():
    parser=argparse.ArgumentParser(description='AeroPlan Local')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--workspace',type=Path,default=ROOT/'workspace-v22')
    a=parser.parse_args()
    if sys.version_info<(3,10):parser.error('Python 3.10 or newer is required.')
    if not 1024<=a.port<=65535:parser.error('Choose a port between 1024 and 65535.')
    a.workspace.mkdir(parents=True,exist_ok=True)
    try:workspace_lock=lock_workspace(a.workspace)
    except RuntimeError as e:print(str(e));return 1
    logging.basicConfig(filename=a.workspace/'aeroplan.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    print('AeroPlan Local | Preparing the local workspace...',flush=True)
    try:server=LocalServer(a.port,None)
    except OSError as e:
        print(f'Cannot open local port {a.port}: {e}\nClose the existing app, or run python launch.py --port 8766.');return 1
    try:app=Application(ROOT,a.workspace)
    except Exception:
        server.server_close();workspace_lock.close();raise
    server.app=app
    url=f'http://127.0.0.1:{a.port}'
    print(f'Open {url}\nData stays in: {a.workspace.resolve()}\nPress Ctrl+C in this window to stop. No cloud service is used.',flush=True)
    if not a.no_browser:threading.Timer(.8,lambda:webbrowser.open(url)).start()
    try:server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:print('\nStopping local application.')
    finally:
        if app.cancel_event:app.cancel_event.set()
        server.server_close()
        workspace_lock.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
