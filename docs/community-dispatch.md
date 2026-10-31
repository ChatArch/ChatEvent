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
      "cwd": "/absolute/authorized/project",
      "timeout_seconds": 180,
      "max_iterations": 2
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

## Initial Hermes boundary

The initial adapter uses the existing Hermes Python agent API with the existing model resolver, a fixed project cwd, an explicit empty toolset and a runtime assertion that no tool schemas were exposed. `source_sha` can pin the existing source revision; the adapter refuses dirty sources. It does not invoke Hermes `-z`: the installed version's oneshot implementation automatically enables YOLO and accepts hooks, and an empty CLI `--toolsets` falls back to configured defaults. It does not install, start gateway, copy credentials, enable host shell, discover MCP, or expand workspace rights. Model text processing is a real execution capability; coding/deployment with tools remains a separate, unverified capability until an existing restricted Task/Sandbox route is verified and bound explicitly.

The subprocess reads private JSON input over stdin, produces a bounded result file under the companion state directory, runs in its own process group with a deadline and output limits, and is normally terminated then killed only within that owned group on timeout/cancellation. Logs and output files are private. Existing Hermes user configuration/model secrets remain on Recall. A failed/partial model result is never `succeeded`.
