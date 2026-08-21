# Changelog

## 0.2.0

- Aligned ChatEvent with standard Chat-series package conventions by adding `click`, `chatstyle`, and `chatenv` dependencies.
- `chatevent --tree` now uses a ChatStyle-rendered CLI tree while preserving the existing argparse command runtime.
- Added `chatevent.config:ChatEventConfig` and registered it under the ChatEnv `chatenv.configs` entry point.
- Default runtime paths now prefer ChatEnv `get_paths().home_dir` while keeping `CHATARCH_HOME`, `CHATEVENT_DB`, and legacy DB migration compatibility.
- MkDocs navigation now uses standard grouped command/interface pages, including bilingual `CLI Tree` and `Interface Tree` docs.

## 0.1.5

- Corrected the login model: the Web entry now uses username/password login, and `arch_xxx` tokens are no longer Web login credentials.
- Added password-hash storage and bootstrap admin initialization through `CHATEVENT_BOOTSTRAP_USERNAME` + `CHATEVENT_BOOTSTRAP_PASSWORD_FILE`.
- Added API token issue endpoints: `POST /api/me/token` and `POST /api/users/{id}/token`; tokens are for CLI, model, or programmatic API calls on behalf of an account.
- The logged-in Web session can edit subscriptions directly; CLI/API clients can use a token or login with username + password file.

## 0.1.4

- Added a login-page gate: once an admin token or users exist, unauthenticated visits to `/` see only the login page and cannot enter the Observatory.
- Added `/api/login` / `/api/logout` cookie login; read APIs return 401 when login is required.
- Replaced the theme button wording with `☾ Night / ☀ Day` semantics instead of black/white labels.

## 0.1.3

- Advanced action-kind options now merge the platform action catalog with observed event kinds for the selected source.
- The GitHub action catalog now includes `workflow_run.requested` and `workflow_run.in_progress`.
- Added an early login/user-management skeleton (corrected in 0.1.5 to username/password Web login plus API tokens): `/api/session`, `/api/users`, and CLI `api create-user`.
- `Subscription.owner_user_id` provides the first isolation boundary for member-owned subscriptions while administrators can still manage all subscriptions.

## 0.1.2

- The Observatory top filter bar now keeps only source and time dropdowns; the rest moved into Advanced options.
- Advanced options support source-bound action-kind checkboxes, subscription/channel checkboxes, keyword search, and custom time ranges.
- Platform action chips can be opened to show action kind, target types, acquisition modes, webhook events, and a short API meaning summary.
- The header now includes GitHub / Docs icon links and a black/white theme toggle.

## 0.1.1

- Add open-ended `CarrierTarget` / `ActionDescriptor` / `ActorDescriptor` to record action, carrier target chain, and initiator role.
- The Observatory shows a Target column and event details now include Action, Action target, Target chain, and Actor role.

## 0.1.0

The first complete Event Hub release. It moves ChatEvent from an event-model skeleton into a runnable, observable, consumable ChatArch-series service package.

- Default runtime state is ChatArch-internal: `$CHATARCH_HOME/chatevent/` or `~/.chatarch/chatevent/`.
- `events.db` stores the event ledger and subscription config; `secrets/admin-token` can provide the admin token file.
- `chatevent paths --json` reports effective runtime paths and configuration state without printing token values.
- Legacy `~/.chatevent/events.db` is copied into the new default location on first default startup, while the legacy file is kept in place.
- The Web Observatory provides Event Stream / Subscriptions / Platform actions tabs.
- Subscriptions can be created, edited, enabled/disabled, and deleted; mutation routes can require an admin token.
- REST API endpoints align with the `chatevent api ...` CLI client for event writes, event queries, single-event reads, and subscription management.
- Official event capture and normalizers cover Discourse, Zulip, Gitea, and GitHub.

## 0.0.1

Initial event envelope and monitor protocol placeholder release.
