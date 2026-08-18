# 更新日志

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
