# 发行说明

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
