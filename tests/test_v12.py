import io
import json
import sqlite3
import threading
import time
import zipfile
import pytest
from app import db
from app.config import settings
from app.inference import runtime
from app.request_queue import RequestQueue,scheduler
from app.maintenance import create_backup
from conftest import sign_in
from test_application import fake_model,indexed
from test_v11 import add_document,add_member


def settle(predicate,seconds=5):
    deadline=time.monotonic()+seconds
    while not predicate():
        assert time.monotonic()<deadline,'Background operation did not settle'
        time.sleep(.02)


def test_fifo_positions_cancellation_and_limits(admin,monkeypatch):
    fake_model(monkeypatch)
    q=RequestQueue()
    a=q.submit('a',1);b=q.submit('b',2);c=q.submit('c',3)
    q.wait(a)
    assert [r['position'] for r in q.snapshot()['requests']]==[0,2,3]
    assert not q.cancel('b',99)
    assert q.cancel('b',2)
    assert [r['key'] for r in q.snapshot()['requests']]==['a','c']
    q.finish(a);q.wait(c);q.finish(c)
    assert not runtime.gate.locked()
    monkeypatch.setattr(settings,'queue_per_user',1)
    a=q.submit('a',1)
    with pytest.raises(RuntimeError,match='limit'):q.submit('b',1)
    q.cancel('a');q.finish(a)


def test_paused_queue_and_expiration(admin,monkeypatch):
    fake_model(monkeypatch);q=RequestQueue();q.paused=True
    with pytest.raises(RuntimeError,match='paused'):q.submit('a',1)
    q.paused=False;a=q.submit('a',1);a.created-=1000
    with pytest.raises(RuntimeError,match='waiting time'):q.wait(a)
    q.finish(a)


def test_queue_controls_responsive_during_generation(admin,monkeypatch):
    fake_model(monkeypatch)
    ticket=scheduler.submit('chat:123',1);scheduler.wait(ticket)
    try:
        start=time.monotonic()
        assert admin.get('/api/queue').json()['requests'][0]['status']=='running'
        assert admin.post('/api/queue/pause',json={'paused':True}).status_code==200
        assert admin.get('/api/knowledge').status_code==200
        assert time.monotonic()-start<2
        assert admin.post('/api/queue/cancel',json={'key':'chat:123'}).json()['cancelled']
        assert ticket.stop.is_set()
    finally:scheduler.finish(ticket);scheduler.paused=False


def test_waiting_request_rechecks_revoked_knowledge(admin,kb,monkeypatch):
    fake_model(monkeypatch);indexed(admin,kb);add_member(admin,kb)
    q=scheduler.submit('blocker',1);scheduler.wait(q)
    sign_in(admin,'member','member-password-123')
    cid=admin.post('/api/conversations',json={}).json()['id']
    response={}
    thread=threading.Thread(target=lambda:response.update(result=admin.post(f'/api/conversations/{cid}/chat',json={'content':'MikroTik','kb_id':kb,'mode':'documents'})))
    thread.start()
    settle(lambda:len(scheduler.items)==2)
    db.execute('DELETE FROM knowledge_members WHERE user_id=2')
    scheduler.finish(q)
    thread.join(5);assert not thread.is_alive()
    assert 'Knowledge base not found' in response['result'].text
    assert not scheduler.items


def test_feedback_is_owned_and_opt_in(admin,kb,monkeypatch):
    fake_model(monkeypatch)
    cid=admin.post('/api/conversations',json={}).json()['id']
    admin.post(f'/api/conversations/{cid}/chat',json={'content':'hello','mode':'general'})
    mid=db.one("SELECT id FROM messages WHERE role='assistant'")['id']
    assert admin.get('/api/feedback').json()==[]
    assert admin.post(f'/api/messages/{mid}/feedback',json={'rating':'incorrect','note':'Wrong fact'}).status_code==200
    assert admin.get('/api/feedback').json()[0]['note']=='Wrong fact'
    add_member(admin,kb);sign_in(admin,'member','member-password-123')
    assert admin.post(f'/api/messages/{mid}/feedback',json={'rating':'helpful'}).status_code==404
    assert admin.get('/api/feedback').status_code==403
    sign_in(admin)
    admin.delete(f'/api/messages/{mid}/feedback')
    assert admin.get('/api/feedback').json()==[]


