# ChatEvent

ChatEvent 捕获社区动作，规范化为 `ChatEvent`，保存在 SQLite，并通过 API、CLI 和 Observatory 查询。`Subscription` 定义上游采集范围；`SavedView` 定义已入库事实的查询条件。Agent 框架自行决定何时读取、调度和行动。**0.3.0** 提供多动作捕获、组合过滤和保存视图，变更见[发行说明](CHANGELOG.md)。

[英文版](README.en.md) · [完整文档](https://arch.gh.wzhecnu.cn/ChatEvent/) · [过滤与视图](docs/filtering.md)

## 安装与启动

从此源码检出目录执行：

```bash
python -m pip install -e '.[serve]'
chatevent --tree
chatevent --tree-brief
chatevent paths --json
chatevent serve --host 127.0.0.1 --port 8765
```

浏览器打开 `http://127.0.0.1:8765/`。生产认证使用 `CHATEVENT_BOOTSTRAP_USERNAME` 和 `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` 初始化管理员；账号登录后生成 API token，CLI 可从 `CHATEVENT_ADMIN_TOKEN` 环境变量读取。配置值由操作者的 ChatEnv profile 或 secret 文件提供，不写入仓库。未配置任何用户和管理员 token 时，服务保留显式本地开发模式；此模式允许本地匿名读写，请只绑定可信本地接口。

数据库默认在 ChatEnv 管理的 `<chatarch-home>/chatevent/events.db`；`CHATEVENT_DB` 可覆盖。兼容路径为 `$CHATARCH_HOME/chatevent/events.db` 或 `~/.chatarch/chatevent/events.db`。`chatevent paths --json` 显示实际路径，不显示凭据。

## 捕获

Zulip 队列命令请求 `message`、`update_message`、`delete_message`、`reaction`、`stream`、`subscription` 和 `realm_user`，在有界时长内读取并删除队列：

```bash
chatevent capture zulip-once --env-file ./zulip.env --timeout 30 --subscription-id zulip-community
```

`zulip.env` 需要 `ZULIP_SITE`、`ZULIP_BOT_EMAIL`、`ZULIP_BOT_API_KEY`（或 ChatEnv 兼容命名）。`--content` 会实际发消息，仅供明确的写入练习；普通采集不使用。每次新建队列之间的动作可能丢失；`capture subscription-once` 的 topic 消息 ID 回填只能恢复当前可见消息创建，不能恢复编辑或 reaction 历史。

Discourse 在平台管理界面配置 `https://events.example.org/webhooks/discourse`。服务端设置 `CHATEVENT_DISCOURSE_WEBHOOK_SECRET_FILE`、`CHATEVENT_DISCOURSE_INSTANCE` 和可选的 `CHATEVENT_DISCOURSE_SUBSCRIPTION_ID`，与平台 webhook secret、实例和绑定相对应。HMAC 验证原始请求体的 `X-Discourse-Event-Signature`。其他 webhook 或规范化 `POST /api/events` 在配置认证后需要授权 token/session。Discourse 当前 topic/posts 快照可只读、限量回填：

```bash
chatevent capture discourse-topic-backfill --base-url https://forum.example.org --topic-id 18 --limit 50 --api-key-env DISCOURSE_API_KEY --api-username api-user
```

此命令不重建历史编辑或删除。保存或启用 `Subscription` 只是采集配置，不会自动运行 collector。平台目录也不代表全部动作都已接入；详见[动作覆盖表](docs/platform-actions.md)。

## 查询与视图

`GET /api/query` 先在服务端过滤，再按不可变入库序号分页。`sort=desc` 供浏览；`sort=asc` 和 `next_cursor` 供不漏页的增量读取。旧 `GET /api/events` 保持兼容，其 `next_since` 是本页最新时间，**不能**作为可靠的积压消费 checkpoint。

```bash
cat > filter.json <<'JSON'
{"all":[{"field":"source","op":"eq","value":"zulip"},{"field":"kind","op":"in","value":["message.created","reaction.added"]},{"not":{"field":"actor.role","op":"eq","value":"bot"}}]}
JSON
chatevent api query --filter-file filter.json --sort asc --limit 50
chatevent api save-view view.json
chatevent api views
```

`view.json` 示例：`{"name":"Community facts","filter":{"field":"source","op":"eq","value":"zulip"},"sort":"asc"}`。视图归当前账号所有；member 只能读自有订阅关联的事件，未归属旧事件仅管理员可见。网页同样支持多选、条件组 JSON、分页和保存/加载/删除视图。[过滤指南](docs/filtering.md)含 curl、Python 和完整字段/空值语义。

ChatEvent 不负责 Agent 唤醒、任务队列、分配或通用发帖网关。Voice 保留 metadata-only 采集边界。
