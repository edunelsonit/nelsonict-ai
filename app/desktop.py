"""Desktop launcher; packaged processes share the same per-user bootstrap directory."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request
import webbrowser


def configure():
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'NelsonictAI'
    base.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('NELSON_DATA_DIR',str(base/'data'))
    os.environ.setdefault('NELSON_MODELS_DIR',str(base/'models'))
    if not getattr(sys, 'frozen', False):
        project=str(Path(__file__).resolve().parent.parent)
        os.environ['PYTHONPATH']=project+os.pathsep+os.environ.get('PYTHONPATH','')
    os.chdir(base)
    return base


def child(*args):
    return [sys.executable,*args] if getattr(sys,'frozen',False) else [sys.executable,'-m','app.desktop',*args]


def main():
    base=configure()
    if len(sys.argv)>1:
        option=sys.argv[1]
        if option=='--worker':
            from app.worker import run as worker_main
            worker_main();return
        if option=='--index':
            from app.index_document import index_document
            from app import db
            identifier=int(sys.argv[2])
            try:
                index_document(identifier)
            except Exception as exc:
                db.execute("UPDATE documents SET status='failed',error=? WHERE id=?",(str(exc)[:500],identifier))
                raise SystemExit(1)
            return
        if option=='--api':
            import uvicorn
            uvicorn.run('app.main:app',host=sys.argv[2],port=int(sys.argv[3]),workers=1);return
        if option=='--service':
            from app.cli import main as cli_main
            sys.argv=[sys.argv[0],'run'];cli_main();return
    import tkinter as tk
    from tkinter import messagebox
    from app.config import settings
    root=tk.Tk();root.title('Nelsonict AI');root.geometry('530x440')
    state=tk.StringVar(value='Start your local AI workspace.')
    service=None
    launch_root=settings.launch_root
    def address():
        path=launch_root/'runtime-settings.json'
        values=json.loads(path.read_text()) if path.exists() else {}
        host=values.get('bind_host',settings.bind_host)
        if host in ('0.0.0.0','::'):host='127.0.0.1'
        if ':' in host and not host.startswith('['):host='['+host+']'
        return 'http://'+host+':'+str(values.get('bind_port',settings.bind_port))
    def alive():
        try:
            with urllib.request.urlopen(address()+'/api/health',timeout=2) as response:
                return json.load(response).get('status')=='ok'
        except Exception:
            return False
    def start():
        nonlocal service
        if alive():
            state.set('Nelsonict AI is running. Open the workspace.');return
        if service and service.poll() is None:
            state.set('Starting… Check the desktop-service.log if startup fails.');return
        log=(base/'desktop-service.log').open('ab')
        service=subprocess.Popen(child('--service'),stdout=log,stderr=log)
        log.close();state.set('Starting API and document worker…')
    def copy_setup_token():
        config_path=launch_root/'runtime-settings.json'
        values=json.loads(config_path.read_text()) if config_path.exists() else {}
        token_path=Path(values.get('data_dir',str(settings.data_dir)))/'setup-token.txt'
        if not token_path.exists():
            state.set('No setup token: wait for startup, or sign in to your existing account.');return
        root.clipboard_clear();root.clipboard_append(token_path.read_text().strip())
        state.set('Setup token copied. Paste it into the first-run form in your workspace.')
    def stop():
        launch_root.mkdir(parents=True,exist_ok=True)
        (launch_root/'stop.request').touch();state.set('Stop requested. Active requests will be interrupted.')
    def restart():
        if alive():(launch_root/'restart.request').touch();state.set('Restart requested.')
        else:start()
    def startup():
        if sys.platform=='win32':
            import winreg
            key=winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run')
            try:
                if auto.get():winreg.SetValueEx(key,'NelsonictAI',0,winreg.REG_SZ,subprocess.list2cmdline(child('--service')))
                else:
                    try:winreg.DeleteValue(key,'NelsonictAI')
                    except FileNotFoundError:pass
            finally:winreg.CloseKey(key)
        else:
            import shlex
            dest=Path.home()/'.config'/'autostart'/'nelsonict-ai.desktop';dest.parent.mkdir(parents=True,exist_ok=True)
            if auto.get():
                # Packaged executable is installed at a fixed path without spaces.
                command='/opt/nelsonict-ai/nelsonict-ai --service'
                dest.write_text('[Desktop Entry]\nType=Application\nName=Nelsonict AI\nExec='+command+'\nTerminal=false\n')
            else:dest.unlink(missing_ok=True)
        state.set('Automatic startup preference saved for this user.')
    def startup_enabled():
        if sys.platform=='win32':
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                    winreg.QueryValueEx(key,'NelsonictAI');return True
            except FileNotFoundError:return False
        return (Path.home()/'.config'/'autostart'/'nelsonict-ai.desktop').exists()
    tk.Label(root,text='NELSONICT AI',font=('Arial',22,'bold')).pack(pady=18)
    tk.Label(root,textvariable=state,wraplength=490).pack(pady=8)
    for label,fn in [('Start application',start),('Open workspace',lambda:webbrowser.open(address())),('Copy first-run setup token',copy_setup_token),('Restart application',restart),('Stop application',stop),('Check for updates',lambda:webbrowser.open('https://github.com/edunelsonit/nelsonict-ai/releases/latest'))]:
        tk.Button(root,text=label,command=fn,width=30).pack(pady=3)
    auto=tk.BooleanVar(value=startup_enabled())
    tk.Checkbutton(root,text='Start automatically when I sign in',variable=auto,command=startup).pack(pady=8)
    tk.Label(root,text='Updates open the official release page. Back up, stop the app,\nthen install the matching package. Your per-user data is retained.').pack()
    # Closing the launcher does not terminate the background service.
    root.after(100,start)
    root.mainloop()


if __name__=='__main__':
    main()
