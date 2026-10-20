# ChatEvent

ChatEvent 捕获已授权社区里的动作，统一保存为事件，再通过网页、命令行和接口展示与过滤。**采集配置决定抓什么，保存视图决定看什么；Agent 框架自行决定如何行动。**

```text
平台 webhook / 事件队列 / API 快照 → ChatEvent → SQLite → 服务端查询 / Observatory
```

<div class="grid cards" markdown>

- **接入社区**

    配置 Zulip 官方事件队列、Discourse 签名 webhook 或只读主题回填。

    [注册采集范围](monitoring.md) · [动作覆盖](platform-actions.md)

- **筛选需要的信息**

    组合来源、动作、作者、目标、标签和时间条件；先筛选，再分页，保存为可复用视图。

    [过滤与视图](filtering.md)

- **让工具和 Agent 读取**

    Python、REST 和 CLI 使用同一套查询语义；按稳定游标读取新增事实。

    [快速开始](quickstart.md) · [接口参考](reference.md)

- **查看完整能力**

    真实命令树、接口树与实现状态，避免把平台目录误认为已接通能力。

    [CLI 树](cli-tree.md) · [接口树](interface-tree.md) · [发行说明](changelog.md)

</div>

## 运行与边界

默认数据库位于 ChatEnv 的 `<chatarch-home>/chatevent/events.db`；兼容 `$CHATARCH_HOME/chatevent/events.db` 与 `~/.chatarch/chatevent/events.db`。使用 `chatevent paths --json` 回读实际位置，使用 `chatevent --tree` 查看真实命令。

ChatEvent 不运行 Agent，不提供唤醒派发、任务分配或通用发帖网关。保存订阅不等于采集器已运行；平台目录的 `capture_status` 区分已实现与仅目录动作。采集只覆盖当前凭据可见的数据，查询过滤不能扩大权限。Voice 始终只保留元数据。
