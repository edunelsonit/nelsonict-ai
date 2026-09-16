import argparse
import getpass
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from . import db
from .config import settings


def main():
    parser = argparse.ArgumentParser(description="Nelsonict AI administration")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Start the web app and PDF worker")
    run.add_argument("--host", default=None)
    run.add_argument("--port", type=int, default=None)
    sub.add_parser("setup-token", help="Show local first-run setup token")
    backup = sub.add_parser("backup")
    backup.add_argument("file", type=Path)
    restore = sub.add_parser("restore", help="Restore into a new directory")
    restore.add_argument("file", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    reset = sub.add_parser("reset-password")
    reset.add_argument("username")
    args = parser.parse_args()
    if args.command == "restore":
        from .maintenance import restore_backup
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        restore_backup(args.file, args.destination)
        print(f"Restored to {args.destination.resolve()}")
        print("Set NELSON_DATA_DIR in .env to this folder, then restart.")
        print("Review NELSON_MODELS_DIR, NELSON_EMBEDDING_MODEL and NELSON_ALLOWED_HOSTS.")
        print("Sessions were revoked. Sign in and select a GGUF model in Models.")
        return
    db.initialize()
    if args.command == "setup-token":
        if db.one("SELECT id FROM users LIMIT 1"):
            raise SystemExit("Setup already completed.")
        from .main import bootstrap_token
        print(bootstrap_token())
    elif args.command == "backup":
        from .maintenance import create_backup
        if args.file.exists():
            raise SystemExit("Choose a new filename; backup will not overwrite an existing file.")
        create_backup(args.file)
        print(f"Backup saved to {args.file.resolve()}")
    elif args.command == "reset-password":
        from .security import hasher
        password = getpass.getpass("New password (12–128 characters): ")
        if not 12 <= len(password) <= 128 or password != getpass.getpass("Repeat password: "):
            raise SystemExit("Password length or confirmation invalid.")
        row = db.one("SELECT id FROM users WHERE username=?", (args.username.lower(),))
        if not row:
            raise SystemExit("User not found.")
        with db.connect() as conn:
            conn.execute("UPDATE users SET password=?,disabled=0 WHERE id=?", (hasher.hash(password), row["id"]))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        print("Password updated; existing sessions revoked.")
    else:
        import json
        root = settings.launch_root or settings.data_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        restart_file, stop_file = root / "restart.request", root / "stop.request"
        stop_file.unlink(missing_ok=True)
        os.environ["NELSON_MANAGED_LAUNCH"] = "1"
        processes = []

        def stop_children():
            import psutil
            descendants=[]
            for process in processes:
                try:
                    descendants.extend(psutil.Process(process.pid).children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
                if process.poll() is None:
                    process.terminate()
            for process in descendants:
                try: process.terminate()
                except psutil.NoSuchProcess: pass
            for process in processes:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            _, alive = psutil.wait_procs(descendants, timeout=3)
            for process in alive:
                try: process.kill()
                except psutil.NoSuchProcess: pass
            processes.clear()

        def stop(*_):
            stop_children()
            raise SystemExit(0)
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        try:
            while True:
                restart_file.unlink(missing_ok=True)
                config_path = root / "runtime-settings.json"
                overlay = json.loads(config_path.read_text()) if config_path.exists() else {}
                host = args.host or overlay.get("bind_host", settings.bind_host)
                port = args.port or overlay.get("bind_port", settings.bind_port)
                if getattr(sys, "frozen", False):
                    worker = [sys.executable, "--worker"]
                    api = [sys.executable, "--api", host, str(port)]
                else:
                    worker = [sys.executable, "-m", "app.worker"]
                    api = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port), "--workers", "1"]
                processes.append(subprocess.Popen(worker))
                processes.append(subprocess.Popen(api))
                print(f"Nelsonict AI: http://{host}:{port}", flush=True)
                while all(p.poll() is None for p in processes):
                    if stop_file.exists():
                        stop_file.unlink(missing_ok=True)
                        stop()
                    if restart_file.exists():
                        break
                    time.sleep(0.5)
                restarting = restart_file.exists()
                stop_children()
                if not restarting:
                    break
        finally:
            stop_children()


if __name__ == "__main__":
    main()
