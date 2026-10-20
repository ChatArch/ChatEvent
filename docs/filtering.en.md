# Filtering, cursors, and saved views

Upstream platform permissions and a `Subscription` define acquisition scope. A `SavedView` stores a query over captured facts; it does not start a collector or hold an Agent model, wakeup URL, or assignment policy. The Agent framework decides when and how to act on facts.

## Condition expressions

A leaf is `{"field":"source","op":"eq","value":"zulip"}`. Groups are `{"all":[...]}`, `{"any":[...]}`, and `{"not":{...}}`. Filters allow at most 6 levels and 64 nodes, `in` allows up to 50 elements, and text values are limited to 1024 characters. Unknown fields, operators, shapes, and excessive expressions fail before database I/O. There is no arbitrary SQL, `eval`, or regex operator.

| Field | Type | Meaning |
| --- | --- | --- |
| `source`, `instance`, `kind`, `subscription_id` | text | Platform, instance, action, acquisition subscription |
| `action.kind`, `action.object_type`, `action.verb` | text | Structured action fields for cross-platform matching |
| `actor.id`, `actor.type`, `actor.role`, `actor_id`, `actor_role` | text | Initiating identity and role, including bot/self query exclusion |
| `subject_id`, `subject_type`, `conversation_id` | text | Affected object and conversation |
| `target.type`, `target.key`, `target.parent.type`, `target.parent.key`, `target.parent.parent.type`, `target.parent.parent.key` | text | Carrier and immediate parent |
| `tags` | array | `contains` tests exact membership; `in`/`any` test overlap and `all` requires every member |
| `occurred_at`, `captured_at` | time | Timezone-aware ISO 8601; SQLite comparisons have approximately millisecond precision |
| `url`, `payload.title`, `payload.content`, `payload.text`, `payload.topic`, `payload.stream`, `payload.post_number`, `payload.topic_id`, `payload.emoji_code`, `payload.from_topic`, `payload.from_stream`, `payload.sender_id`, `payload.name` | text | Declared display fields |
| `payload.score` | number | Declared numeric extension field |
| `metadata.timestamp_source`, `metadata.event_name` | text | Declared metadata |

`eq`, `ne`, and `in` apply to scalars (`in` lists exclude null). For `tags`, `in`/`any` test any membership, `all` requires every requested member, `contains` tests one member, and `exists` checks presence. Text `contains` is a case-insensitive substring test. `exists` takes a boolean. `gt`, `gte`, `lt`, `lte`, and `between` apply only to time or number fields. Comparisons do not coerce strings to numbers or times. A missing field matches no leaf except `exists:false`. Explicit JSON `null` exists and matches `eq:null`; `ne` excludes missing and incompatible types. `not` negates the two-valued result and can therefore include missing fields. SQLite JSON paths and values are both bound parameters; undeclared dynamic paths are rejected.

Example:

```json
{"all":[
  {"field":"source","op":"eq","value":"zulip"},
  {"any":[{"field":"kind","op":"eq","value":"message.created"},{"field":"kind","op":"eq","value":"reaction.added"}]},
  {"not":{"field":"actor.role","op":"eq","value":"bot"}}
]}
```

## Query and pagination

Filtering happens on the server before paging. `sort=desc` browses newest insertion sequence first; `sort=asc` reads a backlog in order. `limit` is 1–500, default 100. Responses have `items`, `count`, `next_cursor`, and `has_more`. After successfully processing a nonempty page, retain its `next_cursor` even if `has_more=false`; use it for the next incremental poll. Retain the previous cursor after an empty page. Changing filter, sort, or account requires a fresh cursor; mixing them returns 422. Duplicate deliveries increase `seen_count` without a new sequence. Capture timestamp ties do not skip items. New arrivals before an old descending page require a fresh first-page browse.

Legacy `GET /api/events` and its shorthand parameters remain for browsing. Its `next_since` is only the latest capture timestamp in that page and is not a lossless backlog checkpoint.

```bash
chatevent api query --filter-file filter.json --sort asc --limit 50
chatevent api query --filter-file filter.json --sort asc --cursor '<next_cursor>' --limit 50
chatevent api query --source zulip --kind message.created --sort desc
```

```bash
curl --get 'https://events.example.org/api/query' \
  -H "X-ChatEvent-Admin-Token: $CHATEVENT_ADMIN_TOKEN" \
  --data-urlencode 'filter@filter.json' --data-urlencode 'sort=asc' --data-urlencode 'limit=50'
```

```python
import os
from chatevent.client import ChatEventApiClient
client = ChatEventApiClient(base_url="https://events.example.org", admin_token=os.environ["CHATEVENT_ADMIN_TOKEN"])
condition = {"field": "source", "op": "eq", "value": "zulip"}
page = client.query_events(filter=condition, sort="asc", limit=50)
while True:
    for item in page["items"]:
        print(item["event"]["kind"], item["event"]["subject_id"])
    if not page["has_more"]:
        break
    page = client.query_events(filter=condition, sort="asc", limit=50, cursor=page["next_cursor"])
```

## Saved views

`POST /api/views` takes `name`, `filter`, and `sort` and returns a generated `id` and the authenticated `owner_user_id`. For members, `GET /api/views`, `GET /api/views/{id}`, `PUT /api/views/{id}`, and `DELETE /api/views/{id}` are owner-scoped; admins can inspect and manage all views. `GET /api/query?view_id=<id>` uses the stored definition. Ad hoc filters require no view. Dashboard multi-select and advanced JSON create the same condition format and support save/load/delete and page navigation.

```bash
cat > view.json <<'JSON'
{"name":"Community messages","filter":{"field":"kind","op":"in","value":["message.created","reply.created"]},"sort":"asc"}
JSON
chatevent api save-view view.json
chatevent api views
chatevent api query --view-id '<view_id>' --limit 50
chatevent api delete-view '<view_id>'
```

Members can query only events linked to subscriptions they own; admins can query all events. Unowned legacy events are admin-only. Filters and views never widen access. Event responses include raw payload, so protect account credentials accordingly.
