# CLI 树

ChatEvent 的 CLI 分成四类：本地运行与 schema、REST API 客户端、平台 capture、ChatArch 运行态路径。`chatevent --tree` 使用 ChatStyle 渲染，作为文档和测试共同校对的命令表面。

## 顶层命令

```text
chatevent
├── --help  # Show this message and exit.
├── --tree  # Print the registered CLI tree.
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
│   └── zulip-once [--db DB] [--env-file ENV-FILE] [--stream STREAM] [--topic TOPIC] [--content CONTENT] [--timeout TIMEOUT] [--subscription-id SUBSCRIPTION-ID]  # Official Zulip event-queue capture pass.
├── paths [--json]  # Show ChatArch-owned runtime paths.
├── platforms [--json]  # List supported platforms and action kinds.
├── record-json <FILE> [--db DB]  # Validate and write one local ChatEvent JSON file.
├── schema <EVENT|SUBSCRIPTION>  # Print local JSON Schema contracts.
└── serve [--host HOST] [--port PORT] [--db DB]  # Run the local Event Observatory and REST API.
```

## 本地运行与 contracts

```bash
chatevent paths --json
chatevent serve --host 127.0.0.1 --port 8765
chatevent schema event
chatevent schema subscription
chatevent platforms --json
chatevent record-json event.json
```

`paths` 不输出 secret 值，只回读 ChatArch-owned runtime 路径。默认数据库路径解析顺序是 `--db`、`CHATEVENT_DB`、ChatEnv `get_paths().home_dir/chatevent/events.db`、`CHATARCH_HOME/chatevent/events.db`、`~/.chatarch/chatevent/events.db`。

## REST API 客户端

`chatevent api ...` 是 ChatEvent REST API 的命令行镜像。默认 base URL 是 `CHATEVENT_API_URL`，未设置时使用 `http://127.0.0.1:8765`。CLI 可以用两种身份访问：

- API token：传 `--admin-token` 或 `CHATEVENT_ADMIN_TOKEN`，推荐由 ChatEnv profile、secret 文件或服务环境注入，不写进命令历史。
- 账号密码：传 `--username` + `--password-file`，用于缺少 API token 的自动化恢复场景。

```bash
chatevent api health --base-url http://127.0.0.1:8765
chatevent api events --source github --kind issue.opened --days 7 --limit 20
chatevent api create-user agent-worker@example.invalid --new-password-file ./password.txt --role member
chatevent api create-token
```

Web 登录使用账号密码；`arch_xxx` token 只作为 CLI、模型和程序的账号 API 凭据。

## Capture 命令

当前一等 capture 命令只有 `zulip-once`。它使用 Zulip 官方 event queue：注册 queue、可选发测试消息、拉取一次 bounded event pass、删除 queue。默认 env 文件路径来自 ChatEnv `envs_dir/Zulip/.env`；其他平台的首选入口是 webhook endpoint 或后续 API cursor worker，不在 CLI 里伪装成全站扫描。

```bash
chatevent capture zulip-once \
  --env-file ~/.chatarch/envs/Zulip/.env \
  --stream demo \
  --topic loop \
  --subscription-id zulip-practice
```
