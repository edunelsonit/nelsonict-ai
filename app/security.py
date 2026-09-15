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


def knowledge_access(identifier, user_id, write=False, conn=None):
    sql = ("SELECT k.*,CASE WHEN k.user_id=? THEN 'owner' ELSE m.permission END permission "
           "FROM knowledge_bases k LEFT JOIN knowledge_members m ON m.kb_id=k.id AND m.user_id=? "
           "WHERE k.id=? AND (k.user_id=? OR m.user_id=?)")
    params = (user_id, user_id, identifier, user_id, user_id)
    row = dict(r) if conn and (r := conn.execute(sql, params).fetchone()) else None
    if conn is None:
        row = db.one(sql, params)
    if not row:
        raise HTTPException(404, "Knowledge base not found.")
    if write and row["permission"] not in ("owner", "editor"):
        raise HTTPException(403, "Editor access required.")
    return row


def owned_document(identifier, user_id, write=False, owner_only=False):
    row = db.one("SELECT id,kb_id,name,status,format FROM documents WHERE id=?", (identifier,))
    if not row:
        raise HTTPException(404, "Document not found.")
    knowledge = knowledge_access(row["kb_id"], user_id, write)
    if owner_only and knowledge["permission"] != "owner":
        raise HTTPException(403, "Only the collection owner can delete documents.")
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