def test_evaluation_run_snapshot_and_human_review(admin,kb,monkeypatch):
    indexed(admin,kb);fake_model(monkeypatch)
    qid=admin.post('/api/evaluation/questions',json={'kb_id':kb,'question':'MikroTik','expected':'networking'}).json()['id']
    rid=admin.post('/api/evaluation/runs',json={'question_ids':[qid]}).json()['id']
    settle(lambda:db.one('SELECT status FROM eval_runs WHERE id=?',(rid,))['status'] not in ('queued','running'))
    settle(lambda:not scheduler.items)
    r=admin.get(f'/api/evaluation/runs/{rid}').json()
    assert r['status']=='complete' and r['results'][0]['sources']
    assert 'expected_term_coverage' in r['results'][0]
    assert admin.post(f'/api/evaluation/runs/{rid}/review',json={'question_id':qid,'verdict':'fail','note':'Needs review'}).status_code==200
    assert admin.get(f'/api/evaluation/runs/{rid}').json()['results'][0]['review']=='fail'
    admin.put(f'/api/evaluation/questions/{qid}',json={'kb_id':kb,'question':'Changed question','expected':'changed'})
    assert admin.get(f'/api/evaluation/runs/{rid}').json()['results'][0]['question']=='MikroTik'


def test_evaluation_cross_user_and_revoked_access(admin,kb,monkeypatch):
    indexed(admin,kb);fake_model(monkeypatch);add_member(admin,kb)
    qid=admin.post('/api/evaluation/questions',json={'kb_id':kb,'question':'MikroTik','expected':'networking'}).json()['id']
    sign_in(admin,'member','member-password-123')
    assert admin.post('/api/evaluation/runs',json={'question_ids':[qid]}).status_code==404
    qid=admin.post('/api/evaluation/questions',json={'kb_id':kb,'question':'MikroTik','expected':'networking'}).json()['id']
    db.execute('DELETE FROM knowledge_members WHERE user_id=2')
    assert admin.post('/api/evaluation/runs',json={'question_ids':[qid]}).status_code==404


def backup_bytes(tmp_path):
    path=tmp_path/'backup.zip';create_backup(path);return path.read_bytes()


def test_gui_restore_stages_without_switching_and_activates_on_restart(admin,kb,tmp_path):
    indexed(admin,kb);original=settings.data_dir
    response=admin.post('/api/migration/stage',content=backup_bytes(tmp_path))
    assert response.status_code==201,response.text
    stage=response.json();assert stage['counts']['documents']==1
    assert settings.data_dir==original and admin.get('/api/me').status_code==200
    with sqlite3.connect(stage['data_dir']+'/nelsonict.sqlite3') as conn:
        assert conn.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
    body={'models_dir':str(settings.models_dir),'allowed_hosts':'localhost,127.0.0.1','confirm':'no'}
    assert admin.post('/api/migration/'+stage['id']+'/activate',json=body).status_code==400
    body.update(confirm='RESTORE',context=2048,threads=2,gpu_layers=0)
    assert admin.post('/api/migration/'+stage['id']+'/activate',json=body).status_code==200
    overlay=json.loads((original/'runtime-settings.json').read_text())
    assert overlay['data_dir']==stage['data_dir'] and settings.data_dir==original
    assert admin.delete('/api/migration/'+stage['id']).status_code==409
    with sqlite3.connect(stage['data_dir']+'/nelsonict.sqlite3') as conn:
        assert json.loads(conn.execute("SELECT value FROM settings WHERE key='migration_hardware'").fetchone()[0])['context']==2048


def test_gui_restore_rejects_bad_archive_and_member(admin,kb):
    assert admin.post('/api/migration/stage',content=b'bad zip').status_code==400
    assert list((settings.launch_root/'restores').iterdir())==[]
    add_member(admin,kb);sign_in(admin,'member','member-password-123')
    assert admin.post('/api/migration/stage',content=b'bad').status_code==403
    assert admin.get('/api/migration/settings').status_code==403


