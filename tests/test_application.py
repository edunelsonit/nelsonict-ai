import io
import sqlite3
import zipfile
import pytest
from reportlab.pdfgen import canvas
from app import db
from app.config import settings
from app.index_document import index_document
from app.inference import runtime
from app.maintenance import create_backup, restore_backup
from app.retrieval import chunk_text, search
from app.worker import claim
from conftest import sign_in


def pdf_bytes(text="Nelsonict provides MikroTik hotspot training and practical network workshops."):
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(40, 750, text)
    pdf.save()
    return stream.getvalue()


def upload(admin, kb, payload=None):
    return admin.post(f"/api/knowledge/{kb}/documents", content=payload or pdf_bytes(),
                      headers={"Content-Type":"application/pdf","X-Filename":"training.pdf"})


def indexed(admin, kb):
    result = upload(admin, kb)
    assert result.status_code == 202, result.text
    identifier = result.json()["id"]
    assert claim() == identifier
    index_document(identifier)
    return identifier


def test_first_run_is_protected(client):
    assert client.get("/api/setup").json()["required"]
    result = client.post("/api/setup",json={"username":"owner","password":"correct-password-123","setup_token":"x"*32})
    assert result.status_code == 403
    assert client.get("/api/knowledge").status_code == 401


def test_setup_cannot_be_reclaimed(admin):
    assert not admin.get("/api/setup").json()["required"]
    assert admin.post("/api/setup",json={"username":"other","password":"correct-password-123","setup_token":"x"*32}).status_code == 409


def test_csrf_required(admin):
    csrf = admin.headers.pop("X-CSRF-Token")
    assert admin.post("/api/knowledge",json={"name":"No"}).status_code == 403
    admin.headers["X-CSRF-Token"] = csrf
    assert admin.post("/api/knowledge",json={"name":"Yes"}).status_code == 201


def test_cross_origin_rejected(admin):
    assert admin.post("/api/knowledge",json={"name":"Bad"},headers={"Origin":"https://attacker.example"}).status_code == 403


def test_password_hash_and_logout(admin):
    assert db.one("SELECT password FROM users")["password"].startswith("$argon2id$")
    assert admin.post("/api/logout").status_code == 200
    assert admin.get("/api/me").status_code == 401


def test_user_isolation(admin,kb):
    document=indexed(admin,kb)
    assistant=admin.post("/api/assistants",json={"name":"Tutor","kb_id":kb}).json()["id"]
    convo=admin.post("/api/conversations",json={"assistant_id":assistant}).json()["id"]
    assert admin.post("/api/users",json={"username":"member","password":"member-password-123"}).status_code == 201
    sign_in(admin,"member","member-password-123")
    assert admin.get("/api/knowledge").json() == []
    assert admin.get("/api/conversations").json() == []
    for path in [f"/knowledge/{kb}/documents",f"/documents/{document}/download",f"/conversations/{convo}/messages"]:
        assert admin.get("/api"+path).status_code == 404
    assert admin.delete(f"/api/documents/{document}").status_code == 404
    assert admin.post("/api/assistants",json={"name":"Steal","kb_id":kb}).status_code == 404
    assert admin.get("/api/models").status_code == 403
    assert admin.get("/api/backup").status_code == 403
    assert search(2,kb,"MikroTik") == []


def test_invalid_pdf_and_upload_limit(admin,kb,monkeypatch):
    assert upload(admin,kb,b"not a PDF").status_code == 400
    monkeypatch.setattr(settings,"max_upload_mb",1)
    assert upload(admin,kb,b"%PDF-"+b"x"*(1024*1024)).status_code == 413


def test_duplicate_pdf(admin,kb):
    payload=pdf_bytes()
    assert upload(admin,kb,payload).status_code == 202
    assert upload(admin,kb,payload).status_code == 409


def test_quota_is_enforced(admin,kb,monkeypatch):
    monkeypatch.setattr(settings,"user_storage_mb",0)
    assert upload(admin,kb).status_code == 413


def test_real_pdf_index_search_delete(admin,kb):
    identifier=indexed(admin,kb)
    assert db.one("SELECT status FROM documents WHERE id=?",(identifier,))["status"] == "ready"
    sources=search(1,kb,"MikroTik hotspot training")
    assert sources and sources[0]["page"] == 1 and "MikroTik" in sources[0]["text"]
    assert admin.delete(f"/api/documents/{identifier}").status_code == 200
    assert search(1,kb,"MikroTik") == []
    assert db.one("SELECT count(*) n FROM chunks")["n"] == 0


def test_queued_and_reindexed_docs_not_searchable(admin,kb):
    identifier=indexed(admin,kb)
    assert admin.post(f"/api/documents/{identifier}/reindex").status_code == 200
    assert search(1,kb,"MikroTik") == []
    assert claim() == identifier
    index_document(identifier)
    assert len(search(1,kb,"MikroTik")) == 1


def test_deleted_during_index_does_not_reappear(admin,kb,monkeypatch):
    identifier=upload(admin,kb).json()["id"]
    claim()
    from app import index_document as module
    original=module.extract_pages
    def extracting(pdf):
        yield from original(pdf)
        db.execute("DELETE FROM documents WHERE id=?",(identifier,))
    monkeypatch.setattr(module,"extract_pages",extracting)
    index_document(identifier)
    assert not db.one("SELECT id FROM documents WHERE id=?",(identifier,))
    assert db.one("SELECT count(*) n FROM chunks")["n"] == 0


