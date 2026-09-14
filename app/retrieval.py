"""Local embeddings and permission-filtered hybrid retrieval."""
import hashlib
import re
import threading
from pathlib import Path
import numpy as np
from . import db
from .config import settings

_lock = threading.Lock()
_embedder = None
_identity = None
_STOP = {"the", "a", "an", "is", "are", "what", "how", "do", "does", "of", "in", "to",
         "and", "for", "please", "tell", "me", "about", "this", "that", "it", "with"}


def chunk_text(text, size=1400, overlap=200):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Character bound also handles languages without spaces.
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def embedding_identity():
    global _embedder, _identity
    if not settings.embedding_model:
        return None
    with _lock:
        if _embedder is None:
            path = Path(settings.embedding_model).resolve()
            if not path.is_dir():
                raise RuntimeError("Local embedding model folder is missing.")
            from sentence_transformers import SentenceTransformer
            digest = hashlib.sha256()
            for item in sorted(path.rglob("*")):
                if item.is_file():
                    digest.update(str(item.relative_to(path)).encode())
                    with item.open("rb") as handle:
                        while data := handle.read(1024 * 1024):
                            digest.update(data)
            _identity = digest.hexdigest()
            _embedder = SentenceTransformer(str(path), local_files_only=True, trust_remote_code=False, device="cpu")
        return _identity


def embed(texts, query=False):
    identity = embedding_identity()
    if identity is None:
        return None, None
    with _lock:
        fn = _embedder.encode_query if query else _embedder.encode_document
        vectors = fn(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    return np.asarray(vectors, dtype="<f4"), identity


def search(user_id, kb_id, question, limit=5):
    # Every candidate, including vectors, is selected only from an owned, ready knowledge base.
    candidates = db.rows(
        "SELECT c.id,c.page,c.text,c.vector,c.embedding_id,d.id document_id,d.name "
        "FROM chunks c JOIN documents d ON d.id=c.document_id JOIN knowledge_bases k ON k.id=d.kb_id "
        "WHERE k.user_id=? AND k.id=? AND d.status='ready' LIMIT ?",
        (user_id, kb_id, settings.max_chunks + 1))
    if len(candidates) > settings.max_chunks:
        raise RuntimeError("Knowledge base exceeds the configured search limit.")
    if not candidates:
        return []
    scores = {}
    tokens = [t for t in re.findall(r"\w+", question.lower()) if t not in _STOP][:24]
    if tokens:
        expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
        hits = db.rows(
            "SELECT c.id FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid "
            "JOIN documents d ON d.id=c.document_id JOIN knowledge_bases k ON k.id=d.kb_id "
            "WHERE chunks_fts MATCH ? AND k.user_id=? AND k.id=? AND d.status='ready' "
            "ORDER BY bm25(chunks_fts) LIMIT 30", (expression, user_id, kb_id))
        for rank, hit in enumerate(hits):
            scores[hit["id"]] = 1 / (60 + rank)
    if settings.embedding_model:
        q, identity = embed([question], query=True)
        semantic = []
        for row in candidates:
            if row["embedding_id"] != identity or row["vector"] is None:
                raise RuntimeError("Embedding model changed. Reindex every document in this knowledge base.")
            vector = np.frombuffer(row["vector"], dtype="<f4")
            if vector.shape != q[0].shape:
                raise RuntimeError("Embedding dimensions differ. Reindex the knowledge base.")
            similarity = float(np.dot(vector, q[0]))
            if similarity >= 0.25:
                semantic.append((similarity, row["id"]))
        for rank, (_, identifier) in enumerate(sorted(semantic, reverse=True)[:30]):
            scores[identifier] = scores.get(identifier, 0) + 1 / (60 + rank)
    lookup = {r["id"]: r for r in candidates}
    result = []
    for identifier in sorted(scores, key=scores.get, reverse=True)[:limit]:
        row = lookup[identifier]
        result.append({"id": f"S{len(result)+1}", "chunk_id": identifier,
                       "document_id": row["document_id"], "name": row["name"],
                       "page": row["page"], "text": row["text"]})
    return result
