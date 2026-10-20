"""Regressions from the immutable-candidate independent security review."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient

from chatevent.model import ChatEvent
from chatevent.query import FilterError, validate_filter
from chatevent.store import EventStore
from chatevent.subscription import Subscription
from chatevent.capture import capture_zulip_once
from chatevent.server import create_app


def event(sub, content='fixture'):
    return ChatEvent(id='shared-native-id',source='zulip',kind='message.created',subscription_id=sub,occurred_at='2026-10-20T00:00:00Z',capture_mode='test_fixture',payload={'content':content})


def test_subscription_id_cannot_be_reclaimed_by_another_owner(tmp_path):
    store=EventStore(tmp_path/'events.db')
    store.save_subscription(Subscription(id='watch',source='zulip',target='stream:test',owner_user_id='alice'))
    store.record_event(event('watch','private-alice'))
    store.delete_subscription('watch')
    with pytest.raises(PermissionError):
        store.save_subscription(Subscription(id='watch',source='zulip',target='stream:test',owner_user_id='bob'))
    assert store.query_events(owner_user_id='bob').count==0
    assert store.query_events(owner_user_id='alice').count==1
    assert store.stats(owner_user_id='alice')['event_count']==1


def test_concurrent_subscription_claim_is_atomic(tmp_path):
    store=EventStore(tmp_path/'events.db')
    def claim(owner):
        try:
            store.save_subscription(Subscription(id='collision',source='zulip',target='stream:test',owner_user_id=owner))
            return True
        except PermissionError:return False
    with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(claim,['alice','bob']))
    assert outcomes.count(True)==1
    assert outcomes.count(False)==1


def test_dedupe_is_scoped_to_immutable_capture_owner(tmp_path):
    store=EventStore(tmp_path/'events.db')
    for owner in ('alice','bob'):
        store.save_subscription(Subscription(id=owner,source='zulip',target='stream:test',owner_user_id=owner))
    first,_=store.record_event(event('alice','private-alice'))
    second,created=store.record_event(event('bob','private-bob'))
    assert created is True
    assert first.dedupe_key!=second.dedupe_key
    assert store.get_event(first.dedupe_key).seen_count==1
    assert store.query_events(owner_user_id='bob').items[0].event.payload['content']=='private-bob'
    assert store.get_event(first.dedupe_key,owner_user_id='bob') is None


def test_capture_receipt_uses_persisted_owner_scoped_key(tmp_path):
    from chatevent.capture import capture_zulip_subscription_once
    db=tmp_path/'events.db';store=EventStore(db)
    store.save_subscription(Subscription(id='watch',source='zulip',target='stream:demo/topic:wanted',owner_user_id='alice',filters={'stream':'demo','topic':'wanted'}))
    env=tmp_path/'fixture.env';env.write_text('ZULIP_SITE=https://zulip.example.org\nZULIP_BOT_EMAIL=fixture@example.org\nZULIP_BOT_API_KEY=synthetic\n')
    message={'id':11,'stream_id':3,'sender_id':8,'display_recipient':'demo','subject':'wanted','timestamp':1792454400,'content':'fixture'}
    with patch('chatevent.capture._fetch_zulip_topic_messages',return_value=[message]):
        summary=capture_zulip_subscription_once(db_path=db,env_file=env,subscription_id='watch')
    assert store.get_event(summary.events[0],owner_user_id='alice') is not None
    assert summary.events[0]==store.query_events(owner_user_id='alice').items[0].dedupe_key


def test_legacy_owner_migration_keeps_body_and_key(tmp_path):
    import sqlite3
    db=tmp_path/'legacy.db'
    sample=event('watch','legacy-private'); data=sample.to_dict();data.pop('instance',None)
    body=json.dumps(data); stamp=sample.captured_at.isoformat()
    subscription=Subscription(id='watch',source='zulip',target='stream:test',owner_user_id='alice')
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE subscriptions(id TEXT PRIMARY KEY,source TEXT,target TEXT,enabled INTEGER,updated_at TEXT,body TEXT)')
        conn.execute('CREATE TABLE events(dedupe_key TEXT PRIMARY KEY,source TEXT,kind TEXT,subscription_id TEXT,conversation_id TEXT,occurred_at TEXT,captured_at TEXT,first_captured_at TEXT,last_captured_at TEXT,seen_count INTEGER,body TEXT)')
        conn.execute('INSERT INTO subscriptions VALUES(?,?,?,?,?,?)',('watch','zulip','stream:test',1,stamp,subscription.model_dump_json()))
        conn.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sample.dedupe_key,'zulip',sample.kind,'watch',None,sample.occurred_at.isoformat(),stamp,stamp,stamp,1,body))
    store=EventStore(db)
    stored,created=store.record_event(sample)
    assert not created and stored.dedupe_key==sample.dedupe_key and stored.seen_count==2
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT body FROM events').fetchone()[0]==body
    store.delete_subscription('watch')
    store=EventStore(db)
    assert store.query_events(owner_user_id='alice').count==1
    assert store.query_events(owner_user_id='bob').count==0


def test_http_deleted_id_and_cross_owner_event_isolation(tmp_path,monkeypatch):
    from chatevent.auth import UserRecord,token_digest
    monkeypatch.setenv('CHATEVENT_ADMIN_TOKEN','synthetic-admin')
    app=create_app(db_path=tmp_path/'events.db')
    for who in ('alice','bob'):
        app.state.store.save_user(UserRecord(id=who,username=who,role='member'),token_hash=token_digest(who+'-token'))
    a={'X-ChatEvent-Admin-Token':'alice-token'};b={'X-ChatEvent-Admin-Token':'bob-token'}
    with TestClient(app) as client:
        assert client.post('/api/subscriptions',json={'id':'watch','source':'zulip','target':'stream:test'},headers=a).status_code==201
        response=client.post('/api/events',json=event('watch').to_dict(),headers=a)
        assert response.status_code==202
        key=response.json()['dedupe_key']
        assert client.get('/api/events/'+key,headers=b).status_code==404
        assert client.delete('/api/subscriptions/watch',headers=a).status_code==200
        assert client.post('/api/subscriptions',json={'id':'watch','source':'zulip','target':'stream:test'},headers=b).status_code==403
        assert client.get('/api/query',headers=b).json()['count']==0
        assert client.get('/api/query',headers=a).json()['count']==1
        assert client.get('/api/events/'+key,headers=a).status_code==200
        assert client.get('/api/events/'+event('watch').dedupe_key,headers=a).status_code==200


def test_ne_null_respects_declared_type(tmp_path):
    store=EventStore(tmp_path/'events.db')
    for i,score in enumerate([3,'3',None]):
        store.record_event(event(None).model_copy(update={'id':str(i),'payload':{'score':score}}))
    rows=store.query_events(filter_expr={'field':'payload.score','op':'ne','value':None}).items
    assert [row.event.id for row in rows]==['0']


@pytest.mark.parametrize('condition',[
    {'field':'payload.content','op':'contains','value':None},
    {'field':'tags','op':'contains','value':None},
    {'field':'tags','op':'any','value':[None]},
    {'field':'tags','op':'all','value':['x',None]},
])
def test_text_and_tag_operands_reject_null(condition):
    with pytest.raises(FilterError):validate_filter(condition)


def test_sparse_edit_does_not_erase_known_capture_scope(tmp_path):
    db=tmp_path/'events.db';store=EventStore(db)
    known=event(None).model_copy(update={'id':'message:11','instance':'https://zulip.example.org','subject_id':'message:11','subject_type':'message','payload':{'stream':'demo','topic':'wanted'}})
    store.record_event(known)
    store.record_event(known.model_copy(update={'id':'edit:11','kind':'message.edited','payload':{'stream':'','topic':'','content':'updated'}}))
    env=tmp_path/'fixture.env';env.write_text('ZULIP_SITE=https://zulip.example.org\nZULIP_BOT_EMAIL=fixture@example.org\nZULIP_BOT_API_KEY=synthetic\n')
    def request(_env,method,path,**kwargs):
        if path.endswith('/register'):return {'queue_id':'fixture','last_event_id':-1}
        if method=='DELETE':return {'result':'success'}
        return {'events':[{'type':'reaction','id':1,'message_id':11,'user_id':8,'op':'add','emoji_code':'1f389'}]}
    with patch('chatevent.capture._zulip_request',request),patch('chatevent.capture.time.time',side_effect=[0,0,0,2]):
        summary=capture_zulip_once(db_path=db,env_file=env,stream='demo',topic='wanted',timeout_seconds=1,subscription_id=None)
    assert summary.created==1


@pytest.mark.parametrize('missing',['CHATEVENT_DISCOURSE_INSTANCE','CHATEVENT_DISCOURSE_SUBSCRIPTION_ID'])
def test_signed_ingest_requires_both_trusted_bindings(tmp_path,monkeypatch,missing):
    for key,value in {'CHATEVENT_ADMIN_TOKEN':'synthetic-admin','CHATEVENT_DISCOURSE_WEBHOOK_SECRET':'synthetic-hook','CHATEVENT_DISCOURSE_INSTANCE':'https://forum.example.org','CHATEVENT_DISCOURSE_SUBSCRIPTION_ID':'watch'}.items():monkeypatch.setenv(key,value)
    monkeypatch.delenv(missing)
    app=create_app(db_path=tmp_path/'events.db')
    app.state.store.save_subscription(Subscription(id='watch',source='discourse',target='category:test'))
    raw=json.dumps({'post':{'id':42,'post_number':1,'created_at':'2026-10-20T00:00:00Z'}}).encode()
    signature='sha256='+hmac.new(b'synthetic-hook',raw,hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        response=client.post('/webhooks/discourse',content=raw,headers={'Content-Type':'application/json','X-Discourse-Event':'post_created','X-Discourse-Event-Signature':signature})
    assert response.status_code==503
    assert app.state.store.stats()['event_count']==0