def test_restore_discard_and_missing_paths(admin,tmp_path):
    stage=admin.post('/api/migration/stage',content=backup_bytes(tmp_path)).json()
    assert admin.post('/api/migration/'+stage['id']+'/activate',json={'models_dir':'relative','allowed_hosts':'localhost','confirm':'RESTORE'}).status_code==400
    assert admin.delete('/api/migration/'+stage['id']).status_code==200
    assert admin.delete('/api/migration/'+stage['id']).status_code==404


def public_site(admin):
    r=admin.post('/api/public-sites',json={'name':'Website','origins':['https://nelsonict.com.ng']})
    assert r.status_code==201,r.text
    return r.json()


def approve(admin,site,ids,enabled=True):
    return admin.put('/api/public-sites/'+str(site['id']),json={'enabled':enabled,'confirm_public':True,'document_ids':ids,'origins':['https://nelsonict.com.ng']})


def test_public_site_requires_explicit_ready_document_approval(admin,kb):
    private=indexed(admin,kb);site=public_site(admin)
    assert site['kb_id']!=kb
    assert admin.get('/widget/'+str(site['id'])).status_code==404
    assert approve(admin,site,[private]).status_code==400
    assert approve(admin,site,[]).status_code==400
    public=add_document(admin,site['kb_id'],'approved.txt',b'Nelsonict provides MikroTik training.')
    assert approve(admin,site,[public]).status_code==200
    page=admin.get('/widget/'+str(site['id']))
    assert page.status_code==200
    assert 'frame-ancestors https://nelsonict.com.ng' in page.headers['content-security-policy']
    assert 'x-frame-options' not in page.headers
    assert admin.get('/').headers['x-frame-options']=='DENY'


def test_public_answers_never_search_private_or_unapproved_documents(admin,kb,monkeypatch):
    fake_model(monkeypatch)
    add_document(admin,kb,'secret.txt',b'MikroTik private confidential value secret-78123.')
    site=public_site(admin)
    pub=add_document(admin,site['kb_id'],'approved.txt',b'MikroTik training is available at Nelsonict.')
    add_document(admin,site['kb_id'],'draft.txt',b'MikroTik draft confidential value draft-99123.')
    assert approve(admin,site,[pub]).status_code==200
    admin.cookies.clear();admin.headers.pop('X-CSRF-Token',None)
    result=admin.post(f'/api/public/{site["id"]}/chat',json={'question':'MikroTik'})
    assert result.status_code==200,result.text
    assert 'approved.txt' in result.text
    assert 'secret-78123' not in result.text and 'draft-99123' not in result.text
    assert '/download' not in result.text
    assert not db.rows('SELECT * FROM conversations')
    assert not scheduler.items


def test_public_no_approved_evidence_does_not_fall_back(admin,kb,monkeypatch):
    fake_model(monkeypatch);site=public_site(admin)
    pub=add_document(admin,site['kb_id'],'approved.txt',b'MikroTik approved.')
    approve(admin,site,[pub]);db.execute("UPDATE documents SET sha256='changed' WHERE id=?",(pub,))
    result=admin.post(f'/api/public/{site["id"]}/chat',json={'question':'MikroTik'})
    assert 'No supporting information' in result.text and 'approved.txt' not in result.text


def test_public_disable_and_backup_restore_disable_publication(admin,tmp_path):
    site=public_site(admin);pub=add_document(admin,site['kb_id'],'approved.txt',b'MikroTik approved.')
    approve(admin,site,[pub]);stage=admin.post('/api/migration/stage',content=backup_bytes(tmp_path)).json()
    with sqlite3.connect(stage['data_dir']+'/nelsonict.sqlite3') as conn:
        assert conn.execute('SELECT enabled FROM public_sites').fetchone()[0]==0
    approve(admin,site,[],False)
    assert admin.get('/widget/'+str(site['id'])).status_code==404
    assert admin.post(f'/api/public/{site["id"]}/chat',json={'question':'test'}).status_code==404


@pytest.mark.parametrize('origin',["https://good.com;evil",'https://*.example.com','http://nelsonict.com.ng','https://example.com/path','https://user:pass@example.com'])
def test_widget_rejects_unsafe_origins(admin,origin):
    assert admin.post('/api/public-sites',json={'name':'Test','origins':[origin]}).status_code==422
