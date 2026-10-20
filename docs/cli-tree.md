# CLI 树

以下树由当前源码的真实 `chatevent --tree` 命令执行输出生成；`chatevent --tree-brief` 保留节点但省略参数签名。CLI 使用 ChatStyle 渲染和 argparse 执行。

```text
chatevent
├── --help  # Show this message and exit.
├── --tree  # Print the registered CLI tree.
├── --tree-brief  # Print the registered CLI tree without parameter signatures.
├── --version  # Print package version.
├── api  # Call a running ChatEvent REST API server.
│   ├── create-token [USER-ID] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/me/token or /api/users/{id}/token.
│   ├── create-user <USERNAME> [--new-password-file NEW-PASSWORD-FILE] [--display-name DISPLAY-NAME] [--role ROLE] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/users.
│   ├── delete-subscription <ID> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # DELETE /api/subscriptions/{id}.
│   ├── delete-user <ID> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # DELETE /api/users/{id}.
│   ├── delete-view <ID> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # DELETE /api/views/{id}.
│   ├── event <DEDUPE-KEY> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/events/{dedupe_key}.
│   ├── events [--source SOURCE] [--kind KIND] [--subscription-id SUBSCRIPTION-ID] [--q Q] [--since SINCE] [--days DAYS] [--from FROM] [--to TO] [--limit LIMIT] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/events.
│   ├── health [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/health.
│   ├── platforms [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/platforms.
│   ├── query [--filter-file FILTER-FILE] [--filter-json FILTER-JSON] [--view-id VIEW-ID] [--source SOURCE] [--kind KIND] [--subscription-id SUBSCRIPTION-ID] [--sort SORT] [--cursor CURSOR] [--limit LIMIT] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/query with stable cursor paging.
│   ├── record-json <FILE> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/events.
│   ├── save-subscription <FILE> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/subscriptions.
│   ├── save-view <FILE> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/views.
│   ├── schema <EVENT|SUBSCRIPTION> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/schema/{kind}.
│   ├── session [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/session.
│   ├── stats [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/stats.
│   ├── subscription <ID> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/subscriptions/{id}.
│   ├── subscriptions [--enabled ENABLED] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/subscriptions.
│   ├── update-view <ID> <FILE> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # PUT /api/views/{id}.
│   ├── users [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/users.
│   ├── view <ID> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/views/{id}.
│   └── views [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/views.
├── capture  # Run bounded official platform capture passes.
│   ├── discourse-topic-backfill [--db DB] [--base-url BASE-URL] [--topic-id TOPIC-ID] [--limit LIMIT] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID] [--api-key-env API-KEY-ENV] [--api-username API-USERNAME]  # Read a bounded current Discourse topic/posts snapshot.
│   ├── subscription-once [--db DB] [--env-file ENV-FILE] [--subscription-id SUBSCRIPTION-ID] [--limit LIMIT] [--timeout TIMEOUT]  # Run one capture pass for a saved subscription.
│   ├── voice-backfill [--db DB] [--env-file ENV-FILE] [--base-url BASE-URL] [--token-env TOKEN-ENV] [--all] [--limit LIMIT] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID]  # Backfill Speakr/ChatVoice talk metadata through the read-only data API.
│   ├── voice-once [--db DB] [--env-file ENV-FILE] [--base-url BASE-URL] [--token-env TOKEN-ENV] [--since SINCE] [--limit LIMIT] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID]  # Capture one incremental Speakr/ChatVoice metadata poll.
│   ├── watch-zulip-topic [--db DB] [--stream STREAM] [--topic TOPIC] [--assignment-id ASSIGNMENT-ID] [--interval-seconds INTERVAL-SECONDS] [--expires-at EXPIRES-AT] [--ttl-seconds TTL-SECONDS] [--hot-until HOT-UNTIL] [--reason REASON] [--subscription-id SUBSCRIPTION-ID]  # Create a temporary Zulip stream/topic watch subscription.
│   ├── x-status [--db DB] [--url URL] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID] [--proxy-env-file PROXY-ENV-FILE]  # Capture one public X status URL through the web/oEmbed path.
│   ├── x-user [--db DB] [--handle HANDLE] [--limit LIMIT] [--days DAYS] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID] [--proxy-env-file PROXY-ENV-FILE]  # Capture recent public posts from one X user page.
│   └── zulip-once [--db DB] [--env-file ENV-FILE] [--stream STREAM] [--topic TOPIC] [--content CONTENT] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID]  # Official Zulip event-queue capture pass.
├── paths [--json]  # Show ChatArch-owned runtime paths.
├── platforms [--json]  # List supported platforms and action kinds.
├── record-json <FILE> [--db DB]  # Validate and write one local ChatEvent JSON file.
├── schema <EVENT|SUBSCRIPTION>  # Print local JSON Schema contracts.
└── serve [--host HOST] [--port PORT] [--db DB]  # Run the local Event Observatory and REST API.
```

`api query`、`api views/view/save-view/update-view/delete-view` 和 `capture discourse-topic-backfill` 是可执行命令。`capture zulip-once --content` 会发送消息，常规读取不使用它。详见[过滤与视图](filtering.md)。
