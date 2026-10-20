# Interface tree

These names match current source exports and registered FastAPI routes. The CLI tree is generated separately from an executed `render_cli_tree()` call.

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
GET    /                        Observatory or login page
POST   /api/login               Account login
POST   /api/logout              Logout
GET    /api/session             Current account
GET    /api/health              Service health
GET    /api/platforms           Capability catalog
GET    /api/schema/event        Event JSON Schema
GET    /api/schema/subscription Subscription JSON Schema
GET    /api/subscriptions       Visible acquisition configurations
POST   /api/subscriptions       Create/update acquisition configuration
GET    /api/subscriptions/{id}  Configuration detail
DELETE /api/subscriptions/{id}  Delete configuration
GET    /api/query               Bounded conditions, server filter, sequence cursor
GET    /api/events              Legacy read compatibility
GET    /api/events/{key}        Event detail
POST   /api/events              Authorized normalized ingest
GET    /api/views               Owner's views
POST   /api/views               Create owner's view
GET    /api/views/{id}          Owner's view detail
PUT    /api/views/{id}          Update owner's view
DELETE /api/views/{id}          Delete owner's view
GET    /api/stats               Authorized counters
POST   /webhooks/discourse      Signature or authorized ingest credentials
POST   /webhooks/zulip          Authorized ingest credentials
POST   /webhooks/gitea          Authorized ingest credentials
POST   /webhooks/github         Authorized ingest credentials
```

`EventStore` preserves old SQLite event rows and adds `event_offsets` and `saved_views`. `query_events()` restricts by owner; `validate_filter()` bounds paths, types, depth, and node count before querying. `CHATEVENT_DB`, `CHATEVENT_ADMIN_TOKEN(_FILE)`, `CHATEVENT_BOOTSTRAP_USERNAME`, and `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` continue under ChatEnv/service configuration. Discourse hooks add `CHATEVENT_DISCOURSE_WEBHOOK_SECRET(_FILE)`, `CHATEVENT_DISCOURSE_INSTANCE`, and `CHATEVENT_DISCOURSE_SUBSCRIPTION_ID`. Default database paths remain compatible with `$CHATARCH_HOME/chatevent/events.db` and `~/.chatarch/chatevent/events.db`.

See [Reference](reference.md) and [Filtering and Views](filtering.md) for semantics.
