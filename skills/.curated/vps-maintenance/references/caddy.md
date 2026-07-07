# Caddy：安装、基础反代、认证与文档私链分享

> 这份参考按“先把基础反代跑通，再叠加功能”的顺序组织：
>
> - 安装并验证 Caddy  
> - 选择基础站点模式：域名模式 / IP 模式  
> - 按需加错误页  
> - 需要 GitHub OAuth 时安装 `caddy-security`  
>
> 经验上，**先把最小反代跑通，再加认证**，排错会轻松很多。

## 选型速查

| 场景 | 推荐方案 | 关键前提 |
|---|---|---|
| 有域名、想省心上 HTTPS | 域名模式 | 域名已解析到机器，`80/443` 可从公网直达 |
| 只有 IP / 未备案 | IP 模式 | 用 `tls internal`，并在客户端导入 Caddy local root CA |
| 需要 GitHub OAuth 登录 | `caddy-security` | 使用自定义 Caddy 二进制，配置 `GITHUB_CLIENT_*` 与 `JWT_SHARED_KEY` |
| 需要“拿到链接即可读”的文档私链 | RustFS S3 + presigned + Markdeep viewer (docs-share) | 桶级 SigV4 签名 URL，自带过期；无 caddy-security 层 |

## 安装 Caddy

### 通过 APT 安装

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

### 修改 Caddyfile 的标准流程

```bash
sudo nano /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

注意：

- **改 Caddyfile 用 `reload`**；**换二进制或改 systemd 环境变量用 `restart`**。
- **`reload` 走 Caddy 的 admin（管理 / 控制）API**：本质是 `POST /load`（**默认 `localhost:2019`**，阻塞到加载完成 / 失败、失败自动回滚旧配置、零停机）。`curl localhost:2019/...` 是在本机访问它自己的控制口、免 sudo；admin API 全貌与 `pprof` 诊断见文末「排障与诊断 · 通用诊断入口」。
- **reload 出问题**（永久挂起 / 退出码非零 / `validate` 报 `{env.*}` / 域名白屏 / 登录死循环…）统一见文末「排障与诊断」节。

## 基础反代：先选站点模式

两种模式的差异不止"有没有域名"——从证书、端口形态到认证体系都成对地相反。先看总览，细节在后面各小节展开：

| 维度 | 域名模式（推荐） | IP 模式（无域名 / 未备案） |
|---|---|---|
| 适用前提 | 有域名，`80/443` 公网直达 | 没域名 / 不走备案 |
| 证书 | ACME 自动签 Let's Encrypt，客户端零配置 | `tls internal` 自签，客户端要导 root CA |
| SNI | 浏览器带 SNI=域名，正常匹配 | IP 直连 SNI 常为空，需全局 `default_sni <IP>` 兜底 |
| 端口形态 | 多域名**共享** `80/443`，靠 SNI/Host 分流 | 每个服务**独占**一个端口（`:443`、`:8082`…） |
| HTTP→HTTPS | Caddy 默认自动跳 | **默认也会自动跳**（IP 不例外），但要关掉（多端口会乱跳）；手写跳转受同口约束 |
| `bind` 限定网卡 | 共享端口上**别写**（会劫持整段端口 → 白屏，见下） | 独占端口，`bind` 安全可用 |
| caddy-security cookie | **必须**写 `cookie domain example.com` | **必须不**写（RFC 6265 禁 `Domain=IP`） |
| GitHub OAuth App | 用域名 callback 那一套 | 另用 IP callback 一套，两套独立不复用 |

> 表里每一行后文都有展开：证书 / SNI / HTTP 跳转见本节下面几个小节，cookie / OAuth App 见 `caddy-security` 章节，`bind` 见本节末「`bind` 与 listener 分组」。

### 域名模式（推荐）

适用：有域名，且 `80/443` 都能从公网访问。

```caddyfile
example.com {
    reverse_proxy localhost:8000
}
```

要点：

- Caddy 会自动通过 ACME 申请 Let's Encrypt 证书。
- **`80` 端口必须能从公网直达**，否则默认的 HTTP-01 challenge 过不了。
- 多域名直接平铺写多个 site block；每个站点独立配置，最省心。
- **多个域名 / 子域名共享同一对 `80/443`**：它们默认都监听通配 `:443`，Caddy 把 listen 地址相同的站点合并进**同一个内部 server**，再靠 TLS 的 SNI（和 HTTP 的 Host 头）把每个请求分流到对应站点。平时无感，但一旦给某个站点单独加 `bind` 就会破坏这套合并——详见本节末「`bind` 与 listener 分组」。

### IP 模式（无域名 / 未备案）

适用：没有可用域名，或者暂时不走域名备案。

```caddyfile
{
    auto_https disable_redirects
    default_sni <主 IP>
}

https://<主 IP>:<对外端口> {
    tls internal
    reverse_proxy localhost:<后端端口>
}
```

为什么这样配：

- **`auto_https disable_redirects`**  
   Caddy 默认会为**每个** HTTPS 站点（**含 IP 站点**）在 `80` 端口起 HTTP→HTTPS `308` 跳转。多端口共享同一个 IP 时，`:80` 只会按"监听地址字典序最小"挑**一个**端口去跳，对其余服务全是错的目标；而 `tls internal` 也不需要 `80` 做 ACME 验证，所以直接关掉。机制与关闭方式详见下文「自动 HTTP→HTTPS 跳转」。

- **`default_sni <主 IP>`**  
   客户端通过 IP 直连时，SNI 往往为空；按 RFC 6066，SNI 只能是 hostname，不能是 IP。Caddy 匹配不到 connection policy 时会回 TLS alert 80，`default_sni` 是兜底。注意它**只影响证书选择**（写进 `ConnectionPolicy.DefaultSNI` → certmagic `DefaultServerName`），**不路由 handler、也不是 fallback cert**（那是 `FallbackSNI`）。源码 `caddy/caddyconfig/httpcaddyfile/httptype.go:610-636` + `modules/caddytls/connpolicy.go:281-316`。参考：[caddyserver/caddy#6344](https://github.com/caddyserver/caddy/issues/6344)

- **非标端口建议显式写 `https://` 前缀**  
   技术上 `host:port` 也会自动启 HTTPS，但显式写出来更直观，不容易误读。

- **`tls internal` 只解决发证，不解决信任**  
   客户端仍然需要导入 Caddy 的 local root CA，见下一节。

> 如果你刻意让 **Caddy 只绑定主 IP**、后端只绑定 `127.0.0.1`，那么“外部端口”和“后端端口”写成同一个数字也可以共存；文档里分开写只是更不容易看错。
>
> IP 模式天然是"每服务独占一个端口"，所以用 `bind` 把监听限定到指定网卡在这里是安全的；这跟域名模式下多站点共享 `:443` 的情形正好相反（见本节末「`bind` 与 listener 分组」）。

### 自动 HTTP→HTTPS 跳转：默认行为、关闭、多端口选择

**默认行为**：只要 Caddy 知道站点的 host——**域名、IP、hostname 都算**——就会给它自动管 HTTPS，并在 HTTP 口（默认 `80`）起 `308` 跳转。**IP 站点一样自动跳**；"IP 不自动跳"的说法对当前版本（v2.11.2 实测 + 源码核对）是错的。域名和 IP 的差别只在**证书来源**，不在跳不跳：

| 站点形态 | 默认自动跳 | 证书来源 |
|---|---|---|
| `https://example.com`（域名） | ✅ `:80→:443` | ACME 公网证书，系统信任 |
| `https://<IP>`（标准 443） | ✅ `:80→:443` | internal issuer 自签（Caddy Local CA），client 要导 root CA / `-k` |
| `https://<IP>:8082`（非标口） | ✅ `:80→:8082`（"跳哪个"见下） | 同上，自签 |
| `http://example.com`（显式 `http://`） | ❌ 不跳 | 无证书，纯明文 |

> 机制：IP 拿不到 ACME 公网证书，但 Caddy 把它归到 **internal issuer** 自签（即 `tls internal` 的效果）；有证书可发，跳转照加。跳转的生成只看"有没有这个 host"，**与证书是不是 ACME 签的无关**。

**三种关闭方式**（源码 `caddy/modules/caddyhttp/autohttps.go`：`disable_redirects` 只在 `:199-237` 处 `continue` 掉 redirect 注册、**不碰证书管理**；`auto_https off` 则 `:116-123` 整个 `Disabled`）**：**

| 手段（作用范围） | 跳转 | 自动证书 | `:443` listener |
|---|---|---|---|
| 全局 `auto_https disable_redirects` | ❌ 关 | ✅ 照签 | ✅ 照起 |
| 全局 `auto_https off` | ❌ 关 | ❌ 不自动管 | 仅显式 `https://` 站点的 listener 仍 bind（无托管证书） |
| 单站写成 `http://host { }` | ❌ 该 host 退出自动跳 | 该 host 无自动证书 | — |

**多端口共享同一个 host 时，`:80` 跳哪个端口？**

典型场景：`https://<IP>:8082`、`https://<IP>:8080`… 都用同一个 IP。`:80` 的跳转目标由 **Caddyfile 适配阶段对"监听地址字符串"的字典序排序**决定（源码 `caddyconfig/httpcaddyfile/addresses.go` 的 `consolidateAddrMappings` → `sort.Strings` 定 server 顺序，运行时 `modules/caddyhttp/autohttps.go` 按排好的 server 名顺序处理），取**字典序最小**的那个站点的 https 口；只有正好等于标准 `443` 口的站点能再额外登记一条竞争跳转。两个坑：

- **是字典序，不是数字大小。** `sort.Strings` 按文本逐字节比：端口位数不齐会乱序（`:10000` 文本上排在 `:8080` 前面）；用了 `bind <IP>` 后监听地址是 `<IP>:<port>`，**IP 字符串成了主排序键**，端口反而次要。别理解成"最小端口赢"。
- **确定但无文档。** 固定配置下结果是确定的（非随机），但这套排序是**未公开的内部实现**，auto-HTTPS 文档只承诺"HTTP 跳 HTTPS"、不规定选哪个端口——**不要依赖**。

**实践结论**：IP 模式 / 任何"一个 host 多端口"的配置，**务必保留 `auto_https disable_redirects`**。否则 `http://<IP>/`（:80）会把所有明文请求 `308` 到字典序最小的那个端口，对其余每个服务都是错的目标——这才是关掉它的硬理由（不是"跳得不好看"）。

### 手写 HTTP→HTTPS 跳转的同口约束

开了 `auto_https disable_redirects` 后，Caddy 不再自动做任何 HTTP→HTTPS 跳转，需要的话自己写。有一条硬约束决定了能做到什么程度：**同一个端口要么是 TLS 监听、要么是明文 HTTP 监听，不能两者兼有。**

- **`80 → 443` 能干净地跳。** `80` 没被任何 HTTPS 站点占用，单独写一个明文站点做 308 即可，裸 IP 访问会自动升到 HTTPS：

  ```caddyfile
  http://<主 IP>:80 {
      redir https://{host}{uri} 308
  }
  ```

- **非标 HTTPS 端口（如 `:8082`）无法同口跳转。** 该端口已是 `tls internal` 的 TLS 监听，明文请求会被 Go 的 HTTP 栈在进入 Caddy 路由之前直接挡掉，固定返回下面这个 400，且无法改写成 302/308：

  ```text
  HTTP/1.0 400 Bad Request
  Client sent an HTTP request to an HTTPS server.
  ```

  所以 `http://<主 IP>:8082` → `https://<主 IP>:8082` 这种「同口自动跳」做不到，只能要求访问方显式写 `https://`。

- **「对某几个端口做跳转」只能跨端口。** 另起一个**未被 HTTPS 占用**的端口 A 当明文入口，跳到真正的 HTTPS 端口 B。代价是对外端口号变了；访问方既然已知道端口，多半不如直接写 `https://`，按需取舍：

  ```caddyfile
  http://<主 IP>:<端口A> {
      redir https://{host}:<端口B>{uri} 308
  }
  ```

### 导入 Caddy local root CA（仅 `tls internal` 场景）

使用 `tls internal` 时，Caddy 的本机 PKI 默认放在：

```text
/var/lib/caddy/.local/share/caddy/
```

