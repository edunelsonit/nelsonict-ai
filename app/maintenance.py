"""Consistent snapshots and offline restore into a NEW data directory."""
import hashlib
import json
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from . import db
from .config import settings


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while data := handle.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def create_backup(destination):
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "nelsonict.sqlite3"
        with db.connect() as source:
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
        manifest = {"format": "nelsonict-ai", "version": 1, "created": time.time(),
                    "sha256": checksum(snapshot), "models_included": False,
                    "embedding_configured": bool(settings.embedding_model)}
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "nelsonict.sqlite3")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return manifest


def restore_backup(archive_path, destination):
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Restore requires a new or empty data directory; existing data is never overwritten.")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if sorted(names) != ["manifest.json", "nelsonict.sqlite3"]:
            raise ValueError("Unexpected or duplicate backup archive entries.")
        if archive.getinfo("manifest.json").file_size > 10000:
            raise ValueError("Invalid manifest size.")
        if archive.getinfo("nelsonict.sqlite3").file_size > 2 * 1024**3:
            raise ValueError("Backup exceeds the 2 GiB restore limit.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "nelsonict-ai" or manifest.get("version") != 1:
            raise ValueError("Unsupported backup format.")
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            snapshot = Path(temporary) / "nelsonict.sqlite3"
            # Never extract paths from an archive.
            with archive.open("nelsonict.sqlite3") as source, snapshot.open("wb") as target:
                while data := source.read(1024 * 1024):
                    target.write(data)
            if checksum(snapshot) != manifest["sha256"]:
                raise ValueError("Backup checksum verification failed.")
            conn = sqlite3.connect(snapshot)
            try:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup database failed its integrity check.")
                if conn.execute("PRAGMA user_version").fetchone()[0] not in (1, 2, 3):
                    raise ValueError("Unsupported database schema.")
                if conn.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Backup contains invalid references.")
                with conn:
                    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if 'public_sites' in tables:
                        conn.execute("UPDATE public_sites SET enabled=0")
                    if 'eval_runs' in tables:
                        conn.execute("UPDATE eval_runs SET status='interrupted' WHERE status IN ('queued','running')")
                    conn.execute("DELETE FROM sessions")
                    conn.execute("DELETE FROM login_attempts")
                    conn.execute("UPDATE documents SET status='queued',progress=0 WHERE status='processing'")
                    conn.execute("UPDATE messages SET status='interrupted' WHERE status='generating'")
                    conn.execute("DELETE FROM settings WHERE key IN ('model_config','worker_heartbeat','model_test_passed','wizard_complete')")
                conn.execute("PRAGMA journal_mode=DELETE")
            finally:
                conn.close()
            destination.mkdir(parents=True, exist_ok=True)
            # Exclusive create prevents a concurrent restore overwriting an existing DB.
            with snapshot.open("rb") as source, (destination / "nelsonict.sqlite3").open("xb") as target:
                while data := source.read(1024 * 1024):
                    target.write(data)
    return manifest
