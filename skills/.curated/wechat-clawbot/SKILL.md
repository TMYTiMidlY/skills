---
name: wechat-clawbot
description: 用 OpeniLink Hub（微信 ClawBot / iLink 协议开源平台）收发微信消息、管理 Bot/App/权限。当用户要用程序给自己或他人发微信消息 / 通知（含"搞定后通知我"）、用 REST API 收消息（webhook / WebSocket 推送）、调微信 Bot API、给 App 设/改 scope、regenerate app_token、或排查 openilink-hub（oih）时触发。核心：分清 Bot API（程序用 app_token）与管理 API（后台登录 session）两套；收消息是 Hub 主动推（webhook / WS）不是轮询；改 scope 走管理 API 不改库；密码用 portal secret 注入、绝不进对话。自托管部署（oih + 反代）见 vps-maintenance skill。
---

# WeChat ClawBot — OpeniLink Hub 操作

操作微信 Bot 平台 **OpeniLink Hub**（`github.com/openilink/openilink-hub`，开源 MIT）。它是微信 2026.3 官方 **ClawBot** 插件 / **iLink（智联）协议**的自托管封装：单一 `oih` 二进制（或 docker）+ SQLite，默认监听 `:9800`。

> 本 skill 只写**使用侧**通用操作（收 / 发 / 管理）。**自托管部署**（装 `oih` / docker compose / 反代 / env）见 `vps-maintenance` skill 的 [`references/wechat-clawbot.md`](../../vps-maintenance/references/wechat-clawbot.md)。hub 地址、用户名、app_id、installation_id 等通过 env / 参数传入，不写死在此。远端执行 / 密码注入用 `portal_*` MCP 工具（`portal_exec` / `portal secret`，用法见其工具 docstring）。

## 一句话心智模型

- **iLink 只有 1 对 1 私聊，没有群**。数据库里的 `group_id` 字段是平台为「多 provider」预留的通用列，iLink 永远为空；UI 里即便能勾「入群/退群」类事件，对 iLink bot 也**永不触发**。先验证再下结论：查 `messages` 表 `group_id` 是否全空、看实际 `event_type`。
- **两套 API，别混**：

| | Bot API | 管理 API |
|---|---|---|
| 路径 | `/bot/v1/*` | `/api/*` |
| 给谁用 | 程序 / 外部多端 client | Web 后台（人）|
| 鉴权 | `Authorization: Bearer <app_token>` | 登录 `session` cookie |
| 官方文档 | **有**：仓库 `docs/app-development.md` | **无**，只能读 `internal/api/router.go` 源码 |

- **没有 OpenAPI/Swagger spec**（运行时 `/openapi.json`、`/docs` 都是 SPA 兜底页，假的）。`oih` CLI 只有 `version` / `install` / `uninstall` 三个子命令，**没有任何设 scope / 管理命令**。

## 凭证模型（两层，最容易搞混）

- **App 层**：`app_id` + `webhook_secret`。`webhook_secret` 用于**验证收到的事件确实来自 Hub**（`HMAC-SHA256(secret, "{ts}:{body}")`，对应 `X-Signature` 头），也用于 app 级 WebSocket。
- **Installation 层**（App 装到某个微信号后）：`app_token`（形如 `app_<64hex>`，Bearer）+ `installation_id` + `handle`（@提及句柄）。`app_token` 用于**发消息 / 调 Bot API**。
- **标识符 ≠ 密钥**：`bot_id` / `installation_id` / `handle` 是标识符，可示人；`webhook_secret` / `app_token` 才是密钥，必须保密、别进 git / 别进对话。
- 方向记忆：**收**消息验真伪 → `webhook_secret`（被动）；**发**消息 / 操控 → `app_token`（主动）。

## 发消息（Bot API）

```
POST <hub>/bot/v1/message/send
Authorization: Bearer <app_token>
{"type":"text","content":"...","to":"<对方 wxid，省略=发给 Bot 自身>"}
→ {"ok":true,"client_id":"...","trace_id":"..."}
```

- 需要 `message:write` scope。其它：`GET /bot/v1/info`（需 `bot:read`）、`GET /bot/v1/contact`（需 `contact:read`）、WebSocket `GET /bot/v1/ws?token=<app_token>`。
- **24h 窗口**（iLink 协议层限制）：Hub 不能后台静默续期，只能到期前提醒。所以「无限制主动群发任意人」做不到，主动推送受窗口约束。
- 个人号 + 非官方协议，有**封号/合规风险**（官方 README 自带免责声明）。
- 可直接用 `scripts/send_message.py`（hub / app_token / to / content 走 env，`app_token` 用 portal secret 注入）——也是"搞定后通知我"类完成通知的最快入口。

## 收消息（Hub 主动推，不是轮询）

**没有 GET 轮询接口**——消息由 Hub **推**给你，两条通道（都需 `message:read` scope）：

### 通道一：Webhook（HTTP POST，你跑个 HTTP 端点收）

后台给 App 配一个 webhook URL，Hub 把事件 POST 过来：

