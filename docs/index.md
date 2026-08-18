# ChatEvent

ChatEvent 是 ChatArch 的协作事件观察层：把 Zulip、Discourse、Gitea、GitHub 等平台的官方事件捕获下来，规范化为 Pydantic `ChatEvent`，写入 SQLite，并在 Web Observatory 中查看、筛选和调试。

```text
平台官方事件 / webhook / API cursor
  → ChatEvent normalizer
  → SQLite event store
  → Observatory / API
```

<div class="grid cards" markdown>

- **启动观察台**

  本地启动 `chatevent serve`，浏览器打开 Observatory，看统计、订阅、事件流和 raw payload。

  [进入快速开始](quickstart.md)

- **注册监控对象**

  为 Discourse category/topic、Zulip stream/topic、Gitea/GitHub repo 创建订阅，并把平台 webhook 或事件队列接到 ChatEvent。

  [查看注册监控](monitoring.md)

- **查看 action 目录**

  当前只把四个平台的常见动作列为一等公民，避免把任意 `tag` 当成事件语义。

  [查看平台与事件](platform-actions.md)

- **对接 API / CLI**

  用 HTTP API 写入、查询事件；用 `chatevent api ...` 作为 REST API 的命令行对应。

  [查看接口参考](reference.md)

- **确认默认目录**

  默认运行态位于 `$CHATARCH_HOME/chatevent/` 或 `~/.chatarch/chatevent/`，可用 `chatevent paths --json` 回读。

  [查看快速开始](quickstart.md)

</div>

## 当前产品边界

- ChatEvent 只负责 **捕获、规范化、去重、保存、观察**。
- 当前不直接执行 Agent、不开任务、不做路由决策。
- 平台 REST API 只用于官方事件后的对象补全、明确订阅范围内的 cursor 增量补偿和验收读回；ChatEvent 自身提供标准 REST API 供下游写入、查询和按 checkpoint 消费事件。
- 默认安装、运行、SQLite 账本和可选管理员 token 文件都归入 ChatArch 内部目录 `$CHATARCH_HOME/chatevent/`，未设置 `CHATARCH_HOME` 时为 `~/.chatarch/chatevent/`。
- 不做全盘扫帖、全站消息遍历、全仓库历史扫描或 HTML 爬虫式 capture。

## 事件语义

- `source`：平台来源，例如 `zulip`、`discourse`、`gitea`、`github`。
- `target`：兼容展示用订阅范围，例如 stream/topic、category/topic、repo/org。
- `scope`：结构化承载目标链，例如 repo → pull request 或 stream → topic。
- `kind` / `action`：发生了什么业务动作，例如 `message.created`、`reply.created`、`issue.opened`。
- `capture_mode`：怎么捕获，例如 `webhook`、`event_queue`、`api_cursor`。
- `tags`：筛选/路由标签，不定义事件动作本身。

## 当前验证入口

服务器 demo 当前暴露为：

- https://event.public.wzhecnu.cn/
- https://event.local.wzhecnu.cn/

生产化部署前应加认证、验签和受控服务管理；当前 demo 服务只绑定 loopback，由 nginx 反代。