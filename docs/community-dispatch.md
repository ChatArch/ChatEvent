# Community dispatch companion contract

This opt-in companion is separate from ChatEvent ingestion and does not change capture subscriptions into execution permissions. Runtime configuration, SQLite state, private inputs and outputs belong under `~/.chatarch/community/`. Capturing an event or returning an enqueue receipt does not prove execution completed.

## Registry (trusted operator configuration)

```json
{
  "version": 1,
  "human_actor_ids": {"zulip": ["user:1"], "discourse": ["user:1"]},
  "ignored_actor_ids": {"zulip": ["user:18"], "discourse": ["user:5"]},
  "agents": [{
    "agent_id": "hermes-recall",
    "enabled": true,
    "bindings": {
      "zulip": {"account_id": "user:18", "instance": "https://zulip.example.org", "profile": "~/.chatarch/envs/Zulip/hermes-recall.env", "allowed_stream_ids": [12]},
      "discourse": {"account_id": "user:5", "instance": "https://forum.example.org", "profile": "~/.chatarch/envs/Discourse/hermes-recall-community.env", "allowed_category_ids": [7]}
    },
    "runtime": {
      "kind": "hermes",
      "python": "/absolute/committed/venv/bin/python",
      "source": "/absolute/existing/hermes-agent",
      "home": "/absolute/existing/hermes-home",
      "cwd": "/absolute/authorized/workspace",
      "timeout_seconds": 3600,
      "approval_mode": "native"
    }
  }]
}
```

Include **all** known Agent community IDs as bindings (or in `ignored_actor_ids`), even when an entry is disabled. All registered Agent authors are ignored before mention matching. Only explicitly listed human IDs may trigger; scopes match allowed native stream/category IDs, with no wildcard; capture must set `metadata.community_scope` to `stream:ID` or `category:ID`, and the matching native ID must exist in `raw_payload.message.stream_id` / `raw_payload.post.category_id`. Topics may vary inside those permitted containers. Account instance must equal the normalized event instance. An enabled binding is snapshotted at enqueue and cannot change an in-flight invocation. Registry holds paths/references, never credential values. The examples are placeholders, not existing permissions.

## Capture → enqueue

```python
store = DispatchStore(db_path)
receipt = store.enqueue(event, mentions=["user:18"], registry=registry)
```

`event` is a validated ChatEvent or its dictionary. `mentions` must come from the capture layer's platform-native, authenticated mention parsing, never an LLM or a regex over arbitrary display names. Root capture preserves canonical IDs and authenticated original message fields. The dispatcher accepts new Zulip `message.created` and Discourse `post.created` / `reply.created` facts only, ignores bot/system authors and all registered Agent identities, checks human/scopes/instance, then deduplicates `(source, instance, source event id, agent_id)`. To dedupe separate collectors of the same message, it prefers the stable source `subject_id` for these create facts over queue delivery IDs.

Receipt: `{"dispatch_ids":["..."],"duplicate":false,"ignored_reason":null}`. Ignored facts return an empty ID list and a machine-readable reason. Repeated delivery returns the existing IDs with `duplicate:true`. A conflicting replay of the same source message is rejected rather than replacing the original payload.

## Worker / adapter / reply sender

```python
worker = DispatchWorker(store, adapters={"hermes": adapter}, reply_sender=sender)
receipt = worker.run_once()
```

`adapter(invocation: dict) -> dict` returns:

```json
{"status":"succeeded","text":"actual final output","session_id":"runtime-issued-or-null","runtime_status":"completed","evidence":{}}
```

Statuses: `succeeded`, `failed`, `waiting_for_user`, `cancelled`, `unknown`. A success requires nonempty output and real completion evidence. Adapter exceptions are `unknown`, not an automatic re-execution. No return value or text prefix proves success on its own.

`sender(invocation: dict, result: dict) -> dict` must use the invocation's snapshotted `agent_id` and account binding (`binding.account_id`), reply only to the source message/conversation, and return `{"id":"native-reply-id","identity_id":"user:18"}` after platform acceptance. It must not substitute owner credentials. Failure/ambiguous network outcome leaves `reply_state=unknown`; retry requires explicit reconciliation to avoid duplicate posts. Dispatch ID is available as a reconciliation marker.

One `run_once()` claims at most one invocation or one already-computed pending reply. Execution states are `queued/running/succeeded/failed/waiting_for_user/cancelled/unknown`; reply states are `not_ready/pending/sending/sent/unknown`. Database transactions claim work before side effects. A cross-process worker lock serializes workers; after owning that lock, recovery changes interrupted `running`/`sending` states to `unknown`, never replays them. Completed results and replies are durably recorded separately. No queue means no adapter/model call. Definitive failures may receive a bounded failure reply; ambiguous outcomes stay unknown without automatic retries.

## Native Hermes capability binding

The adapter uses the existing Hermes interpreter, model resolver, configured CLI toolsets and MCP discovery. It loads native workspace context, SOUL identity, memory, skills and SessionDB. Work starts at the configured workspace root; tasks read AGENTS.md and projects/README.md, create the required dated project/PRD/progress records, validate their changes and commit understood edits. Native tools operate with the existing host user's permissions.

`runtime.approval_mode` is `native` by default. An operator may explicitly bind `full` after authorizing that agent's work: the adapter uses Hermes' auditable session-scoped full approval API and clears it in `finally`. It does not call the CLI's implicit-YOLO oneshot path or alter global approval configuration. Existing native user deny/hardline policies still apply. The adapter does not impose a two-turn or fixed output-token demonstration budget; configured native iteration limits are preserved. An optional operator lifecycle deadline can be configured independently.

The private request file survives interpreter re-execution; implicit bootstrap installation is disabled. Each execution has its own process group and private diagnostics under ChatArch home. The source revision is verified, actual completion is recorded, and interrupted/ambiguous work is never automatically re-executed.

## Visible task acknowledgements

A durable status projection is created with each newly accepted invocation. It is delivered by a separate model-free worker: queued/received, running, succeeded, failed, unknown, waiting_for_user or cancelled. Central claim and remote claim do not prove work has started. The Hermes child writes a private marker immediately before invoking its agent turn, after native initialization; the parent sends an idempotent started callback. Outbound workers acknowledge that boundary through their authenticated started endpoint.

Zulip switches only the invoked account's managed reaction on the original message. Discourse uses one own-author status post and edits it in the original topic with a separate minimally scoped status credential. A status receipt is independently read back before it is considered delivered. Ambiguous new-post creation is quarantined or recovered from its known native post ID; it is never blindly repeated. Status failures cannot block execution, change its result or cause another model turn. Received status can coalesce to a later truthful state when processing completes quickly.