1. **首次校验**：Hub 先发 `{"type":"url_verification","challenge":"<rand>"}`，你原样回 `{"challenge":"<rand>"}`。
2. **验签**（每个事件 POST 都带头，**必须验**）：`X-Signature: sha256=<hex>`，算法 `HMAC-SHA256(webhook_secret, "{X-Timestamp}:{原始 body}")`，相等才可信。其它头：`X-App-Id` / `X-Installation-Id` / `X-Timestamp` / `X-Trace-Id`。
3. **事件信封**（`message.text` 为例）：
   ```json
   {"v":1,"type":"event","trace_id":"tr_x","installation_id":"inst_x","bot":{"id":"bot_x"},
    "event":{"type":"message.text","id":"evt_x","timestamp":1711234567,
             "data":{"message_id":123,"sender":{"id":"wxid_abc","role":"user"},
                     "group":null,"content":"hello","msg_type":"text"}}}
   ```
   类型：`message.text` / `.image` / `.voice` / `.video` / `.file`、通配 `message`、`command`（slash 命令 / AI tool 调用，`sender.role` 区分 `user`/`agent`）。iLink 私聊 `group` 恒 `null`。
4. **回复**（**3 秒内**必须响应 HTTP，否则重试：立即 / 10s / 60s 三次）：
   - 同步回：响应体 `{"reply":"..."}`，或 `{"reply_type":"image","reply_url":"...","reply_name":"x.png"}`。
   - 来不及（>3s）：先回 `{"reply_async":true}`，再用上面的 Bot API 把结果 `POST /bot/v1/message/send` 异步推回（带 `trace_id` 关联）。**别回 "处理中…" 占位**——会被当成最终回复（AI tool 调用还会把占位喂回 LLM）。

### 通道二：WebSocket（实时推，免暴露公网回调）

不想开公网 webhook（脚本 / 自托管集成最适合）就连 WS，收 `{"type":"event",...}` 帧：

```
GET <hub>/bot/v1/ws?token=<app_token>                               # 单 installation
GET <hub>/bot/v1/app/ws?app_id=<app_id>&secret=<webhook_secret>     # 一个连接收本 Hub 所有 installation（事件带 installation_id 区分）
```

帧：server→client `{"type":"init"|"event"|"ack"|"error"|"pong"}`；client→server `{"type":"ping"}` / `{"type":"send","req_id":"r1","content":"hello"}`。

### 投递优先级（重要）

`installation WS 已连 → 走 WS`；否则 `app WS 已连 → 走 WS`；否则 `配了 webhook_url → POST`；都没有 → **事件丢弃**。所以同一 installation **别又连 WS 又指望 webhook**——WS 在就不会再 POST。


## 改 scope —— 走管理 API，别改数据库（重点）

正道（session + API，走应用层校验、UI 同步、token 重签都正确）：

1. **拿 session**（密码登录）：`POST /api/auth/login {"username","password"}` → 响应 `Set-Cookie: session=...`（HttpOnly，7 天）。用 cookie jar 自动持有。
2. **改 app scopes**：`PUT /api/apps/{app_id}`，body 只传 `{"scopes":[...]}`（部分更新，其它字段 nil 则保留）。
3. **installation 继承**：`POST /api/apps/{app_id}/installations/{iid}/reauthorize` —— 把 `installation.scopes ← app.scopes`（官方「加 scope 后授权」机制）。
4. （可选）**换 token**：`POST /api/apps/{app_id}/installations/{iid}/regenerate-token` → 返回新 `app_token`，旧的立即失效。

要点：**只有 `installation.scopes` 实际生效**（Slack model：`app.scopes` 是上界、不可越权）。所以必须「改 app → reauthorize」两步，单改 app 不够。

常用 scope：`message:write`（发）、`message:read`（收）、`bot:read`、`contact:read`、`tools:write`。

可直接用 `scripts/api_setscope.py`（登录→改 app scope→reauthorize→查证）和 `scripts/api_regen.py`（regenerate，新 token 写 0600 文件不打印 + 验证旧 token 失效）。

## 密码安全注入（portal-mcp-server）

agent 自动化时**绝不让密码进对话**：

1. 用户在本机跑 `portal secret set <name>`（或 `portal secret confirm <name>` 双输防手滑）把 hub 密码存进**本机 credential agent**。
2. agent 用 `portal_bash(secrets=["<name>"])` 把它注入成环境变量（名字大写，如 `openilink_password` → `$OPENILINK_PASSWORD`）。脚本里 `os.environ[...]` 读取，agent 全程只传 secret 的**名字**、不碰明文；输出里若回显也被 redact 成 `***`。secret 没设/过期时 portal 直接拒绝执行，不会问你要明文。
3. portal 工具的完整用法见各 `portal_*` 工具的 docstring（`portal_exec` 的 `secrets=[...]` 注入、`portal secret set` 存密码）。

> session 本身只在脚本进程的 cookie jar 内存里、跑完即弃，不打印 / 不落盘 / 不外传。每次登录会在服务端 `sessions` 表留一条 7 天有效记录（token 没被持有 = 孤儿 session，自然过期即可）。

## 验证技巧（高信号）

- **401 vs 403**：`401`=token 无效 / 未认证；`403`=token 有效但缺 scope。用这个区分「token 坏了」还是「权限不够」——是排查这套系统最有用的一刀。
- **只读验 token**：`GET /bot/v1/info` 验有效性，不用真发消息打扰人。
- **轮换验证**：regenerate 后，用新 token 调 info 应 `200`、旧 token 应 `401`，即确认旧的已吊销。
- 自签证书（反代常用 `tls internal`）：client 端 `curl -k` / Python `ssl.CERT_NONE`。
