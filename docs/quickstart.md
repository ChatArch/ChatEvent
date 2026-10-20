# 快速开始

ChatEvent 负责捕获、规范化、保存和查询社区事实。Agent 的唤醒、运行、调度和任务分配由 Agent 框架决定。

## 安装

在源码检出目录：

```bash
python -m pip install -e '.[serve]'
chatevent --tree
chatevent --tree-brief
chatevent paths --json
chatevent serve --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765/`。默认数据库由 ChatEnv 管理，兼容 `$CHATARCH_HOME/chatevent/events.db` 和 `~/.chatarch/chatevent/events.db`；可用 `CHATEVENT_DB` 覆盖。默认路径存在旧库时会按既有兼容逻辑迁移，事件序号表再对旧事件做加法迁移。

## 账号和凭据

设置 `CHATEVENT_BOOTSTRAP_USERNAME` 与 `CHATEVENT_BOOTSTRAP_PASSWORD_FILE` 初始化管理员，在网页用账号密码登录，再生成 API token。CLI 使用 `CHATEVENT_ADMIN_TOKEN` 环境变量，或 `--username` 与 `--password-file`。配置值应由 ChatEnv profile 或服务 secret 文件提供，示例不包含实际值。未配置账号和管理员 token 时保留本地开发匿名模式；只应绑定可信本地接口。

## 第一个查询

先通过[注册监控](monitoring.md)连接平台，或者用已授权的规范化事件写入接口。保存订阅本身不会开始采集。查询所有已授权事件：

```bash
chatevent api query --sort desc --limit 50
chatevent api query --source zulip --kind message.created --sort asc --limit 50
```

`next_cursor` 用于下一页和增量续读。`GET /api/events` 为旧客户端保留，但其 `next_since` 不是无损 checkpoint。Observatory 的多选与 JSON 条件组均在服务端分页前执行。[过滤与视图](filtering.md)提供 curl、Python 和保存视图示例；[接口参考](reference.md)列出入口。

Voice 路径只保存元数据，不保存摘要或转写正文。
