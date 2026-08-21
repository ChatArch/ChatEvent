# 接口树

这页把 ChatEvent 的 Python 模块、HTTP API、ChatEnv 配置和安全边界放在一张接口树里，方便和标准 Chat 系列项目对齐。

## Python 包接口

```text
chatevent
├── catalog.py                  # 平台 action catalog
│   ├── PlatformAction
│   ├── PlatformSpec
│   ├── list_platform_specs()
│   ├── get_platform_spec(source)
│   └── action_kinds_for(source)
├── model.py                    # 标准事件 envelope
│   ├── CaptureMode
│   ├── CarrierTarget
│   ├── ActionDescriptor
│   ├── ActorDescriptor
│   └── ChatEvent
├── subscription.py             # 订阅 contract
│   └── Subscription
├── auth.py                     # 账号、密码 hash、API token hash
│   ├── UserRecord
│   ├── generate_arch_token()
│   ├── token_digest(token)
│   └── password_digest(password)
├── config.py                   # ChatEnv 配置注册
│   └── ChatEventConfig
├── state.py                    # ChatEnv/ChatArch-owned runtime path
│   ├── ChatEventPaths
│   ├── state_paths()
│   ├── default_database_path()
│   ├── load_admin_token()
│   └── admin_token_source()
├── store.py                    # SQLite event/user/subscription store
│   ├── StoredEvent
│   └── EventStore
│       ├── save_user() / list_users() / delete_user()
│       ├── save_subscription() / list_subscriptions() / delete_subscription()
│       ├── record_event() / get_event() / list_events()
│       └── stats()
├── adapters.py                 # 官方平台 payload normalizer
│   ├── normalize_zulip_message_event()
│   ├── normalize_discourse_webhook()
│   ├── normalize_gitea_webhook()
│   └── normalize_github_webhook()
├── capture.py                  # bounded platform capture helpers
│   ├── load_env_file()
│   └── capture_zulip_once()
├── client.py                   # REST API client used by CLI
│   └── ChatEventApiClient
├── server.py                   # FastAPI app factory and REST/webhook endpoints
│   └── create_app()
├── dashboard.py                # Observatory HTML/CSS/JS
├── monitor.py                  # in-process event observer helper
└── cli.py                      # argparse runtime + ChatStyle-rendered CLI tree
    ├── build_parser()
    ├── render_cli_tree()
    └── main()
```

`__init__.py` re-exports the core domain objects and `ChatEventConfig` for downstream packages and ChatEnv discovery.

## HTTP API surface

```text
GET    /                         # Web Observatory; username/password login gate when auth is configured
POST   /api/login                # Browser username/password login; sets session cookie
POST   /api/logout               # Clear browser session cookie
GET    /api/health               # Health and runtime path summary
GET    /api/session              # Current API token/cookie identity
GET    /api/users                # Admin: list users
POST   /api/users                # Admin: create username/password user
POST   /api/me/token             # Current user: issue one-time arch_xxx API token
POST   /api/users/{id}/token     # Admin: issue one-time token for user
DELETE /api/users/{id}           # Admin: delete user
GET    /api/schema/event         # ChatEvent JSON Schema
GET    /api/schema/subscription  # Subscription JSON Schema
GET    /api/platforms            # Platform action catalog
GET    /api/subscriptions        # List subscriptions; member sees own subscriptions
POST   /api/subscriptions        # Create/update subscription; member-owned when not admin
GET    /api/subscriptions/{id}   # Read one subscription
DELETE /api/subscriptions/{id}   # Delete subscription, not historical events
POST   /api/events               # Write normalized ChatEvent
GET    /api/events               # Query events with filters and next_since checkpoint
GET    /api/events/{dedupe_key}  # Read one stored event
GET    /api/stats                # Event/source/kind/duplicate counters
POST   /webhooks/zulip           # Zulip webhook/event payload ingress
POST   /webhooks/discourse       # Discourse webhook ingress
POST   /webhooks/gitea           # Gitea webhook ingress
POST   /webhooks/github          # GitHub webhook ingress
```

## ChatEnv 配置接口

ChatEvent 注册 `chatevent.config:ChatEventConfig` 到 `chatenv.configs` entry point。ENV/profile/secret 的职责边界是：

| 字段 | 用途 | 敏感性 |
| --- | --- | --- |
| `CHATARCH_HOME` | ChatArch runtime home；默认由 ChatEnv `get_paths().home_dir` 提供 | 非敏感 |
| `CHATEVENT_DB` | 显式 SQLite DB path override | 非敏感 |
| `CHATEVENT_API_URL` | CLI 默认 REST API base URL | 非敏感 |
| `CHATEVENT_ADMIN_TOKEN` | CLI/model/programmatic API token | 敏感 |
| `CHATEVENT_ADMIN_TOKEN_FILE` | API token 文件路径 | 路径非敏感，内容敏感 |
| `CHATEVENT_API_USERNAME` | CLI password-login fallback 用户名 | 非敏感 |
| `CHATEVENT_API_PASSWORD_FILE` | CLI password 文件路径 | 路径非敏感，内容敏感 |
| `CHATEVENT_BOOTSTRAP_USERNAME` | 首个管理员账号用户名 | 非敏感 |
| `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` | 首个管理员密码文件路径 | 路径非敏感，内容敏感 |

平台凭据不归 ChatEvent 自己 invent：Zulip、Discourse、Gitea、GitHub 等平台 secret 应继续放在各自 ChatEnv profile 或服务 secret 文件里。`capture zulip-once` 的默认 env 文件来自 ChatEnv `envs_dir/Zulip/.env`。

## 安全和兼容边界

- Web 入口是账号密码登录；`arch_xxx` token 是账号 API 凭据，不是主页登录凭据。
- CLI 和模型优先用 API token；缺 token 时可用 `--username` + `--password-file` 登录，不在 argv 中传密码。
- `CHATEVENT_ADMIN_TOKEN` 作为 bootstrap/恢复路径保留兼容，但新配置应由 ChatEnv/secret file 管理。
- FastAPI、SQLite schema、webhook endpoints 和 `chatevent api ...` 命令保持向后兼容；这次对齐不改变已发布事件 JSON contract。
