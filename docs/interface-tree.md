# 接口树

以下名称与当前源码导出及 FastAPI 注册路由一致；CLI 树单独从实际 `render_cli_tree()` 执行结果生成。

```text
chatevent/
├── model.py          ChatEvent, CaptureMode, ActorDescriptor, CarrierTarget
├── query.py          SavedView, FilterError, validate_filter(), compile_filter()
├── subscription.py   Subscription
├── store.py          EventStore, StoredEvent, QueryPage
│   └── record_event(), query_events(), list_events(), save_view(), list_views(), get_view(), delete_view(), stats()
├── adapters.py       normalize_zulip_message_event(), normalize_zulip_queue_event()
│                     normalize_discourse_post(), normalize_discourse_webhook()
│                     normalize_gitea_issue(), normalize_github_event()
├── capture.py        capture_zulip_once(), capture_zulip_subscription_once()
│                     capture_discourse_topic_backfill(), capture_subscription_once()
├── client.py         ChatEventApiClient.query_events(), list_views(), get_view(), save_view(), update_view(), delete_view()
├── server.py         create_app()
├── dashboard.py      DASHBOARD_HTML
├── config.py         ChatEventConfig (ChatEnv entry point)
└── cli.py            build_parser(), render_cli_tree(), main()
```

```text
GET    /                        Observatory 或登录页
POST   /api/login               账号登录
POST   /api/logout              登出
GET    /api/session             当前账号
GET    /api/health              服务健康
GET    /api/platforms           能力目录
GET    /api/schema/event        Event JSON Schema
GET    /api/schema/subscription Subscription JSON Schema
GET    /api/subscriptions       当前账号可见采集配置
POST   /api/subscriptions       创建/更新采集配置
GET    /api/subscriptions/{id}  采集配置详情
DELETE /api/subscriptions/{id}  删除采集配置
GET    /api/query               有界条件、服务端过滤、序号游标
GET    /api/events              兼容旧读接口
GET    /api/events/{key}        事件详情
POST   /api/events              授权的规范化入库
GET    /api/views               owner 视图列表
POST   /api/views               新建 owner 视图
GET    /api/views/{id}          owner 视图详情
PUT    /api/views/{id}          更新 owner 视图
DELETE /api/views/{id}          删除 owner 视图
GET    /api/stats               授权范围内统计
POST   /webhooks/discourse      需签名或授权 ingest 凭据
POST   /webhooks/zulip          需授权 ingest 凭据
POST   /webhooks/gitea          需授权 ingest 凭据
POST   /webhooks/github         需授权 ingest 凭据
```

`EventStore` 在 SQLite 中保持旧 events 行，添加 `event_offsets` 和 `saved_views`。`query_events()` 按 owner 限制；`validate_filter()` 在查询前限制路径、类型、深度和节点数。`CHATEVENT_DB`、`CHATEVENT_ADMIN_TOKEN(_FILE)`、`CHATEVENT_BOOTSTRAP_USERNAME`、`CHATEVENT_BOOTSTRAP_PASSWORD_FILE` 继续沿用 ChatEnv/服务配置；Discourse webhook 另有 `CHATEVENT_DISCOURSE_WEBHOOK_SECRET(_FILE)`、`CHATEVENT_DISCOURSE_INSTANCE` 与 `CHATEVENT_DISCOURSE_SUBSCRIPTION_ID`。默认库兼容 `$CHATARCH_HOME/chatevent/events.db` 与 `~/.chatarch/chatevent/events.db`。

详细语义见[接口参考](reference.md)与[过滤与视图](filtering.md)。