默认 lifetime（见 [官方文档](https://caddyserver.com/docs/caddyfile/directives/tls) / [#3427](https://github.com/caddyserver/caddy/issues/3427)）：

| 层级 | lifetime | 文件 | 是否需要手动导入到客户端 |
|---|---|---|---|
| Root | 10 年 | `pki/authorities/local/root.crt` | **是：只导这个** |
| Intermediate | 7 天 | `pki/authorities/local/intermediate.crt` | 否 |
| Leaf | 12 小时 | `certificates/local/<host>/<host>.crt` | 否 |

关键点：

- **客户端只需要导入 root**。  
- intermediate 和 leaf 都会自动续签覆盖，手动导入它们意味着后面要持续重导。  
- 导入 root 后，整条链（未来续签的 intermediate、后续新增 host 的 leaf）都会被一次性信任。  
- TLS 握手时，Caddy 会把 intermediate 一起发给客户端，无需单独导入。

服务端导出 root 证书到家目录：

```bash
sudo cp /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt ~/caddy-root.crt
sudo chown "$USER":"$USER" ~/caddy-root.crt
```

然后把它拉回客户端：

```bash
scp user@server:~/caddy-root.crt .
```

再按客户端 OS 导入到系统或浏览器证书库。

校验它是不是 root：

```bash
openssl x509 -in caddy-root.crt -noout -subject -issuer
```

**`Subject == Issuer`** 就是自签 root。

### `on_demand_tls`：陌生 SNI 的按需签证

global options 里见到的：

```caddyfile
{
    on_demand_tls {
        ask http://127.0.0.1:9119
    }
}
```

作用：当一个**没在 Caddyfile 里显式声明**的 host 来握手时，Caddy 不立刻签证书，而是先 GET `ask` 端点问"这个域名允许签吗"，**HTTP 2xx 才放行**去签：

- 请求形如 `GET http://127.0.0.1:9119/?domain=<握手的SNI>`（`caddy/modules/caddytls/ondemand.go:131` `qs.Set("domain", name)`）。
- **状态码 200–299 = 放行**，其它一律拒（`ondemand.go:164-165`：`if resp.StatusCode < 200 || > 299 { return ErrPermissionDenied }`）。
- 站点真正启用 on-demand 还需站点里写 `tls { on_demand }`；`ask` 只是全局的"准入裁决器"。
- 跟 `default_sni` **不冲突也不互斥**：`default_sni` 管"没带 SNI 时拿哪个名字选证书"，`on_demand_tls ask` 管"某个陌生名字能不能现签"。

⚠️ **on-demand 必须配 permission（`ask` 或 internal）**：否则任意 SNI 都能让你签 = 被打爆 ACME 限额 / 占内存，官方强制要求。

### 可复用的错误页 snippet

如果你有一个单独的 `error-pages` 服务跑在 `localhost:4040`，可以用 snippet 集中定义，再按站点 `import`：

```caddyfile
(error_pages) {
    handle_errors 4xx 5xx {
        rewrite * /{err.status_code}
        reverse_proxy localhost:4040
    }
}

example.com {
    reverse_proxy localhost:8000
    import error_pages
}
```

说明：

- `handle_errors` 是 Caddy 内置错误捕获指令。
- `{err.status_code}` 是 placeholder。
- `snippet` 用 `(name)` 定义，用 `import name` 引用。
- 想让错误页真正走到 `handle_errors`，要用 `error` 触发，而不是 `respond`。

### `reverse_proxy` 注入请求头给上游（给后端补凭据）

`reverse_proxy` 里的 `header_up` 能改**发往上游**的请求头（注入 / 覆盖 / 删除）。一个常用模式：**后端自己需要一份凭据，但你不想让用户手填**——在边缘用 caddy-security 认证放行用户后，reverse_proxy 顺手把后端要的头注入进去，用户端全程无感、也不接触这份凭据。

```caddyfile
https://panel.example.com {
    authorize with app_admin          # 边缘先鉴权（前提，见 caddy-security 章节）
    reverse_proxy 10.x.x.x:<port> {
        header_up Authorization "Bearer <backend-secret>"   # 给上游注入它要的头
    }
}
```

典型场景（都是"边缘鉴权 + 注入后端凭据"）：

- **要 token 的控制台**：后端 REST/API 设了 secret，就注入 `Authorization: Bearer <secret>`。比如把 mihomo 控制器暴露成公网面板——见 `network` skill 的 mihomo Web 面板章节。
- **认 cookie / 头的 web 服务**：后端要一个登录 cookie / 头才放行，就注入对应的 `Cookie` / 自定义头。比如 zellij Web——见 `software` skill 的 zellij 章节。

要点：

- **方向别混**：`header_up` 是改**发往上游**的头（本节，给后端补凭据）；caddy-security 的 `inject headers with claims` 是把**登录者身份** claim 注入给下游后端（`X-Token-*`，见下文），两者无关。
- **边缘鉴权是前提**：注入 = 把后端凭据托管在 Caddy 侧，**任何过了边缘 `authorize` 的人都自动带着这份凭据访问后端**。所以那道边缘鉴权不能省，注入的凭据强度也不再是后端的独立防线。
- **凭据用占位符 / `{env.*}`**，别把真实 secret 写死进版本库。

### 基础反代常见坑

- **一个服务一个端口** 往往比“全塞到 `443` 的不同子路径”更省心。  
  尤其用了 `caddy-security` 之后，像 `/assets/*` 这类静态资源路径容易和后端自己的 `/assets/*` 打架。

- **端口被占 / 想限定监听网卡 → 用 `bind`**：`bind` 的分组机制、独占端口 vs 共享端口的正反用法见下一节；`address already in use`（常见 Docker 占了 `127.0.0.1:port`）的诊断修复、以及共享端口误加 `bind` 导致的域名白屏，见文末「排障与诊断」。

- **公网端口别忘了放行安全组/防火墙**。  
  中国大陆 Aliyun ECS 的未备案 SNI 封锁与“IP 直连 + `tls internal`”绕过方案另见 [icp-filing.md](icp-filing.md)。

### `bind` 与 listener 分组：独占端口 vs 共享端口

`bind` 表面是"决定监听哪个网卡地址"，但它真正的杀伤力是会**改变 Caddy 的 server 分组**，进而决定整段端口的流量归属。一次把 `:443` 上一堆域名全打白屏的事故就出在这里，所以单独拎出来讲。

**机制三连**：

1. **不写 `bind` = 监听通配 `:PORT`**（`0.0.0.0` + `::`，所有网卡）；**写 `bind 1.2.3.4` = 只监听 `1.2.3.4:PORT`** 这个具体地址。
2. **Caddy 按 listen 地址给站点分组**：listen 地址完全相同的站点合并进**同一个内部 server**（在 server 内部再靠 SNI/Host 路由到具体站点）；listen 地址不同就拆成不同 server。所以**给某站点加 `bind` = 把它从默认 `:PORT` 那组里拆出来、独占 `IP:PORT`**。
3. **OS 内核：具体 IP 的 socket 优先于通配 `*`**（more-specific 优先，且两者能并存不冲突）。进 `1.2.3.4:PORT` 的连接会被那个 bind 出来的独立 server 抢走，而不是落到通配 server。

**于是分两种端口场景，结果完全相反**：

- **独占端口（一个端口只挂一个站点）→ `bind` 安全、有用。**
  典型是每个后端各占一个非标端口（`:8082`、`:9000`…）。这个端口本来就它一个站点，拆成独立 server 也没人跟它抢。`bind` 在这里是正面用途：限定只在公网 NIC + mesh NIC 上监听（不监听不该听的地址），或避开 Docker 已占的 `127.0.0.1:port`（`address already in use` 的修复见文末「排障与诊断」）。**IP 模式天然是"每服务一个独占端口"，所以这种 bind 在 IP 模式下随便用。**

- **共享端口（一个端口靠 SNI/Host 给多个站点分流，典型 `:443`）→ `bind` 会劫持整段端口。** ⚠️
  `:443` 上挂着一堆域名（`a.example.com`、`b.example.com`、auth portal…），默认都 listen `:443`，合并进同一个 server 靠 SNI 分流——这是对的。**此时只要给其中一个站点加 `bind 1.2.3.4`**，它就独占 `1.2.3.4:443`，按"具体 IP 优先"截走**所有**经 `1.2.3.4` 进来的 `:443` 流量；可它的路由表里只有自己一个域名，对别的域名一律不匹配 → 同端口其它域名集体故障。**这个故障的现象（`200` + 空 body 白屏、本机自查却正常）、诊断与修复见文末「排障与诊断 · 共享端口 `bind` 劫持白屏」。**

**规矩**：

- **共享端口（尤其 `:443`）上的域名站点一律不写 `bind`**——公网域名本来就该在所有网卡监听，让它们全部合并进通配 `:443` server 靠 SNI 分流。
- 若确实要给所有站点统一限定网卡，用**全局** `default_bind <IP>...`（写在 global options 里、对所有站点生效）——这样所有站点 listen 地址仍然一致、照样合并、不拆 server；**别**在单个 `:443` 站点上局部 bind（局部 `bind` 会**覆盖** `default_bind`，那个站点又被拆出去——所以这是硬性前提，不是风格建议）。
  - *源码核对（v2.11.2）*：`default_bind` 是全局选项，注册于 `caddyconfig/httpcaddyfile/options.go`（`RegisterGlobalOption("default_bind", …)`）；应用逻辑在 `caddyconfig/httpcaddyfile/addresses.go` 的 `listenersForServerBlockAddress`，优先级为「站点自带 `bind` > 全局 `default_bind` > 通配 `:PORT`」。监听地址拼成 `<bindHost>:<port>` 后，由同文件 `consolidateAddrMappings` 按地址字符串分组决定合并/拆分（上面「机制三连」第 2 条即出自这里）。

## 安装带插件的 Caddy 二进制

APT 安装的系统自带 Caddy **不包含** `caddy-security` 这类第三方扩展。需要插件时，做法是：

- 去 [Caddy Download Page](https://caddyserver.com/download) 勾选所需插件；
- 下载**一个包含全部所需插件**的新二进制；
- 用它替换系统自带的 `/usr/bin/caddy`。

> 已经装过一个插件、后面还想加另一个插件时，不是再叠一层，而是**重新下载一个同时包含两者的新二进制**。
>
> **下载时优先取页面默认的最新 stable 版本**（caddy 本体和插件都取最新）。多台机共用同一套 `caddy-security` 时（尤其跨主机的 portal↔gatekeeper 分离部署），**各台的 caddy-security 版本要尽量一致**——否则会踩文末「排障与诊断 · 跨版本 cookie 名陷阱」。

### 下载（不带版本参数 = 始终最新 stable）

```bash
curl -fsSL -A "Mozilla/5.0" -o caddy.new \
  "https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com/greenpau/caddy-security"
chmod +x caddy.new
./caddy.new version; ./caddy.new list-modules --versions | grep -i security   # 确认版本
```

- 多插件就追加多个 `&p=...`（每个插件一个 `&p=...`），一次下一个**包含全部插件**的二进制。
- **没带 `-A "Mozilla/5.0"` User-Agent 会被拒**（返回 ~22 字节的 `Contact: ...` 文本，不是二进制）。
- 不带版本参数时该 API **默认给最新 stable**（caddy 本体 + 各插件都最新）。

> ⚠️ **自定义二进制不会自动更新**。`dpkg-divert` 之后 APT 只更 `caddy.default`，**`caddy.custom` 冻结在你上次下载的版本**——这就是版本会悄悄落后、多机出现版本 skew 的根源（见文末「排障与诊断 · 跨版本 cookie 名陷阱」）。想升级**只能手动重新下载**；多机共用 portal 时要把各台一起升、保持版本一致。

### 首次安装（`caddy.custom` 还不存在）

```bash
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy   # 只做一次
sudo install -m 0755 caddy.new /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo systemctl restart caddy
```

- `dpkg-divert` 把原始 `/usr/bin/caddy` 移到 `caddy.default`，防 APT 升级覆盖；`custom`(50) 优先 `default`(10)；`sudo update-alternatives --config caddy` 可切换。**`dpkg-divert` 只做一次**。
- **RHEL 系通常没有 `dpkg-divert`**，改用发行版自己的 alternatives 机制。

### 更新到最新版（`caddy.custom` 已存在且正在运行）

**坑：不能直接 `cp` 覆盖正在运行的二进制**——会报 `Text file busy`；从 `/tmp` 跨文件系统 `mv` 也会退化成 copy 同样失败。正解是**拷到目标同目录再用 `mv` 原子 rename**（rename 只换目录项，运行中的旧 inode 不受影响，重启才加载新的）：

```bash
B=/usr/bin/caddy.custom
# 1) 先用新二进制验证当前配置兼容（大版本升级可能改 Caddyfile 语法 / 默认值）。
#    {env.*} 占位符给 dummy 值（validate 只查能否解析，不查值是否合法）。
GITHUB_CLIENT_ID=x GITHUB_CLIENT_SECRET=x \
JWT_SHARED_KEY=0000000000000000000000000000000000000000000000000000000000000000 \
  ./caddy.new validate --config /etc/caddy/Caddyfile --adapter caddyfile   # 出 "Valid configuration" 才继续
# 2) 备份 → 同目录暂存 → 原子 rename 覆盖忙文件 → 重启
sudo cp -a "$B" "$B.bak-$(date +%Y%m%d-%H%M%S)"
sudo cp caddy.new "$B.new" && sudo chmod +x "$B.new"
sudo mv -f "$B.new" "$B"
sudo systemctl restart caddy
# 3) 确认新版真在跑（不是还在跑旧 inode）；起不来就 cp -a 把 .bak 拷回再 restart
caddy list-modules --versions | grep -i security
```

升级 `caddy-security` **大版本**前务必看文末「排障与诊断 · 跨版本 cookie 名陷阱」：默认 cookie 名变过，**升级会让所有现存会话失效（全员重登）**，且共用同一 portal 的各机要一起升、否则签发/读取的 cookie 名对不上会登录死循环。

## `caddy-security`：GitHub OAuth 认证

### 安装

从 [Caddy Download Page](https://caddyserver.com/download) 下载带 `github.com/greenpau/caddy-security` 的二进制，然后按上一节的方法替换系统自带 Caddy。

官方完整示例可参考：[authcrunch GitHub OAuth Caddyfile](https://github.com/authcrunch/authcrunch.github.io/blob/main/assets/conf/oauth/github/Caddyfile)

### 三件套：provider / portal / policy

caddy-security 的 GitHub OAuth 由三种东西拼起来，先理清它们的关系，后面所有配置都好懂：

- **identity provider**（`oauth identity provider …`）：身份来源，对接 GitHub OAuth。决定"用谁家账号登录、回调地址长什么样"。
- **authentication portal**（`authentication portal …` + 站点里 `authenticate with`）：登录门户，跑完整 OAuth flow、签发 JWT/cookie、按 `transform user` 给登录者打角色。一个 portal 用 `enable identity provider` 启用一个或多个 provider。
- **authorization policy**（`authorization policy …` + 站点里 `authorize with`）：业务站点的门禁，验 portal 签的 JWT、按 `allow roles` 放行，未登录就按 `set auth url` 跳去 portal。

数据流：浏览器 →（业务站点 `authorize` 发现没 token）→ 跳 portal `authenticate` → GitHub OAuth → portal 签 cookie/JWT → 跳回业务站点 → `authorize` 验通过放行。portal（签）和 policy（验）共用同一个 `JWT_SHARED_KEY`。

### 指令与默认行为速查（v1.1.61 源码核对）

> 本节默认值/行为全部按以下版本读源码核对：**caddy-security v1.1.61 + go-authcrunch v1.1.38 + caddy v2.11.2**（各仓库 checkout 到对应 tag 后读源码）。
>
> **caddy-security 只是 Caddyfile→Go config 的翻译层，真正的认证/授权逻辑全在 go-authcrunch**（caddy-security `go.mod` 依赖 `go-authcrunch v1.1.38`；前者 6千多行全是 `caddyfile_*.go` 把文本语法翻成后者的 config 结构体 + 注册 Caddy module）。所以：**指令叫什么名 / 怎么嵌套** → 看 caddy-security 的 `caddyfile_*.go`；**默认值 / 实际行为** → 看 go-authcrunch 的 `pkg/`。下面行号随版本漂移，升级后要重核。

**authentication portal 指令（签发侧）**

| 指令 | 不写时的默认 | 源码（未注明即 go-authcrunch） |
|---|---|---|
| `crypto default token lifetime <秒>` | **900s（15min）** | `pkg/kms/crypto_key_config.go:32`（`defaultTokenLifetime=900`），`TokenLifetime==0` 时回退 `:439-443` |
| `cookie lifetime <秒>` | **不输出 Max-Age → session cookie（关浏览器即失效）**；**不**继承 token lifetime | `pkg/authn/cookie/cookie_get.go:41-46`（仅 `Lifetime!=0` 才写 `Max-Age`） |
| `cookie domain <域>` | 不设 → host-only（子域拿不到）；**域名模式必写、IP 模式必不写**（见「cookie 作用域」） | — |
| `set access_token cookie name <名>` | **`AUTHP_ACCESS_TOKEN`**（前缀 `AUTHP` + `_` + `ACCESS_TOKEN`） | 常量 `pkg/authn/cookie/cookie_config.go:20,35`；拼接 `:67`/`:89-91` |
| `crypto key sign-verify {env.K}` | 必配（否则每次启动随机新 key，重启=全员重登）；详见下「sign-verify vs verify」 | `pkg/kms/crypto_key_config.go:39-41` |

**authorization policy 指令（验签侧）**

| 指令 | 不写时的默认 | 源码 |
|---|---|---|
| `set token sources <...>` | **cookie + header + query 三者全开**；优先级 cookie→header→query，**命中即停** | 默认集合 `pkg/authz/validator/sources.go:39-53`；迭代+短路 `sources.go:155-168` |
| `validate bearer header` | **不写 = 根本不解析 `Authorization: Bearer <jwt>`**（这是"开启 Bearer 来源"的开关，不是"放宽校验"） | `pkg/authz/validator/sources.go:105-118`（`v.opts.ValidateBearerHeader && HasPrefix("Bearer")`） |
| `set user identity <field>` | **email；没 email 才回退 subject**。只影响 `ar.Response.User["id"]` →（caddy-security）Caddy `user.id`（access log / `{http.auth.user.id}`），**不影响注入头、不影响 whoami** | `switch` 逻辑 `pkg/user/user.go:180-191`；唯一消费点 `pkg/authz/authenticate.go:80` |
| `inject headers with claims` | **不写 = 不注入任何 `X-Token-*` 头**（下游拿不到身份）；详见下「inject headers 注入了什么」 | `pkg/authz/authenticate.go:270-306` |
| `set auth url <U>` | 未登录跳这里；默认 `/auth` | `pkg/authz/authenticate.go:192-228`；默认 `pkg/authz/config.go:170-178` |
| `set forbidden url <U>` | **已识别用户但被 ACL 拒绝**才跳这里（≠ auth url）；支持 `{uri}`/`{url}` 占位符 | 触发 `pkg/authz/authenticate.go:114`（`ErrAccessNotAllowed*`）→ `:166-186` |
| `allow roles A B` | **OR**（任一命中即放行；要 AND 用 `match all`） | `pkg/user/user.go:257`（`HasRole`=any-of）；ACL 规则 `pkg/acl/rule.go` |
| `crypto key verify {env.K}` | 只验签不签发；详见下「sign-verify vs verify」 | `pkg/kms/crypto_key_config.go:39-41` |

**⚠️ 安全提醒：`set token sources` 不写时，query 来源默认是开的。** 即 `https://站点/path?access_token=<JWT>` 这种把 JWT 塞进 URL query 的访问默认能过鉴权（默认集合含 `query`：`sources.go:39-53`；`parseQueryParams` 把 query 里长度 >32 的参数当 token：`sources.go:78-93`）。

- 这里塞的是 **JWT 本身**（已签好的明文凭证，base64 可解出 `sub/roles/exp`），不是签名密钥；泄露 = token 有效期内（取决于配置的 lifetime，可能数天）被冒充。
- query 比 cookie/header 危险：URL 会进**浏览器历史/书签**、**`Referer` 头**、**access log / 日志归档**（工业界 JWT 最常见的泄露途径）。cookie 有 `HttpOnly`/`SameSite` 保护、header 是程序自己塞的，都不会"无意飞出去"。
- **纯浏览器站点想关掉 query**：`set token sources cookie`（或 `cookie header`）。若现状是三源全开（不写 `set token sources`），属可接受的放宽——只要后端不读这些 token、也没人故意把 JWT 贴进 query，攻击面就只是"理论"级，可不强制收紧。

#### `crypto key sign-verify` vs `verify`（签发侧 vs 验签侧）

- portal 用 `sign-verify`：该 key 既能签 JWT 也能验签（portal 要签发）。
- policy 用 `verify`：只验签（业务站点只需验、不签发）。
- 二者不是反义；`sign-verify`/`sign`/`verify` 是 key 的 `Usage` 字段（`pkg/kms/crypto_key_config.go:39-41,66-68`）。
- **对称 HMAC**（你的 `JWT_SHARED_KEY` 这种 hex 字符串）下同一 secret 天然可签可验，写哪个只是限定"这个 key 在这里允许干什么"。**非对称 RSA/ECDSA** 下私钥才能签、公钥只能验，写错 usage 会能力不匹配（`pkg/kms/crypto_key.go:148-203`）。

#### `inject headers with claims` 注入了什么

开启后（且 `PassClaimsWithHeaders=true`），把 JWT claims 转成 HTTP 头注入给下游反代（`pkg/authz/authenticate.go:270-299`）。默认 4 个，对应 claim 非空才注入：

| 注入头 | 来源 claim |
|---|---|
| `X-Token-User-Name` | `Claims.Name` |
| `X-Token-User-Email` | `Claims.Email` |
| `X-Token-User-Roles` | `strings.Join(Claims.Roles, " ")` |
| `X-Token-Subject` | `Claims.Subject` |

另可用 `inject header <H> from <field>` 加自定义头（解析 `caddy-security/caddyfile_authz_inject.go:24-49`、执行 `go-authcrunch/pkg/authz/authenticate.go:301-306`，取值 `pkg/user/user.go:323-345` 支持任意 claim path）。

**删掉这条 = 下游收不到任何 `X-Token-*` 头**。只有"后端靠反代注入的头识别用户"时才需要；后端自带账号系统（OpenList/Coolify）或根本不读这些头时可省。

### 登录态有效期与续期（无 sliding refresh）

**结论：caddy-security 没有 sliding refresh（"持续访问就自动续期"）。** token 只在**登录成功 / grantAccess** 时签发，lifetime 从签发那刻硬倒计时，访问期间不延长。

- `/api/refresh_token` **不是续期接口**——它只返回一个时间戳，不重发 JWT/cookie（`go-authcrunch/pkg/authn/handle_api_refresh_token.go:27-36`，整个 handler 就 `resp["timestamp"]=now` 然后 `Write`）。
- 真正签发/重签只在登录流程（`pkg/authn/handle_http_login.go:302-379`：`SetExpiresAtClaim` → `SignToken` → `Set-Cookie`）。
- 所以 `crypto default token lifetime` / `cookie lifetime` 配多少，就是"登一次能用多久"的硬上限。

**那为什么平时感觉"永不掉线"？** token 过期后这条链路通常无感重签：业务站 302 → portal 发现自己 cookie 也过期 → 跳 GitHub OAuth → **GitHub 自己的登录 session 一般还在**（GitHub cookie 以月计）→ 不要求重输密码，直接 302 回 callback → portal 重签一份新 JWT。整个过程只闪几次重定向。只有 GitHub session 也死了才会真卡在 GitHub 登录页。

**想要更长的免登期**：把两个 lifetime 一起调长（如 30 天 `2592000` / 90 天 `7776000`，两者设一样）。代价：JWT 无状态，调长 = 撤销窗口变长（过期前无法 server-side 失效，强行作废只能换 `JWT_SHARED_KEY`，但那会让**所有人**一起掉线）。

### 改权限不即时生效 · 无法单独踢人（无状态 JWT 的运维后果）

**事故还原**：你在 Caddyfile 里给某用户新加了放行角色（改 `transform user` / `allow roles`），reload 生效，本以为他能进了——可他刷新页面还是 `403`。于是你想"把他踢下线、逼他重登，不就拿到新角色了？"结果发现：**单个用户根本踢不下线**。为什么改了权限他还被拒、为什么踢不了人，根子都在上一节的"无状态"。

**改了权限他仍被拒 = 角色烤进了旧 token。** `transform user` 只在登录那刻算一次角色写进 JWT，`authorize` 端**只验签读 claims、从不重算**。他攥着改配置**之前**签发的旧 token，里面没有新角色，得等 `exp` 过期重签才更新。诊断信号（`authorize` 日志）：

```
reason: user role is valid, but not allowed by access list
```

（token 有效、角色**有值**，但和 `allow roles` 没交集。）对照他最后一次 `Successful login` 时间 vs Caddyfile 改动时间，login 更早就是这个坑。**修法：让他登出重登**（或等 `exp` 过期），配置不用再动。

**他为什么不会自己重登** —— 授权失败分两条路（回链「指令速查」）：

| 情形 | 走向 | 结果 |
|---|---|---|
| 无 token / 已过期 | `set auth url` → 跳 portal | 顺带重签、拿到新角色，自愈 |
| 有旧 token 但角色不够 | `set forbidden url` → 静态页 | 不重登、角色永远刷不了，只看到"突然没权限" |

"线上改权限、老用户被闷在 403 且不自知"就是第二行——他有 token、走 forbidden 分支，不会被送去重登。缓解：把 forbidden 页写成"权限已变更，点此重新登录"的引导，别只丢个死 403。

**为什么踢不了单人。** 无状态服务端不存 session，没有"某人在线记录"可删；唯一能立刻作废旧 token 的服务端手段是换 `JWT_SHARED_KEY`，但那会让**所有人一起掉线**。要精确踢单人只能引入服务端状态（吊销名单 / token introspection，或换 Authelia、Authentik、Keycloak 这类有 session 的方案），代价是丢掉无状态的本地验签、无共享存储、多站解耦，改造大。

**务实解：调短 token lifetime**（分钟~小时级），改权限后最多等一个 lifetime 就自动重签生效——与上一节「想要更长免登期」是同一旋钮的两个方向。小圈子这样够用，不必上有状态。

### portal 页面：`/portal` / `/whoami` / 登录后落点

portal（`authenticate with <portal>` 那个站点）按 path 分发（`go-authcrunch/pkg/authn/respond_http.go:36-73`）：

| 相对路径 | 内容 | 源码 |
|---|---|---|
| `/portal` | 应用入口列表（`PrivateLinks`）+ 登出 | `pkg/authn/handle_http_portal.go:94-107` |
| `/whoami` | 当前 token 的 JSON（claims + `expires_at_utc`/`issued_at_utc` 等时间字段） | `pkg/authn/handle_http_whoami.go:37-66` |
| `/login` | GitHub 登录入口 | `pkg/authn/handle_http_login.go` |
| `/profile/` | 用户资料 SPA（须带尾斜杠） | `respond_http.go:36-73` |

- **登录成功默认落 `/portal`**（除非带了可信 `redirect_url` cookie）：`pkg/authn/handle_http_login.go:347-379`（`redirectLocation==""` 时 → `BaseURL + /portal`）。
- **`/whoami` 显示的是 `usr.AsMap()`（直接读 JWT claims / 内部 user map）**：`pkg/authn/handle_http_whoami.go:42-43` + `pkg/user/user.go:136-139`。它**不经过** authorization policy、**不读** `set user identity` / `inject headers`——所以删那些 policy 指令**不影响 whoami 显示**（whoami 上的 `sub/email/name` 直接来自 JWT claims）。

### 先理解 cookie 作用域

`caddy-security` 通过 cookie 在浏览器和 portal 之间携带 JWT。cookie 的作用域由 `Domain` 决定：

| `Domain` 设置 | 浏览器行为 |
|---|---|
| **不设** | host-only，只发回设它的精确 host，子域名拿不到 |
| `Domain=example.com` | 发回给 `example.com` 及所有子域名 |

关键点：

- **cookie 不区分端口**。  
  RFC 6265 明确不把端口算进 scope。`host:443` 设的 host-only cookie，浏览器**也会**发到 `host:8080`、`host:9220`。

因此两种模式下的配置要求正好相反：

- **域名模式必须写** `cookie domain example.com`  
  否则子域名拿不到 cookie，登录后访问 `app.example.com` 时 JWT 不会带过去，最后就是登录死循环。

- **IP 模式必须不写** `cookie domain`  
  RFC 6265 不允许 `Domain=<IP>`。这时依赖的是 host-only + 不区分端口的特性，让同一 IP 的不同端口共享 cookie。

由此可以推出一个非常重要的结论：

- **IP 访问的认证体系和域名访问的认证体系彼此独立**。  
  域名 cookie 进不到 IP host，IP host 的 cookie 也进不到域名 host。
- **GitHub OAuth App 的 callback URL 是固定的**。  
  所以 IP 体系和域名体系各用一套独立的 GitHub OAuth App，不要试图跨复用。

### 常用配置项

- **`order <指令A> before <指令B>`**  
  显式指定 HTTP handler 的执行顺序（caddy-security 注册时已声明默认相对位置：`caddy-security/plugin_authn.go:34` `authenticate` before `respond`、`plugin_authz.go:42` `authorize` before `basicauth`；写在 global `order` 里是覆盖/保险）。最常见的是：

  ```caddyfile
  order authenticate before respond
  order authorize before basicauth
  ```

- **`crypto default token lifetime` / `cookie lifetime`**  
  分别是 JWT 的 `exp` 和浏览器 cookie 的 `Max-Age`。**两者要设成一样**。默认 token 只有 900 秒（15 分钟，`go-authcrunch/pkg/kms/crypto_key_config.go:32`），通常太短；cookie 不写则**无 Max-Age**（session cookie）。续期机制见上「登录态有效期与续期」。

- **`crypto key sign-verify <key>`**  
  JWT 签名密钥。**不显式配置时，插件每次启动都会生成临时新密钥**，重启等于全员强制重登。  
  建议用 `{env.JWT_SHARED_KEY}` 固定下来；`authorization policy` 里用 `crypto key verify` 指向同一个 key 只做验签。  
  参考：[AuthCrunch auth-cookie 文档](https://docs.authcrunch.com/docs/authenticate/auth-cookie)

- **`transform user` + `allow roles`**  
  `transform user` 给登录用户打角色；`allow roles A B` 是 **OR**，任一角色匹配就放行（`go-authcrunch/pkg/user/user.go:257` `HasRole`=any-of；要 AND 用 `match all`）。  
  `authp/admin` 这类名字只是约定，不是保留字，字符串本身可以自定。

- **`trust login redirect uri`**  
  白名单“哪些 `redirect_url` 允许写入回跳 cookie”。  
  不配置会被**静默丢弃**（`go-authcrunch/pkg/authn/inject_redirect_url.go:32`：`len(TrustedLoginRedirectURIConfigs)<1` 直接 return，只记 debug 日志）。  
  **IP 模式尤其要注意端口**：Go 的 `url.Host` 会把端口也算进去（匹配逻辑 `go-authcrunch/pkg/redirects/redirect_match.go`），匹配非标端口时正则必须显式吃掉端口 `(:[0-9]+)?`。  
  参考：[caddy-security#455](https://github.com/greenpau/caddy-security/issues/455)

### caddy-security 路径隔离经验

`authenticate` 是认证门户本身，`authorize` 是保护业务站点的门禁。常见、稳妥的结构是把认证门户单独放在一个路径前缀或二级域名，不要让它和业务前端/后端共用根路径下的短路径。

推荐二选一：

- **单独路径前缀**：`/auth/*`
- **单独二级域名**：`auth.example.com`

这样可以避免这些常见冲突：

- Vite 等前端构建工具默认会把静态资源放到 `/assets/*`，不要让 auth portal 抢业务前端的 assets。
- 业务后端常用 `/api/*`，而 caddy-security 的 profile app 也会用类似 `/api/refresh_token`、`/api/profile` 的内部 API；portal 挂在根路径时很容易撞到业务 API。
- `/profile`、`/whoami` 这类短路径也容易和业务路由或 SPA fallback 冲突；当前插件源码里没有 `/settings` 这个裸路由，不要把它当作 auth portal 路径。

路径经验：

- 如果业务和 portal 在同一 host，`set auth url` 必须指向 portal 前缀下能被 `authenticate` 接住的路径，例如 `https://example.com/auth/` 或 `https://example.com/auth/login`。
- 保留业务自己的 `/api/*` 和 `/assets/*`，让它们继续进业务后端或前端文件服务。
- 不要把 `authorize with ...` 提到 site block 顶层再用多个 `handle` 分支，否则可能让授权层先于 portal 路径执行，导致登录页、回调或 whoami 被授权层拦住。
- `trust login redirect uri domain suffix example.com path prefix /` 适合信任自己控制的主域和子域；如果只信任当前 host，可用 `domain exact example.com`。不要删除 trust：没有 trust 时，`redirect_url` 会被忽略。
- portal 诊断页如 `/auth/whoami` 未登录时可能使用相对 `redirect_url`；这不应作为业务登录回跳的主流程。正常业务回跳应由 `authorize` 生成完整原始 URL，这会通过 trust 的许可。

下面这些路径都是**相对 portal base path**。如果 portal 挂在 `/auth/*`，就把 `/login` 理解成 `/auth/login`；如果 portal 独占 `auth.example.com` 根路径，就直接是 `/login`。

| 相对路径 | 用途 | 备注 |
|---|---|---|
| `/` | portal 根入口 | 通常会跳到 `/login` |
| `/login` | 登录页 | GitHub OAuth 按钮从这里进入 |
| `/logout` | 登出 | 清理 auth cookie，可能触发外部登出 |
| `/portal` | 登录后的 portal 首页 | auth portal 自己的首页 |
| `/whoami` | 当前身份/Token 信息页 | 诊断用，不建议当业务登录入口 |
| `/profile/` | 用户资料管理 SPA | 必须带尾斜杠；不是 `/profile` |
| `/profile/*` | profile SPA 静态资源/子路由 | 例如 `/profile/assets/...` |
| `/assets/*` | 老 portal UI 静态资源 | CSS、JS、图片等 |
| `/oauth2/*` | OAuth 流程 | 例如 GitHub 登录、callback |
| `/api/refresh_token` | portal 内部刷新 token | profile app 会用 |
| `/api/profile...` | profile app 内部 API | 需要 profile API 开启和用户角色 |
| `/register` | 注册页/流程 | 本地 identity store 场景更有意义 |
| `/recover` / `/forgot` | 找回流程 | 主要是本地账号场景 |
| `/basic/login/*` | Basic login 相关流程 | 特定认证方式用 |
| `/apps/sso` | SSO app 页面 | 插件内置 app |
| `/apps/mobile-access` | 移动访问 app 页面 | 插件内置 app |
| `/sandbox/*` | MFA/交互沙盒流程 | MFA、U2F 等相关 |
| `/barcode/mfa/*` | MFA 条码 | App MFA 注册/展示相关 |


### 配置 OAuth 环境变量

```bash
sudo systemctl edit caddy
```

添加：

```ini
[Service]
Environment="GITHUB_CLIENT_ID=你的ID"
Environment="GITHUB_CLIENT_SECRET=你的密钥"
Environment="JWT_SHARED_KEY=你的JWT密钥"
```

然后重载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
sudo systemctl show caddy --property=Environment
```

说明：

- `JWT_SHARED_KEY` 填一串足够长的随机字符串即可。
- 为什么必须显式配 `JWT_SHARED_KEY`，见上一节的 `crypto key sign-verify` 说明。

### GitHub OAuth 与 callback 踩坑经验

GitHub OAuth 的 Web application flow 不是“浏览器跳回来就登录完成”。GitHub 回调 Caddy 时只带一次性的 `code` 和 `state`；`caddy-security` 必须在服务端用 `code + client_id + client_secret` 请求：

```text
POST https://github.com/login/oauth/access_token
```

换到 access token 后，才能继续查 GitHub 用户身份、执行 `transform user`、签发自己的登录 cookie/JWT。也就是说，GitHub OAuth 登录包含一段由运行 Caddy 的服务器发起的服务端请求；浏览器能访问 GitHub 不等于服务端 OAuth 流程已经完成。

GitHub OAuth App 的 callback URL 用来约束 Caddy 发给 GitHub 的 `redirect_uri`。GitHub 官方规则：

- 如果没有传 `redirect_uri`，GitHub 使用 OAuth App 设置里的 callback URL。
- 如果传了 `redirect_uri`，其 host（不含子域规则）和 port 必须匹配 callback URL。
- `redirect_uri` 的 path 必须是 callback URL path 本身，或 callback URL path 之下的子路径。

例如 OAuth App callback URL 是：

```text
https://<主 IP>/auth/oauth2/github
```

则 GitHub 可接受同 host/port 下的：

```text
https://<主 IP>/auth/oauth2/github
https://<主 IP>/auth/oauth2/github/authorization-code-callback
```

但不会把不同 host 或不同 port 视为同一个 callback。

在 caddy-security 里，`redirect_url` 和 GitHub 的 `redirect_uri` 是两件事：

- `redirect_url`：Caddy 登录成功后送用户回到的原始业务 URL，由 `trust login redirect uri` 约束。
- `redirect_uri`：Caddy 发给 GitHub 的 OAuth callback URL，GitHub 授权后把 `code` 和 `state` 回传到这里。

如果 portal 挂在 `/auth/*`，GitHub provider 的实际 callback endpoint 是：

```text
/auth/oauth2/github/authorization-code-callback
```

### callback URL 与字段映射（哪个字段决定哪一段）

> 把"callback URL 怎么拼出来、各段受哪个 Caddyfile 字段控制"讲透，避免填错被 GitHub 拒。结论按 caddy-security **v1.1.61** / go-authcrunch **v1.1.38** 读源码核对（`caddyfile_identity_provider.go`、`pkg/idp/oauth/authenticate.go`、`pkg/authn/handle_external_login.go`、`pkg/authn/portal.go`）。

**组装公式**（go-authcrunch `pkg/idp/oauth/authenticate.go:104`：`reqRedirectURI := reqPath + "/authorization-code-callback"`，其中 `reqPath = BaseURL + path.Join(BasePath, Method, Realm)`）：

```text
https://<portal 挂载 host>/<handle 前缀>/oauth2/<provider 的 realm>/authorization-code-callback
```

- ① `<portal 挂载 host>` — 跑 `authenticate with <portal>` 的那个站点的 host
- ② `<handle 前缀>` — `handle /auth/*` 里的前缀（独占子域、portal 挂根时这段为空）
- ③ `oauth2` — 固定字面（go-authcrunch 写死的 authMethod）
- ④ `<provider 的 realm>` — provider 的 **`realm`** 字段，**不是 name！**
- 末段 `authorization-code-callback` — 固定后缀（开了 `enable js callback` 才是 `-js-callback`）

**最易错的一点**：第 ④ 段是 provider 的 **`realm`**，不是 name。go-authcrunch 拿 `/oauth2/` 后第一段去 `getIdentityProviderByRealm()`（`provider.GetRealm() == 段`，`handle_http_login.go:77`），不是按 name。只有**单行简写**时 realm 恰好 = name = driver，才显得像 name。

**各字段管什么**（`caddyfile_identity_provider.go` / `portal.go`），别混：

| 字段 | 管什么 |
|---|---|
| **name**（`oauth identity provider <name>` 第一个 token） | provider 内部 key，被 portal 的 `enable identity provider <name>` 按 name 引用（`portal.go:124` `GetName()==`）。**不进 callback URL** |
| **realm**（块内 `realm`；单行简写时隐式=name，**必填**） | **callback URL 第 ④ 段** + `transform user match realm` 的键 |
| **driver**（块内 `driver`；单行简写时隐式=name） | 用哪家 OAuth 端点（github/google/…）。**不进 callback URL** |
| `client_id` / `client_secret` | 绑**哪个** GitHub OAuth App；换 App 必换 callback host |
| portal 内 `cookie domain` | cookie 作用域：**域名模式必写、IP 模式必不写**（见「先理解 cookie 作用域」） |
| portal 内 `transform user { match realm <X> }` | 按 realm 给登录用户赋角色，`<X>` **必须 = 该 provider 的 realm** |
| `authorization policy { set auth url <U> }` | 受保护站点未登录时跳哪个 portal 的登录入口 |

**单行简写 vs 块形式**（`caddyfile_identity_provider.go`）：

- 单行 `oauth identity provider github {id} {secret}`：name 只能是 `github` / `google` / `facebook`（其它报 `unsupported "<x>" shortcut`），此时 `realm = driver = name`。
- 要让 realm / driver 与 name 不一致（自定义 realm、但 driver 仍走 github），**必须**块形式，且 `realm` 必填（空 realm 报 `ErrIdentityProviderConfigureRealmEmpty`，`config.go:128`）：

  ```caddyfile
  oauth identity provider <name> {
      realm <realm>          # ← 决定 callback URL 第 ④ 段
      driver github          # ← 仍走 GitHub OAuth 端点
      client_id {env.XXX_CLIENT_ID}
      client_secret {env.XXX_CLIENT_SECRET}
      scopes read:user
  }
  ```

**改 realm 的连带（最易漏）**：realm 同时是 callback 第 ④ 段**和** `transform user match realm` 的键。改它必须三处同步：① provider 块的 `realm` ② GitHub OAuth App 的 callback URL 那一段 ③ 对应 portal 里所有 `transform user { match realm … }`。漏掉 ③ 的症状：能跳 GitHub、能跳回来，但**一个角色都没拿到** → `authorization policy` 全 deny → 403 / 登录后无限跳。

> 一台机要**同时**支持 IP 直连和域名访问，上面这些字段要成对各来两套——完整骨架见下面「同机同时支持 IP + 域名（双体系并存）」。

### 域名模式模板

```caddyfile
{
    order authenticate before respond
    order authorize before basicauth

    security {
        oauth identity provider github {env.GITHUB_CLIENT_ID} {env.GITHUB_CLIENT_SECRET}

        authentication portal myportal {
            crypto default token lifetime 604800
            cookie lifetime 604800
            cookie domain example.com
            crypto key sign-verify {env.JWT_SHARED_KEY}
            enable identity provider github
            trust login redirect uri domain suffix example.com path prefix /

            transform user {
                match realm github
                regex match sub "github.com/(yourname|otheruser)"
                action add role authp/admin
            }
        }

        authorization policy admin_policy {
            set auth url https://auth.example.com/login
            crypto key verify {env.JWT_SHARED_KEY}
            allow roles authp/admin
        }
    }
}

auth.example.com {
    handle /forbidden {
        error "Unauthorized" 401
    }
    authenticate with myportal
}

app.example.com {
    authorize with admin_policy
    reverse_proxy localhost:8000
}
```

### 受保护站点和登录入口分离到不同机器

做法：

- **登录入口所在机器**：仍然按上一节的“域名模式模板”完整配置。
- **受保护站点所在机器**：只保留 `authorization policy`，两边共享同一个 `JWT_SHARED_KEY`。

受保护站点这台的最小写法：

```caddyfile
{
    order authorize before basicauth

    security {
        authorization policy admin_policy {
            set auth url https://auth.example.com/login
            set forbidden url https://auth.example.com/forbidden
            crypto key verify {env.JWT_SHARED_KEY}
            allow roles authp/admin
        }
    }
}

app.example.com {
    authorize with admin_policy
    reverse_proxy localhost:8000
}
```

注意：受保护站点这台**不要再保留**本地的 `oauth identity provider`、`authentication portal`、`cookie domain` 等登录侧配置。

### IP 模式模板

IP 模式仍然沿用前面“基础反代”里的 global options：

```caddyfile
{
    auto_https disable_redirects
    default_sni <主 IP>

    order authenticate before respond
    order authorize before basicauth

    security {
        oauth identity provider github {env.GITHUB_CLIENT_ID} {env.GITHUB_CLIENT_SECRET}

        authentication portal myportal {
            crypto default token lifetime 604800
            cookie lifetime 604800
            crypto key sign-verify {env.JWT_SHARED_KEY}
            enable identity provider github

            # 不要写 cookie domain（RFC 6265 不允许 Domain=IP）
            trust login redirect uri domain regex ^<主 IP>(:[0-9]+)?$ path prefix /

            transform user {
                match realm github
                regex match sub "github.com/(yourname|otheruser)"
                action add role authp/admin
            }
        }

        authorization policy admin_policy {
            set auth url https://<主 IP>/login
            crypto key verify {env.JWT_SHARED_KEY}
            allow roles authp/admin
        }
    }
}

https://<主 IP> {
    tls internal

    handle /forbidden {
        error "Unauthorized" 401
    }

    authenticate with myportal
}

https://<主 IP>:8080 {
    tls internal
    authorize with admin_policy
    reverse_proxy localhost:8000
}
```

IP 模式里最容易错的两点：

- **不要写** `cookie domain`
- `trust login redirect uri domain regex` 里要把端口吃掉：`(:[0-9]+)?`

### 同机同时支持 IP + 域名（双体系并存）

一台机要**既能 IP 直连（未备案）、又能走域名**访问时，不能只配一套。「先理解 cookie 作用域」已说明：IP host 与域名 host 的 cookie 互不可达，且每个 GitHub OAuth App 的 callback host 写死——所以 **IP 和域名必须各一套独立的 provider + portal + OAuth App**，并存在同一个 `security {}` 里。

成对出现的字段（一套 IP、一套域名）：

- **两个 provider**：IP 套用单行简写（realm 隐式 = `github`）；域名套用块形式、自定义 realm（如 `github_dom`）+ `driver github`，且 `client_id` / `client_secret` 指向**另一个** GitHub OAuth App。
- **两个 portal**：IP 套**不写** `cookie domain`，域名套**必写** `cookie domain example.com`；各自 `enable identity provider` 指自己的 provider；各自 `transform user match realm` 跟自己 provider 的 realm 一致。
- **两组 policy**：role 名可以复用（两套都用 `authp/admin` 等），但 policy 拆两组，`set auth url` 各指自己那套 portal。
- **两个 GitHub OAuth App**，callback URL 各填（注意 realm 段不同）：
  - IP：`https://<主 IP>/auth/oauth2/github/authorization-code-callback`
  - 域名：`https://auth.example.com/auth/oauth2/github_dom/authorization-code-callback`

骨架（占位符 `<主 IP>` / `example.com`，两套用不同的 env client）：

```caddyfile
{
    auto_https disable_redirects        # IP 站点需要
    default_sni <主 IP>
    order authenticate before respond
    order authorize before basicauth

    security {
        # IP 套 provider：单行简写 → realm = name = driver = github
        oauth identity provider github {env.GITHUB_CLIENT_ID} {env.GITHUB_CLIENT_SECRET}
        # 域名套 provider：块形式 → name/realm 自定义、driver=github、另一个 OAuth App
        oauth identity provider github_dom {
            realm github_dom
            driver github
            client_id {env.GITHUB_DOM_CLIENT_ID}
            client_secret {env.GITHUB_DOM_CLIENT_SECRET}
            scopes read:user
        }

        authentication portal portal_ip {
            crypto default token lifetime 604800
            cookie lifetime 604800
            crypto key sign-verify {env.JWT_SHARED_KEY}
            enable identity provider github            # 按 name
            # 不写 cookie domain（IP 模式）
            trust login redirect uri domain regex ^<主 IP>(:[0-9]+)?$ path prefix /
            transform user {
                match realm github                    # = IP 套 provider 的 realm
                regex match sub "github.com/(yourname)"
                action add role authp/admin
            }
        }
        authentication portal portal_dom {
            crypto default token lifetime 604800
            cookie lifetime 604800
            cookie domain example.com                 # 域名模式必写
            crypto key sign-verify {env.JWT_SHARED_KEY}
            enable identity provider github_dom        # 按 name
            trust login redirect uri domain suffix example.com path prefix /
            transform user {
                match realm github_dom                # = 域名套 provider 的 realm
                regex match sub "github.com/(yourname)"
                action add role authp/admin
            }
        }

        # role 名复用，但按体系拆两组，set auth url 各指自己的 portal
        authorization policy admin_ip {
            set auth url https://<主 IP>/auth/
            crypto key verify {env.JWT_SHARED_KEY}
            allow roles authp/admin
        }
        authorization policy admin_dom {
            set auth url https://auth.example.com/auth/
            crypto key verify {env.JWT_SHARED_KEY}
            allow roles authp/admin
        }
    }
}

# IP 入口：没有子域可用，portal 挂在子路径 /auth/*
https://<主 IP> {
    tls internal
    handle /auth/* { authenticate with portal_ip }
    handle /forbidden { error "Unauthorized" 401 }
}
https://<主 IP>:8080 {          # IP 受保护业务
    tls internal
    authorize with admin_ip
    reverse_proxy localhost:8000
}

# 域名入口：portal 独占一个子域，也挂 /auth/*（与 IP 对称）
auth.example.com {
    handle /auth/* { authenticate with portal_dom }
    handle /forbidden { error "Unauthorized" 401 }
}
app.example.com {               # 域名受保护业务
    authorize with admin_dom
    reverse_proxy localhost:8000
}
```

两套共享同一个 `JWT_SHARED_KEY`（同机签 / 验方便），但 cookie、OAuth App、realm 全独立。要再加第三套（另一个域名），照此再加一组 provider + portal + policy 即可。

## 文档私链分享站（docs-share：Git → RustFS S3 + Markdeep viewer）

> 这一套的定位是：**用 S3 presigned URL 做带过期、可撤销的只读文档分享**。后端是 RustFS（S3-compatible）；上传走 Git push（forgejo runner `rclone sync`）；浏览器渲染靠 Caddy 按 `Accept` 分流到本地 `_viewer.html`。
>
> **配套**：
>
> - **客户端怎么用**（凭据存哪、生成分享链接、Markdeep 写作惯例）→ `software` skill 的 `references/docs-share.md`
> - **viewer 壳子** → [`../assets/md-viewer.html`](../assets/md-viewer.html)
>
> 本节只覆盖服务端：RustFS 桶 + 受限 CI key + Caddy 边缘反代 + viewer rewrite。

### 架构与组件

```text
git push → forgejo (gitea-self-hosted) → forgejo-runner (DinD)
                                          │
                                          ▼
                                 rclone sync --checksum --remove
                                          │
                                          ▼
                                 RustFS S3 (mesh)
                                          │
                                          │ Caddy 边缘反代
                                          ▼
                                s3.example.com
                          ┌──────────────────────────────────┐
                          │ Idiom A: viewer.html?doc=...     │  (桶内匿名可读对象)
                          │ Idiom B: 浏览器贴 .md 直接渲染   │  (Caddy Accept rewrite → /srv/viewer/_viewer.html)
                          └──────────────────────────────────┘
```

两套 idiom 共存：

| Idiom | 入口 URL | 桶里需要 | Caddy 需要 | 适用 |
|---|---|---|---|---|
| **A. viewer 包装** | `<S3>/<bucket>/viewer.html?doc=<URL-encoded presigned>` | 桶根放 `viewer.html`（**单对象匿名可读**） | 仅普通反代 | 简单、跨 S3 后端通用 |
| **B. 地址栏直贴** | `<S3>/<bucket>/<path>.md?<presigned>` | 不需要 | `s3.example.com` 加 Accept matcher + 本地 `_viewer.html` | 想要 “同一 URL 浏览器排版 / `curl` 拿原文” |

### 客户端配置

服务端部署完成后，把受限 CI key 交给两个位置：forgejo 仓库 secret（runner 跑 rclone sync）和操作者本机 mc alias（生成 presigned URL）。密钥体系、alias 组织、presigned 生成方式的完整说明见 `software` skill 的「私有 docs-share 站点（Git 仓库 → S3 直链分享）」章节。

### 安装 viewer 壳子

```bash
sudo install -D -m 0644 ../assets/md-viewer.html /srv/viewer/_viewer.html
```

viewer 壳子是**外置文件**（Caddy 本地 file_server 直接 serve），不在桶里——所以**不需要桶里有任何匿名可读对象就能跑 Idiom B**。

> Idiom A 仍可并存：桶里另放一个对象级 anonymous policy 放行的 `viewer.html`（详见 `software/docs-share.md`「从零部署」步骤 4）。两者不冲突，因为 Caddy matcher 只对 `*.md` 生效，不影响 `/viewer.html` 路径。

### Caddy 站点模板

下面模板假设：

- 边缘域名：`<S3_HOST>`（如 `s3.example.com`）
- 后端 RustFS：`<RUSTFS_S3_API>`（如 mesh 内 `10.144.18.10:9000`）
- 外置 viewer：`/srv/viewer/_viewer.html`

```caddyfile
<S3_HOST> {
    # Accept-based rewrite: browsers (text/html) → viewer.html;
    # everything else (CLI / viewer JS fetch with Accept:text/plain) → RustFS.
    @md_in_browser {
        path *.md
        header Accept *text/html*
    }
    handle @md_in_browser {
        header Vary Accept
        header Cache-Control "no-cache"
        rewrite * /_viewer.html
        root * /srv/viewer
        file_server
    }
    handle {
        reverse_proxy <RUSTFS_S3_API>
    }
    import error_pages
}
```

### 这套设计为什么这么配

- **浏览器和 CLI 用 `Accept` 分流**
  浏览器分支匹配 `.md` + `Accept: text/html`，内部 `rewrite` 到 `/_viewer.html`；viewer 里再 `fetch(location.pathname + location.search)` 拉原始 Markdown。第二次请求的 `Accept` 默认不含 `text/html`，自然落到 raw 分支透传 RustFS，不会递归套 viewer。

- **viewer 反向 fetch 必须把 SigV4 query 透传**
  S3 presigned URL 的签名签了 host + path + query，缺一不可。viewer 不能只用 `location.pathname`（旧 `/data/share` 时代的写法），必须 `location.pathname + location.search`。否则 RustFS 拿到无签名请求直接 403。

- **viewer 壳子采用 Markdeep 自己的工作方式**
  先把原始 Markdown 塞进 `document.body.textContent`，再动态加载 Markdeep CDN；Markdeep 会同步处理整页内容。处理结束后再把导航条（面包屑、下载按钮）插回 `body` 首位。

- **`_viewer.html` 不需要在桶里**
  Caddy 直接 file_server `/srv/viewer/`；rewrite 是服务端内部重写，不发实际 HTTP 请求到 RustFS，所以 viewer 这块不消耗 SigV4 / 不增加桶里匿名对象。

- **`rclone sync --checksum` 而不是 `mc mirror`**
  `actions/checkout` 每次把所有文件以**当前时间**写入工作区，mtime 全被重置。按 mtime 判变化的工具会把整棵树判为“已变”→每次全量重传。`rclone --checksum` 改按内容哈希（对比 S3 ETag/MD5）判断，无视 mtime，只传内容真的变了的对象。`sync` 同时镜像删除（仓库删的对象桶里也删）。

### 验证矩阵（部署完跑一遍）

| 场景 | 命令 | 期望 |
|---|---|---|
| 浏览器贴签名 .md URL | `curl -H 'Accept: text/html' "<signed-md>"` | 200 + `text/html`（viewer 壳子内容） |
| viewer JS 反向 fetch（同 URL + 改 Accept） | `curl -H 'Accept: text/plain' "<signed-md>"` | 200 + `text/markdown` + md 原文 |
| CLI 默认（Accept:*/*） | `curl "<signed-md>"` | 200 + `text/markdown` + md 原文 |
| 浏览器贴**未签名** .md URL | `curl -H 'Accept: text/html' "<S3>/<bucket>/foo.md"` | 200 + viewer 壳子（viewer 是 Caddy 本地 serve，无需签名；viewer JS 后续 fetch 拿 403） |
| CLI 未签名 | `curl "<S3>/<bucket>/foo.md"` | 403（透传 RustFS，SigV4 验签拒） |
| 兼容 Idiom A | `curl "<S3>/<bucket>/viewer.html"` | 200（桶内匿名 viewer.html 仍可访问，老工作流不破） |

### 这套方案踩过的坑

- **Caddy matcher 是按 client 请求的 path + header 判断**，**不**按 backend 返 Content-Type；所以匹配 `*.md` 与 RustFS 把 `.md` 返成 `text/markdown` 还是别的无关。

- **`rewrite` 是服务端内部重写，浏览器地址栏不变**
  viewer 不能靠 `?src={uri}` 取原文地址，要直接看 `location.pathname` + `location.search`。

- **浏览器按 URL 缓存响应，不看 `Accept`**
  首访 `Accept: text/html` 可能把 viewer 壳子缓存下来，之后 viewer 内 `fetch()` 同 URL 时也吃缓存。靠三件事一起修：
  - viewer 分支发 `Vary: Accept`
  - raw 分支由 RustFS 控制（默认带 `Vary`，必要时在 caddy fallback handle 里也加）
  - viewer 分支额外发 `Cache-Control: no-cache`，前端 fetch 加 `cache: 'no-store'`

- **`<base href>` 会把 `#anchor` 解析成 `base-origin/#anchor`**
  TOC 里的 `<a href="#section">` 会跳目录页而不是当前文档内滚动。解决方式是在 `document` 上用 capture 阶段监听 click，拦截 `href` 以 `#` 开头的链接，改成 `location.hash = h`。其他相对/绝对链接仍交给 `<base href>` 处理。

- **`tocStyle` 没官方文档**
  可用字面量是 `"auto"`、`"short"`、`"medium"`、`"long"`、`"none"`，是从 `markdeep.min.js` 源码里 grep 出来的。当前 viewer 用 `"auto"`。

- **Markdeep 默认给标题和 TOC 都加自动序号**
  官方没有直接关掉的配置项。viewer 里扩了一个自定义选项 `noSectionNumbers`：设为 `true` 时注入 CSS 同时隐藏正文标题的 `::before` counter 内容和 TOC 里的 `.tocNumber`；改回 `false` 两处编号都会恢复。

- **CDN 用 `casual-effects.com/markdeep/latest/markdeep.min.js`**
  这是作者 Morgan McGuire 的官方站。

- **微信 WebView 无法下载文件**
  这是微信平台层面的下载拦截。viewer 检测 `MicroMessenger` UA 后，下载按钮要改成弹出蒙层，引导用户“在浏览器中打开”；其他浏览器再正常用 `download` 属性。

- **`_viewer.html` 直接访问 `https://<S3_HOST>/_viewer.html`（没带 .md 后缀）会 400**
  因为不命中 matcher，落到 fallback handle 透传 RustFS → “桶名 = `_viewer.html`, key = 空” → `InvalidBucketName`。这是预期：viewer 总是通过 rewrite 内部 serve，外部不该直接访问。

- **不要把 `?raw` 或 `?download` 这种 file_server 习惯的 query 拼到 fetch URL**
  会破坏 SigV4 签名，RustFS 直接 403。下载按钮直接 `dl.href = location.pathname + location.search` 即可（presigned `.md` GET 本来就是原文，不需要 `?raw` 切换 inline/attachment）。

- **`_viewer.html` 是公共组件**
  任何修改都同时影响所有 .md 在浏览器的渲染行为。改前测 6 场景矩阵，改后保留 `<TIMESTAMP>.bak` 至少 7 天。改完后**新版 viewer 对所有用 viewer 渲染的 .md 立即生效**——这是公共组件，改前确认不破老工作流（`viewer.html?doc=<URL>` 这种 query 模式必须仍可用）。

### 撤销与过期

S3 presigned URL **自带过期**（`X-Amz-Expires`，最长 7 天）。比 capability URL 强：

| 需求 | 做法 |
|---|---|
| 单链接撤销 | 链接到期自动失效；要立刻作废所有在途链接，用 root key `mc admin accesskey rm` 删掉受限 CI key 再重发一把（**让所有已发链接同时失效**） |
| 链接过期时间 | `mc share download --expire 168h` 生成时指定；最大 7 天（S3 SigV4 协议上限） |
| 后台管理 | RustFS console (`:9001`) 看对象级访问日志；forgejo Actions 看 sync 历史；细粒度审计：开 RustFS audit log |

### 不要做的事

- **不要让 `:9001`（RustFS console）暴露到公网**——Caddy 反代只对 `:9000`（S3 API）做。
- **不要绕过 forgejo / rclone sync 直接 mc cp 写桶**——下次 sync `--remove` 会把它抹掉，除非你**确实**在做“对齐桶到 main HEAD” 这种 hot-fix（见 `~/TiMidlY-projects/docs-share/.github/copilot-instructions.md` 的 rerun 覆盖事故说明）。
- **不要对早 sha 的 forgejo Actions run 做 rerun**——`rclone sync --remove` 会按那个 sha 的 tree mirror，覆盖更新 commit 的产物。要重新对齐桶用：rerun **当前 HEAD 对应那条 run**，或 push 一个空 commit。

## 排障与诊断

> 本节把散在各章的**故障排查**集中到一处。先用「诊断总表」按症状定位，再翻对应小节；通用工具（admin API / pprof）在「通用诊断入口」统一讲。各故障对应的**概念与正常配置**仍在其所属章节（`bind` 分组、cookie 作用域、`on_demand_tls`…），本节只讲**现象 + 诊断 + 修复**并回链。

### 诊断总表：症状 → 根因 → 去哪看

| 症状 | 最可能根因 | 详见 |
|---|---|---|
| `systemctl reload` 永久不返回、但服务仍在跑 | reload 在全局配置锁 `rawCfgMu` 里卡住 | 本节「reload 卡住 / 永久挂起」 |
| `systemctl reload` 秒退 exit 0，但 `is-active` 卡 `reloading`（小时/天级） | 历史上有次 reload 卡在锁里没解，caddy 从没发过 `sd_notify READY=1`；之后每次 reload 都被吞 | 本节「reload 卡住 / 永久挂起」变体现象 |
| `systemctl reload` 秒退但退出码非零 | 关旧 admin endpoint 的 10s timeout，配置其实已加载 | 本节「reload 退出非零 ≠ 失败」 |
| `caddy validate` 报 `{env.X}` 解析失败 | validate 不经 systemd、读不到注入的环境变量 | 本节「validate 读不到 systemd 环境变量」 |
| 一批域名集体白屏（`200` + 空 body），本机自查却正常 | 共享端口（`:443`）某站点误加 `bind`，劫持整段端口 | 本节「共享端口 `bind` 劫持白屏」 |
| `reload` 报 `address already in use` | 端口被别的进程（常见 Docker `127.0.0.1:port`）占了 | 本节「`address already in use`」 |
| 大量 WS / 长连接僵尸、内存缓涨、疑似拖累 reload | hijack 裸管道无超时、客户端静默死 | 本节「WebSocket / 长连接泄漏」 |
| 登录后无限 302 / `ERR_TOO_MANY_REDIRECTS` | 签发 / 读取方 caddy-security 版本不同 → cookie 名对不上 | 本节「跨版本 cookie 名陷阱」 |
| 能登、能跳回来，但一个角色都没有 → 403 / 无限跳 | 改了 provider `realm` 没同步 `transform user match realm` | 「callback URL 与字段映射」改 realm 的连带 |
| 某用户能登、也有角色，改过权限后却仍 403（`role is valid, but not allowed by access list`） | 旧 token 角色早于配置变更，`authorize` 不重算、只等 `exp` | 「改权限不即时生效 · 无法单独踢人」 |
| 证书签不出 / ACME 反复失败 / 垃圾子域名狂签 | DNS 没指过来，或 on-demand `ask` 太宽 | 本节「reload 卡住」第 3 条 + 「`on_demand_tls`」节 |
| docs-share viewer 渲染 / 下载 / 缓存异常 | viewer 壳子 / Markdeep / SigV4 细节 | docs-share「这套方案踩过的坑」 |
| 大陆 Aliyun ECS 未备案 SNI 被封 | 备案 / SNI 封锁 | [icp-filing.md](icp-filing.md) |

### 通用诊断入口：admin API 与 pprof

**`reload` / 配置读写都走 Caddy 的 admin（管理 / 控制）API**——一个 REST endpoint，**默认 `localhost:2019`**（可用 `CADDY_ADMIN` 环境变量或配置里的 `admin` 块改；配置里的地址优先于默认）。`caddy reload` 本质就是 `POST /load`（阻塞到加载完成 / 失败、失败自动回滚旧配置、零停机）；另有 `GET /config/`（导出实时配置）、`POST /stop`、`GET /debug/pprof/`（运行态 goroutine dump）。**`curl localhost:2019/...` 是在跑 Caddy 的那台机上访问它自己的控制口，不需要 sudo。**

一个关键差异贯穿下面多个排查：**`GET /config/` 要抢配置锁 `rawCfgMu`，而 `GET /debug/pprof/...` 不碰这把锁**。所以「`/config/` 挂住 + `pprof` 秒回」= 配置锁被占死，是 reload / 长连接类卡死的**通用指纹**。

```bash
# /config/ 是否被锁死（挂住 / 超时 = 锁被占）
curl -s --max-time 3 http://127.0.0.1:2019/config/ -o /dev/null -w '%{http_code} %{time_total}s\n'
# 全量 goroutine 栈（pprof 不抢锁、恒秒回），抓下来看谁卡在锁里
curl -s "http://127.0.0.1:2019/debug/pprof/goroutine?debug=2" > /tmp/caddy-goroutine.txt
grep -nE 'changeConfig|rawCfgMu|ManageSync|tls.obtain|Shutdown|io\.Copy|streaming\.go' /tmp/caddy-goroutine.txt
```

### `systemctl reload caddy` 卡住 / 永久挂起

**现象**：`sudo systemctl reload caddy`（或裸 `caddy reload`）**永久挂起、命令行不返回**；但 **caddy 主进程一直在跑、旧配置继续服务、网站不掉**——不是宕机，只是新配置迟迟加载不上、终端卡死。systemd 到点（`TimeoutStartUSec`，实测 90s）打一条 `Reload operation timed out. Killing reload process.`（`journalctl -u caddy` 可见，可能反复出现）；多数情况得手动 `sudo systemctl restart caddy` 才能解卡并让新配置真正生效。

**变体现象（更隐蔽，历史卡死没清干净）**：`sudo systemctl reload caddy` **秒退 exit 0**，但 `systemctl is-active caddy` 显示 `reloading` 而不是 `active`，`systemctl show caddy -p ActiveEnterTimestamp` 显示 reloading 状态已挂了**小时甚至天级**——不是本次 reload 造成的、是历史遗留。服务在跑旧配置、`curl` 拿不到本次改动，**每次改动都像被吞了**。触发链：前一次 reload 卡在锁里之后，caddy 从没发过 `sd_notify READY=1`，systemd 就把服务标成 `reloading` 定住；之后每次 `systemctl reload` 表面秒退 exit 0（systemd 层认为服务本来就在 reloading），但下发到 caddy 端的 `POST /load` 还是抢不到下面机制节讲的那把 `rawCfgMu` 全局锁，配置根本吃不进去。修复同下节解法第 1 条：`sudo systemctl restart caddy`。

> 四岔分诊：**永久不返回、配置迟迟没加载上** = 本节主分支；**秒退 exit 0 + `is-active` 卡 `reloading`** = 本节变体（历史卡死没清）；**秒回就报错**（不是挂住）= 多半配置语法错，`caddy validate` 能查、改对再 reload，不属本节；**秒退但退出码非零** = 配置其实已加载，见本节「`reload` 退出非零 ≠ 失败」。

#### 机制：reload 全程持一把全局配置锁

`caddy reload` = 往 admin API `POST /load`（见「通用诊断入口」）。服务端 `changeConfig()` **全程持 `rawCfgMu` 这把全局锁**（`Lock()` 后 `defer Unlock()`），锁内顺序：provision 新配置 → 逐个 `app.Start()`（起新 server / TLS / PKI…）→ `unsyncedStop()` 停旧 app。**这一整套里任意一步卡住，锁就一直不放**，于是 `POST /load` 不返回 → `systemctl reload` 挂死，`GET /config/` 也拿不到锁跟着挂，而 `GET /debug/pprof/...` 不碰锁照样秒回——这组「`/config/` 挂 + `pprof` 秒回」就是「reload 被锁死」的确诊指纹（锁机制已从源码坐实：`caddy.go` 的 `changeConfig` 全程持 `rawCfgMu`）。

至于卡在锁内哪一步，源码排除了两个想当然的嫌疑：reload 时 http app 的 `Stop()` 只等「旧 server 停止接受新连接」就返回、**不等**长连接排空（排空丢给后台 goroutine 跑）；TLS app 的 `Start()` 走 `ManageAsync`、**不同步**等签证。所以「旧连接没排完」和「新域名签不出」**都不会直接**卡住 reload 主链路——真正卡点得靠现场 pprof dump 定位（certmagic 内部锁、PKI、`finishSettingUp` 等仍有嫌疑，**暂未逐一坐实，待现场验证**）。

#### 解法（先救活 → 再防复发）

1. **救一个已卡死的 reload：直接 `sudo systemctl restart caddy`**。restart 是「停旧起新」、有界（本机实测 1~5s，其间旧配置在服务、切换瞬间断一下连接），能解锁并把新配置真正加载上。**卡住时的第一手就是它**。

2. **别让终端 / systemd 无限等：给 reload 套 `timeout`**。
   - 手动：`sudo timeout 60 caddy reload --config /etc/caddy/Caddyfile --force` —— 60s 没完就返回非零，你拿回控制权。
   - systemd 层（让 `systemctl reload` 自身有界、不再无限卡在 `reloading`）：
     ```bash
     sudo systemctl edit caddy
     ```
     ```ini
     [Service]
     TimeoutStartSec=60
     ExecReload=
     ExecReload=/usr/bin/timeout 60 /usr/bin/caddy reload --config /etc/caddy/Caddyfile --force
     ```
     （`ExecReload=` 先清空再重设，是 systemd 覆盖既有指令的固定写法；改完 `sudo systemctl daemon-reload`。）
   - **注意 `timeout` 只截断「客户端 / systemd 这一侧」**：`caddy reload` 客户端被 kill，**服务端那次 `POST /load` 可能仍在锁里跑**——锁没放，下一次 reload 照样卡。所以 timeout 是「止血、给你信号」，**真正清干净还得靠第 1 条 restart**。

3. **掐掉最常见的诱因：ACME / on-demand 签证风暴**。历史卡死窗口里高频出现「给某域名反复签证失败」（`challenge failed` 打转）和「给垃圾子域名狂签」（`o69iay0p...` / `notexists...` 撞 Let's Encrypt `too many subdomain labels` 退避，最长 30 天重试）。签证虽走后台、不直接卡 reload 主链路，但会持续占 certmagic 的锁 / obtain 池，与卡死高度同时段出现。两条收敛：
   - **域名 DNS 没解析到本机前，别把它写进 Caddyfile**——托管证书签不出会一直在后台重试打转。
   - **收严 `on_demand_tls` 的 `ask` 端点**（见「`on_demand_tls`：陌生 SNI 的按需签证」节），别让任意子域名都能触发签证。

4. **现场确诊卡在哪**：趁还卡着时，用「通用诊断入口」的 `/config/` + pprof 两条命令抓当次卡点栈，才能把上面第 3 条那类嫌疑从「嫌疑」钉成「这次就是它」。

5. **大改 / 加新域名，宁可 `restart` 不 `reload`**。reload 要在一把全局锁里同时收尾旧配置、起新配置，配置越大越容易卡；换二进制、改 systemd 环境变量本来就必须 restart。有界的 restart 比「可能挂死的 reload」省心。

### `reload` 退出非零 ≠ 失败

**`systemctl reload caddy` 退出非零 ≠ reload 失败**：caddy 关旧 admin endpoint 时常有 10s timeout 让 systemctl 退出 1，但配置其实已加载。脚本里用 exit code 触发回滚会误把好配置覆盖回旧的；要判断真失败请看 `curl` 实测或 `journalctl -u caddy` 有无 `loading new config` 之类成功标志。

> 与上一节区分：这里是**秒退 + 退出码非零、配置已生效**；上一节是**永久不返回、配置没加载上**。别把前者误判成 reload 失败去回滚。

### `caddy validate` 读不到 systemd 注入的环境变量

**`caddy validate` 读不到 systemd 注入的环境变量**。无论是 `sudo` shell 下的 env placeholder，还是 `systemctl edit caddy` 里的 `Environment=...`，`validate` 都是命令行直接启动的，不会经过 systemd。

如果 Caddyfile 里用了 `{env.XYZ}`，先在当前 shell 里手动 `export`（或命令前置）一遍即可；值随便填，`validate` 只检查占位符能否解析。例如带 caddy-security 的配置：

```bash
GITHUB_CLIENT_ID=x GITHUB_CLIENT_SECRET=x \
JWT_SHARED_KEY=0000000000000000000000000000000000000000000000000000000000000000 \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

### 共享端口 `bind` 劫持白屏

**现象**：`:443` 上挂着的一批域名**集体白屏**——浏览器拿到 **`200` 但 body 为空**；偏偏在服务器本机 `curl` 自查往往正常，极隐蔽。

**根因**：给共享端口（`:443`）上**某一个**站点加了 `bind 1.2.3.4`。按 bind 的分组机制（完整机制见「`bind` 与 listener 分组」节），它会独占 `1.2.3.4:443`、按「具体 IP 优先于通配」截走**所有**经 `1.2.3.4` 进来的 `:443` 流量；可这个被拆出去的独立 server 路由表里只有它自己一个域名，对别的域名一律不匹配 → Caddy 兜底回 **200 + 空 body** → 白屏。本机 `curl` 常走回环 / 别的地址、不命中那个 bind，所以自查正常、更难发现。

**诊断**：

```bash
# 受影响域名是不是 200 + 0 字节
curl -s -o /dev/null -w '%{http_code} %{size_download}B\n' https://受影响域名/
```

再翻 Caddyfile / `curl -s localhost:2019/config/`，找**共享 `:443` 的站点里有没有谁写了 `bind`**。

**修复**：

- 把那个站点的 `bind` **删掉**——公网域名本就该在所有网卡监听、合并进通配 `:443` server 靠 SNI 分流。
- 若确实要给所有站点统一限定网卡，改用**全局** `default_bind <IP>...`（写在 global options，对所有站点生效、listen 地址仍一致、不拆 server）；**别**在单个 `:443` 站点上局部 bind。

### `address already in use`

**现象**：`reload` / `restart` 失败，报 `address already in use`。

**根因**：该端口已被别的进程占用，最常见是 **Docker 把某服务绑在了 `127.0.0.1:port`**，而 Caddy 站点默认监听通配 `0.0.0.0:port`（含 `127.0.0.1`）冲突。

**修复**：给该站点显式 `bind` 外网 IP（而不是默认通配），避开被占的回环地址：

```caddyfile
example.com {
    bind <eth0 ip> <tun0 ip>
    reverse_proxy 127.0.0.1:8000
}
```

这属于「独占端口用 `bind`」的正当用法（为什么独占端口 bind 安全、共享端口 bind 危险，见「`bind` 与 listener 分组」节）。

### WebSocket / 长连接反代的连接泄漏与 `stream_timeout`

`reverse_proxy` 代理 WebSocket 时会 **hijack** 掉连接、退化成一条双向 `io.Copy` 的裸管道（后端↔客户端各一个 copier goroutine）。这条管道**默认不设任何读写超时**（`stream_timeout` 默认无）。当客户端**不告而别**——手机休眠 / 标签切后台 / NAT 空闲驱逐 / **上游代理节点被墙**，没有 FIN/RST——Caddy 察觉不到，copier 永不返回，连接与 goroutine **泄漏**。

**两种泄漏、命运不同（实测对照）**：

- **空闲流**（copier 卡在 `waitRead` 等后端）：客户端的死会被 TCP keepalive / 重连时的 RST 探到，**能自愈**（观测到数小时内清掉）。
- **后端在推的流**（copier 卡在 `waitWrite` 写死客户端）：mkdocs livereload 心跳 / 终端输出这类**服务端主动推**的连接，写入先塞满 TCP 发送缓冲，之后对着黑洞死等重传——**能拖 ~40h**（`tcp_retries2` 默认的满重传窗口）。这才是真正危险、会累积的那种。

**危害边界**：goroutine 泄漏本身**不影响** Caddy 正常服务（Go 扛几万并发，几十条僵尸只占点内存），且**重启即清**。真正麻烦的是**大批同时半死**——典型是作为上游出口的代理节点被墙，一瞬切断所有经它回程的客户端——会攒出成百上千条。（曾疑似与某次 `caddy reload` 卡死相关，但源码看 reload 时 `Stop()` 并不等长连接排空、不会因此挂住，此因果**未坐实**；reload 卡死另见本节「`systemctl reload caddy` 卡住 / 永久挂起」。）

**诊断**（admin API，本地无需 sudo；通用命令见「通用诊断入口」）：

```bash
# DOWN 复制器（后端→客户端）数量；UP 用 streaming.go:648
curl -s http://127.0.0.1:2019/debug/pprof/goroutine?debug=1 | grep -c streaming.go:642
# 卡死者完整栈：找 copyFromBackend(streaming.go:642) + crypto/tls.(*Conn).Write → waitWrite
curl -s "http://127.0.0.1:2019/debug/pprof/goroutine?debug=2" | grep -A25 'streaming.go:642'
```

对照实验坐实机制：开一个走 WS 的标签→静默掐断其路径（防火墙 DROP / 飞行模式，**不能**干净关，那会发 FIN/RST）→ 对应 copier 赖着不走；而**干净关闭**标签→copier 秒回收。同一连接只差"死法"，静默死=漏、干净关=收。

**修复：给带 WS 的 `reverse_proxy` 加 `stream_timeout`**（到点强制关闭流，卡死 copier 被迫返回 → 泄漏有上界）。`stream_timeout` **只对流式 / hijack 连接生效**，普通 HTTP 请求不受影响，所以加在共享 snippet 上对非 WS 站点也无害。

snippet 形态（一改覆盖所有用它的 vhost）：

```caddyfile
(app_org) {
    authorize with app_org
    reverse_proxy {args[0]} {
        stream_timeout 24h
    }
    import error_pages
}
```

裸 `reverse_proxy` 形态（zellij / code-server / paseo 逐个加）：

```caddyfile
reverse_proxy http://127.0.0.1:8082 {
    header_up Cookie "******"
    stream_timeout 24h
}
```

**取舍**：

- `stream_timeout` **按龄一刀切**，到点连**活着的**长连接也砍——但 zellij / code-server 客户端会自动重连、服务端会话还在，代价可接受。文档类（livereload）给 `3h` 都够；终端类给 `24h` 更友好；图省事全 `24h`。
- **全局 `grace_period` 给「旧 server 后台排空」设硬上界**（reload / 退出时旧 server 等活跃连接关闭的最长时长）。不设时默认 `0` = **永久等**（源码 `modules/caddyhttp/app.go` 就是这么写的，还专门警告「频繁 reload + 长 / 无限 grace period 会耗尽资源」）——于是每次 reload 都可能攒下一批永不退出的排空 goroutine。设个有界值即可：
  ```caddyfile
  {
      servers {
          grace_period 10s
      }
  }
  ```
  它和 `stream_timeout` 层次不同、互补：`grace_period` 管「reload 时旧 server 整体排空的截止」，`stream_timeout` 管「单条流自身的最大存活」。平时靠 `stream_timeout` 防单条泄漏，reload 时靠 `grace_period` 兜底不让旧 server 赖着。**注意 `grace_period` 治泄漏累积，不等于让已卡死的 reload 立刻返回**（详见本节「`systemctl reload caddy` 卡住 / 永久挂起」）。
- 更外科手术的补充（可选、**系统级**）：调小 `net.ipv4.tcp_retries2`（如 `8`，≈100s），让"对端不 ACK 的写"在内核层几分钟就失败——**只杀真死连接、不动活连接**，精准打 `waitWrite` 那种。代价：影响本机所有 TCP，非 Caddy 局部。
- ~~`stream_close_delay`~~ 治的是 reload 时避免重连风暴（延迟关流），**方向相反、不治泄漏**，别混用。

> 触发这次排查的真实事件：2026-06-25 作为上游出口的 vless+ws 节点被墙，大批经它回程的 WS 客户端同时半死。

### 跨版本 cookie 名陷阱：登录后无限跳 / `ERR_TOO_MANY_REDIRECTS`

> 前置概念（cookie 的 `Domain` 作用域、域名模式必写 / IP 模式必不写 `cookie domain`）见 caddy-security 章节「先理解 cookie 作用域」。本节讲的是**多机 / 跨版本**下 cookie **名字**对不上导致的登录死循环。

`caddy-security` 在版本演进中**改过 access token 的默认 cookie 名**：旧版（实测 `v1.1.49`）默认 `access_token`；新版（`v1.1.61`+）默认 `AUTHP_ACCESS_TOKEN`（= 前缀 `AUTHP` + `ACCESS_TOKEN`，源码 `go-authcrunch/pkg/authn/cookie/cookie_config.go`：`DefaultCookieNamePrefix="AUTHP"` + `DefaultAccessTokenCookieName="ACCESS_TOKEN"`）。

**坑**：当**签发方**（`authentication portal`）和**读取方**（`authorization policy` / gatekeeper）跑在**不同版本**时——典型是跨主机部署（一台只跑 portal，另一台只跑 `authorize`）——两边默认 cookie 名对不上：portal 发 `access_token`，gatekeeper 默认找 `AUTHP_ACCESS_TOKEN`，**永远找不到 token → 登录后无限 302 回 login → 浏览器 `ERR_TOO_MANY_REDIRECTS`**。同一台机（portal+gatekeeper 同版本）天然自洽、不触发，所以极隐蔽，容易误判成网络 / JWT key 问题。

**诊断**（Caddy admin API，默认 `http://localhost:2019/config/`）：

- **读取方实际找哪个 cookie**：reload 时全局开 `debug`，捞 `journalctl -u caddy` 里 `msg="Configured gatekeeper"` 那条的 `auth_cookies` 字段（= gatekeeper 真正会读的 cookie 名集合）。
- **浏览器实际带哪个 cookie**：全局加 `servers { log_credentials }` 临时取消 Cookie 脱敏，再看请求 `Cookie` 头里 JWT（`eyJ...`）挂在哪个名下。**抓完务必撤掉**，别把 JWT 长期写进 journal。
- **portal 签发名**：`curl -s localhost:2019/config/` 看 `authentication_portals[].cookie_config.access_token_cookie_name`（新版 resolve 成 `AUTHP_ACCESS_TOKEN`；旧版为 `null` → 回退到 `crypto_key_configs[].token_name`，即 `access_token`）。

**两种修法**：

1. **各机版本对齐**（根治）：所有共用同一 portal 的机器升到同一 `caddy-security` 版本，默认名自然统一。**注意连锁后果**：升级会改变签发的 cookie 名 → **所有现存会话失效、全员重登**；且**所有 gatekeeper 要同步**（要么都用新默认 `AUTHP_ACCESS_TOKEN` 删掉显式 pin，要么都改成新名）——否则刚对齐又会对不上。
2. **显式 pin cookie 名**（局部、抗版本漂移）：在 authorization policy 里写 `set access_token cookie name <portal 实际签发的名>`。要稳就多名全收：`set access_token cookie name AUTHP_ACCESS_TOKEN access_token jwt_access_token`（新旧默认 + query 默认一锅端）。**注意**：省略该指令 ≠ 安全默认——新版 gatekeeper 省略时默认只找 `AUTHP_ACCESS_TOKEN`，跨版本读旧 portal 的 `access_token` 必炸。

## 实用备忘

- 基础站点优先顺序：**域名模式 > IP 模式**
- 功能叠加顺序：**先反代，再错误页，再认证**
- `reload` 只适合改 Caddyfile；**换二进制或改环境变量用 `restart`**
- **`reload` 永久卡住 / 挂起**（终端不返回、服务仍在）：第一手 `systemctl restart caddy` 解卡；治本 = `timeout` 包住 reload + 收严 on-demand 签证 + `grace_period`/`stream_timeout` 封顶泄漏，详见「`systemctl reload caddy` 卡住 / 永久挂起」节
- `tls internal` 场景下，**客户端只导 root CA**
- **共享端口（`:443`）上的域名站点别写 `bind`**：会独占该 `IP:443`、劫持整段端口流量 → 其它域名 200 空 body 白屏；偏偏本机回环自查正常，极隐蔽。只有独占端口的站点才可以 bind。
- `caddy-security`：
  - 域名模式：**必须写** `cookie domain`
  - IP 模式：**必须不写** `cookie domain`
  - `JWT_SHARED_KEY`：**必须固定**
  - GitHub callback URL = `https://<portal host>/<handle 前缀>/oauth2/<provider realm>/authorization-code-callback`；第 ④ 段是 **realm 不是 name**
  - 改 provider `realm` 三处同步：provider 块 / GitHub callback URL / 该 portal 的 `transform user match realm`
  - IP 与域名各一套独立 provider+portal+OAuth App（cookie 互不可达、callback host 写死）
  - token source 默认含 **query**：`?access_token=<JWT>` 默认能过鉴权（`sources.go:39-53`）；纯浏览器站点用 `set token sources cookie` 关掉
  - **无 sliding refresh**：token 到期靠 GitHub session 无感重签；要长免登期就把 `crypto default token lifetime` + `cookie lifetime` 一起调长（撤销窗口随之变长）
  - 默认值（v1.1.61 源码核对）：token lifetime **900s**、cookie **无 Max-Age（session）**、access-token cookie 名 **`AUTHP_ACCESS_TOKEN`**、`allow roles` 是 **OR**
  - 删 `inject headers with claims` → 下游收不到 `X-Token-*`；删 `set token sources`/`set user identity`/`validate bearer header` 是回到默认（不影响 whoami，whoami 直接读 JWT claims）
- docs-share（S3 + viewer rewrite）：
  - 后端 RustFS S3，鉴权 SigV4 presigned，**自带过期 ≤ 7d**
  - viewer 壳子是 Caddy 本地 file_server（`/srv/viewer/_viewer.html`），**不在桶里**
  - 浏览器和脚本靠 `Accept` 分流：`text/html` → viewer rewrite；其他 → 透传 RustFS
  - viewer JS 必须用 `pathname + search` 把 SigV4 query 透传给反向 fetch
