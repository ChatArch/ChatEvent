# 过滤、游标与保存视图

ChatEvent 采集范围由上游 `Subscription` 与平台权限决定。`SavedView` 只保存查询定义，不启动采集器，也不包含 Agent 模型、唤醒 URL 或任务分配。Agent 框架决定何时消费事实和如何行动。

## 条件表达式

叶子节点为 `{"field":"source","op":"eq","value":"zulip"}`。组合节点为 `{"all":[...]}`、`{"any":[...]}` 或 `{"not":{...}}`；最多 6 层、64 节点，`in` 最多 50 项，文本值最长 1024 字符。未知字段、操作符、格式和过深表达式在数据库查询前被拒绝。没有任意 SQL、`eval` 或正则操作符。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source`, `instance`, `kind`, `subscription_id` | 文本 | 来源、实例、动作、采集订阅 |
| `action.kind`, `action.object_type`, `action.verb` | 文本 | 结构化动作，可跨平台按动词或对象筛选 |
| `actor.id`, `actor.type`, `actor.role`, `actor_id`, `actor_role` | 文本 | 发起者身份和角色；可在查询中排除 bot/self |
| `subject_id`, `subject_type`, `conversation_id` | 文本 | 被作用对象及会话 |
| `target.type`, `target.key`, `target.parent.type`, `target.parent.key`, `target.parent.parent.type`, `target.parent.parent.key` | 文本 | 承载目标和直接父级 |
| `tags` | 数组 | `contains` 为精确成员匹配；`in`/`any` 为交集，`all` 要求全部成员 |
| `occurred_at`, `captured_at` | 时间 | 带时区 ISO 8601；SQLite 时间比较精度约毫秒 |
| `url`, `payload.title`, `payload.content`, `payload.text`, `payload.topic`, `payload.stream`, `payload.post_number`, `payload.topic_id`, `payload.emoji_code`, `payload.from_topic`, `payload.from_stream`, `payload.sender_id`, `payload.name` | 文本 | 声明过的展示字段 |
| `payload.score` | 数值 | 声明过的数值扩展字段 |
| `metadata.timestamp_source`, `metadata.event_name` | 文本 | 声明过的元数据 |

`eq`、`ne`、`in` 适用于标量（`in` 列表不含 null）；`tags` 支持 `in`/`any`（任一成员）、`all`（全部成员）、`contains`（单个成员）和 `exists`。文本 `contains` 不区分大小写；`exists` 接受布尔值；`gt`、`gte`、`lt`、`lte`、`between` 仅适用于时间或数值。数值/时间比较不会将字符串自动转换。缺失字段不匹配叶子（`exists:false` 除外）；显式 JSON `null` 算存在，只匹配 `eq:null`。`ne` 不包含缺失或类型不符的字段。`not` 对叶子结果取反，因此能包含缺失字段。JSON path 和值均作为 SQLite 参数绑定；不允许动态未声明路径。

示例：

```json
{"all":[
  {"field":"source","op":"eq","value":"zulip"},
  {"any":[{"field":"kind","op":"eq","value":"message.created"},{"field":"kind","op":"eq","value":"reaction.added"}]},
  {"not":{"field":"actor.role","op":"eq","value":"bot"}}
]}
```

## 查询和分页

先在服务端过滤，再分页。`sort=desc` 按不可变入库序号浏览新事件；`sort=asc` 可顺序读取积压。`limit` 为 1–500，默认 100。响应含 `items`、`count`、`next_cursor`、`has_more`。处理成功后保存最后非空页的 `next_cursor`；即使 `has_more=false`，后续增量轮询仍用这个游标。空页时保留之前的游标。改变 filter、sort 或账号后必须重新开始，混用游标会返回 422。重复投递只增加 `seen_count`，不会生成新序号；同一捕获时间的事件不会因时间并列漏掉。新写入事件不会出现在已开始的 `desc` 旧页前面；刷新首页可看到它们。

旧 `GET /api/events` 仍可浏览并接收原有简写参数。其 `next_since` 是单页最新捕获时间，不是无损积压消费游标。

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

## 保存视图

`POST /api/views` 接收 `name`、`filter`、`sort`；返回服务器生成的 `id` 和当前账号 `owner_user_id`。member 的 `GET /api/views`、`GET /api/views/{id}`、`PUT /api/views/{id}`、`DELETE /api/views/{id}` 均限定其 owner；admin 可查看并管理全部视图。`GET /api/query?view_id=<id>` 使用视图定义；无需保存也可直接传 `filter`。网页的多选/高级 JSON 生成同一表达式，并支持保存、加载、删除和翻页。

```bash
cat > view.json <<'JSON'
{"name":"Community messages","filter":{"field":"kind","op":"in","value":["message.created","reply.created"]},"sort":"asc"}
JSON
chatevent api save-view view.json
chatevent api views
chatevent api query --view-id '<view_id>' --limit 50
chatevent api delete-view '<view_id>'
```

member 只能查询其拥有的订阅关联事件；admin 可查询全部事件。没有订阅归属的旧事件只对 admin 可见。过滤条件和视图都不能扩大权限。事件响应包含原始 payload，因此应按账号授权控制 API 凭据。
