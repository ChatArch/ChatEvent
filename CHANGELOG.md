# 更新日志

## 0.1.4 - 2026-08-19

- 新增登录页 gate：配置管理员 token 或用户后，未登录访问 `/` 只显示登录页，不能直接进入 Observatory。
- 新增 `/api/login` / `/api/logout` cookie 登录流程；`/api/stats`、`/api/events`、schema、platforms、subscriptions 等读取 API 在需要登录时会返回 401。
- 主题切换按钮从“黑底/白底”改为“☾ 夜间 / ☀ 日间”。

## 0.1.3 - 2026-08-19

- 修复来源联动高级事件类型列表：现在会合并平台 action catalog 与当前已观察到的该来源事件类型。
- GitHub action catalog 补充 `workflow_run.requested` 与 `workflow_run.in_progress`，避免真实 webhook 事件在高级筛选中缺失。
- 新增轻量登录与用户管理骨架：`arch_xxx` token 登录、`/api/session`、`/api/users`、CLI `api create-user`，token 只返回一次且服务端只存 hash。
- Subscription 增加 `owner_user_id`，为后续用户数据隔离打基础；member token 创建/读取订阅时按 owner 隔离，bootstrap/admin token 可管理全部。

## 0.1.2 - 2026-08-19

- Observatory 顶层筛选收敛为 `source` 与时间下拉框；事件类型、订阅/渠道、关键词和自定义起止时间移入“高级选项”。
- 高级事件类型改为随来源联动的多选 checkbox，订阅/渠道也按来源联动，可组合过滤更复杂场景。
- Platform actions 中的 action chip 可点击打开详情，展示 action kind、target types、捕获方式、webhook events 与 API 大致含义。
- 页面头部新增 GitHub 与 Docs 图标链接，并增加黑底/白底主题切换，主题偏好保存在浏览器本地。

## 0.1.1 - 2026-08-19

- 新增开放式 `CarrierTarget`、`ActionDescriptor` 与 `ActorDescriptor`，把订阅和事件明确建模为“动作 + 发起人/角色 + 承载目标”。
- `Subscription` 新增 `scope` 与 `actions`，并从旧字段 `target` / `event_kinds` 自动派生，保持旧客户端兼容。
- `ChatEvent` 新增 `action`、`actor`、`actor_role` 与 `target`，平台 adapter 会写入真实 action target chain，例如 repo → PR → comment 或 stream → topic → message，并可保留 maintainer/member/bot/moderator 等发起人角色。
- `/api/platforms` 的 action catalog 新增 `target_types`，前端可以展示每类 action 通常挂载在哪些承载目标上。
- Observatory Event Stream 新增 Target 列；事件详情显示 `Action`、`Action target`、`Target chain`；Subscriptions 编辑页可以查看/编辑 scope leaf。

## 0.1.0 - 2026-08-19

第一个完整 Event Hub 版本。

- 将默认运行态迁移到 ChatArch 内部：`$CHATARCH_HOME/chatevent/` 或 `~/.chatarch/chatevent/`。
- 新增 `chatevent paths --json`，用于回读数据库、secret 目录和旧库迁移状态，不输出 token 值。
- 默认数据库改为 `<chatarch-home>/chatevent/events.db`；首次默认启动会把旧版 `~/.chatevent/events.db` 复制到新位置，旧文件保留。
- 新增默认管理员 token 文件 `<chatarch-home>/chatevent/secrets/admin-token`，并保留 `CHATEVENT_ADMIN_TOKEN` / `CHATEVENT_ADMIN_TOKEN_FILE` 覆盖。
- 提供 Web Observatory：事件流、订阅、平台 action 目录、日期筛选、搜索、source/kind 筛选和事件详情。
- 提供 REST API 与 `chatevent api ...` CLI 对应，用于查询事件、写入标准事件、读取/编辑订阅、按 checkpoint 消费事件。
- 支持 Discourse、Zulip、Gitea、GitHub 的官方 webhook / event queue / API cursor 风格 normalizer。
- 公开 MkDocs 双语文档与 GitHub Pages 发布流程。

## 0.0.1 - 2026-08-18

- 初始事件 envelope 和 monitor protocol 占位版本。
