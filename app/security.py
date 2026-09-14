import hashlib
import secrets
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, Request
from . import db

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify(password, encoded):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def current_user(request: Request):
    token = request.cookies.get("nelson_session", "")
    row = db.one(
        "SELECT u.id,u.username,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.expires>? AND u.disabled=0", (token_hash(token), time.time()))
    if not row:
        raise HTTPException(401, "Please sign in.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), row["csrf"]):
            raise HTTPException(403, "Session verification failed. Reload and try again.")
    return row


def administrator(request: Request):
    user = current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")
    return user


def owned(table, identifier, user_id):
    if table not in {"knowledge_bases", "assistants", "conversations"}:
        raise ValueError("Invalid ownership table")
    row = db.one(f"SELECT * FROM {table} WHERE id=? AND user_id=?", (identifier, user_id))
    if not row:
        raise HTTPException(404, "Item not found.")
    return row


def owned_document(identifier, user_id):
    row = db.one(
        "SELECT d.id,d.kb_id,d.name,d.status FROM documents d JOIN knowledge_bases k ON k.id=d.kb_id "
        "WHERE d.id=? AND k.user_id=?", (identifier, user_id))
    if not row:
        raise HTTPException(404, "Document not found.")
    return row


def rate_limit(key, limit=10, window=300):
    now = time.time()
    key = token_hash(key)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM login_attempts WHERE until<?", (now,))
        row = conn.execute("SELECT count FROM login_attempts WHERE key=?", (key,)).fetchone()
        if row and row["count"] >= limit:
            raise HTTPException(429, "Too many attempts. Please wait five minutes.")
        conn.execute(
            "INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1",
            (key, now + window))
