import subprocess
import sys
import time
import portalocker
from . import db
from .config import settings


def claim():
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT id FROM documents WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if row:
            conn.execute("UPDATE documents SET status='processing',progress=0,error=NULL WHERE id=?", (row["id"],))
            return row["id"]


def run():
    db.initialize()
    with portalocker.Lock(str(settings.data_dir / "worker.lock"), timeout=0):
        db.execute("UPDATE documents SET status='queued',progress=0 WHERE status='processing'")
        while True:
            db.set_setting("worker_heartbeat", time.time())
            identifier = claim()
            if identifier is None:
                time.sleep(2)
                continue
            process = subprocess.Popen([sys.executable, "-m", "app.index_document", str(identifier)])
            started = time.monotonic()
            try:
                while process.poll() is None:
                    db.set_setting("worker_heartbeat", time.time())
                    if time.monotonic() - started > settings.index_timeout:
                        process.kill()
                        process.wait()
                        db.execute("UPDATE documents SET status='failed',error='Processing time limit exceeded.' WHERE id=?",
                                   (identifier,))
                        break
                    time.sleep(2)
                row = db.one("SELECT status FROM documents WHERE id=?", (identifier,))
                if row and row["status"] == "processing":
                    db.execute("UPDATE documents SET status='failed',error='Document processor exited unexpectedly.' WHERE id=?",
                               (identifier,))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    run()
