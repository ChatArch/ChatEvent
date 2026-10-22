"""Supervisor regressions for observable capture and query contracts."""
import pytest
from unittest.mock import patch

from chatevent.adapters import normalize_discourse_webhook, normalize_zulip_queue_event
from chatevent.capture import capture_zulip_once
from chatevent.catalog import get_platform_spec
from chatevent.model import ChatEvent
from chatevent.store import EventStore
from test_dashboard_session_js import run_dashboard_script


def envfile(tmp_path):
    path = tmp_path / 'zulip.env'
    path.write_text('ZULIP_SITE=https://zulip.example.org\nZULIP_BOT_EMAIL=fixture@example.org\nZULIP_BOT_API_KEY=synthetic-only\n')
    return path


def test_bounded_queue_uses_nonblocking_poll_and_cleans_up(tmp_path):
    calls = []
    def request(_env, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.endswith('/register'):
            return {'queue_id':'fixture-queue', 'last_event_id':-1}
        return {'events':[],'result':'success'}
    with patch('chatevent.capture._zulip_request', request), patch('chatevent.capture.time.time', side_effect=[0, 0, 0, 2]), patch('chatevent.capture.time.sleep'):
        result=capture_zulip_once(db_path=tmp_path/'events.db',env_file=envfile(tmp_path),timeout_seconds=1)
    poll=next(row for row in calls if row[0]=='GET')
    assert poll[2]['query']['dont_block'] is True
    assert result.captured==0
    assert calls[-1][0]=='DELETE'


def test_registered_queue_cleanup_includes_failed_practice_send(tmp_path):
    calls=[]
    def request(_env,method,path,**kwargs):
        calls.append((method,path))
        if path.endswith('/register'): return {'queue_id':'fixture-queue','last_event_id':-1}
        if method=='POST': raise RuntimeError('synthetic rejected practice send')
        return {'result':'success'}
    with patch('chatevent.capture._zulip_request',request), pytest.raises(RuntimeError,match='synthetic rejected'):
        capture_zulip_once(db_path=tmp_path/'events.db',env_file=envfile(tmp_path),stream='demo',topic='wanted',content='fixture-only',timeout_seconds=1)
    assert calls[-1]==('DELETE','/api/v1/events')


def test_sparse_bulk_delete_uses_each_messages_scoped_context(tmp_path):
    db=tmp_path/'events.db'; store=EventStore(db)
    for mid,topic in [(11,'wanted'),(12,'other')]:
        store.record_event(ChatEvent(id=f'message:{mid}',source='zulip',instance='https://zulip.example.org',kind='message.created',subject_id=f'message:{mid}',subject_type='message',occurred_at='2026-10-20T00:00:00Z',capture_mode='test_fixture',payload={'stream':'demo','topic':topic}))
    def request(_env,method,path,**kwargs):
        if path.endswith('/register'):return {'queue_id':'fixture-queue','last_event_id':-1}
        if method=='DELETE':return {'result':'success'}
        return {'events':[{'type':'delete_message','id':1,'message_ids':[11,12]}]}
    with patch('chatevent.capture._zulip_request',request), patch('chatevent.capture.time.time',side_effect=[0,0,0,2]):
        result=capture_zulip_once(db_path=db,env_file=envfile(tmp_path),stream='demo',topic='wanted',timeout_seconds=1)
    assert result.created==1
    rows=store.list_events(source='zulip',kind='message.deleted')
    assert [row.event.subject_id for row in rows]==['message:11']


def test_move_scope_does_not_cross_product_old_stream_with_new_topic(tmp_path):
    db=tmp_path/'events.db'; store=EventStore(db)
    store.record_event(ChatEvent(id='message:11',source='zulip',instance='https://zulip.example.org',kind='message.created',subject_id='message:11',subject_type='message',occurred_at='2026-10-20T00:00:00Z',capture_mode='test_fixture',payload={'stream':'demo','topic':'wanted'}))
    def request(_env,method,path,**kwargs):
        if path.endswith('/register'):
            return {'queue_id':'fixture-queue','last_event_id':-1,'subscriptions':[{'stream_id':3,'name':'demo'},{'stream_id':4,'name':'other'}]}
        if method=='DELETE':return {'result':'success'}
        return {'events':[{'type':'update_message','id':1,'message_id':11,'message_ids':[11],'stream_id':3,'new_stream_id':4,'orig_subject':'wanted','subject':'next'}]}
    with patch('chatevent.capture._zulip_request',request), patch('chatevent.capture.time.time',side_effect=[0,0,0,2]):
        result=capture_zulip_once(db_path=db,env_file=envfile(tmp_path),stream='demo',topic='next',timeout_seconds=1)
    assert result.created==0


def test_legacy_zulip_stream_removal_and_changed_properties():
    removed=normalize_zulip_queue_event({'type':'stream','op':'delete','id':1,'streams':[{'stream_id':3},{'stream_id':4}]},queue_lifetime='fixture')
    assert [e.subject_id for e in removed]==['stream:3','stream:4']
    updated=normalize_zulip_queue_event({'type':'subscription','op':'update','id':2,'stream_id':3,'property':'is_muted','value':True},queue_lifetime='fixture')[0]
    assert updated.payload['property']=='is_muted'
    assert updated.payload['value'] is True


def test_catalog_exposes_actual_capture_actions_and_marks_catalog_only():
    zulip={a.kind:a for a in get_platform_spec('zulip').actions}
    assert {'message.edited','message.moved','message.deleted','stream.updated','subscription.updated','user.updated'}<=set(zulip)
    assert zulip['message.edited'].capture_status=='implemented'
    assert zulip['mention.created'].capture_status=='catalog_only'
    discourse={a.kind:a for a in get_platform_spec('discourse').actions}
    assert {'topic.recovered','user.suspended','category.updated','like.created','group_user.removed'}<=set(discourse)
    assert discourse['user.suspended'].capture_status=='implemented'


def test_distinct_like_actors_without_action_id_do_not_collapse():
    first=normalize_discourse_webhook({'like':{'post_id':3,'user_id':10}},event_name='like_created')
    second=normalize_discourse_webhook({'like':{'post_id':3,'user_id':11}},event_name='like_created')
    assert first.dedupe_key!=second.dedupe_key


def test_normalized_action_is_queryable(tmp_path):
    store=EventStore(tmp_path/'events.db')
    store.record_event(ChatEvent(id='fixture',source='discourse',kind='reply.created',subject_type='post',occurred_at='2026-10-20T00:00:00Z',capture_mode='test_fixture'))
    result=store.query_events(filter_expr={'all':[{'field':'action.verb','op':'eq','value':'created'},{'field':'action.object_type','op':'eq','value':'post'}]})
    assert len(result.items)==1


def test_backfill_records_instance_for_sparse_queue_context(tmp_path):
    from chatevent.capture import capture_zulip_subscription_once
    from chatevent.subscription import Subscription
    db=tmp_path/'events.db'; store=EventStore(db)
    store.save_subscription(Subscription(id='watch',source='zulip',target='stream:demo/topic:wanted',filters={'stream':'demo','topic':'wanted'}))
    message={'id':11,'stream_id':3,'sender_id':8,'display_recipient':'demo','subject':'wanted','timestamp':1792454400,'content':'fixture'}
    with patch('chatevent.capture._fetch_zulip_topic_messages',return_value=[message]):
        capture_zulip_subscription_once(db_path=db,env_file=envfile(tmp_path),subscription_id='watch')
    assert store.list_events()[0].event.instance=='https://zulip.example.org'


def test_dashboard_query_respects_saved_view_sort():
    result=run_dashboard_script('''
      context.__chateventTest.state.querySort="asc";
      let actualSort=null;
      context.fetch=async(path) => {
        let body={};
        if(path.startsWith("/api/query?")){actualSort=new URLSearchParams(path.split("?")[1]).get("sort");body={items:[],count:0,has_more:false,next_cursor:null};}
        else if(path==="/api/subscriptions" || path==="/api/views")body=[];
        else if(path==="/api/platforms")body={items:[]};
        else if(path==="/api/stats")body={sources:{},kinds:{}};
        return {ok:true,json:async()=>body};
      };
      await context.loadAll();
      return {sort:actualSort};
    ''')
    assert result['sort']=='asc'


def test_loaded_advanced_filter_is_counted_visibly():
    result=run_dashboard_script('''
      context.document.getElementById("advancedFilterJson").value=JSON.stringify({field:"source",op:"eq",value:"zulip"});
      context.updateAdvancedCount();
      return {count:context.document.getElementById("advancedFilterCount").textContent};
    ''')
    assert result['count']=='1'
