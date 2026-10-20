# 注册采集范围

`Subscription` 描述上游平台、目标、授权范围和动作范围；`SavedView` 是对已入库事件的查询。保存或启用订阅不会启动后台 collector。平台凭据仍由平台的 ChatEnv profile 或服务 secret 文件管理。

## 创建订阅

账号 API token 通过 `CHATEVENT_ADMIN_TOKEN` 提供；以下请求由服务端把 member 的 `owner_user_id` 绑定为当前账号。

```bash
curl -X POST 'https://events.example.org/api/subscriptions' \
  -H "X-ChatEvent-Admin-Token: $CHATEVENT_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"id":"zulip-community","source":"zulip","target":"stream:community/topic:news","event_kinds":["*"],"capture_modes":["event_queue"]}'
```

member 的事件查询只会看到其拥有订阅关联的事实。无订阅归属的历史事件仅管理员可见。查询视图不能扩大这个权限。

## Zulip 事件队列

在操作员管理的 env 文件中配置 `ZULIP_SITE`、`ZULIP_BOT_EMAIL`、`ZULIP_BOT_API_KEY`（或兼容的 Actor 名称）；不要把值放入文档、Git 或 CLI 参数。

```bash
chatevent capture zulip-once --env-file ./zulip.env --subscription-id zulip-community --timeout 30
```

命令注册一个官方队列，请求消息创建、编辑/移动、单条/批量删除、reaction、stream、subscription 和 realm_user 事件，按类型分发后删除队列。输出 `captured`、`created`、`unsupported`、`scope_unknown`、`control`，可判断这一轮覆盖。带 `--stream`/`--topic` 的窄范围模式对缺少可验证上下文的稀疏事件按 fail-closed 跳过并增加 `scope_unknown`。`--content` 会真实发送消息，仅供明确练习。每次新建队列之间有潜在缺口；需要持续运行时，采用有界但足够长的捕获窗口及外部监督，不能把反复短轮询说成完整队列历史。

已有的 `capture subscription-once --subscription-id zulip-community` 是 message ID 游标 topic 回填，读取当前可见的消息创建；它不恢复队列断开期间的 reaction 或编辑历史，也不能恢复已删除消息。

## Discourse webhook 与只读回填

在 Discourse 管理界面把 webhook URL 指向 `https://events.example.org/webhooks/discourse`，选中[动作覆盖表](platform-actions.md)中的 core 事件，并设置平台 webhook secret。ChatEvent 服务端配置：

```text
CHATEVENT_DISCOURSE_WEBHOOK_SECRET_FILE=<operator-managed-secret-file>
CHATEVENT_DISCOURSE_INSTANCE=https://forum.example.org
CHATEVENT_DISCOURSE_SUBSCRIPTION_ID=discourse-community
```

绑定的订阅必须预先存在且 source=discourse。ChatEvent 用原始请求体验证 `X-Discourse-Event-Signature: sha256=...`，读取 `X-Discourse-Event` 动作名与 `X-Discourse-Event-Type` 包装类型。`X-Discourse-Instance` 只有在与已配置的实例绑定一致时才被接受为路由依据；不要仅凭不可信 header 或 payload 赋值 owner/instance。未配置签名 secret 时，webhook 需要授权的 ChatEvent API token 或 session。其他平台 webhook 在配置认证时同样需要授权 ingest 凭据。

只读、限量的当前 topic/posts 快照：

```bash
chatevent capture discourse-topic-backfill --base-url https://forum.example.org --topic-id 18 --limit 50 --subscription-id discourse-community --api-key-env DISCOURSE_API_KEY --api-username api-user
```

`DISCOURSE_API_KEY` 由调用环境提供。该命令读取 `/t/{id}.json` 和最多 100 个 `/posts/{id}.json`，只写本地 ChatEvent 数据库，不修改 Discourse。快照只表示当前可见对象，不重建历史编辑、删除或恢复。Discourse webhook 重试可能生成新的 delivery-row ID；去重使用动作、对象、修订/时间和规范化 payload 指纹，不仅靠 `X-Discourse-Event-Id`。

观察捕获结果：

```bash
chatevent api stats
chatevent api query --source discourse --sort desc --limit 50
```

Voice 始终只保存 metadata；平台 action catalog 是能力目录，不等于 collector 已运行。完整过滤方式见[过滤与视图](filtering.md)。
