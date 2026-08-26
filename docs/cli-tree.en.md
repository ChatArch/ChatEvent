# CLI Tree

ChatEvent's CLI is organized into four surfaces: local runtime and schemas, REST API client commands, platform capture, and ChatArch runtime paths. Both `chatevent --tree` and `chatevent --tree-brief` are rendered by ChatStyle and shared by docs and tests.

## Full Command Tree

`--tree` keeps parameter signatures by default:

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
│   ├── event <DEDUPE-KEY> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/events/{dedupe_key}.
│   ├── events [--source SOURCE] [--kind KIND] [--subscription-id SUBSCRIPTION-ID] [--q Q] [--since SINCE] [--days DAYS] [--from FROM] [--to TO] [--limit LIMIT] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/events.
│   ├── health [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/health.
│   ├── platforms [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/platforms.
│   ├── record-json <FILE> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/events.
│   ├── save-subscription <FILE> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # POST /api/subscriptions.
│   ├── schema <EVENT|SUBSCRIPTION> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/schema/{kind}.
│   ├── session [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/session.
│   ├── stats [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/stats.
│   ├── subscription <ID> [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/subscriptions/{id}.
│   ├── subscriptions [--enabled ENABLED] [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/subscriptions.
│   └── users [--base-url BASE-URL] [--timeout TIMEOUT] [--admin-token ADMIN-TOKEN] [--username USERNAME] [--password-file PASSWORD-FILE]  # GET /api/users.
├── capture  # Run bounded official platform capture passes.
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

## Brief Command Tree

`--tree-brief` keeps command nodes and descriptions while omitting parameter signatures, which is useful for README snippets, capability maps, and quick human checks:

```text
chatevent
├── --help  # Show this message and exit.
├── --tree  # Print the registered CLI tree.
├── --tree-brief  # Print the registered CLI tree without parameter signatures.
├── --version  # Print package version.
├── api  # Call a running ChatEvent REST API server.
│   ├── create-token  # POST /api/me/token or /api/users/{id}/token.
│   ├── create-user  # POST /api/users.
│   ├── delete-subscription  # DELETE /api/subscriptions/{id}.
│   ├── delete-user  # DELETE /api/users/{id}.
│   ├── event  # GET /api/events/{dedupe_key}.
│   ├── events  # GET /api/events.
│   ├── health  # GET /api/health.
│   ├── platforms  # GET /api/platforms.
│   ├── record-json  # POST /api/events.
│   ├── save-subscription  # POST /api/subscriptions.
│   ├── schema  # GET /api/schema/{kind}.
│   ├── session  # GET /api/session.
│   ├── stats  # GET /api/stats.
│   ├── subscription  # GET /api/subscriptions/{id}.
│   ├── subscriptions  # GET /api/subscriptions.
│   └── users  # GET /api/users.
├── capture  # Run bounded official platform capture passes.
│   ├── subscription-once  # Run one capture pass for a saved subscription.
│   ├── voice-backfill  # Backfill Speakr/ChatVoice talk metadata through the read-only data API.
│   ├── voice-once  # Capture one incremental Speakr/ChatVoice metadata poll.
│   ├── watch-zulip-topic  # Create a temporary Zulip stream/topic watch subscription.
│   ├── x-status  # Capture one public X status URL through the web/oEmbed path.
│   ├── x-user  # Capture recent public posts from one X user page.
│   └── zulip-once  # Official Zulip event-queue capture pass.
├── paths  # Show ChatArch-owned runtime paths.
├── platforms  # List supported platforms and action kinds.
├── record-json  # Validate and write one local ChatEvent JSON file.
├── schema  # Print local JSON Schema contracts.
└── serve  # Run the local Event Observatory and REST API.
```

## Local Runtime And Contracts

```bash
chatevent paths --json
chatevent serve --host 127.0.0.1 --port 8765
chatevent schema event
chatevent schema subscription
chatevent platforms --json
chatevent record-json event.json
```

## REST API Client

```bash
chatevent api health
chatevent api session
chatevent api users
chatevent api create-user rexwzh@lookeng.cn --new-password-file ~/.chatarch/chatevent/secrets/admin-password
chatevent api create-token
chatevent api subscriptions --enabled true
chatevent api events --source github --kind pull_request.opened --limit 20
chatevent api record-json event.json
chatevent api save-subscription subscription.json
```

API tokens are for CLI/model/programmatic access. The Web Observatory homepage still uses username/password login.

## Platform Capture

```bash
chatevent capture voice-backfill --all \
  --env-file /home/zhihong/Playground/.env

chatevent capture voice-once \
  --since 2026-08-25T16:26:37Z \
  --env-file /home/zhihong/Playground/.env

chatevent capture x-user --handle thsottiaux --limit 20 --days 7 \
  --proxy-env-file /home/zhihong/Playground/.env

chatevent capture x-status \
  --url https://x.com/thsottiaux/status/2087423996115681767 \
  --proxy-env-file /home/zhihong/Playground/.env

chatevent capture zulip-once \
  --env-file ~/.chatarch/envs/Zulip/.env \
  --stream demo \
  --topic loop \
  --subscription-id zulip-demo

chatevent capture watch-zulip-topic \
  --stream "voice note" \
  --topic "assignment-123" \
  --assignment-id assign-123 \
  --interval-seconds 5 \
  --ttl-seconds 3600 \
  --reason "active assignment clarification" \
  --subscription-id zulip-topic-assign-123

chatevent capture subscription-once \
  --env-file ~/.chatarch/envs/Zulip/.env \
  --subscription-id zulip-topic-assign-123
```

`voice-backfill` and `voice-once` read only the ChatVoice list metadata endpoint and write `source=voice` / `talk.created` or `talk.updated`. Event payloads keep `talk_id`, `title`, `tags`, `created_at`, `updated_at`, `duration_seconds`, and summary/transcript availability booleans; they do not store full summary text, transcript text, preview text, or token values.

Temporary Zulip topic watches use `source=zulip`, `target=stream:<stream>/topic:<topic>`, `event_kinds=["message.created"]`, `filters={"stream": "...", "topic": "..."}`, and metadata including `temporary`, `assignment_id`, `interval_seconds`, `expires_at`, `hot_until`, `reason`, `content_policy=topic-scoped-message-content`, and a `policy_boundary` note. ChatEvent stores scoped message content and sender identity fields for the active thread; consumer-specific sender/user/tag policy stays outside capture.

Platform secrets are managed by ChatEnv profiles or service secret files. ChatEvent references them by path and never prints credential values.
