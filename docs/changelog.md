# 发行说明

## 0.2.0

- 对齐标准 Chat 系列包规范：新增 `click`、`chatstyle`、`chatenv` 依赖。
- `chatevent --tree` 改为由 ChatStyle 渲染的标准 CLI 树，保留现有 argparse 命令执行路径。
- 新增 `chatevent.config:ChatEventConfig` 并注册到 ChatEnv `chatenv.configs` entry point。
- 默认运行态路径优先使用 ChatEnv `get_paths().home_dir`，同时保留 `CHATARCH_HOME`、`CHATEVENT_DB` 和旧库迁移兼容。
- MkDocs 改为标准分组导航，新增 `CLI 树` 与 `接口树` 中英文页面。

## 0.1.5

- 修正登录模型：Web 主页改为账号密码登录，`arch_xxx` token 不再作为网页登录凭据。
- 新增 password hash 存储与 bootstrap 管理员账号初始化：`CHATEVENT_BOOTSTRAP_USERNAME` + `CHATEVENT_BOOTSTRAP_PASSWORD_FILE`。
- 新增 API Token 生成接口：`POST /api/me/token` 与 `POST /api/users/{id}/token`；token 仅用于 CLI、模型或程序代表账号调用 API。
- Web 登录后可直接编辑订阅；CLI/API 可用 token，也可通过用户名 + 密码文件先登录后操作。

## 0.1.4

- 新增登录页 gate：配置管理员 token 或用户后，未登录访问 `/` 只显示登录页，不能直接进入 Observatory。
- 新增 `/api/login` / `/api/logout` cookie 登录流程；读取型 API 在需要登录时会返回 401。
- 主题切换按钮从“黑底/白底”改为“☾ 夜间 / ☀ 日间”。

## 0.1.3

- 高级事件类型列表现在会合并平台 action catalog 与当前已观察到的来源事件类型。
- GitHub action catalog 补充 `workflow_run.requested` 与 `workflow_run.in_progress`。
- 新增轻量登录与用户管理骨架（0.1.5 已修正为账号密码网页登录 + API Token 机制）：`/api/session`、`/api/users` 和 CLI `api create-user`。
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
