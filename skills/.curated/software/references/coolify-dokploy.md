# Coolify 与 Dokploy

[Coolify](https://coolify.io) 与 [Dokploy](https://dokploy.com) 都是自托管 PaaS：控制面负责连接代码仓库、构建镜像、管理运行环境和生成入口路由，真正的业务应用仍作为独立容器或服务运行。本文先讲两者共有的部署判断，再分别记录产品专有架构、异常状态、前置反代和清理边界。

## <a id="common"></a>共性

### <a id="host-selection"></a>宿主约束与选型

| 判断维度 | Coolify | Dokploy |
|---|---|---|
| 编排基础 | 普通 Docker / Compose；也能管理 Swarm destination | 安装和控制面依赖 Docker Swarm，单节点也要初始化 Swarm |
| 官方默认入口 | 平台代理默认占用宿主 80/443 | 独立 `dokploy-traefik` 默认占用 80/443；控制面另发布 3000 |
| 安装前端口处理 | 不会自动寻找空闲端口；冲突通常在容器启动时暴露 | 滚动安装脚本先检查 80/443/3000，任一占用即退出 |
| 多服务宿主上的改造 | 可以人为修改端口和前置反代，但要维护升级持久性 | 跳过官方入口后容易形成“面板可访问、应用入口不完整”的非标准运行态 |

表中的“官方默认”描述产品原生安装或源码行为；非标准宿主端口、额外端口桥接、上游反代改写都属于部署者的改造，不是平台自动避让或推荐拓扑。若宿主已经承载多个入口服务，先决定谁拥有 80/443、谁负责证书和域名分流，再安装平台。

### <a id="control-and-workload-planes"></a>控制面与工作负载面

两类平台都至少包含以下两层：

1. **控制面**：dashboard、数据库、缓存、队列、平台自己的反向代理和管理网络。
2. **工作负载面**：由平台构建或拉取的业务镜像、应用容器或 Swarm service、应用卷、应用网络、域名路由和证书状态。

控制面能打开，只能证明 dashboard 的访问链路成立；不能证明新应用的域名路由、TLS、WebSocket、健康检查或自动部署链路成立。排障和清理时也要分别盘点这两层，否则很容易删掉面板却留下业务容器，或保住面板却误以为应用入口可用。

### <a id="upstream-proxy-and-port-ownership"></a>上游反代与端口所有权

把平台放到 Cloudflare、Caddy、nginx 或另一层 Traefik 后面时，先画清请求链：

```text
浏览器
  → 公网 DNS / TLS 终结
  → 上游反向代理
  → 平台入口代理
  → dashboard 或业务应用
```

共通原则：

- 一个宿主端口同一时刻只能由一个监听者拥有。平台不会因为前面已有反代就天然理解端口该让给谁；非标准宿主端口通常是人为修改或额外转发。
- 上游反代可以终结 TLS，再用 HTTP 回源；但必须保留正确的 `Host`、`X-Forwarded-*` 和 WebSocket upgrade 语义。具体产品怎样信任这些头、怎样生成路由，见 [Coolify](#coolify) 与 [Dokploy](#dokploy)。
- dashboard 域名通了，不等于应用域名通了。平台生成的应用路由通常仍假定请求会到达它自己的入口代理；若绕过该代理，就要另外承担域名分流、证书和实时连接配置。
- 若继续使用平台的自动签证和自动域名路由，公网 80/443 到平台入口的路径必须完整；若完全由上游接管，则要明确 TLS 终结层和挑战流量路径，避免重复签证、挑战失败或重定向环。

### <a id="pre-deployment-checks"></a>部署前检查

1. 列出宿主当前监听端口，确认 80/443 及产品控制面端口的所有者。
2. 决定 TLS 在哪一层终结，以及平台入口代理是否仍保留。
3. 区分“只访问 dashboard”和“还要发布对外应用”两种目标；后者必须额外验证应用域名路由。
4. 记录平台创建的容器或 service、卷、网络、配置目录、SSH key、端口转发和防火墙规则。
5. 记录安装时为释放端口而停掉或迁走的原服务；卸载平台后要恢复它们，不能只删除平台资源。
6. 用一个最小测试应用验证完整路径：构建、启动、域名匹配、TLS、WebSocket（如有）、重启和升级后配置是否仍在。

### <a id="cleanup-boundary"></a>清理边界

卸载平台不是只停 dashboard，也不是只删配置目录。建议按依赖从外到内清理：

1. 先确认业务应用和数据是否需要导出；盘点平台实际部署出的容器、service、卷和镜像。
2. 撤掉公网 DNS、上游反代、端口转发、非标准端口映射和平台生成的应用入口，避免流量继续进入待删除环境。
3. 先删除工作负载，再删除控制面；控制面 compose 或 service 停止后，独立容器和已部署应用不一定随之消失。
4. 分层核对配置目录、Docker 卷、网络、镜像、应用容器和边缘路由。它们属于不同资源层，删除某个目录不等于完整卸载。
5. 检查平台写入普通用户与 root 账户的 SSH 管理 key，以及防火墙、宿主端口转发和其他宿主级改造。
6. 恢复安装时为释放 80/443 或其他端口而停掉、改端口或迁走的原服务。
7. 最后复核监听端口、Docker/Swarm 资源和外部访问结果。只有确认 Swarm 没有承载其他工作负载时，才能为清理 Dokploy 而退出 Swarm。

Coolify 的 standalone sentinel、带管理标签的应用容器和网络占用见 [Coolify 产品专有清理](#coolify-product-cleanup)；Dokploy 的独立代理或 socat 容器、task 收敛和 Swarm 生命周期见 [Dokploy 产品专有清理](#dokploy-product-cleanup)。

## <a id="coolify"></a>Coolify

[Coolify](https://coolify.io) 是开源自托管 PaaS（Heroku/Vercel 替代品），Laravel 12 + Livewire 3 + Tailwind v4，用 SSH 管理 server / 应用 / 数据库 / 服务。默认自带一个 Traefik 反代，直接占宿主 80/443 对外。

本章讲 Coolify 专有内容：**把 Coolify 塞到另一层前置反代（Cloudflare / 独立 Caddy / nginx）后面**时会踩的一整套坑——CSS 全变 http、实时功能连不上 WebSocket、端口拓扑、改管理员账号、界面汉化——以及它们对应的 Coolify 源码位置。

> 所有源码行号对齐 **v4.1.2**（`git tag v4.1.2`, commit `e7dff30b7`）。换版本前先自查行号是否漂移。核实这类结论的方法：完整 clone `coollabsio/coolify`（非 shallow），`git checkout` 到跟你运行的镜像同版本的 tag（`docker inspect coolify --format '{{.Config.Image}}'` 看运行版本，`git log -1` 确认 HEAD 落在对应 tag），再对着源码逐条核对——别只信文档里的行号。
>
> `coolify.io/docs` 没有与 v4.1.2 一一对应的冻结 URL，本文把它只当产品说明入口；能由源码证明的结论均优先链接到 v4.1.2 tag。只有在线文档描述的 GUI/产品行为，升级后要重新核验。

---

### <a id="runtime-architecture"></a>运行架构

一个标准 Coolify 主机跑 6 个容器，但它们**不在一个 compose 里**——这点反直觉，改配置前必须先分清：

| 容器 | 镜像 | 归属 | 职责 |
|---|---|---|---|
| `coolify` | `coollabsio/coolify` | source compose | Laravel + Livewire 主应用（dashboard UI / API / 全部业务逻辑）。容器内 nginx 听 8080 |
| `coolify-proxy` | `traefik:v3.x` | **proxy compose**（独立） | Traefik 反代：① 反代 dashboard 域名 → `coolify:8080`；② 给你用 Coolify 部署的 app 自动签证书 + 反代（读 docker labels） |
| `coolify-realtime` | `coollabsio/coolify-realtime` | source compose | 两个进程：**6001 = Soketi**（Pusher 协议兼容的 WebSocket server，推部署进度 / 状态 / 日志流）、**6002 = web terminal** |
| `coolify-db` | `postgres:15-alpine` | source compose | Coolify 自己的元数据（server/app/service/project/team/user/env/部署历史）。**不是给你部署的业务用的** |
| `coolify-redis` | `redis:7-alpine` | source compose | Laravel session/cache/queue（Horizon 调度）+ broadcast driver 把 PHP 事件转给 Soketi |
| `coolify-sentinel` | `coollabsio/sentinel` | **standalone `docker run`** | 监控 agent，报告**被管理 server** 的 CPU/RAM/磁盘/容器健康 |

**两个 compose 的边界（决定改哪个文件、会不会被升级覆盖）**：

- **source compose** = `/data/coolify/source/docker-compose.yml` + `docker-compose.prod.yml`（叠加文件，一个 project）。装 coolify / coolify-db / coolify-redis / coolify-realtime。**安装和升级时从 GitHub 拉 prod template 覆盖这俩文件**，直接改它们升级即失效。要持久化改动有两个官方落点：① 大多数可调项走 `/data/coolify/source/.env`；② `.env` 覆盖不了的（如把 dashboard 端口 bind 到 `127.0.0.1`、加资源限制）走 `/data/coolify/source/docker-compose.custom.yml`——升级脚本会 `if [ -f ... ]` 判断存在就 `-f` 合并进去（[`scripts/upgrade.sh:L70-L71`](https://github.com/coollabsio/coolify/blob/v4.1.2/scripts/upgrade.sh#L70-L71)），所以能扛升级。**注意不是 `docker-compose.override.yml`**：升级脚本永远显式 `-f` 指定 compose 文件，Docker Compose 的 override 自动发现机制（仅在不带 `-f` 时生效）不会触发，那个文件名会被静默忽略。
- **proxy compose** = `/data/coolify/proxy/docker-compose.yml`。只装 coolify-proxy(Traefik)。**由 Coolify 后端 PHP 动态生成**（[`generateDefaultProxyConfiguration()`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L226-L366)）。
- **sentinel** 不在任何 compose，Coolify 用单独 `docker run` 起。它设计成"每台被管理 server 装一个"，所以不属于 source compose；自管自的机器也会跟着装上。

为什么 Coolify 要把 proxy 拆出去单独 compose：① 你可以在 dashboard 换 proxy 类型（Traefik ↔ Caddy，`beta.237+`）或设 `Proxy → None` 交给外部反代；② proxy 升级不牵动 Laravel。

---

### <a id="ports-and-entry"></a>端口与入口

Coolify 文档 [firewall 章节](https://coolify.io/docs/knowledge-base/server/firewall) 列的"官方端口"：

| 端口 | 谁 | 源码 |
|---|---|---|
| **80 / 443** | Traefik 公网入口（HTTP-01 签证 + HTTPS 主入口） | [`bootstrap/helpers/proxy.php:L288-L290`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L288-L290) `ports: 80:80 / 443:443 / 443:443/udp` |
| **8080** | Traefik 自己的 dashboard/API（`api@internal`），通过 [Docker label](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L268-L271) 接到 public `http` entrypoint，**不受 `--api.insecure=false` 门控**、且没设 `rule=` | [`bootstrap/helpers/proxy.php:L291`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L291) `8080:8080` |
| **8000** | Laravel **直连**入口（备用；文档说用域名访问后可 "safely close"） | [`docker-compose.prod.yml:L24`](https://github.com/coollabsio/coolify/blob/v4.1.2/docker-compose.prod.yml#L24) `${APP_PORT:-8000}:8080` |
| **6001** | Soketi 实时 WS | [`docker-compose.prod.yml:L65`](https://github.com/coollabsio/coolify/blob/v4.1.2/docker-compose.prod.yml#L65) `${SOKETI_PORT:-6001}:6001` |
| **6002** | web terminal | [`docker-compose.prod.yml:L66`](https://github.com/coollabsio/coolify/blob/v4.1.2/docker-compose.prod.yml#L66) `6002:6002`（**硬编码、无 env 开关**） |
| 5432 / 6379 | db / redis | 仅容器内，无宿主 binding |

> `8080:8080` 常被忽略（连 Coolify 官方 firewall 文档都没提），但它是 proxy compose 里真实生成的宿主 binding——排查/加固时别漏。同一 `ports:` 数组里就在 80/443 下一行。

**关键落差**：Coolify **不会**探测端口占用、也不会自动避让——[`bootstrap/helpers/proxy.php:L287-L291`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L287-L291) 把 Traefik 的宿主端口**硬编码**成 `80:80 / 443:443 / 8080:8080`，[`scripts/install.sh:L1031-L1046`](https://github.com/coollabsio/coolify/blob/v4.1.2/scripts/install.sh#L1031-L1046) 也恒按 `:8000` 打印访问地址，没有任何"挑空闲端口"逻辑。**所以如果你看到某台 Coolify 的 Traefik 跑在非标准宿主端口（如 `127.0.0.1:8001:80`），那一定是人为改过 proxy compose 的 `ports:`，不是 Coolify 自动挑的。** 宿主 80/443 被别的服务占用时，要么装之前腾开端口，要么装完手动改 proxy compose 的端口映射（改法与保留见[代理配置持久性](#proxy-persistence)里的 `ports:` 例外）。

`APP_PORT` 是官方唯一暴露的 Laravel 端口开关（[`config/app.php:L8`](https://github.com/coollabsio/coolify/blob/v4.1.2/config/app.php#L8) `env('APP_PORT', 8000)`）。**没有第二个官方推荐的 Laravel 端口数字**——一旦你让 Traefik 占 8000、把 Laravel 挪走，挪去哪个端口在文档里就没有官方说法了。

---

### <a id="protocol-detection"></a>反向代理协议识别

**症状**：`https://<coolify域名>/` 打开后页面无样式（CSS 不加载）、JS 报错。抓页面 HTML 看到资源引用是 `href="http://<coolify域名>/build/assets/app-xxx.css"`——**页面是 https、资源是 http**，浏览器按混合内容（mixed content）策略直接拒载。

**根因链**（对着源码）：

1. Laravel 用 `TrustProxies` 中间件从 `X-Forwarded-Proto` 头判断请求真实协议。Coolify 的 [`app/Http/Middleware/TrustProxies.php:L15-L44`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Http/Middleware/TrustProxies.php#L15-L44) 已经把 `$proxies = '*'`（信任所有上游）、`$headers` 含 `HEADER_X_FORWARDED_PROTO`，还在 `handle()` 里根据 `$request->secure()` 自动设 `session.secure`。**Laravel 侧是配好的**。
2. 但 Coolify 自带的 Traefik **默认不信任** `X-Forwarded-*` 头——Traefik 只信任直连它的那一跳的头，前置反代（Cloudflare/Caddy）传来的 `X-Forwarded-Proto: https` 被 Traefik 丢弃。于是 Laravel 收到的 proto 退化成 http，`URL::` helper 就生成 http 资源链接。
3. 默认生成的 [Traefik command](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L304-L318) 里**没有** `forwardedHeaders.trustedIPs`——需要手动加。

**修法**：给 Traefik 的 http/https entrypoint 加 `forwardedHeaders.trustedIPs`，让它信任前置反代传来的 `X-Forwarded-*`：

```
--entrypoints.http.forwardedHeaders.trustedIPs=0.0.0.0/0
--entrypoints.https.forwardedHeaders.trustedIPs=0.0.0.0/0
```

`0.0.0.0/0`（信任所有来源）在"Traefik 只监听内网 / 只有前置反代能打到它"的拓扑下是安全的——外部进不来，唯一上游就是那条受信反代链，而反代自己会把进入它的 `X-Forwarded-Proto` 重置为真实值。这跟 Coolify 官方给 Cloudflare 用户的做法同源（见[代理配置持久性](#proxy-persistence)，[`bootstrap/helpers/proxy.php:L354`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L354) 的注释原文就是 `trustedIPs for Cloudflare`）。

> 只有一个 entrypoint 时只加对应那行。若前置反代把 HTTPS 终结、以 **plain HTTP** 回源到 Traefik 的 http entrypoint，那只加 `entrypoints.http.*` 就够；加了不存在的 entrypoint 那行会让 Traefik 起不来。

---

### <a id="realtime-routing"></a>实时服务路由

**症状**：dashboard 弹红框 `WARNING: Cannot connect to real-time service`（[`resources/views/livewire/layout-popups.blade.php:L71`](https://github.com/coollabsio/coolify/blob/v4.1.2/resources/views/livewire/layout-popups.blade.php#L71)）。部署进度 / 状态变更 / 日志流 / 健康检查都不实时（要手动刷页面）。点 "Acknowledge & Disable This Popup" 只是 [`localStorage.popupRealtime='disabled'`](https://github.com/coollabsio/coolify/blob/v4.1.2/resources/views/livewire/layout-popups.blade.php#L219-L224) 把弹框关掉，底层 WS 依然没通。

**注意别误判**：主题（暗/亮）切换是**纯前端** Alpine（[`classList.toggle('dark')`](https://github.com/coollabsio/coolify/blob/v4.1.2/resources/views/livewire/profile/appearance.blade.php#L23-L26)），**不走 WS**。CSS 坏时切主题看着"没反应"，是因为没有 dark variant CSS 可套，不是 WS 问题——先修协议识别再判断 WS。

**浏览器实际连哪**（对着源码）：Echo client 配置在 [`resources/views/layouts/base.blade.php:L176-L183`](https://github.com/coollabsio/coolify/blob/v4.1.2/resources/views/layouts/base.blade.php#L176-L183)：

```js
wsHost: "{{ config('constants.pusher.host') }}" || window.location.hostname,   // 180
wsPort: "{{ getRealtime() }}",                                                 // 181
forceTLS: false,                                                               // 183
```

- `constants.pusher.host` = `env('PUSHER_HOST')`（[`config/constants.php:L42`](https://github.com/coollabsio/coolify/blob/v4.1.2/config/constants.php#L42)）——通常空 → 回落 `window.location.hostname`（即 `<coolify域名>`）。
- `getRealtime()`（[`bootstrap/helpers/shared.php:L1525-L1534`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/shared.php#L1525-L1534)）：`PUSHER_PORT` 空时，URL 带端口就返 `'6001'`、不带端口返 `null`（`null` 时 pusher.js 按页面 scheme 用默认 wss:443）。

所以浏览器默认去连 `wss://<coolify域名>:443/app/<PUSHER_APP_KEY>?...`。这个 `/app/*` WebSocket 路径必须被反代到 Soketi(6001)，upgrade 才能成功。

**真正的根因（容易搞反）**：Coolify **本来就会自动生成**这条 WS 路由——[`setupDynamicProxyConfiguration()`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Models/Server.php#L447-L504) 会往 `/data/coolify/proxy/dynamic/coolify.yaml` 写三条 router：`coolify-http`（→`coolify:8080`）、`coolify-realtime-ws`（`Host(...) && PathPrefix(/app)` → `coolify-realtime:6001`，[`Server.php:L483-L488`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Models/Server.php#L483-L488)）、`coolify-terminal-ws`（`/terminal/ws` → `coolify-realtime:6002`）。**但有个前置守卫**：[`Server.php:L452-L455`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Models/Server.php#L452-L455) 的 `if (empty($settings->fqdn) || (isCloud() && $this->id !== 0) || ! $this->isLocalhost())` 一旦成立，就删掉 `coolify.yaml`（连带 WS 路由）。

所以放在前置反代后面时最常见的情形是：**你从没在 Coolify 里设"实例 FQDN"（Settings → Instance's Domain），只靠边缘反代的域名访问 → `settings->fqdn` 为空 → Coolify 主动删掉 `coolify.yaml` → WS 路由不存在 → 报 "Cannot connect to real-time service"**。不是 Coolify 缺这个能力、要你从头手写，而是它把自带的路由删了。

**两种修法**：

**修法 A（首选，用 Coolify 自带机制）**：在 dashboard 里把"实例 FQDN"设成你实际访问 Coolify 的域名。Coolify 就会自己生成 `coolify.yaml`、把 `/app`→6001 和 `/terminal/ws`→6002 路由带上。代价：设了 FQDN 后 Coolify 还会生成 `coolify-http` 路由和（当 scheme 是 https 时）`redirect-to-https` 中间件——要确认这套跟你的边缘反代 TLS 终结不打架（尤其别和边缘反代形成 http→https 重定向环）。

**修法 B（边缘反代已经接管路由、不想让 Coolify 管 FQDN 时手写）**：往 [`--providers.file.directory=/traefik/dynamic/`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L314)（官方 file provider 扩展点）丢一个**用不同 router/service 名**的路由文件（**千万别叫 `coolify-realtime-ws`——那正是 Coolify 自己生成的名字，将来一旦设了 FQDN 就撞名**）：

```yaml
# /data/coolify/proxy/dynamic/custom-realtime-ws.yaml   ← 用自定义名，避开 Coolify 的 coolify.yaml
http:
  routers:
    custom-realtime-ws:
      rule: "Host(`<coolify域名>`) && PathPrefix(`/app`)"   # Pusher/Soketi 端点就是 /app/<key>
      entryPoints:
        - http
      service: custom-realtime-ws
      priority: 200          # 比默认 Host-only 路由更具体，优先匹配 /app
  services:
    custom-realtime-ws:
      loadBalancer:
        servers:
          - url: "http://coolify-realtime:6001"
```
（要 web terminal 就再加一条 `/terminal/ws` → `coolify-realtime:6002`。）

- [`--providers.file.watch=true`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L315) 让 Traefik **秒级热加载**，不用重启任何容器。
- **WebSocket header 透传**：Traefik 和 Caddy 反代 WS 默认就透传 `Connection: Upgrade` / `Upgrade: websocket` / `Sec-WebSocket-*`，不用额外配。**但 nginx 不是**——nginx 做 WS 反代必须显式写 `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`（`Upgrade`/`Connection` 是 hop-by-hop 头，nginx 默认不转发）。如果你的**边缘**反代是 nginx，这一条要单独配。
- `coolify-realtime` 与 `coolify-proxy` 同在 `coolify` docker 网络，容器名直接 DNS 解析——**不需要把 6001/6002 暴露到宿主或 mesh**。这条路避开了"WSL/mesh 缺 6001 portproxy"之类的入站问题（那类问题见 network skill 的 wsl.md）。

验证握手成功 = `curl` 打 `/app/<KEY>` 带 WS upgrade 头拿到 `HTTP/1.1 101 Switching Protocols` + 首帧 `{"event":"pusher:connection_established",...}`（`\x81` 开头的字节是 RFC6455 真 WS text frame，不是长轮询伪造）。

---

### <a id="proxy-persistence"></a>代理配置持久性

放在前置反代后要加的自定义（协议识别所需的 trustedIPs、实时服务所需的 WS 路由），有两个官方落点，但**它们各自"能扛什么、扛不住什么"要分清**，别当成万能保留：

1. **[`--providers.file.directory=/traefik/dynamic/`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L314)**：Traefik file provider 扩展点，手写 realtime 路由文件放这。Coolify 自己也用它——[`app/Models/Server.php:L451`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Models/Server.php#L451) 生成的 `coolify.yaml` 就在同目录（不是"coolify-dashboard.yaml"；那种名字是人手动建的）。dashboard 里 **Server → Proxy → Dynamic Configurations** 就是这个目录的 UI 入口。**你自己的文件用不同文件名 + 不同 router 名**，就跟 Coolify 生成的 `coolify.yaml` 井水不犯河水，升级/重生成都不动你的。

2. **自定义 Traefik `command`**（协议识别所需的 `forwardedHeaders.trustedIPs`）：靠 [`extractCustomProxyCommands()`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L170-L217) "扛"，但要看清它到底怎么工作——它**不是**"每次重生成都主动保留自定义项"，而是一个 **backfill 兜底**：

   - [`GetProxyConfiguration`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Actions/Proxy/GetProxyConfiguration.php#L17-L60) 拿配置的顺序是：先读 DB 里 `last_saved_proxy_configuration`，DB 空了再从磁盘 backfill。**正常重启 / 升级都是读已保存的配置原样用**，你的 trustedIPs 早在里头，天然不丢。
   - `extractCustomProxyCommands()` 只在"要重新生成默认配置、且手上有一份旧配置可抠"时才跑（[`GetProxyConfiguration.php:L45-L49`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Actions/Proxy/GetProxyConfiguration.php#L45-L49)）：它把旧 `command` 里**不匹配默认前缀清单**的条目抠出来、拼回新默认配置。默认前缀清单见 [`bootstrap/helpers/proxy.php:L188-L203`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L188-L203)。
   - **`forwardedHeaders.trustedIPs` 不匹配任何默认前缀 → 被当自定义抠回来 → 保留**。✅

   **但两个反直觉的坑**：

   - **"Reset to Defaults" 会把自定义 command 一起清掉**，不只是 ports。UI 点 Reset 走的是 [`forceRegenerate: true`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Livewire/Server/Proxy.php#L166-L173)，此时 GetProxyConfiguration 直接跳过读旧配置、`$custom_commands = []`（[`GetProxyConfiguration.php:L45-L49`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Actions/Proxy/GetProxyConfiguration.php#L45-L49)），`extractCustomProxyCommands` 根本不执行 → trustedIPs 和 ports 全部打回默认。**所以改过 proxy 的别点 Reset to Defaults**（不像 Restart Proxy 是安全的）。
   - **默认前缀是 `str_starts_with` 裸前缀匹配，会误伤**。清单里有一条 `'--providers.docker'`（裸的，没有结尾 `.` 或 `=`，[`proxy.php:L200`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L200)），所以 `--providers.docker.network=coolify` 这种也会被判成"默认" → 抠取时被排除 → 重生成时丢掉。如果你在运行的 Traefik 里看到 `--providers.docker.network=coolify` 之类 v4.1.2 默认不生成的 command（[`proxy.php:L350-L351`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L350-L351) 只生成 `--providers.docker=true` + `exposedbydefault=false`），那是**老版本生成、至今没触发过重生成才还在**，不是被"保留"机制留住的——下次重生成就没了。排查时用 `docker inspect coolify-proxy` 看运行态 command、跟你 checkout 的源码默认值比对才准。

> proxy compose 的 **`ports:` 段完全不在 `extractCustomProxyCommands` 覆盖内**（它只处理 `command`）。若你改过 Traefik 的宿主端口映射，一旦触发默认重生成，`ports` 会被打回 [`bootstrap/helpers/proxy.php:L288-L291`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L288-L291) 的默认（`80:80 / 443:443 / 443:443/udp / 8080:8080`），可能和宿主既有占用冲突导致 Traefik 起不来。端口映射这类要持久，更稳的是走前面说的 source 侧 `docker-compose.custom.yml` 思路在 proxy 侧的等价手段，或至少记住"别点 Reset"。

---

### <a id="target-server-deployment"></a>目标服务器部署机制

Coolify 让你部署"非静态"应用（需要构建/运行时的应用，不是纯文件托管）时，**不是** Docker-in-Docker（容器里跑嵌套 Docker daemon）。核心机制是：**SSH 到目标 server，在目标 server 自己的 Docker daemon 上直接跑 `docker build` / `docker compose up`**。

**证据链**（v4.1.2）：

1. `coolify` 容器（Laravel）**没有挂载 `/var/run/docker.sock`**——[`docker-compose.yml`](https://github.com/coollabsio/coolify/blob/v4.1.2/docker-compose.yml#L1-L179) + [`docker-compose.prod.yml`](https://github.com/coollabsio/coolify/blob/v4.1.2/docker-compose.prod.yml#L1-L155) 全文搜不到这个 mount（`coolify-proxy` 那边的 Traefik 才挂，且是给 Traefik 自己发现容器用，跟部署应用无关）。
2. `docker build` / `docker compose` 等命令以**字面 shell 命令字符串**的形式，通过 `instant_remote_process()` / `execute_remote_command()`（在 [`app/Jobs/ApplicationDeploymentJob.php`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Jobs/ApplicationDeploymentJob.php#L1-L2500) 里大量调用，如 `docker build`、`{$this->coolify_variables} docker compose`）发给目标 server。
3. 命令执行走 [`bootstrap/helpers/remoteProcess.php:L139-L152`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/remoteProcess.php#L139-L152) 的 `instant_remote_process()`，它调用 `SshMultiplexingHelper::generateSshCommand()` 拼出实际的 `ssh` 命令；`generateSshCommand` 内部再调 `ensureMultiplexedConnection()` 建立/复用连接。（注意：[`remoteProcess.php:L46`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/remoteProcess.php#L46) 那处 `ensureMultiplexedConnection` 调用属于**另一个**函数 `remote_process()`——基于 Activity 的异步版本，别跟 `instant_remote_process` 混淆。两条路都经 `SshMultiplexingHelper`。）

**关键设计：连"本机自己"都当一台远程 server 用 SSH 管**——不是特例代码路径，是同一套逻辑。哪怕 Coolify 就装在这台机器上，管理"这台机器"（dashboard 里的 `localhost` server，[`app/Models/Server.php:L650`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Models/Server.php#L650) 判定：`ip === 'host.docker.internal' || id === 0`）时，也是从 `coolify` 容器内 SSH 出去、回环打到**宿主自己的 sshd**，在宿主上跑 `docker` CLI。这不是一个"专用 SSH 服务"：安装脚本用宿主现成的 OpenSSH，生成一把 key 追加到当前用户的 `~/.ssh/authorized_keys`（[`scripts/install.sh:L899-L908`](https://github.com/coollabsio/coolify/blob/v4.1.2/scripts/install.sh#L899-L908)），seeder 把 localhost server 的 IP 记成 `host.docker.internal`（[`database/seeders/ProductionSeeder.php:L115-L122`](https://github.com/coollabsio/coolify/blob/v4.1.2/database/seeders/ProductionSeeder.php#L115-L122)）、SSH 端口默认 `22`（[`create_servers_table.php:L20`](https://github.com/coollabsio/coolify/blob/v4.1.2/database/migrations/2023_03_24_140711_create_servers_table.php#L20)）。`host.docker.internal` 是 Docker 用 [`--add-host=host.docker.internal:host-gateway`](https://github.com/coollabsio/coolify/blob/v4.1.2/bootstrap/helpers/proxy.php#L284) 注入的、指向宿主网关的名字。全程没有嵌套 Docker daemon，部署出来的应用容器和 `coolify` 容器是**兄弟关系**（sibling containers），不是嵌套。（WSL 等特殊环境里宿主 sshd 可能不在 22、而在另一个端口——那是环境特例，不是 Coolify 装了"专用服务"。）

**性能优化层**：不是每条命令都开新 SSH 连接。[`establishNewMultiplexedConnection()`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Helpers/SshMultiplexingHelper.php#L67-L90) 用 OpenSSH 的连接复用（`ssh -fN -o ControlMaster=auto -o ControlPath=$muxSocket -o ControlPersist=...`，[`SshMultiplexingHelper.php:L76`](https://github.com/coollabsio/coolify/blob/v4.1.2/app/Helpers/SshMultiplexingHelper.php#L76)）先建一条持久主连接，后续命令走同一个 `ControlPath` socket 复用 TCP，避免每条命令都走完整 SSH 握手（三次握手 + 密钥交换 + 认证）。

**为什么不用 DinD**：DinD 需要 privileged 模式（安全风险）、有存储驱动兼容性坑、镜像层无法跟宿主共享缓存。SSH+目标机原生 docker 的好处：① 部署出的应用容器和 Coolify 自己是兄弟关系而非嵌套；② "管理任意远程 server" 和 "管理本机" 走同一套代码，不用维护两套逻辑；③ 不需要给 Laravel 容器 privileged 权限或挂 docker.sock（缩小攻击面）。

**代价**：`coolify` 容器必须能稳定 SSH 通它管理的**每一台** server，**包括它自己**。如果这条"自环 SSH"链路不稳（网络抖动、SSH 服务重启、密钥或防火墙问题），后台的 `ServerConnectionCheckJob`（定时轮询各 server 可达性）会反复报连接超时/失败——这类日志出现不代表 dashboard 本身坏了（该 job 是异步队列任务，不会同步阻塞页面渲染），但提示 SSH 自环链路有问题，值得单独排查。

---

### <a id="latency-diagnostics"></a>访问延迟诊断

Coolify dashboard（Livewire，每次导航都会发请求刷新页面状态）感觉"卡"、"切页面慢"时，别急着怀疑 Coolify 本身，按下面顺序分层排除，逐层缩小范围：

#### <a id="request-path-latency"></a>请求链路时延

用 `curl -o /dev/null -s -w` 在链路的每一跳分别测（`time_connect` = TCP 握手耗时，`time_starttransfer` = 首字节耗时即 TTFB，`time_total` = 总耗时）：

```bash
# 直连 Laravel（绕过反代）
curl -o /dev/null -s -w 'total=%{time_total}s connect=%{time_connect}s ttfb=%{time_starttransfer}s\n' http://127.0.0.1:<laravel直连端口>/login
# 经反代（本机）
curl -o /dev/null -s -w '...\n' -H 'Host: <coolify域名>' -H 'X-Forwarded-Proto: https' http://127.0.0.1:<反代端口>/login
# 经中间网络跳（如 mesh/VPN）
curl -o /dev/null -s -w '...\n' -H 'Host: <coolify域名>' http://<mesh或内网地址>/login
```

哪一跳耗时突然变大，问题就在那一跳。**本机 Laravel/反代通常都在几十毫秒量级**——如果本机测下来正常、只有经过某条网络跳（VPN/mesh/公网）才慢，问题大概率在那条网络链路，不在 Coolify 应用本身。

#### <a id="response-size-comparison"></a>响应体规模对照

同一条链路，分别测一个**极小响应**（如故意访问 404 路径）和一个**正常大小的页面**（如 `/login`，通常几十 KB，含内联的 Livewire 快照 JSON）：

- 两者都稳定、耗时接近 → 该链路本身干净，慢不是这条链路的锅。
- **小响应稳定、大响应剧烈抖动**（几倍差异、锯齿状） → 典型的**网络层丢包**信号：TCP 丢包对小请求（几个包）命中概率低，对大响应（几十上百个包）命中概率显著升高，一旦某个包丢了就要等 RTO 超时重传（起始几百毫秒且指数退避）。这种模式下问题不在应用，在网络链路的丢包率。
- 两者都稳定但**都比预期慢** → 更可能是应用层或后端处理慢，往下看第 3、4 点。

> 注意这个方法的局限：如果只有**某一个特定路由**慢、其余路由（哪怕响应更大）都正常，这个"大小相关"的网络丢包假设就不成立了——应该转向该路由自己的逻辑（数据库查询、是否触发了额外的同步检查）排查，而不是网络层。这种"单路由异常"和"全局网络抖动"要注意区分，别把偶发的网络噪音误判成路由自身问题（或反过来）。

#### <a id="log-sources"></a>日志来源

Coolify 的 `coolify` 容器内部用 **s6-overlay** 同时跑 nginx + PHP-FPM + Laravel scheduler 等多个进程（不是 supervisord）。两份日志来源不同、内容也不同：

- **`docker logs coolify`**（容器 stdout/stderr）：nginx 的 **error/warn log**（如 `[warn]`/`[error]`；**注意生产镜像默认 [`access_log off;`](https://github.com/coollabsio/coolify/blob/v4.1.2/docker/production/etc/nginx/conf.d/custom.conf#L3-L4)，所以这里看不到正常 access log，只有告警和错误**）、Laravel scheduler 每个 job 的执行耗时（`Running [App\Jobs\XxxJob] ... DONE`）。
- **`storage/logs/laravel.log`**（容器内文件，`docker exec coolify tail storage/logs/laravel.log`）：Laravel 应用代码自己用 `Log::` facade 写的内容（如各种 `Job failed`、`WARNING` 业务日志）。

**只查 `laravel.log` 会完全看不到 nginx 的告警和 scheduler 的执行耗时**——这些线索只在 `docker logs`。排查慢的问题两份都要看。

#### <a id="nginx-response-buffering"></a>nginx 响应缓冲

`docker logs` 里如果看到类似：
```
[warn] an upstream response is buffered to a temporary file ... while reading upstream, ... request: "GET /xxx HTTP/1.1", upstream: "fastcgi://127.0.0.1:9000", ...
```
意思是 PHP-FPM 返回的响应体超过了 nginx 的 `fastcgi_buffers`/`fastcgi_buffer_size` 内存缓冲区容量，nginx 只能把响应先写临时文件、再读出来转发——多了一次磁盘 I/O。这**不一定是耗时的元凶**（现代 SSD/内存盘这个操作通常几十毫秒内，实测过 1GB/s+ 的写入速度就不构成瓶颈），但它是一个信号：**这个路由返回的响应体比大多数页面大得多**，值得留意该路由是不是可以精简响应体积（分页、懒加载、减少内联数据）。

#### <a id="mesh-vpn-quality"></a>Mesh-VPN 链路质量

如果反代链路经过 EasyTier / WireGuard / Tailscale 之类的 mesh 组网，这类工具通常自带 CLI 能查每条 peer 连接的实时延迟和丢包率（如 EasyTier 的 `easytier-cli peer`），可以直接读出某条隧道当前的 loss% 作为"网络层是否有问题"的旁证。但**丢包率是瞬时值、会随时间波动**，不要把某次测量的具体数字当成长期事实记录——只记录"用这个命令能查、这是判断依据"这件事本身。

**重要边界**：mesh/VPN 层的丢包是**全局性**的——同一条隧道上跑的所有流量都会按响应大小概率性地撞上，不会精确只影响某一个特定的应用路由。如果症状是"只有 A 页面卡、其他页面（含更大的响应）都正常"，这个特征本身就在提示"不是网络层丢包"，而更可能是 A 页面自己的逻辑（例如是否间接触发了额外的同步检查、慢查询、或本文前一节提到的 SSH reachability 检查）有问题——这种情况下往应用代码和该路由的具体渲染逻辑查，而不是重复去查网络。

---

### <a id="admin-account-maintenance"></a>管理员账号维护

忘了 dashboard 密码、或要改 name/email 时，从 `coolify` 容器跑 artisan tinker 直接改 DB。

**先认清 schema**：`users` 表**没有 `role` 列**（`SELECT ... role FROM users` 会报 `column "role" does not exist`）。用户角色是 **team 级** 的，在 `team_user` pivot 表：[`create_team_user_table.php:L18`](https://github.com/coollabsio/coolify/blob/v4.1.2/database/migrations/2023_03_20_112812_create_team_user_table.php#L18) `$table->string('role')->default('member')`（member/admin/owner）。查用户列 `id, email, name, created_at` 即可。

改法（密码通过环境变量或等价的凭据旁路注入，不写进对话、argv 或日志；容器内用 `getenv()` 读取）：

```php
// docker exec -e COOLIFY_ADMIN_PWD coolify php artisan tinker --execute '...'
$u = App\Models\User::where("email","<旧email>")->first();
$u->name = "<新name>"; $u->email = "<新email>";
$u->password = Hash::make(getenv("COOLIFY_ADMIN_PWD"));
$u->force_password_reset = false;
$u->email_verified_at = now();
$u->pending_email = null; $u->email_change_code = null; $u->email_change_code_expires_at = null;
$u->save();
```

（后三个 `pending_email` / `email_change_code*` 是清掉 Coolify 的换邮箱二次确认残留状态，避免改完 email 后被"待确认"卡住。）

---

### <a id="localization"></a>界面本地化

**结论先行**：Coolify 官方 i18n 只起了个框架、远未完工，主体 UI 全是硬编码英文。想**自己**彻底汉化 = 接管几百处 blade 硬编码字符串的外提 + 翻译，且每次上游更新都要重新翻/rebase——**别自己 DIY**，要么用浏览器翻译插件（沉浸式翻译 / DeepL，工具型 dashboard 的术语 deployment/proxy/health check 留英文反而更准），要么评估下面的第三方 fork。

证据（v4.1.2 实测）：

- [`lang/zh-cn.json`](https://github.com/coollabsio/coolify/blob/v4.1.2/lang/zh-cn.json#L1-L44) 只有 **42 个 JSON key**，[`lang/en.json`](https://github.com/coollabsio/coolify/blob/v4.1.2/lang/en.json#L1-L44) 同样 42 个（另有 [`lang/en/passwords.php`](https://github.com/coollabsio/coolify/blob/v4.1.2/lang/en/passwords.php#L1-L22) 5 个 Laravel 框架 PHP-array key，无中文对应）——**官方走 i18n 的可翻译字符串总共就这点**。
- `__()` / `@lang()` 调用只出现在 **10 个 blade 文件**：6 个 `auth/*`（登录/注册/找回密码/2FA）+ 2 个 livewire 页 + 2 个 vendor mail 模板。Server / Project / Resource / Settings / 部署 / 日志 / 终端等主体 UI **全是硬编码英文字面量**，根本没走 i18n——这也正是"想汉化就得整体 fork + 持续追上游"的根源。
- 上游官方仓库没有中文 i18n（相关 issue 如 [#7681](https://github.com/coollabsio/coolify/issues/7681) 只要求项目描述字段允许 UTF-8，不是 UI 汉化）。
- **但存在第三方汉化 fork**：[`loccen/coolify-zh`](https://github.com/loccen/coolify-zh/tree/f806dab0abf4135342c11dbbc1693fcc340cb402)（fork 自 `coollabsio/coolify`）确实在做整体汉化——该不可变快照的 `lang/zh_CN.json` 有 36 万+ 字节的真实翻译（对比上游 42-key），commit 里能看到"发布 4.1.x 汉化版本""roundNN"这类持续追上游的记录。**这恰好印证了上面"整体 fork + 持续追上游"的高维护成本**。是否采用要自行评估：非官方、star/采用度低、质量与长期维护未验证、且必然滞后上游版本——把这些风险掂量清楚再决定，别当成官方方案。

---

### <a id="reverse-proxy-checklist"></a>前置反代配置清单

把 Coolify 放到独立边缘反代（Cloudflare/Caddy/nginx）后面，要一次配齐：

1. **Traefik 加 `forwardedHeaders.trustedIPs`**（见[反向代理协议识别](#protocol-detection)）——否则 CSS 全 http。
2. **保证 `/app` WebSocket 路由存在**（见[实时服务路由](#realtime-routing)）——否则实时功能死。首选给 Coolify 设"实例 FQDN"让它自己生成，或用 file provider 手写一条**独立命名**的路由到 `coolify-realtime:6001`。
3. **别把 8000 暴露到不受信网络**。8000 是 Laravel 直连口，绕过你边缘反代上的鉴权（如 caddy-security SSO）直打 dashboard。共享机 / mesh 上尤其注意：`docker-compose.prod.yml` 默认 `0.0.0.0:8000:8080`，等于对同网段敞开。文档说的 "safely close 8000" 就是指这个——用域名访问后应把它挡在防火墙外或改 bind `127.0.0.1`。持久化改法走 **`/data/coolify/source/docker-compose.custom.yml`**（**不是 `docker-compose.override.yml`**——那个文件名 Coolify 从不读，见[运行架构](#runtime-architecture)中的 compose 边界）；官方 [custom-compose-overrides 文档](https://coolify.io/docs/knowledge-base/custom-compose-overrides) 给了把 coolify 绑 `127.0.0.1:8000:8080` 的示例。⚠️ 注意 Docker Compose 对 `ports:` 是**列表合并**语义，改完 `docker inspect coolify` 确认只剩你想要的那一条 binding、没把默认的 `0.0.0.0:8000` 一起留着（真不放心就在防火墙层挡 8000 最稳）。
4. **APP_URL / 边缘 TLS**：边缘反代终结 HTTPS、以 https 语义回源（配好 `X-Forwarded-Proto`）即可，配合第 1 条 Laravel 就能生成正确的 https 链接。

---

### <a id="upstream-access-port"></a>上游接入端口

把 Coolify 放到上游反代后面时，"上游反代到底打到 Coolify Traefik 的哪个端口"有两种选择，理解取舍能帮你决定要不要花力气回到官方端口。

**拓扑 A —— 上游反代打到一个非标准宿主端口**（如 `127.0.0.1:8001:80`，把宿主 8001 映射到 Traefik 容器的 `:80` entrypoint）。
- 什么时候会落到这：宿主的 80/443 已经被别的服务占了（这时得**人为**改 proxy compose 的 `ports:` 把 Traefik 挪到空闲端口——Coolify 自己不会探测/避让，见[端口与入口](#ports-and-entry)），或者中间还隔了一层端口转发（如 WSL NAT 下 Windows `netsh portproxy`）而那层当时只转发了这个非标准端口。
- 对 HTTP / WebSocket 流量来说，这条路**功能上完全没问题**——上游反代指向哪个端口，Traefik 就在哪个端口收，路由/WS/trustedIPs 全部照常。

**拓扑 B —— 上游反代打到 Coolify 官方的 80/443**。
- 为什么想回到它：这是 Coolify 文档假定的默认拓扑。Coolify 自己的自动化都假设 **Traefik 独占宿主 80/443**——尤其当你还打算**用这台 Coolify 去部署对外应用**时，它给每个 app 自动生成的 Traefik label + Let's Encrypt HTTP-01 签证都默认 Traefik 在 80 上接挑战。严格说 HTTP-01 只要求"该域名的公网 :80 能到达 Traefik 的 http entrypoint"——理论上上游反代在公网 :80 把每个 app 域名的挑战流量转到 Traefik 的非标准端口也行，但那要你为每个新 app 域名手动配上游转发，等于放弃了 Coolify 的自动化。停在官方端口 = 跟 Coolify 自带自动化零摩擦。
- 代价：要求宿主 80/443 空闲；**并且**如果中间隔了端口转发层，那层也得把 80/443 一起转发过去。

**两种拓扑之间怎么迁移**（A → B）：
1. 让 Traefik 在宿主绑上 80/443（改 proxy compose 的 `ports:`，注意这段不受 `extractCustomProxyCommands` 保护，见[代理配置持久性](#proxy-persistence)），以及/或者在中间转发层加上 80/443 的转发规则。
2. 把上游反代的目标从"非标准端口"改成 80（走 Traefik 的 http entrypoint，plain HTTP 回源最省心）或 443，reload 上游反代。
3. （可选）撤掉那条非标准端口映射，彻底退役。

**常见硬卡点**：中间转发层如果是 WSL NAT 下的 Windows `netsh portproxy`，**加新端口转发规则需要 Windows 管理员权限**（见 network skill 的 wsl.md）。拿不到 admin 时就只能停在拓扑 A——保留那条已有的非标准端口映射当活口，功能不受影响，只是没"回到官方默认端口"这个整洁性收益。**所以是否迁移是个整洁性/自动化兼容性的权衡，不是功能必需**：只做上游反代入口、不用这台 Coolify 部署对外 app 的话，拓扑 A 一直用下去也没问题。

---

### <a id="external-app-publishing"></a>对外应用发布

前面几节是"运维 Coolify 实例本身"；这节是**用这台 Coolify 去部署一个对外 web 应用**时，GUI 里几个最容易填错/误解的点（都在前置反代拓扑下验证过）。

#### <a id="destination-types"></a>Destination 类型

New Resource 时要选 **Destination**：它就是目标 server 上的一个 **Docker network**（应用容器的落点，提供网络隔离）。两种类型：

- **Standalone Docker**：普通单机 docker daemon 上的 bridge / 自定义网络。
- **Docker Swarm**：Swarm 集群的 overlay 网络（跨节点通信）。

两种**都不是** DinD（和上一节"部署机制不是 DinD"同理，只是那节讲构建过程、这里讲网络落点）。类型**不是你在 UI 里选的，是目标 server 加入 Coolify 时按它底层 Docker 是不是 Swarm 模式自动判定的**——官方 [destinations/create](https://coolify.io/docs/knowledge-base/destinations/create) 原文："automatically determined... You cannot manually choose"。**默认 Standalone**：标准单机安装脚本不开 Swarm，新装 server 就是 Standalone，对应自动建的 `coolify` bridge 网络（前文 Traefik 的 `--providers.docker.network=coolify` 就是它）；要 Swarm 得先手动把 server 配成 Swarm 节点再加进来。

#### <a id="domain-and-tls-termination"></a>Domain 与 TLS 终结

app 的 **Domain** 字段决定 Coolify 给这个 app 生成的 Traefik 路由 label。前置反代拓扑（边缘反代已终结 TLS、以明文回源到 Coolify Traefik）下有三个要点：

- **协议前缀决定 Traefik 要不要自己再签证书**。填 `https://` → Traefik 会去 Let's Encrypt 申证（官方 [domains](https://coolify.io/docs/knowledge-base/domains)）。但这一步在本拓扑里既**多余**（TLS 已在边缘终结）又**大概率失败**——该域名的公网 DNS 指向的是边缘反代、不是 Coolify 这台机器，ACME HTTP-01 挑战根本连不到 Traefik，超时失败后退化成自签证书，纯浪费重试和日志。所以填 **`http://`** 前缀，让 Traefik 只做明文路由、不碰证书。
- **域名部分必须 = 外部访客实际访问的那个真实域名**。Traefik 靠 `Host()` 请求头字符串匹配路由，边缘反代默认原样透传 Host 头，所以 Traefik 收到的就是真实域名——这里填别的（比如自造一个"内网名"）Traefik 匹配不上，直接 404。**不是**填某个内网专用域名。
- **不填 = 这个 app 在 Traefik 里没有任何路由规则**。`Host()` 规则直接由 Domain 字段生成，空着就没有路由条目，边缘反代转过来的请求匹配不到 → 404。空 Domain 只适合"仅在同一 Docker 网络内被别的容器按服务名互调、完全不对外"的场景。

**证据**（本部署 `docker inspect` 一个 Coolify 部署出来的容器的 labels，节选）：

```
traefik.http.routers.http-0-<id>.rule                      = Host(`<app域名>`) && PathPrefix(`/`)
traefik.http.routers.http-0-<id>.entryPoints               = http           # 只有 http 入口、没有 https
traefik.http.services.http-0-<id>.loadbalancer.server.port = 3001
```

当初 Domain 填的就是不带 `https://` 的域名，所以 Traefik 只生成了 http 路由、完全没有证书相关配置。多个 app 共享 Coolify Traefik 的同一个宿主端口，靠各自 `Host()` label 分流（Host-based 多路复用），不用为每个 app 单开端口。

#### <a id="git-repository-authentication"></a>Git 仓库认证

容易把"认证方式"和"自动触发"混成一张并列表。其实是两个独立维度：

- **维度 1 — 认证（Coolify 怎么读到你的代码）**：**GitHub App**（仅 GitHub；App 权限大：读代码 + 管 webhook + 读 PR + 写 commit 状态）vs **Deploy Key**（任何 Git 平台都行——GitLab/Gitea/Bitbucket/自建；就是一把**单仓库只读** SSH key，除了 `git clone` 这一个仓库什么 API 权限都没有）。二选一。
- **维度 2 — 触发（push 之后谁去重新部署）**：独立问题。GitHub App 借自己那套权限**自动把 webhook 也装好** → push 自动部署；Deploy Key 只读、没权限替你建 webhook，默认只有"手动点 Deploy"，想要自动就得**自己去仓库设置手动加一条 webhook** 指回 Coolify（官方 [ci-cd](https://coolify.io/docs/applications/ci-cd) 原文 "More manual webhook setup required"）。
- **手动配了 webhook ≠ 功能对等**：`Auto Deploy` 开关、PR 自动预览部署这两个功能官方明确写 "only available for GitHub App based repositories"（[applications](https://coolify.io/docs/applications)），commit 状态回写 GitHub 也仅 App 有。Deploy Key + 手动 webhook 顶多做到"push 触发一次重新部署"，拿不到这两个更深的功能（它们要 App 那种 GitHub API 权限，普通 webhook 顶不上）。

> 构建这一步本身**不是**另起一个 CI runner：Coolify 自己在目标 server 上用你选的 Build Pack（Nixpacks 默认 / Dockerfile / Docker Compose / 直接拉镜像）build 出镜像再起容器（见[目标服务器部署机制](#target-server-deployment)）。官方把"push→自动构建部署"整个流程叫 CI/CD，但它指这个内建流程，不是接了 GitHub Actions 之类的外部流水线。

### <a id="coolify-product-cleanup"></a>产品专有清理

通用清理边界见 [共性清理边界](#cleanup-boundary)。Coolify 还需按其实际资源归属逐层核对：

- proxy compose 与 source compose 停止后，standalone `coolify-sentinel` 不会随之删除；它不属于任何 compose project。
- Coolify 部署出的应用容器也不会随控制面 compose 停止。可用 `coolify.managed=true` 等管理标签辅助盘点；这些容器仍可能连接 `coolify` 网络，使网络删除报 `active endpoints`。应先确认并处理工作负载，再删除网络。
- Coolify 可能把管理 key 写入目标服务器普通用户和 root 的 `authorized_keys`。卸载时应分别检查两类账户，不能只检查安装命令最初使用的用户。
- `/data/coolify`、Docker 卷、网络、镜像、应用容器和边缘路由属于不同层。删除配置目录不等于完整卸载，删除控制面也不等于工作负载已经消失。
- 上游 Caddy 路由、宿主端口转发、非标准端口映射、`trustedIPs`、自定义 realtime file route 都属于本次部署可能添加的人为改造，不是 Coolify 默认资源；清理时应按实际拓扑逐项撤除。
- 若安装时为释放 80/443 或其他端口停掉了原服务，卸载平台后还要恢复原服务及其入口。清理完成的判断不是“Coolify 已删”，而是宿主原有服务与端口所有权已经恢复。

## <a id="dokploy"></a>Dokploy

[Dokploy](https://dokploy.com) 是开源自托管 PaaS。本章记录 Dokploy 专有架构，以及多服务宿主上可能出现的非标准运行态。

运行镜像与仓库证据对齐 **v0.29.8**（tag commit `1f4f9404`）。源码链接均锁定该 tag。安装行为来自 2026-07-05 抓取的滚动来源 [`https://dokploy.com/install.sh`](https://dokploy.com/install.sh)：它不随仓库 tag 固定，也未找到与 v0.29.8 对应的不可变归档，因此升级或复核时必须重新抓取比较，不能把下面的脚本片段冒充为版本锁定证据。

### <a id="dokploy-swarm-prerequisites"></a>Swarm 编排与安装前置

2026-07-05 抓取的官方滚动安装脚本在 `install_dokploy()` 开头检查 80、443、3000；任何一个端口已被监听都会直接 `exit 1`，不是警告后继续：

```bash
if ss -tulnp | grep ':80 ' >/dev/null; then
    echo "Error: something is already running on port 80" >&2
    exit 1
fi
if ss -tulnp | grep ':443 ' >/dev/null; then
    echo "Error: something is already running on port 443" >&2
    exit 1
fi
if ss -tulnp | grep ':3000 ' >/dev/null; then
    echo "Error: something is already running on port 3000" >&2
    echo "Dokploy requires port 3000 to be available. Please stop any service using this port." >&2
    exit 1
fi
```

该脚本随后会退出可能存在的旧 Swarm，执行 `docker swarm init --advertise-addr <检测到的私网IP>`，再创建 `--driver overlay --attachable` 的 `dokploy-network`。这意味着在已有 Swarm 工作负载的宿主上直接运行脚本，安装前置动作本身就可能影响其他系统。

仓库 v0.29.8 的目标服务器设置逻辑也直接执行 [`docker swarm init`](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/server-setup.ts#L433-L441)，随后创建 [`attachable` overlay 网络](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/server-setup.ts#L442-L449)。因此 Swarm 不是一次实测中的偶然选择；即使只有一个节点，Dokploy 仍以 Swarm manager 为编排基础。

### <a id="dokploy-control-plane-and-entry-proxy"></a>控制面与入口代理

2026-07-05 抓取的滚动安装脚本把 Dokploy 本体创建为 Swarm service，并用 `--publish published=3000,target=3000,mode=host` 发布控制面。`mode=host` 绕开 Swarm routing mesh，直接在运行 task 的节点监听 3000。诊断时不要只看 `docker service ls` 的 `PORTS` 列，应检查 service 规格：

```bash
docker service inspect dokploy --format '{{json .Spec.EndpointSpec}}'
```

官方默认入口还包括独立的 `dokploy-traefik`。v0.29.8 源码中的 [`initializeStandaloneTraefik()`](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/traefik-setup.ts#L27-L91) 把它作为普通容器创建，绑定 80/443 并接入 `dokploy-network`；同文件也保留了 [Swarm service 形式](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/traefik-setup.ts#L93-L166)。端口常量 [`TRAEFIK_PORT`、`TRAEFIK_SSL_PORT`](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/traefik-setup.ts#L14-L21) 默认分别为 80、443，可由同名环境变量覆盖。

官方完整入口因此包含两部分：

- 3000：Dokploy 控制面自身的 host-mode 发布。
- 80/443：`dokploy-traefik` 接收平台面板域名和已部署应用域名，再转发到 overlay 网络内的目标。

### <a id="dokploy-nonstandard-runtime"></a>非标准运行态的识别

一次实测环境中，80/443/3000 已由其他服务占用，最终运行态出现了两个关键偏差：

1. `docker service inspect dokploy --format '{{json .Spec.EndpointSpec}}'` 只有 `{"Mode":"vip"}`，没有任何 `Ports` 配置；本体的官方 host-mode 3000 发布被摘掉。
2. `dokploy-traefik` 容器不存在，因此平台部署出的应用没有官方 80/443 入口。

这不是滚动安装脚本按默认路径能够自然产生的状态，而是端口冲突后的人为改造。没有操作历史时，不臆测修改者和具体步骤；只依据 service 规格、容器清单、overlay 网络连接和实际监听状态判断。

控制面可访问也不能证明发布链路完整。该实例的 `/etc/dokploy/applications/` 为空，说明只形成了面板运行态，没有形成可验证的应用发布链路；这个观察只描述当次实测，不能推广为 Dokploy 默认行为。

### <a id="dokploy-socat-bridge"></a>socat 桥接

该环境通过一个独立 `alpine/socat` 容器把非标准宿主端口桥接到 overlay 网络里的 `dokploy:3000`：

```text
TCP4-LISTEN:<非标准宿主端口>,fork,reuseaddr TCP:dokploy:3000
```

`dokploy` 是 overlay 网络里的 DNS 服务名，解析到 Swarm VIP。Dokploy v0.29.8 仓库与 2026-07-05 抓取的安装脚本中都没有 socat 方案；这是为绕过端口冲突手工添加的 workaround，不是官方推荐路径。

它的能力边界很明确：

- dashboard 可以经非标准端口打开；
- TLS 可以由更上游的反向代理终结；
- 已部署应用的入口不会因此恢复，应用域名仍依赖平台入口代理的路由和 80/443；
- 独立 socat 容器不是 Swarm service，删除 Dokploy services 不会自动带走它。

### <a id="dokploy-multi-service-host-options"></a>多服务宿主的部署选择

如果 80/443/3000 已被占用，有三种现实选择：

1. **给 Dokploy 独占宿主**：最贴近官方安装假设，端口和 Swarm 生命周期最清晰。
2. **重新规划端口所有权后完整安装**：保留控制面的 host-mode 发布和平台入口代理，再把 TLS 或公网入口交给上游反代；同时验证升级后自定义端口仍保留。
3. **只做临时 dashboard 桥接**：可用于调查已有数据，但应明确标记为不完整实例，不把它当成能部署对外应用的生产方案。

单纯删掉 publish、跳过 `dokploy-traefik`、再加 socat，只解决 dashboard 可达性；它没有替代 Dokploy 的应用入口控制面。

### <a id="dokploy-product-cleanup"></a>产品专有清理

通用清理边界见 [共性清理边界](#cleanup-boundary)。Dokploy 还需额外确认：

- 独立 `dokploy-traefik`、socat 或其他端口桥接容器不是 Swarm service，`docker service rm` 不会自动删除它们。
- 删除 service 后，task containers 可能短暂显示为 `Exited`，随后才由 Swarm 自动回收；等待收敛后再判断是否存在真正残留。
- overlay 网络、产品卷、配置目录和镜像属于不同资源层，需要分别核对；删除 service 或配置目录都不是完整卸载。
- `/etc/dokploy/applications/` 为空只能说明当次实例没有形成应用发布链路，不能省略对 service、卷、网络、镜像和独立容器的核查。
- 退出 Swarm 前先检查全部 service、node 和 overlay network。只有确认没有其他 Swarm 工作负载时，才执行 `docker swarm leave --force`。
