# 快速开始

## 安装开发环境

```bash
uv sync --extra serve --extra test --extra docs
uv run chatevent --tree
```

如果只运行 API/UI，至少安装 `serve` extra：

```bash
uv sync --extra serve
```

## 启动 Observatory

```bash
uv run --extra serve chatevent serve \
  --host 127.0.0.1 \
  --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

当前服务器 demo 的实际入口：

```text
https://event.public.wzhecnu.cn/
https://event.local.wzhecnu.cn/
```


## 确认默认目录

默认不需要传 `--db`。ChatEvent 会把运行态放到 ChatArch home 内部：

```text
$CHATARCH_HOME/chatevent/events.db
# 未设置 CHATARCH_HOME 时：~/.chatarch/chatevent/events.db
```

用 `paths` 回读实际位置：

```bash
uv run chatevent paths --json
```

如果旧版 `~/.chatevent/events.db` 存在，且新的 ChatArch 内部数据库还不存在，第一次默认启动会复制旧库到 `~/.chatarch/chatevent/events.db`，但不会删除旧文件。

## 页面刷新机制

Observatory 当前是前端轮询，不是 WebSocket/SSE。

- 页面加载后立即执行一次 `loadAll()`。
- 之后每 **5 秒** 自动刷新一次。
- 点击页面右侧事件流标题旁的 **刷新** 按钮，会立即手动刷新。
- 搜索框输入会做约 **260ms debounce** 后刷新。
- 来源筛选、事件类型筛选变化后会立即刷新。

每次刷新会并行请求：

```text
GET /api/stats
GET /api/subscriptions
GET /api/events?...filters
GET /api/platforms
```

所以“平台动作发生 → Observatory 看到”的延迟由两段组成：

1. 平台把官方事件送到 ChatEvent 的时间：webhook 通常是秒级；Zulip event queue 取决于 capture pass 的轮询或运行方式；API cursor 取决于配置的增量任务频率。
2. 前端下一次 5 秒轮询的时间；手动点刷新可立即查看。

## 写入一条事件

```bash
uv run chatevent record-json event.json
```

事件最小字段：

```json
{
  "id": "issue:owner/repo:42",
  "source": "gitea",
  "kind": "issue.opened",
  "occurred_at": "2026-08-18T12:00:00Z",
  "capture_mode": "webhook"
}
```

## 查看平台 action 目录

```bash
uv run chatevent platforms
uv run chatevent platforms --json
```

这些 action 也会出现在 Observatory 左侧的 **Platform actions** 区块里。