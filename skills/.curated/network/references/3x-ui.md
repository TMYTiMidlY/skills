# 3x-ui：官方配置方案（服务端 / 落地侧）

3x-ui 是 [Xray-core](https://github.com/XTLS/Xray-core) 的 Web 管理面板：在面板里建 **inbound**（VLESS / VMess / Trojan / Shadowsocks / Hysteria2 / WireGuard 等），配传输（TCP·mKCP·WebSocket·gRPC·HTTPUpgrade·XHTTP）与安全层（TLS·XTLS·REALITY），面板再把它翻译成 Xray 配置下发。

> 官方 feature 列表（`3x-ui/README.md`）：「Modern transports & security — TCP (Raw), mKCP, WebSocket, gRPC, HTTPUpgrade, and XHTTP, secured with TLS, XTLS, and REALITY.」以及「Fallbacks — serve multiple protocols on a single port (e.g. VLESS and Trojan on 443) using Xray's fallback support.」

本篇只覆盖**服务端经 3x-ui 面板做的配置**，讲两套官方部署形态：先讲**简单的直接接管对外端口**（inbound 自己占对外端口、自管 TLS/握手），再讲**结合 Caddy**（反代复用 443）。其余分工：

- 客户端节点配置、协议选型 / 性能、Brutal / 拥塞控制、DNS / WebRTC 泄漏排查 → [mihomo.md](mihomo.md)。
- **独立 systemd 版 Hysteria2 服务端**（不经面板、官方脚本装）→ [hysteria2.md](hysteria2.md)。
- Caddy 反代本身的写法（`reverse_proxy`、站点模式、证书）→ `vps-maintenance` skill 的 caddy.md。
- 带宽 / 丢包质量测试 → `vps-maintenance` skill 的质量检测。

## 面板改动怎么变成 Xray 生效

理解这条流水线，才知道「改完 inbound 要不要重启、为什么偶尔断流」：

> `3x-ui/docs/architecture.md` §5.1「DB → Xray config pipeline」：面板控制器**从不直接改 Xray 运行配置**。流程是 ① service 改 DB（inbound/client/setting）→ ② `XrayService`（`service/xray.go`）据 DB 重建整份 `xray.Config` → ③ 先尝试 **hot apply**（`xray/hot_diff.go`，只把增删的 inbound/user 通过 Xray gRPC 推过去，**不重启进程**，活连接不断）→ ④ 结构性变更 hot 不了才**整进程重启**（`xray/process.go`）。重启由「need restart」原子标志去抖，`@every 30s` cron 消费，窗口内多次改动最多重启一次。

所以：加 / 删客户端一般热生效不断流；改传输 / 安全层这类结构变更会触发一次整体重启（30s 内合并）。

## 安装与基面

```bash
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh)
```

> `3x-ui/README.md`「Quick Start」：安装时**随机生成** username / password / access path；装完 `x-ui` 打开管理菜单（启停服务、看 / 重置登录凭据、管理 SSL 证书等）。面板访问路径由 `XUI_INIT_WEB_BASE_PATH` 决定（默认 `/`），SQLite 单文件 `/etc/x-ui/x-ui.db`。

面板本身也建议套 TLS + 非默认路径，别裸 http 暴露。下面两套方案讲的是**节点 inbound**怎么落地，和面板自身 TLS 是两回事（可共用同一张证书）。

---

## 方案一：直接接管对外端口（不经反代）

**思想**：inbound 直接 bind 对外端口，TLS 握手 / 加密由 inbound（或面板签的证书）自己负责，链路上没有 Caddy/Nginx。协议无关——凡是「自己占端口 + 自管握手」的都算这一类。最省事，少一层反代，代价是这个端口的流量特征就是该协议本身（除非用 REALITY 伪装）。下面三种是常见落地子情形。

### A. VLESS + REALITY（免证书、借真实站点握手）

最省心的直连方案：**不用域名、不用证书**，inbound 直接占 443（或任意 TCP 端口），靠「偷用」一个真实大站的 TLS 握手来伪装。

> 机制（`Xray-core/transport/internet/reality/reality.go`、`config.proto`）：服务端 REALITY 配置里 `dest` 指向一个真实目标站（如 `www.microsoft.com:443`），`server_names` 是允许的 SNI，配一对 `private_key`/公钥与 `short_ids`。未授权的主动探测握手会被**代理到真实 `dest`**，探测者看到的就是那个大站的合法证书与响应；只有持正确公钥 + shortId 的客户端才被放行进代理。较新版本还带 `mldsa65_seed`（ML-DSA-65 后量子额外校验）与 `limit_fallback_*`（对回落流量限速）。

面板操作要点（版面随版本变，认字段即可）：建 VLESS inbound → security 选 **reality** → 填 `dest` / `serverNames`（选一个在你 VPS 出口能正常访问、且 TLS1.3 + H2 的站）→ 面板一键生成密钥对 → 设一个 `shortId`。客户端从分享链接 / 订阅拿 `publicKey`+`shortId`+`sni`。

- 优点：无证书运维、无需域名、抗主动探测（SNI 白名单外 / 探测都回落到真站）。
- 坑：`dest` 站必须自己在 VPS 上访问正常且支持 TLS1.3；SNI 要和 `dest` 匹配；客户端 fingerprint（uTLS）要真实。

### B. 面板自管 TLS 证书（VLESS / VMess / Trojan + TLS）

要用真证书（有域名、或想走标准 TLS）时，证书直接由 3x-ui 的 `x-ui` 菜单签发和续期，不必自己配 acme：

> `3x-ui/x-ui.sh`：主菜单 **option 20（SSL Certificate Management）**内置 `acme.sh`。域名证书 `ssl_cert_issue`：`acme.sh --issue -d <domain> --standalone --httpport <port>`（HTTP-01，需该端口对外可达且空闲），默认 CA 为 Let's Encrypt，`--reloadcmd "x-ui restart"`，证书落在 `/root/cert/<domain>/fullchain.pem` + `privkey.pem`。还有 `ssl_cert_issue_for_ip`：**给纯 IP 签 Let's Encrypt 短期证书**（`/root/cert/ip`，有效 ~6 天、自动续），适合没有域名的机器。

面板里给 inbound 的 TLS 指向 `/root/cert/<domain>/`（或 IP 证书目录）即可。要点：

- `--standalone` 签发时会**临时占用签发端口**（通常 80），要放行且没别的服务占着；续期用同样方式，`reloadcmd`（默认 `x-ui restart`）负责让面板 / Xray 加载新证书。
- 证书是 root-owned，面板以 root 跑没有权限问题；但若把同一张证书**给独立服务**（如 systemd 版 Hysteria2）用，注意权限坑，见 [hysteria2.md](hysteria2.md)。

### C. Hysteria2（UDP 直连）

3x-ui 也能直接管 Hysteria2 inbound，它天然就是「直接接管一个 **UDP** 端口」，和独立 systemd 版**二选一**：

- **走面板**：入站里新增 Hysteria2 类型 inbound，要处理三件事——① 监听 **UDP** 端口；② 证书来源（可复用上面 option 20 签的证书，或 Caddy 证书的 root-owned 副本，理由同独立版的 cert 权限坑）；③ 密码 + `obfs(salamander)`。好处是和现有 VLESS 节点统一在一个面板管、共享客户端 / 流量统计。
- **走独立 systemd**（隔离、独立升级、不碰面板）：搭法见 [hysteria2.md](hysteria2.md)。

> 客户端怎么配 / 验证 Brutal（`up`/`down` 与服务端 `ignoreClientBandwidth` 协商）见 [mihomo.md](mihomo.md)。

### 共性：端口放行

直连方案的对外端口**必须在防火墙 + 云安全组一起放行**，按协议放 TCP 或 UDP：

> `3x-ui/x-ui.sh` 自带防火墙菜单，可 `ufw` 放行如 `80,443,2053` 或端口段。UDP 协议（Hysteria2）记得放 `<port>/udp`。云厂商安全组是**另一层**，面板 / ufw 放了但安全组没放照样不通。

---

## 方案二：结合 Caddy（反代复用 443）

**思想**：让 **Caddy 独占 443 并统一管证书（自动续）**，3x-ui 的 inbound 退化成一个**明文上游**（WebSocket / gRPC / HTTPUpgrade / XHTTP，inbound 本身**不做 TLS**），由 Caddy 按 path / SNI 反代过去。这样代理节点**藏在一个真实网站背后**——直接访问域名看到的是正常站点，只有特定路径 + 客户端才走代理；证书也蹭 Caddy 的自动签发与续期，不用面板单独管。

原「主节点：VLESS + WS + TLS」就是这套：3x-ui 建 VLESS inbound → transport 选 **ws**（设一个隐蔽 `path`）→ **security 关掉（none）**（TLS 交给 Caddy）→ Caddy 站点里把该 `path` `reverse_proxy` 到 inbound 的本地端口。

> Caddyfile 的 `reverse_proxy`、WebSocket 长连接反代、站点模式与证书细节**不在这里固化**，见 `vps-maintenance` skill 的 caddy.md。这里只讲 3x-ui 一侧：inbound 走明文 ws + 隐蔽 path，监听 `127.0.0.1:<port>`（只给 Caddy 连，不对外）。

### 反代后要修「真实客户端 IP」

一旦 inbound 藏在 Caddy 后面，Xray 看到的源 IP 就成了 Caddy 的地址（127.0.0.1），**面板的在线列表 / 每客户端 IP 限制会全部失效**。3x-ui 官方专门给了处理：

> `3x-ui/docs/real-client-ip.md`：inbound → **Transport / Stream Settings → 开 Sockopt → Real client IP 预设**。两种机制二选一——`sockopt.trustedXForwardedFor`（从 HTTP 头取真实 IP，仅 WebSocket / HTTPUpgrade / XHTTP 有效）或 `acceptProxyProtocol`（从 L4 PROXY 协议头取，上游必须真的发 PROXY 头，否则连不上）。**只用一个，别两个都开**。这些字段是服务端专用，会从订阅输出里剥掉；且只有确实在可信反代后才开 `trustedXForwardedFor`，否则客户端能伪造头骗源 IP。

对 **Caddy HTTP 反代**：Caddy 默认给上游注入 `X-Forwarded-For`，所以在 Sockopt 里手动把 `trustedXForwardedFor` 设成 `["X-Forwarded-For"]`（预设里的 `CF-Connecting-IP` 是给 Cloudflare CDN 的，不适用）。

```json
"streamSettings": {
  "network": "ws",
  "sockopt": { "trustedXForwardedFor": ["X-Forwarded-For"] }
}
```

### 不想引 Caddy 也能同 443 复用：Xray fallback

如果只是想「一个 443 上同时挂代理 + 一个幌子网站 / 多协议」，Xray 自带 **fallback** 就够，不一定要 Caddy：

> `Xray-core/proxy/vless/inbound/config.proto`：VLESS inbound 的 `fallbacks` 是一组 `Fallback{ name(SNI), alpn, path, dest, xver }`。带 TLS 的 VLESS inbound 占 443，未命中的 TLS / HTTP 握手按 SNI / ALPN / path **回落到 `dest`**（一个真实 web 服务或另一个协议的本地监听）。README 说的「VLESS and Trojan on a single port (443)」就是靠它。

fallback（Xray 内建、纯 TCP 层按握手特征分流）与 Caddy 反代（HTTP 层、能顺带做认证 / 多站点 / 自动证书）是两条路：只想省一个端口用 fallback；想藏在完整网站后 + 蹭 Caddy 证书生态用 Caddy。

---

## 方案一 vs 方案二（取舍速查）

| 维度 | 方案一 直连端口 | 方案二 结合 Caddy |
| --- | --- | --- |
| 证书 | REALITY 免证书 / 面板 acme 自管 | Caddy 统一签发续期 |
| 域名 | REALITY 不需要 | 需要（反代靠域名） |
| 隐蔽性 | REALITY 借真站握手；裸 TLS 特征明显 | 藏在真实网站背后，访问域名即正常站 |
| 运维复杂度 | 低（少一层） | 高（多一层 Caddy + 真实 IP 处理） |
| UDP / QUIC | Hysteria2 直连天然支持 | Caddy 反代是 TCP/HTTP，UDP 仍走直连 |
| 同 443 多协议 | 单 inbound 各占端口 | Caddy 按 path/SNI 分，或用 Xray fallback |

经验默认：想省事 / 无域名 → **方案一的 REALITY**；已经有 Caddy 站点、想把节点藏进正常网站 → **方案二**；Hysteria2 无论哪套都走 UDP 直连，作差异化备用（见 [hysteria2.md](hysteria2.md)）。