def test_chunking_handles_long_words_and_overlap():
    parts=chunk_text("A"*5000)
    assert len(parts)>1 and max(map(len,parts))<=1400
    assert chunk_text("   ") == []


def test_missing_model_and_path_traversal(admin):
    convo=admin.post("/api/conversations",json={}).json()["id"]
    result=admin.post(f"/api/conversations/{convo}/chat",json={"content":"Hello","mode":"general"})
    assert result.status_code == 409
    assert admin.get(f"/api/conversations/{convo}/messages").json() == []
    with pytest.raises(ValueError):
        runtime.path("../outside.gguf")


def fake_model(monkeypatch):
    class Fake:
        def tokenize(self,text):
            return list(text[::4])
    runtime.model=Fake()
    runtime.config={"context":4096,"max_tokens":512,"temperature":0.3,"filename":"test.gguf"}
    monkeypatch.setattr(runtime,"stream",lambda messages,stop: iter(["Training is available ","[S1]."]))


def test_streaming_chat_persists_sources(admin,kb,monkeypatch):
    indexed(admin,kb)
    fake_model(monkeypatch)
    convo=admin.post("/api/conversations",json={}).json()["id"]
    result=admin.post(f"/api/conversations/{convo}/chat",json={"content":"MikroTik training","mode":"documents","kb_id":kb})
    assert result.status_code == 200
    assert '"type": "done"' in result.text
    rows=admin.get(f"/api/conversations/{convo}/messages").json()
    assert len(rows)==2 and rows[-1]["status"]=="complete"
    assert rows[-1]["sources"][0]["name"]=="training.pdf"
    assert rows[-1]["content"]=="Training is available [S1]."
    assert not runtime.gate.locked()


def test_generation_failure_saves_partial_answer(admin,monkeypatch):
    fake_model(monkeypatch)
    def failure(messages,stop):
        yield "Partial"
        raise RuntimeError("inference failed")
    monkeypatch.setattr(runtime,"stream",failure)
    convo=admin.post("/api/conversations",json={}).json()["id"]
    result=admin.post(f"/api/conversations/{convo}/chat",json={"content":"Hello","mode":"general"})
    assert '"type": "error"' in result.text
    row=admin.get(f"/api/conversations/{convo}/messages").json()[-1]
    assert row["status"]=="failed" and row["content"].startswith("Partial")
    assert not runtime.gate.locked()


def test_empty_evidence_abstains(admin,kb,monkeypatch):
    fake_model(monkeypatch)
    def forbidden(*args):
        raise AssertionError("Model must not generate without evidence")
    monkeypatch.setattr(runtime,"stream",forbidden)
    convo=admin.post("/api/conversations",json={}).json()["id"]
    result=admin.post(f"/api/conversations/{convo}/chat",json={"content":"missing subject","mode":"documents","kb_id":kb})
    assert "could not find supporting passages" in result.text


def test_unknown_citations_are_flagged(admin,kb,monkeypatch):
    indexed(admin,kb)
    fake_model(monkeypatch)
    monkeypatch.setattr(runtime,"stream",lambda *args:iter(["Claim [S99]"]))
    convo=admin.post("/api/conversations",json={}).json()["id"]
    result=admin.post(f"/api/conversations/{convo}/chat",json={"content":"MikroTik","mode":"documents","kb_id":kb})
    assert "unsupported reference labels" in result.text


def test_busy_model_does_not_block_controls(admin,monkeypatch):
    fake_model(monkeypatch)
    stop=runtime.reserve(999,1)
    try:
        assert admin.get("/api/knowledge").status_code == 200
        assert admin.post("/api/models/unload").status_code == 409
        assert runtime.cancel(999,1) and stop.is_set()
    finally:
        runtime.release(999)


def test_backup_restore_and_revoked_sessions(admin,kb,tmp_path):
    indexed(admin,kb)
    archive=tmp_path/"backup.zip"
    create_backup(archive)
    destination=tmp_path/"restored"
    restore_backup(archive,destination)
    connection=sqlite3.connect(destination/"nelsonict.sqlite3")
    try:
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0]==1
        assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0]>0
        assert connection.execute("SELECT count(*) FROM sessions").fetchone()[0]==0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    finally:
        connection.close()
    with pytest.raises(ValueError):
        restore_backup(archive,destination)


def test_backup_tamper_and_zip_traversal_rejected(admin,tmp_path):
    archive=tmp_path/"bad.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("../escape","bad")
        z.writestr("manifest.json","{}")
    with pytest.raises(ValueError):
        restore_backup(archive,tmp_path/"restored")
    assert not (tmp_path/"escape").exists()


def test_backup_download(admin):
    result=admin.get("/api/backup")
    assert result.status_code==200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert sorted(archive.namelist())==["manifest.json","nelsonict.sqlite3"]


def test_static_interface_and_security_headers(client):
    result=client.get("/")
    assert result.status_code==200 and "Nelsonict AI" in result.text
    assert "script-src 'self'" in result.headers["content-security-policy"]
    assert client.get("/app.js").status_code==200
