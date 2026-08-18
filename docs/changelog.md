# 发行说明

## 0.1.3

- 高级事件类型列表现在会合并平台 action catalog 与当前已观察到的来源事件类型。
- GitHub action catalog 补充 `workflow_run.requested` 与 `workflow_run.in_progress`。
- 新增 `arch_xxx` token 登录与用户管理骨架：`/api/session`、`/api/users` 和 CLI `api create-user`。
- `Subscription.owner_user_id` 为 member 用户订阅隔离打基础，管理员仍可管理全部订阅。

## 0.1.2

- Observatory 顶层筛选收敛为来源和时间下拉框，其余筛选进入高级选项。
- 高级选项支持按来源联动的事件类型多选、订阅/渠道多选、关键词和自定义时间范围。
- Platform actions 的 action chip 可点击打开详情，查看 action kind、target types、捕获方式、webhook events 和 API 大致含义。
- 页面头部新增 GitHub / Docs 图标链接，并支持黑底/白底主题切换。

## 0.1.1

- 新增开放式 `CarrierTarget` / `ActionDescriptor` / `ActorDescriptor`，记录动作、承载目标链和发起人角色。
- Observatory 显示 Target 列，事件详情显示 Action、Action target、Target chain 与 Actor role。

## 0.1.0

第一个完整 Event Hub 版本，重点是把 ChatEvent 从事件模型骨架推进为可运行、可观察、可消费的 ChatArch 系列服务包。

- 默认运行态归入 ChatArch 内部：`$CHATARCH_HOME/chatevent/` 或 `~/.chatarch/chatevent/`。
- `events.db` 保存事件账本和订阅配置；`secrets/admin-token` 可作为管理员 token 文件。
- `chatevent paths --json` 可回读默认目录和配置状态，不输出 token 值。
- 旧版 `~/.chatevent/events.db` 会在首次默认启动时复制到新位置，旧文件保留。
- Web Observatory 支持 Event Stream / Subscriptions / Platform actions 三个标签页。
- Subscriptions 支持新建、编辑、启停和删除；可用管理员 token 保护写操作。
- REST API 与 `chatevent api ...` CLI 对齐，可写入事件、查询事件流、读取具体事件、管理订阅。
- 支持 Discourse、Zulip、Gitea、GitHub 的官方事件捕获和 normalizer。

## 0.0.1

初始事件 envelope 和 monitor protocol 占位版本。
