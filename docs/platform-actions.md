# 平台动作覆盖

下表描述适配器和采集器实际支持的动作，均有自动化载荷与接口测试。生产接入还需要按实际凭据、权限和平台版本验证。`/api/platforms` 的 `capture_status=implemented` 表示有实现；`catalog_only` 仅表示平台概念，不能据此承诺已捕获。保存 `Subscription` 不会自动启动采集器。

| 平台入口 | 上游事件或动作 | 规范化 kind | 覆盖边界 |
| --- | --- | --- | --- |
| Zulip 官方 queue | `message` | `message.created` | 保留 bot/agent 活动；按实例+原生消息 ID 去重 |
| Zulip queue | `update_message` | `message.edited`, `message.moved`, `message.rendered` / `message.updated` | 同一移动事件可展开多个消息；内容编辑只指对应消息 |
| Zulip queue | `delete_message` | `message.deleted` | 单条 `message_id` 与批量 `message_ids` |
| Zulip queue | `reaction` add/remove | `reaction.added`, `reaction.removed` | 稀疏事件的 topic scope 需要已知消息上下文 |
| Zulip queue | `stream` create/update/delete | `stream.created/updated/deleted` | create 列表可展开 |
| Zulip queue | `subscription` add/remove/update | `subscription.added/removed/updated` | 列表可展开；不把 peer 事件假称订阅动作 |
| Zulip queue | `realm_user` add/update/remove | `user.added/updated/removed` | 被修改用户是 subject，不能无依据当作 actor |
| Discourse webhook | `post_created` | `post.created` 或 `reply.created` | `post_number > 1` 为 reply；兼容旧 `normalize_discourse_post()` |
| Discourse webhook | `post_edited`, `post_destroyed`, `post_recovered` | `post.edited/deleted/recovered` | 同一 post 的不同变更保留为不同事实 |
| Discourse webhook | `topic_created`, `topic_edited`, `topic_revised`, `topic_destroyed`, `topic_recovered` | `topic.created/edited/revised/deleted/recovered` | 上游 wrapped `topic` 对象 |
| Discourse webhook | `user_created`, `user_updated`, `user_approved`, `user_suspended`, `user_unsuspended`, `user_destroyed` | `user.created/updated/approved/suspended/unsuspended/deleted` | 被作用 user 是 subject；缺少显式 actor 时保持未知 |
| Discourse webhook | category/tag/group create/update/destroy | `category.*`, `tag.*`, `group.*` | 各 3 类、共 9 个上游名字 |
| Discourse webhook | `like_created`, `notification_created`, `group_user_added/removed` | `like.created`, `notification.created`, `group_user.added/removed` | 仅 payload 有稳定对象/成员身份时入库 |
| Discourse topic API | 当前 topic 和当前 posts | `topic.created`, `post.created` / `reply.created` 快照 | 有界只读回填；不重建历史变更 |

Zulip 注册 **7 个队列事件类型**；Discourse 显式映射 **28 个上游事件名**。计数表示实现覆盖，不是平台全部事件或生产验收结果。协议依据见 [Zulip 事件 API](https://zulip.com/api/get-events)、[队列注册](https://zulip.com/api/register-queue)、[Discourse 事件目录](https://github.com/discourse/discourse/blob/main/app/models/web_hook_event_type.rb)和[投递格式与签名](https://github.com/discourse/discourse/blob/main/app/jobs/regular/emit_web_hook_event.rb)。

Zulip heartbeat/restart 是控制事件，不伪装成消息。未知类型计入 `unsupported`；无法验证的 topic/stream 范围计入 `scope_unknown` 并跳过。`realm_user_groups`、其他 Zulip 类型及 Discourse 插件事件不在当前适配范围，也不宣称支持 `like_removed`。队列断开期间的 edit/reaction 和未投递 webhook 没有历史补偿保证。bot 活动不在采集阶段一概丢弃；通过[过滤条件](filtering.md)控制显示，角色只能在源信息已知时使用。

Zulip 的原生删除/移除事件是相对于当前观察账号而言，也可能表示失去可见性或频道归档，不能据此断言平台对象被永久删除。频道与订阅更新保留 `payload.property` / `payload.value`，完整来源载荷仍在 `raw_payload`。

原生对象 ID 是 `subject_id`；变更事件有自己的 `id`。`instance` 可区分平台实例，重复投递稳定去重，修改、删除和恢复各保留事实。源时间存在时用于 `occurred_at`，否则 `metadata.timestamp_source=capture-time` 表明使用捕获时间。
