"""Exercise all declared Discourse hooks and Zulip action families over HTTP.

Payloads are explicit synthetic fixtures, not claims of live platform writes.
"""
import hashlib
import hmac
import json
from fastapi.testclient import TestClient

from chatevent.adapters import DISCOURSE_WEBHOOK_ACTIONS
from chatevent.server import create_app
from chatevent.subscription import Subscription


def test_all_declared_discourse_actions_through_signed_http(tmp_path, monkeypatch):
    monkeypatch.setenv('CHATEVENT_ADMIN_TOKEN','synthetic-admin')
    monkeypatch.setenv('CHATEVENT_DISCOURSE_WEBHOOK_SECRET','synthetic-hook')
    monkeypatch.setenv('CHATEVENT_DISCOURSE_INSTANCE','https://forum.example.org')
    monkeypatch.setenv('CHATEVENT_DISCOURSE_SUBSCRIPTION_ID','forum-watch')
    app=create_app(db_path=tmp_path/'events.db')
    app.state.store.save_subscription(Subscription(id='forum-watch',source='discourse',target='category:demo'))
    keys=[]
    with TestClient(app) as client:
        for name,(expected_kind,object_type) in DISCOURSE_WEBHOOK_ACTIONS.items():
            obj={'id':42,'group_id':7,'user_id':8,'topic_id':19,'post_number':1,
                 'created_at':'2026-10-20T00:00:00Z','updated_at':'2026-10-20T00:01:00Z',
                 'username':'fixture-user','title':'Synthetic activity','raw':'fixture'}
            raw=json.dumps({object_type:obj},sort_keys=True).encode()
            signature='sha256='+hmac.new(b'synthetic-hook',raw,hashlib.sha256).hexdigest()
            headers={'Content-Type':'application/json','X-Discourse-Event':name,'X-Discourse-Event-Type':object_type,'X-Discourse-Instance':'https://forum.example.org','X-Discourse-Event-Signature':signature}
            response=client.post('/webhooks/discourse',content=raw,headers=headers)
            assert response.status_code==202,(name,response.text)
            key=response.json()['dedupe_key'];keys.append(key)
            assert app.state.store.get_event(key).event.kind==expected_kind
            repeat=client.post('/webhooks/discourse',content=raw,headers=headers)
            assert repeat.status_code==202 and repeat.json()['created'] is False
        assert len(set(keys))==len(DISCOURSE_WEBHOOK_ACTIONS)
        query=client.get('/api/query',headers={'X-ChatEvent-Admin-Token':'synthetic-admin'})
        assert query.status_code==200
        assert query.json()['count']==len(DISCOURSE_WEBHOOK_ACTIONS)


def test_zulip_actions_through_authenticated_http(tmp_path,monkeypatch):
    monkeypatch.setenv('CHATEVENT_ADMIN_TOKEN','synthetic-admin')
    monkeypatch.setenv('ZULIP_SITE','https://zulip.example.org')
    app=create_app(db_path=tmp_path/'events.db')
    cases=[
        ({'type':'message','message':{'id':11,'timestamp':1792454400,'stream_id':3,'display_recipient':'demo','subject':'topic','sender_id':8,'content':'fixture'}},'message.created'),
        ({'type':'update_message','message_id':11,'message_ids':[11],'content':'changed','edit_timestamp':1792454401},'message.edited'),
        ({'type':'update_message','message_id':11,'message_ids':[11],'stream_id':3,'orig_subject':'topic','subject':'moved'},'message.moved'),
        ({'type':'delete_message','message_ids':[11,12]},'message.deleted'),
        ({'type':'reaction','op':'add','message_id':11,'user_id':8,'emoji_code':'1f389'},'reaction.added'),
        ({'type':'reaction','op':'remove','message_id':11,'user_id':8,'emoji_code':'1f389'},'reaction.removed'),
        ({'type':'stream','op':'create','streams':[{'stream_id':3,'name':'demo'}]},'stream.created'),
        ({'type':'stream','op':'update','stream_id':3,'property':'description','value':'changed'},'stream.updated'),
        ({'type':'stream','op':'delete','stream_ids':[3]},'stream.deleted'),
        ({'type':'subscription','op':'add','subscriptions':[{'stream_id':3,'name':'demo'}]},'subscription.added'),
        ({'type':'subscription','op':'remove','subscriptions':[{'stream_id':3,'name':'demo'}]},'subscription.removed'),
        ({'type':'subscription','op':'update','stream_id':3,'property':'is_muted','value':True},'subscription.updated'),
        ({'type':'realm_user','op':'add','person':{'user_id':8,'full_name':'Fixture'}},'user.added'),
        ({'type':'realm_user','op':'update','person':{'user_id':8,'full_name':'Changed'}},'user.updated'),
        ({'type':'realm_user','op':'remove','person':{'user_id':8}},'user.removed'),
    ]
    with TestClient(app) as client:
        for index,(payload,expected) in enumerate(cases):
            raw={**payload,'id':index,'queue_id':'fixture-queue'}
            denied=client.post('/webhooks/zulip',json=raw)
            assert denied.status_code==401
            response=client.post('/webhooks/zulip',json=raw,headers={'X-ChatEvent-Admin-Token':'synthetic-admin'})
            assert response.status_code==202,(expected,response.text)
            result=response.json();items=result.get('items',[result])
            assert all(app.state.store.get_event(item['dedupe_key']).event.kind==expected for item in items)
