# Caddy Admin API 运行态配置

本 reference 说明如何通过 Caddy Admin API 临时修改 HTTP 路由和 caddy-security，并在验证后回滚或固化。它面向已获准操作运行态、需要保留现有服务的场景；常规配置编辑见 [Caddyfile 更新流程](caddy.md#caddyfile-update)，共享入口结构见 [共享 listener 的 Host 分流](caddy.md#shared-listener-routing)。

> Caddy 核心行为按 v2.11.2 核验；caddy-security 的 JSON 结构属于所安装插件的内部 schema，操作前必须以同一二进制的适配结果和实时配置为准。Caddy 的写入、回滚、ID 索引与 autosave 流程见 [v2.11.2 源码](https://github.com/caddyserver/caddy/blob/v2.11.2/caddy.go#L150-L403)。

## <a id="configuration-source"></a>配置来源与持久化

Admin API 的写请求先改 raw JSON，再严格解码并 provision 整份新配置；成功后切换运行上下文并默认写入 `autosave.json`，失败则继续运行旧配置并恢复 raw JSON。单次写入具有原子性，但它不是只修改某一个已存在 handler 的内存补丁。

“临时”取决于进程下次从哪里读取配置：

| 启动方式 | API 写入后的重启行为 | 权威配置 |
|---|---|---|
| `caddy run --config <Caddyfile>`，没有 `--resume` | restart 重新读取文件，API 写入被文件覆盖 | Caddyfile |
| `caddy reload --config <Caddyfile>` | 立即用文件适配出的整份配置覆盖当前运行态 | Caddyfile |
| `caddy run --resume` / `caddy-api.service` | restart 读取 `autosave.json`，API 写入和 `@id` 保留 | Admin API 管理的 JSON |
| `admin.config.persist=false` / `persist_config off` | 当前进程仍应用写入，但不更新 autosave | 取决于启动参数 |

> Caddy 的 API 文档说明变更默认持久化，并由 `--resume` 恢复；官方 systemd 文档把 `caddy.service` 和 `caddy-api.service` 分为文件型与 API 型工作流。见 [API 持久化说明](https://github.com/caddyserver/website/blob/15ac087cfd9c21a53b2ddfa10359fdc63d5ec9b6/src/docs/markdown/api.md#L9-L17)和 [systemd 服务类型](https://github.com/caddyserver/website/blob/15ac087cfd9c21a53b2ddfa10359fdc63d5ec9b6/src/docs/markdown/running.md#L34-L41)。

先读取实际 unit，不从服务名或目录习惯推断：

```bash
systemctl show caddy \
  --property=ExecStart \
  --property=ExecReload \
  --no-pager
```

文件型和 API 型工作流应只选一个作为权威来源。文件型部署的运行态试验最终回写 Caddyfile；API 型部署则把最终 JSON 保存到配置管理系统，并让 autosave 与该来源保持一致。

## <a id="api-address"></a>Admin endpoint

默认 endpoint 是 `localhost:2019`，但 `CADDY_ADMIN`、Caddy 配置和发行版打包均可改变它。默认值及环境变量覆盖逻辑见 [v2.11.2 admin 源码](https://github.com/caddyserver/caddy/blob/v2.11.2/admin.go#L57-L64)和 [默认监听地址](https://github.com/caddyserver/caddy/blob/v2.11.2/admin.go#L1422-L1425)。

下面的命令统一从变量读取实际地址：

```bash
ADMIN_URL="${ADMIN_URL:-http://localhost:2019}"
```

Admin endpoint 应只监听 loopback 或权限受控的 Unix socket。完整配置可能包含 OAuth client secret、JWT key、上游 token 或已经展开的环境变量；能读取或修改 endpoint 的主体应按入口层管理员对待。

## <a id="config-api-semantics"></a>配置 API 语义

`/config/[path]` 对 object 和 array 的语义不同：

| 方法 | object | array |
|---|---|---|
| `GET` | 读取字段或对象 | 读取元素或数组 |
| `POST` | 新建或覆盖字段 | 追加元素；路径以 `/...` 结尾时可展开追加数组 |
| `PUT` | 只新建尚不存在的字段 | 在指定 index 前插入元素 |
| `PATCH` | 替换已存在的字段 | 替换指定 index |
| `DELETE` | 删除字段 | 删除指定 index |

> 方法语义、`@id` 与并发控制见锁定版本的 [Admin API 文档源码](https://github.com/caddyserver/website/blob/15ac087cfd9c21a53b2ddfa10359fdc63d5ec9b6/src/docs/markdown/api.md#L143-L271)。

数组 index 会随插入和删除漂移。给临时 route、policy、transformer 等对象加入全局唯一的 `"@id"`，后续通过 `/id/<name>` 查询和删除。Caddy 在 raw config 中索引 ID，加载模块前剥离该元字段，因此第三方模块不会收到 `@id`。

每次从 `GET /config/...` 读取目标 scope 时，同时保存响应的 `Etag`。对应写请求带 `If-Match`；HTTP 412 表示配置已被其他写入改变，必须重新读取、重新定位对象并重新计算 index。

```bash
ADMIN_URL="${ADMIN_URL:-http://localhost:2019}"
WORK_DIR="${WORK_DIR:?set a protected working directory}"
CONFIG_SCOPE="${CONFIG_SCOPE:?set a scope without the /config/ prefix}"
umask 077

headers_file="$(mktemp "${WORK_DIR%/}/caddy-api-headers.XXXXXX")"
body_file="$(mktemp "${WORK_DIR%/}/caddy-api-body.XXXXXX.json")"

curl --noproxy '*' --fail --silent --show-error \
  --dump-header "$headers_file" \
  --output "$body_file" \
  "$ADMIN_URL/config/$CONFIG_SCOPE"

etag="$(
  sed -n 's/^[Ee][Tt][Aa][Gg]:[[:space:]]*//p' "$headers_file" |
    tr -d '\r'
)"
test -n "$etag"
jq -e . "$body_file" >/dev/null
```

`CONFIG_SCOPE` 是本次读取和写入共同覆盖的父 scope。body 可能包含敏感配置，按完整快照的相同标准保护。不要从另一台机器复制 `srv0`、嵌套数组路径、index 或 adapter 生成的 `groupNN`。

## <a id="preflight"></a>变更前检查

写入前先确认版本、启动方式、endpoint、完整快照和回滚对象。下面的命令作为一个 shell 脚本执行；任一步失败都会停止，不继续发送修改请求。

```bash
set -euo pipefail

systemctl show caddy --property=ExecStart --property=ExecReload --no-pager
CADDY_BIN="${CADDY_BIN:?set the exact ExecStart binary path}"
"$CADDY_BIN" version
"$CADDY_BIN" build-info | grep -E 'caddy-security|go-authcrunch|caddyserver/caddy/v2'

ADMIN_URL="${ADMIN_URL:-http://localhost:2019}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:?set a protected snapshot directory}"
test -d "$SNAPSHOT_DIR"

umask 077
snapshot="$(mktemp "${SNAPSHOT_DIR%/}/caddy-live-before.XXXXXX.json")"

curl --noproxy '*' --fail --silent --show-error \
  --max-time 10 \
  --output "$snapshot" \
  "$ADMIN_URL/config/"

jq -e . "$snapshot" >/dev/null
test -s "$snapshot"
stat -c '%a %n' "$snapshot"
```

只有脚本完整成功后，这份文件才算可用快照。快照不得贴进聊天、工单或普通日志；验证窗口结束后，按所在主机的敏感文件保留与销毁流程处理。

候选 JSON 使用正在运行的同一个 Caddy 二进制生成，输出也放进权限受控的目录：

```bash
set -euo pipefail

CADDY_BIN="${CADDY_BIN:?set the exact ExecStart binary path}"
CANDIDATE_CADDYFILE="${CANDIDATE_CADDYFILE:?set the candidate Caddyfile path}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:?set a protected snapshot directory}"
umask 077
candidate_json="$(mktemp "${SNAPSHOT_DIR%/}/caddy-candidate.XXXXXX.json")"

"$CADDY_BIN" adapt \
  --config "$CANDIDATE_CADDYFILE" \
  --adapter caddyfile \
  --pretty > "$candidate_json"

jq -e . "$candidate_json" >/dev/null
printf '%s\n' "$candidate_json"
```

片段不是完整 Caddyfile 时，先用最小 site block 包起来再适配。也可以调用 `POST /adapt`。复杂对象应从实时配置克隆，或从同版本适配结果抽取；不要凭记忆手写 caddy-security schema。

## <a id="temporary-route"></a>临时 HTTP 路由

共享 listener 依靠 Host matcher 区分业务，Caddyfile 结构与来源限制的安全顺序见 [共享 listener 的 Host 分流](caddy.md#shared-listener-routing)。Admin API 修改的是适配后的 JSON，操作顺序如下：

1. 从 `GET /config/` 中按 listener、Host matcher 或稳定 ID 找到目标 route 数组。
2. 断言目标 server、route 数组、来源限制和 catch-all 各自只有一个符合项；发现 `path`、`expression` 等未识别 matcher 时停止，不把它们归类为 catch-all。
3. 从同版本 `caddy adapt` 结果抽取候选 route，并加入唯一 `@id`。
4. 若来源限制是安全边界，插入点必须在 blocker 之后、catch-all 之前。blocker 若位于已有业务 route 之后，先修正 Caddyfile 的 `route` 顺序；不要继续制造绕过来源限制的新 route。
5. 从相邻业务 route 读取当前互斥 `group` 等结构字段，不复制固定的 `groupNN`。
6. 保存父 scope 的 `Etag`，再执行插入。

```bash
ROUTE_JSON="${ROUTE_JSON:?set the candidate route JSON path}"
ROUTES_PATH="${ROUTES_PATH:?set the active route array path}"
INSERT_AT="${INSERT_AT:?set the verified insertion index}"
test -n "$etag"

curl --noproxy '*' --fail --silent --show-error \
  --max-time 60 \
  -X PUT \
  -H 'Content-Type: application/json' \
  -H "If-Match: $etag" \
  --data-binary @"$ROUTE_JSON" \
  "$ADMIN_URL/config/$ROUTES_PATH/$INSERT_AT"
```

收到 412 后，从读取目标数组开始重做；不能在旧快照上只更新 index。客户端超时也不能立即重发，服务端可能仍在全局配置锁内继续加载。

验证覆盖以下层次：

- `GET /id/<route-id>` 能唯一找到新对象；
- 上游自身健康；
- 直接访问共享 listener 并携带目标 Host 时，来源限制和认证结果符合预期；
- 经过外层入口访问时，证书、Host、转发头和登录回跳符合预期；
- 登录成功只证明认证完成，还要用实际角色验证 authorization policy。

定向回滚前重新读取父 scope 并获取当前 `Etag`，再删除该 ID；index 漂移不会影响 `/id/` 路径。

```bash
curl --noproxy '*' --fail --silent --show-error \
  -X DELETE \
  -H "If-Match: $etag" \
  "$ADMIN_URL/id/<route-id>"
```

## <a id="security-runtime"></a>caddy-security 运行态配置

caddy-security 位于同一棵 JSON 配置树，常见数组路径为：

```text
/config/apps/security/config/identity_providers
/config/apps/security/config/authentication_portals
/config/apps/security/config/authorization_policies
```

这些路径和字段属于安装版本的内部 schema。先读取实时对象，或用同一个二进制把候选 Caddyfile 适配为 JSON。运行态变更按影响面处理：

| 对象 | 候选配置的来源 | 对现有登录态的影响 |
|---|---|---|
| authorization policy | 克隆现有同类 policy，换唯一 name 和 `@id`；需要改规则时从适配结果抽取 | 后续请求立即用新 policy 检查现有 JWT claims |
| portal user transformer | 克隆同一 portal 的同类 transformer，换唯一 `@id` | 只影响以后签发的 JWT；现有 token 要重登或等过期 |
| identity provider、cookie、签名 key | 仅从完整适配结果修改 | 可能打断登录流或使现有 token 全部失效，不用于普通临时验证 |

> policy 与 transformer 的生效时机见 [权限策略与令牌角色](caddy.md#security-token-claims)。

已有共享 policy 的语义满足目标 route 时，route 可以直接引用它；修改共享 policy 会同时影响所有引用者。需要隔离影响时，从实时配置克隆一份独立 policy：

```bash
SOURCE_POLICY="${SOURCE_POLICY:?set the source policy name}"
NEW_POLICY_NAME="${NEW_POLICY_NAME:?set the new policy name}"
NEW_POLICY_ID="${NEW_POLICY_ID:?set the temporary policy ID}"
POLICIES_JSON="${POLICIES_JSON:?set the current policies JSON path}"
POLICY_JSON="${POLICY_JSON:?set the candidate policy JSON path}"

jq --arg source "$SOURCE_POLICY" \
   --arg name "$NEW_POLICY_NAME" \
   --arg id "$NEW_POLICY_ID" '
  map(select(.name == $source))
  | if length == 1
    then .[0]
    else error("expected exactly one source policy")
    end
  | .name = $name
  | .["@id"] = $id
' < "$POLICIES_JSON" > "$POLICY_JSON"

jq -e . "$POLICY_JSON" >/dev/null
```

克隆只复用当前版本已经接受的结构。若要改变 ACL，先在候选 Caddyfile 中表达目标规则并适配，再把对应字段合入 `POLICY_JSON`。读取 policy 数组并保存当前 `Etag` 后，用 `POST` 追加：

```bash
POLICIES_PATH='apps/security/config/authorization_policies'
test -n "$etag"

curl --noproxy '*' --fail --silent --show-error \
  --max-time 60 \
  -X POST \
  -H 'Content-Type: application/json' \
  -H "If-Match: $etag" \
  --data-binary @"$POLICY_JSON" \
  "$ADMIN_URL/config/$POLICIES_PATH"
```

route 在下一次独立请求中引用新 policy。新增 policy 与新增 route 不构成跨请求事务：执行顺序为 policy → route → 验证；回滚顺序为 route → policy。portal transformer 同样先按 portal name 断言唯一对象，再在 `If-Match` 保护下追加；不要保存并复用一个可能漂移的 portal index。

## <a id="timeout-and-rollback"></a>超时与回滚

单个写请求失败时，Caddy 保留旧运行配置；多个请求之间没有事务。写请求超过客户端 `--max-time` 后：

- 不立即重发相同请求；
- 先测试业务 URL，再读取 `/id/<id>`；
- `GET /config/` 也超时而 pprof 正常时，按 [reload 配置锁阻塞](caddy.md#reload-lock)处理；
- 确认对象未生效且没有其他配置写入后，才重新读取并构造请求。

全量快照恢复会覆盖快照之后所有人的修改，只作为最后手段：

```bash
curl --noproxy '*' --fail --silent --show-error \
  --max-time 60 \
  -X POST \
  -H 'Content-Type: application/json' \
  --data-binary @"$snapshot" \
  "$ADMIN_URL/load"
```

执行前再次确认快照是非空合法 JSON，并确认快照之后没有其他写入。可以按 ID 定向回滚时，不使用整份恢复。

## <a id="convergence"></a>验证与配置收敛

运行态验证结束后，按启动方式把配置收敛回唯一权威来源：

| 部署方式 | 接受变更 | 放弃变更 |
|---|---|---|
| Caddyfile 型 | 把等价配置写入实际 import 的文件，格式化、带齐 service 环境变量验证，再 `reload`；完整文件会覆盖临时对象 | 按 ID 删除临时对象，或 reload 原 Caddyfile |
| `--resume` / API 型 | 把临时 name、`@id` 和对象整理为正式 JSON，导出并保存到配置管理系统；确认 autosave 后用 `--resume` restart 验证 | 按依赖反序删除临时对象，确认 autosave 已更新 |

Caddyfile 型配置通过 reload 应用；API 型 JSON 通过 Admin API 写入。新增域名和配置规模本身不是 restart 条件；更换二进制、systemd unit 或进程环境时才需要 restart。reload 已确认卡在配置锁时，restart 是恢复手段，后续仍要定位卡锁模块。

最后重新检查：

- 目标业务和认证结果；
- `GET /config/` 中的最终对象；
- 所有 `temp-*` ID 已删除或改成正式 ID；
- Caddyfile 型部署 reload 后不再出现临时对象；
- API 型部署 `--resume` restart 后仍能恢复正式对象。
