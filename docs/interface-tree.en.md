# Interface Tree

This page maps ChatEvent's Python modules, HTTP API, ChatEnv configuration, and security boundaries into one interface tree so the package aligns with standard Chat-series projects.

## Python Package Interface

```text
chatevent
├── catalog.py                  # Platform action catalog
│   ├── PlatformAction
│   ├── PlatformSpec
│   ├── list_platform_specs()
│   ├── get_platform_spec(source)
│   └── action_kinds_for(source)
├── model.py                    # Standard event envelope
│   ├── CaptureMode
│   ├── CarrierTarget
│   ├── ActionDescriptor
│   ├── ActorDescriptor
│   └── ChatEvent
├── subscription.py             # Subscription contract
│   └── Subscription
├── auth.py                     # Users, password hashes, API token hashes
│   ├── UserRecord
│   ├── generate_arch_token()
│   ├── token_digest(token)
│   └── password_digest(password)
├── config.py                   # ChatEnv configuration registration
│   └── ChatEventConfig
├── state.py                    # ChatEnv/ChatArch-owned runtime paths
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
├── adapters.py                 # Official platform payload normalizers
│   ├── normalize_zulip_message_event()
│   ├── normalize_discourse_webhook()
│   ├── normalize_gitea_webhook()
│   └── normalize_github_webhook()
├── capture.py                  # Bounded platform capture helpers
│   ├── load_env_file()
│   └── capture_zulip_once()
├── client.py                   # REST API client used by CLI
│   └── ChatEventApiClient
├── server.py                   # FastAPI app factory and REST/webhook endpoints
│   └── create_app()
├── dashboard.py                # Observatory HTML/CSS/JS
├── monitor.py                  # In-process event observer helper
└── cli.py                      # argparse runtime + ChatStyle-rendered CLI tree
    ├── build_parser()
    ├── render_cli_tree()
    └── main()
```

`__init__.py` re-exports the core domain objects and `ChatEventConfig` for downstream packages and ChatEnv discovery.

## HTTP API Surface

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
GET    /api/subscriptions        # List subscriptions; members see their own subscriptions
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

## ChatEnv Configuration Interface

ChatEvent registers `chatevent.config:ChatEventConfig` under the `chatenv.configs` entry point. ENV/profile/secret boundaries are:

| Field | Purpose | Sensitivity |
| --- | --- | --- |
| `CHATARCH_HOME` | ChatArch runtime home; defaults to ChatEnv `get_paths().home_dir` | Not sensitive |
| `CHATEVENT_DB` | Explicit SQLite DB path override | Not sensitive |
| `CHATEVENT_API_URL` | Default REST API base URL for CLI commands | Not sensitive |
| `CHATEVENT_ADMIN_TOKEN` | CLI/model/programmatic API token | Sensitive |
| `CHATEVENT_ADMIN_TOKEN_FILE` | API token file path | Path is not sensitive; contents are sensitive |
| `CHATEVENT_API_USERNAME` | Username for CLI password-login fallback | Not sensitive |
| `CHATEVENT_API_PASSWORD_FILE` | CLI password file path | Path is not sensitive; contents are sensitive |
| `CHATEVENT_BOOTSTRAP_USERNAME` | First administrator username | Not sensitive |
| `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` | First administrator password file path | Path is not sensitive; contents are sensitive |

Platform credentials are not invented by ChatEvent. Zulip, Discourse, Gitea, GitHub, and similar secrets should stay in their own ChatEnv profiles or service secret files. `capture zulip-once` defaults to ChatEnv `envs_dir/Zulip/.env`.

## Security And Compatibility Boundaries

- Human Web entry uses username/password login; `arch_xxx` tokens are account API credentials, not homepage login credentials.
- CLI and model automation should prefer API tokens; when no token exists, `--username` plus `--password-file` is available without putting passwords in argv.
- `CHATEVENT_ADMIN_TOKEN` remains as a bootstrap/recovery compatibility path, but new deployments should manage it through ChatEnv or secret files.
- FastAPI endpoints, SQLite schema, webhook endpoints, and `chatevent api ...` commands remain backward compatible; this alignment does not change the published event JSON contract.
