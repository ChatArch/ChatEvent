# Community capture and execution

The community companion is opt-in. The Observatory can keep running a published
ChatEvent release while the companion runs a separately pinned source revision.
It never turns an ordinary capture subscription into permission to execute.

```
chatevent community serve --config ~/.chatarch/community/config.json
chatevent community status --config ~/.chatarch/community/config.json
chatevent community worker --config ~/.chatarch/community/worker.json
```

The real `chatevent --tree` includes these commands. Store trusted registry and
configuration under ChatArch home with owner-only permissions. Store secrets in
ChatEnv / TokenStore, and reference their paths in configuration. No account key,
webhook secret, event body, result database or runtime log belongs in Git.

Zulip uses the official `register` / `events` blocking event queue. Only native
rendered user mentions from authorized humans in permitted channels enter the
inbox. Quotes, code, ordinary name text, registered Agent authors and unrelated
channels do not start a model. Per-account queues preserve private visibility;
reconnect registers a queue before bounded message catch-up and commits progress
after durable capture. A catch-up backlog must complete before live delivery.

Discourse sends only `post_created` webhooks for explicitly permitted categories.
The receiver checks the exact configured instance and HMAC-SHA256 body signature,
uses native numeric author IDs and parsed mention links, and commits the inbox
before returning HTTP 202. Private-network URL exceptions, if required by the
installation, must name one reviewed destination rather than disable SSRF checks.

The capture outbox writes ChatEvent first, then enqueues a dispatch. These are
separate transactions, recoverable by stable native event identity. The companion
does not alter the Observatory's authentication, accounts or old collectors.
The [dispatch contract](community-dispatch.md) describes execution/reply states,
binding snapshots, interrupted-work quarantine and the native Hermes capability
binding. A model reply is not proof of a coding/deployment/Sandbox task.

For an Agent on a different machine, an outbound worker uses an existing SSH
transport and a loopback forward to the private companion. It long-polls for its
own jobs using a dedicated credential. No inbound public worker port is needed.
Its trusted local configuration selects the model home/interpreter; the central
registry cannot substitute local execution paths. A job is claimed once. When a
trusted operator configures `timeout_seconds`, a result accepted before that
deadline remains usable even if the central waiter wakes later; a late result is
retained for reconciliation, not promoted to success. Omitting the optional
deadline permits an indefinite serial wait: a disconnected worker can hold later
invocations until operator intervention. The identity-bound sender replies only
after a durable result is returned. Idle workers make no model calls. Lost
acknowledgments retry the stored result, not the model. Expired or interrupted
central execution requires reconciliation and is never automatically replayed.

The companion handles new channel/forum mentions and can bind native configured
Hermes tools for real workspace tasks. Direct messages, edited-message execution,
arbitrary Agent-to-Agent wakeups and automatic interrupts are separate ingress
capabilities. Add runtime bindings by their verified capabilities rather than
treating an account registration as an online executor.
