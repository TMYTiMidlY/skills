# 3x-ui：官方配置方案（服务端 / 落地侧，手把手）

3x-ui 是 [Xray-core](https://github.com/XTLS/Xray-core) 的 Web 管理面板：在面板里建 **inbound**（VLESS / VMess / Trojan / Shadowsocks / Hysteria2 / WireGuard 等），配传输（TCP·mKCP·WebSocket·gRPC·HTTPUpgrade·XHTTP）与安全层（TLS·XTLS·REALITY），面板再把它翻译成 Xray 配置下发。

> 官方 feature 列表（`3x-ui/README.md`）：「Modern transports & security — TCP (Raw), mKCP, WebSocket, gRPC, HTTPUpgrade, and XHTTP, secured with TLS, XTLS, and REALITY.」以及「Fallbacks — serve multiple protocols on a single port (e.g. VLESS and Trojan on 443) using Xray's fallback support.」

本篇**手把手**搭两套官方部署形态：先**直接接管对外端口**（inbound 自己占对外端口、自管 TLS/握手），再**结合 Caddy**（反代复用 443）。方案二的 Caddyfile 与 inbound **直接取自作者 RackNerd 机器上在跑的真实配置**（域名 / UUID / 密钥已脱敏为占位符，端口保留真实示例值）。其余分工：

- 客户端节点配置、协议选型 / 性能、Brutal / 拥塞控制、DNS / WebRTC 泄漏排查 → [mihomo.md](mihomo.md)。
- **独立 systemd 版 Hysteria2 服务端**（不经面板、官方脚本装）→ [hysteria2.md](hysteria2.md)。
- Caddy 反代本身的写法（`reverse_proxy`、站点模式、`authorize`/caddy-security、证书）→ `vps-maintenance` skill 的 caddy.md。
- 带宽 / 丢包质量测试、被墙运营事实 → `vps-maintenance` skill 的 vps-quality。

## 面板改动怎么变成 Xray 生效

理解这条流水线，才知道「改完 inbound 要不要重启、为什么偶尔断流」：

> `3x-ui/docs/architecture.md` §5.1「DB → Xray config pipeline」：面板控制器**从不直接改 Xray 运行配置**。流程是 ① service 改 DB（inbound/client/setting）→ ② `XrayService`（`service/xray.go`）据 DB 重建整份 `xray.Config` → ③ 先尝试 **hot apply**（`xray/hot_diff.go`，只把增删的 inbound/user 通过 Xray gRPC 推过去，**不重启进程**，活连接不断）→ ④ 结构性变更 hot 不了才**整进程重启**（`xray/process.go`）。重启由「need restart」原子标志去抖，`@every 30s` cron 消费，窗口内多次改动最多重启一次。

所以：加 / 删客户端一般热生效不断流；改传输 / 安全层这类结构变更会触发一次整体重启（30s 内合并）。生成的运行配置落在 `/usr/local/x-ui/bin/config.json`，随时可 `cat` 出来对照。

## 第 0 步：装 3x-ui

```bash
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh)
```

> `3x-ui/README.md`「Quick Start」：安装时**随机生成** username / password / access path；装完命令行敲 `x-ui` 打开管理菜单（启停服务、看 / 重置登录凭据、管理 SSL 证书等）。SQLite 单文件 `/etc/x-ui/x-ui.db`，面板初始路径由 `XUI_INIT_WEB_BASE_PATH` 决定（默认 `/`）。

首次进面板做三件事：① `x-ui` 菜单里看/重置随机账号密码与 access path；② 把面板监听改成 **`127.0.0.1:<高位端口>`**（如 `54324`），不要 `0.0.0.0` 裸暴（对外访问走方案二的 Caddy 反代或 SSH 隧道）；③ 面板设置里改掉默认端口和路径。下面两套方案配的是**节点 inbound**，和面板自身 TLS 是两回事（可共用一张证书）。

---

## 方案一：直接接管对外端口（不经反代）

**思想**：inbound 直接 bind 对外端口，TLS 握手 / 加密由 inbound（或面板签的证书）自己负责，链路上没有 Caddy/Nginx。协议无关——凡是「自己占端口 + 自管握手」的都算这一类。最省事、少一层反代，代价是这个端口的流量特征就是该协议本身（除非用 REALITY 伪装）。下面三种是常见落地子情形。

### A. VLESS + REALITY（免证书、借真实站点握手）

最省心的直连方案：**不用域名、不用证书**，inbound 直接占 443（或任意 TCP 端口），靠「偷用」一个真实大站的 TLS 握手来伪装。

> 机制（`Xray-core/transport/internet/reality/reality.go`、`config.proto`）：服务端 REALITY 配置里 `dest` 指向一个真实目标站（如 `www.microsoft.com:443`），`server_names` 是允许的 SNI，配一对 `private_key`/公钥与 `short_ids`。未授权的主动探测握手会被**代理到真实 `dest`**，探测者看到的就是那个大站的合法证书与响应；只有持正确公钥 + shortId 的客户端才被放行进代理。较新版本还带 `mldsa65_seed`（ML-DSA-65 后量子额外校验）与 `limit_fallback_*`（对回落流量限速）。

手把手（面板 → 入站 → 添加入站）：

1. **协议** 选 `vless`，**监听端口**填对外端口（如 `443`），监听地址留空（占所有网卡）。
2. **传输** `tcp`，**安全** 选 `reality`。
3. 点 reality 的 **`Get New Cert` / 生成密钥** → 面板生成 x25519 **公钥 / 私钥对**（私钥进 inbound，公钥给客户端）。
4. **Dest（回落目标）** 填真实站 `www.microsoft.com:443`，**SNI / serverNames** 填 `www.microsoft.com`（选一个你 VPS 出口能正常访问、支持 TLS1.3 + H2 的站）。
5. **shortId** 点生成（随机），可留多个。
6. **添加客户端**（UUID 面板自动生成）。
7. 放行端口：`ufw allow 443/tcp` + 云安全组也放 443/tcp。
8. 复制客户端「分享链接 / 二维码」，里面已带 `publicKey`+`shortId`+`sni`+`fp`（fingerprint）。

- 优点：无证书运维、无需域名、抗主动探测（SNI 白名单外 / 裸探测都回落到真站）。
- 坑：`dest` 站必须自己在 VPS 上访问正常且支持 TLS1.3；SNI 要与 `dest` 匹配；客户端 fingerprint（uTLS）要设成真实浏览器值。

### B. 面板自管 TLS 证书（VLESS / VMess / Trojan + TLS）

要用真证书（有域名、或想走标准 TLS）时，证书直接由 3x-ui 的 `x-ui` 菜单签发和续期，不必自己配 acme：

> `3x-ui/x-ui.sh`：主菜单 **option 20（SSL Certificate Management）**内置 `acme.sh`。域名证书 `ssl_cert_issue`：`acme.sh --issue -d <domain> --standalone --httpport <port>`（HTTP-01，需该端口对外可达且空闲），默认 CA 为 Let's Encrypt，`--reloadcmd "x-ui restart"`，证书落在 `/root/cert/<domain>/fullchain.pem` + `privkey.pem`。还有 `ssl_cert_issue_for_ip`：**给纯 IP 签 Let's Encrypt 短期证书**（`/root/cert/ip`，有效 ~6 天、自动续），适合没有域名的机器。

手把手：

1. 命令行 `x-ui` → 选 **20（SSL Certificate Management）** → 给域名签（选 acme，standalone），或给 IP 签（option 6）。签发时 acme 会**临时占用 80**（或你填的端口），先放行、别被别的服务占着。
2. 证书生成在 `/root/cert/<domain>/`（`fullchain.pem` + `privkey.pem`）。
3. 面板 → 入站 → 安全选 `tls` → **证书路径** 填 `/root/cert/<domain>/fullchain.pem`、**密钥路径** 填 `/root/cert/<domain>/privkey.pem`。
4. 放行 inbound 对外端口（ufw + 安全组）。续期用同样方式，`--reloadcmd`（默认 `x-ui restart`）负责让面板 / Xray 重新加载新证书。
5. 证书是 root-owned，面板以 root 跑没权限问题；若把同一张证书**给独立服务**（如 systemd 版 Hysteria2）用，注意权限坑，见 [hysteria2.md](hysteria2.md)。

### C. Hysteria2（UDP 直连）

3x-ui 也能直接管 Hysteria2 inbound，它天然就是「直接接管一个 **UDP** 端口」，和独立 systemd 版**二选一**：

- **走面板**：入站里新增 Hysteria2 类型 inbound，处理三件事——① 监听 **UDP** 端口；② 证书来源（可复用上面 option 20 签的证书，或 Caddy 证书的 root-owned 副本，理由同独立版的 cert 权限坑）；③ 密码 + `obfs(salamander)`。好处是和现有 VLESS 节点统一在一个面板管、共享客户端 / 流量统计。
- **走独立 systemd**（隔离、独立升级、不碰面板）：搭法见 [hysteria2.md](hysteria2.md)。

> 实战里 Hysteria2 常和 vless 同机：**Hysteria2 占 UDP 443、vless+ws 经 Caddy 占 TCP 443，同号不冲突**（RackNerd 就是这么跑的：`systemctl is-active hysteria-server` = active、UDP 443 在听，同时 Caddy 占 TCP 443）。客户端怎么配 / 验证 Brutal（`up`/`down` 与服务端 `ignoreClientBandwidth` 协商）见 [mihomo.md](mihomo.md)。

### 共性：端口放行

直连方案的对外端口**必须在防火墙 + 云安全组一起放行**，按协议放 TCP 或 UDP：

> `3x-ui/x-ui.sh` 自带防火墙菜单，可 `ufw` 放行如 `80,443,2053` 或端口段。UDP 协议（Hysteria2）记得放 `<port>/udp`。云厂商安全组是**另一层**，面板 / ufw 放了但安全组没放照样不通。

---

## 方案二：结合 Caddy（反代复用 443）—— 手把手

**思想**：让 **Caddy 独占 443 并统一管证书（自动续）**，3x-ui 的 inbound 退化成一个**明文上游**（WebSocket / gRPC / HTTPUpgrade / XHTTP，inbound 本身**不做 TLS**），由 Caddy 按 path 反代过去。这样代理节点**藏在一个真实域名背后**——直接访问域名看到的是面板登录页 / 403，只有特定路径 + 客户端才走代理；证书也蹭 Caddy 的自动签发续期，不用面板单独管。

下面这份就是 **RackNerd 上在跑的代理站点配置**，照抄即可（把域名、UUID 换成自己的）。

### 第 1 步：建一个「明文」vless + ws inbound

面板 → 入站 → 添加入站：

- **协议** `vless`，**监听地址** `127.0.0.1`、**端口**一个高位随机端口（示例 `54321`）——只让本机 Caddy 连。
- **传输** `ws`，**path** 填隐蔽路径（示例 `/websocket`）。
- **安全** `none`（TLS 交给 Caddy，inbound 不做 TLS）。
- **添加客户端**（UUID 自动）。

面板据此生成的 xray inbound（`/usr/local/x-ui/bin/config.json` 里，脱敏后）长这样，用来对照：

```json
{
  "listen": "127.0.0.1",
  "port": 54321,
  "protocol": "vless",
  "settings": {
    "clients": [{ "email": "<client-name>", "id": "<uuid>", "flow": "" }],
    "decryption": "none"
  },
  "streamSettings": {
    "network": "ws",
    "security": "none",
    "wsSettings": { "path": "/websocket" }
  },
  "sniffing": { "enabled": true, "destOverride": ["http", "tls", "quic"] }
}
```

> 关键是 `security: none` + `listen: 127.0.0.1`：TLS 由 Caddy 终结，端口只对本机开。（RackNerd 现网那份其实 `listen: null`→监听 `*:54321` 对外也开着——**不推荐**，钉死 `127.0.0.1` 更稳，避免绕过 Caddy 直连裸端口。）

### 第 2 步：Caddy 站点反代到这个 inbound

Caddyfile 里加一个站点（RackNerd 在跑的那份，域名/端口换成你的）：

```caddyfile
proxy.example.com {
	encode gzip
	tls {
		protocols tls1.3          # 强制 TLS1.3
	}

	# 代理流量：只放行 WebSocket 升级请求到 xray inbound，其余一律 403（藏住节点）
	handle /websocket* {
		@ws {
			header Connection *Upgrade*
			header Upgrade websocket
		}
		handle @ws {
			reverse_proxy 127.0.0.1:54321
		}
		handle {
			respond "Forbidden" 403
		}
	}

	# 订阅：3x-ui 内置订阅服务（面板「订阅设置」里开，示例端口 2096）
	handle /sub/* {
		reverse_proxy 127.0.0.1:2096
	}

	# 其余流量 → 3x-ui 管理面板（示例端口 54324），务必加认证别裸奔
	handle {
		authorize with admin        # caddy-security 网关；没装就换 basic_auth / 独立端口 / SSH 隧道
		reverse_proxy 127.0.0.1:54324
	}

	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
		X-Content-Type-Options nosniff
		-Server
	}
}
```

逐块解读：

- **`handle /websocket*` + `@ws` 匹配 `Connection: Upgrade` / `Upgrade: websocket`**：只有真正的 WS 升级请求才反代进 xray；有人直接 `GET /websocket` 探测 → 落 `respond 403`，把节点藏在「一个普通网站」后面。这个 path 必须和第 1 步 inbound 的 `wsSettings.path` **完全一致**。
- **`/sub/*` → 3x-ui 内置订阅服务**：面板「订阅设置」里开启并设监听端口（示例 `2096`），客户端订阅地址就是 `https://proxy.example.com/sub/<subId>`。
- **根路径 → 面板**：面板和节点**共用一个域名**，面板挂在根路径、用 `authorize with admin`（caddy-security）挡住。没装 caddy-security 就把这段换成 `basic_auth`、或干脆别经 Caddy 暴露面板（留 `127.0.0.1:54324` 走 SSH 隧道进）。`authorize` / caddy-security 细节见 `vps-maintenance` skill 的 caddy.md。

### 第 3 步：reload + 验证

```bash
caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
# 直接开域名应看到面板登录/403，节点不暴露：
curl -sI https://proxy.example.com/ | head -3
```

客户端用 vless 分享链接连（`address=proxy.example.com`、`port=443`、`type=ws`、`path=/websocket`、`security=tls`、`sni=proxy.example.com`）。

### 反代后要修「真实客户端 IP」

一旦 inbound 藏在 Caddy 后面，Xray 看到的源 IP 就成了 Caddy 的地址（127.0.0.1），**面板的在线列表 / 每客户端 IP 限制会全部失效**。3x-ui 官方专门给了处理：

> `3x-ui/docs/real-client-ip.md`：inbound → **Transport / Stream Settings → 开 Sockopt → Real client IP 预设**。两种机制二选一——`sockopt.trustedXForwardedFor`（从 HTTP 头取真实 IP，仅 WebSocket / HTTPUpgrade / XHTTP 有效）或 `acceptProxyProtocol`（从 L4 PROXY 协议头取，上游必须真的发 PROXY 头，否则连不上）。**只用一个，别两个都开**。这些字段是服务端专用，会从订阅输出里剥掉；且只有确实在可信反代后才开 `trustedXForwardedFor`，否则客户端能伪造头骗源 IP。

对上面这套 **Caddy HTTP 反代**：Caddy 默认给上游注入 `X-Forwarded-For`，所以在这个 inbound 的 Sockopt 里手动把 `trustedXForwardedFor` 设成 `["X-Forwarded-For"]`（预设里的 `CF-Connecting-IP` 是给 Cloudflare CDN 的，不适用）：

```json
"streamSettings": {
  "network": "ws",
  "security": "none",
  "wsSettings": { "path": "/websocket" },
  "sockopt": { "trustedXForwardedFor": ["X-Forwarded-For"] }
}
```

### 不想引 Caddy 也能同 443 复用：Xray fallback

如果只是想「一个 443 上同时挂代理 + 一个幌子网站 / 多协议」，Xray 自带 **fallback** 就够，不一定要 Caddy：

> `Xray-core/proxy/vless/inbound/config.proto`：VLESS inbound 的 `fallbacks` 是一组 `Fallback{ name(SNI), alpn, path, dest, xver }`。带 TLS 的 VLESS inbound 占 443，未命中的 TLS / HTTP 握手按 SNI / ALPN / path **回落到 `dest`**（一个真实 web 服务或另一个协议的本地监听）。README 说的「VLESS and Trojan on a single port (443)」就是靠它。

fallback（Xray 内建、纯 TCP 层按握手特征分流）与 Caddy 反代（HTTP 层、能顺带做认证 / 多站点 / 自动证书）是两条路：只想省一个端口用 fallback；想藏在完整网站后 + 蹭 Caddy 证书生态、面板也要暴露，用 Caddy（RackNerd 走的就是 Caddy 这条）。

---

## 真实部署实例与两条教训（RackNerd / LisaHost）

上面「方案二」那份 Caddyfile + inbound 就是 **RackNerd（海外 VPS）** 上在跑的代理站点配置。这台还**同机并存 Hysteria2**（UDP 443 直连，方案一 C）——TCP 443（Caddy→vless+ws）和 UDP 443（Hysteria2）同号不冲突，实测同落地下 **Hysteria2 吞吐 ≈ 2× vless+ws**（少一跳反代 + QUIC 拥塞控制）、jitter 也小一半。**LisaHost（美国 4837 双 ISP 家宽住宅原生 IP）** 跑同样的 vless+ws+TLS。

> 两台的**机器规格 / IP / 延迟 / 换 IP 操作与费用**（运营事实）见 `vps-maintenance` skill 的 vps-quality「历史服务器信息」（A=RackNerd、B=LisaHost）；**被墙现象 + 协议归因（未坐实）+ 缓解**、以及吞吐 / jitter 实测数据见 [mihomo.md](mihomo.md) 附录「实测封锁记录」。

**教训一：隐蔽性挡不住「长期暴露」。** LisaHost 那个 vless+ws+TLS 是 **TCP+TLS、藏在正常 TLS 流量里**（方案二本该最隐蔽），却在长期稳定使用后于 2026-06-25 被墙；RackNerd 的 Hysteria2（UDP 直连）也在 2026-06-08 被单 IP 精准屏蔽。→ 封锁不挑 QUIC/UDP，**长期固定的域名 + 落地 IP 暴露**本身就是诱因，「藏在真站后」只降主动探测命中率，压不住长期暴露。

**教训二：换 IP 比迁协议更快见效。** 两次都是**换落地 IP** 恢复的（RackNerd 面板自助 $3、LisaHost 工单 ¥60），协议没动、至今仍用。→ 被针对时先换 IP（快、便宜）；要更彻底再换域名，或把 vless 迁到 **REALITY**（免证书 + 借真站握手，比 vless+ws+TLS 的固定域名指纹更难长期锁定，见方案一 A）。个人自用的 Hysteria2 服务端别配 `bandwidth`/`ignoreClientBandwidth`（留给客户端 `up`/`down` 驱动 Brutal，见 [mihomo.md](mihomo.md)）。

## 方案一 vs 方案二（取舍速查）

| 维度 | 方案一 直连端口 | 方案二 结合 Caddy |
| --- | --- | --- |
| 证书 | REALITY 免证书 / 面板 acme 自管 | Caddy 统一签发续期 |
| 域名 | REALITY 不需要 | 需要（反代靠域名） |
| 隐蔽性 | REALITY 借真站握手；裸 TLS 特征明显 | 藏在真实域名背后，访问即面板/403 |
| 运维复杂度 | 低（少一层） | 高（多一层 Caddy + 真实 IP 处理） |
| UDP / QUIC | Hysteria2 直连天然支持 | Caddy 反代是 TCP/HTTP，UDP 仍走直连 |
| 同 443 多协议 | 单 inbound 各占端口 | Caddy 按 path 分，或用 Xray fallback |
| 面板暴露 | 另开端口 / SSH 隧道 | 可挂同域名根路径 + caddy-security 挡 |

经验默认：想省事 / 无域名 → **方案一的 REALITY**；已经有 Caddy 站点、想把节点和面板都藏进正常域名 → **方案二**（RackNerd 走这条）；Hysteria2 无论哪套都走 UDP 直连，作差异化备用（见 [hysteria2.md](hysteria2.md)）。被针对性屏蔽时先换落地 IP、再考虑换域名 / 迁 REALITY。
