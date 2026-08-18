# Changelog

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
