# Caddy：安装、基础反代、认证与文档私链分享

> 这份参考按“先把基础反代跑通，再叠加功能”的顺序组织：
>
> - 安装并验证 Caddy  
> - 选择基础站点模式：域名模式 / IP 模式  
> - 按需加错误页  
> - 需要 GitHub OAuth 时安装 `caddy-security`  
> - 需要无登录文档私链时安装 `caddy-webdav`
>
> 经验上，**先把最小反代跑通，再加认证或 WebDAV**，排错会轻松很多。

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
- **失败的 `reload` 可能让 systemd 卡在 `reloading`**，下一次 `reload` 也会跟着失败；遇到这种情况直接 `sudo systemctl restart caddy`。
- **`caddy validate` 读不到 systemd 注入的环境变量**。无论是 `sudo` shell 下的 env placeholder，还是 `systemctl edit caddy` 里的 `Environment=...`，`validate` 都是命令行直接启动的，不会经过 systemd。  
  如果 Caddyfile 里用了 `{env.XYZ}`，先在当前 shell 里手动 `export` 一遍即可；值随便填，`validate` 只检查占位符能否解析。

## 基础反代：先选站点模式

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
   Caddy 默认会为每个 HTTPS 站点在 `80` 端口起 HTTP→HTTPS 重定向。多端口配置下，HTTP 请求不一定知道该跳去哪个 HTTPS 端口；而 `tls internal` 也不需要 `80` 端口做 ACME 验证，所以直接关掉更省事。

- **`default_sni <主 IP>`**  
   客户端通过 IP 直连时，SNI 往往为空；按 RFC 6066，SNI 只能是 hostname，不能是 IP。Caddy 匹配不到 connection policy 时会回 TLS alert 80，`default_sni` 是兜底。参考：[caddyserver/caddy#6344](https://github.com/caddyserver/caddy/issues/6344)

- **非标端口建议显式写 `https://` 前缀**  
   技术上 `host:port` 也会自动启 HTTPS，但显式写出来更直观，不容易误读。

- **`tls internal` 只解决发证，不解决信任**  
   客户端仍然需要导入 Caddy 的 local root CA，见下一节。

> 如果你刻意让 **Caddy 只绑定主 IP**、后端只绑定 `127.0.0.1`，那么“外部端口”和“后端端口”写成同一个数字也可以共存；文档里分开写只是更不容易看错。

### HTTP→HTTPS 跳转（IP 模式的边界）

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

### 基础反代常见坑

- **一个服务一个端口** 往往比“全塞到 `443` 的不同子路径”更省心。  
  尤其用了 `caddy-security` 之后，像 `/assets/*` 这类静态资源路径容易和后端自己的 `/assets/*` 打架。

- **本机端口已经被其他进程占用**（常见：Docker 绑在 `127.0.0.1:port`）时，给该站点显式 `bind` 外网 IP，而不是默认 `0.0.0.0`。否则整个 `reload` 会因为 `address already in use` 失败。示例：

  ```caddyfile
  example.com {
      bind <eth0 ip> <tun0 ip>
      reverse_proxy 127.0.0.1:8000
  }
  ```

- **公网端口别忘了放行安全组/防火墙**。  
  中国大陆 Aliyun ECS 的未备案 SNI 封锁与“IP 直连 + `tls internal`”绕过方案另见 [icp-filing.md](icp-filing.md)。

## 安装带插件的 Caddy 二进制

APT 安装的系统自带 Caddy **不包含** `caddy-security`、`caddy-webdav` 这类第三方扩展。需要插件时，做法是：

- 去 [Caddy Download Page](https://caddyserver.com/download) 勾选所需插件；
- 下载**一个包含全部所需插件**的新二进制；
- 用它替换系统自带的 `/usr/bin/caddy`。

> 已经装过一个插件、后面还想加另一个插件时，不是再叠一层，而是**重新下载一个同时包含两者的新二进制**。
>
> **下载时优先取页面默认的最新 stable 版本**（caddy 本体和插件都取最新）。多台机共用同一套 `caddy-security` 时（尤其跨主机的 portal↔gatekeeper 分离部署），**各台的 caddy-security 版本要尽量一致**——否则会踩下文「caddy-security 跨版本 cookie 名陷阱」。

### 下载（不带版本参数 = 始终最新 stable）

```bash
curl -fsSL -A "Mozilla/5.0" -o caddy.new \
  "https://caddyserver.com/api/download?os=linux&arch=amd64&p=github.com/greenpau/caddy-security"
chmod +x caddy.new
./caddy.new version; ./caddy.new list-modules --versions | grep -i security   # 确认版本
```

- 多插件就追加多个 `&p=...`（如 `&p=github.com/mholt/caddy-webdav`），一次下一个**包含全部插件**的二进制。
- **没带 `-A "Mozilla/5.0"` User-Agent 会被拒**（返回 ~22 字节的 `Contact: ...` 文本，不是二进制）。
- 不带版本参数时该 API **默认给最新 stable**（caddy 本体 + 各插件都最新）。

> ⚠️ **自定义二进制不会自动更新**。`dpkg-divert` 之后 APT 只更 `caddy.default`，**`caddy.custom` 冻结在你上次下载的版本**——这就是版本会悄悄落后、多机出现版本 skew 的根源（见下文「跨版本 cookie 名陷阱」）。想升级**只能手动重新下载**；多机共用 portal 时要把各台一起升、保持版本一致。

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

升级 `caddy-security` **大版本**前务必看下文「跨版本 cookie 名陷阱」：默认 cookie 名变过，**升级会让所有现存会话失效（全员重登）**，且共用同一 portal 的各机要一起升、否则签发/读取的 cookie 名对不上会登录死循环。

## `caddy-security`：GitHub OAuth 认证

### 安装

从 [Caddy Download Page](https://caddyserver.com/download) 下载带 `github.com/greenpau/caddy-security` 的二进制，然后按上一节的方法替换系统自带 Caddy。

官方完整示例可参考：[authcrunch GitHub OAuth Caddyfile](https://github.com/authcrunch/authcrunch.github.io/blob/main/assets/conf/oauth/github/Caddyfile)

### ⚠️ 跨版本 cookie 名陷阱（多机共用 portal 必看）

`caddy-security` 在版本演进中**改过 access token 的默认 cookie 名**：旧版（实测 `v1.1.49`）默认 `access_token`；新版（`v1.1.61`+）默认 `AUTHP_ACCESS_TOKEN`（= 前缀 `AUTHP` + `ACCESS_TOKEN`，源码 `go-authcrunch/pkg/authn/cookie/cookie_config.go`：`DefaultCookieNamePrefix="AUTHP"` + `DefaultAccessTokenCookieName="ACCESS_TOKEN"`）。

**坑**：当**签发方**（`authentication portal`）和**读取方**（`authorization policy` / gatekeeper）跑在**不同版本**时——典型是跨主机部署（一台只跑 portal，另一台只跑 `authorize`）——两边默认 cookie 名对不上：portal 发 `access_token`，gatekeeper 默认找 `AUTHP_ACCESS_TOKEN`，**永远找不到 token → 登录后无限 302 回 login → 浏览器 `ERR_TOO_MANY_REDIRECTS`**。同一台机（portal+gatekeeper 同版本）天然自洽、不触发，所以极隐蔽，容易误判成网络 / JWT key 问题。

**诊断**（Caddy admin API，默认 `http://localhost:2019/config/`）：

- **读取方实际找哪个 cookie**：reload 时全局开 `debug`，捞 `journalctl -u caddy` 里 `msg="Configured gatekeeper"` 那条的 `auth_cookies` 字段（= gatekeeper 真正会读的 cookie 名集合）。
- **浏览器实际带哪个 cookie**：全局加 `servers { log_credentials }` 临时取消 Cookie 脱敏，再看请求 `Cookie` 头里 JWT（`eyJ...`）挂在哪个名下。**抓完务必撤掉**，别把 JWT 长期写进 journal。
- **portal 签发名**：`curl -s localhost:2019/config/` 看 `authentication_portals[].cookie_config.access_token_cookie_name`（新版 resolve 成 `AUTHP_ACCESS_TOKEN`；旧版为 `null` → 回退到 `crypto_key_configs[].token_name`，即 `access_token`）。

**两种修法**：

1. **各机版本对齐**（根治）：所有共用同一 portal 的机器升到同一 `caddy-security` 版本，默认名自然统一。**注意连锁后果**：升级会改变签发的 cookie 名 → **所有现存会话失效、全员重登**；且**所有 gatekeeper 要同步**（要么都用新默认 `AUTHP_ACCESS_TOKEN` 删掉显式 pin，要么都改成新名）——否则刚对齐又会对不上。
2. **显式 pin cookie 名**（局部、抗版本漂移）：在 authorization policy 里写 `set access_token cookie name <portal 实际签发的名>`。要稳就多名全收：`set access_token cookie name AUTHP_ACCESS_TOKEN access_token jwt_access_token`（新旧默认 + query 默认一锅端）。**注意**：省略该指令 ≠ 安全默认——新版 gatekeeper 省略时默认只找 `AUTHP_ACCESS_TOKEN`，跨版本读旧 portal 的 `access_token` 必炸。

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
  显式指定 HTTP handler 的执行顺序。最常见的是：

  ```caddyfile
  order authenticate before respond
  order authorize before basicauth
  ```

- **`crypto default token lifetime` / `cookie lifetime`**  
  分别是 JWT 的 `exp` 和浏览器 cookie 的 `Max-Age`。**两者要设成一样**。默认 token 只有 900 秒（15 分钟），通常太短。

- **`crypto key sign-verify <key>`**  
  JWT 签名密钥。**不显式配置时，插件每次启动都会生成临时新密钥**，重启等于全员强制重登。  
  建议用 `{env.JWT_SHARED_KEY}` 固定下来；`authorization policy` 里用 `crypto key verify` 指向同一个 key 只做验签。  
  参考：[AuthCrunch auth-cookie 文档](https://docs.authcrunch.com/docs/authenticate/auth-cookie)

- **`transform user` + `allow roles`**  
  `transform user` 给登录用户打角色；`allow roles A B` 是 **OR**，任一角色匹配就放行。  
  `authp/admin` 这类名字只是约定，不是保留字，字符串本身可以自定。

- **`trust login redirect uri`**  
  白名单“哪些 `redirect_url` 允许写入回跳 cookie”。  
  不配置会被**静默丢弃**。  
  **IP 模式尤其要注意端口**：Go 的 `url.Host` 会把端口也算进去，匹配非标端口时正则必须显式吃掉端口。  
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
https://47.102.36.175/auth/oauth2/github
```

则 GitHub 可接受同 host/port 下的：

```text
https://47.102.36.175/auth/oauth2/github
https://47.102.36.175/auth/oauth2/github/authorization-code-callback
```

但不会把不同 host 或不同 port 视为同一个 callback。

在 caddy-security 里，`redirect_url` 和 GitHub 的 `redirect_uri` 是两件事：

- `redirect_url`：Caddy 登录成功后送用户回到的原始业务 URL，由 `trust login redirect uri` 约束。
- `redirect_uri`：Caddy 发给 GitHub 的 OAuth callback URL，GitHub 授权后把 `code` 和 `state` 回传到这里。

如果 portal 挂在 `/auth/*`，GitHub provider 的实际 callback endpoint 是：

```text
/auth/oauth2/github/authorization-code-callback
```

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

服务端部署完成后，把受限 CI key 交给两个位置：forgejo 仓库 secret（runner 跑 rclone sync）和操作者本机 mc alias（生成 presigned URL）。密钥体系、alias 组织、presigned 生成方式的完整说明见 `software` skill 的 [`references/docs-share.md`](../../software/references/docs-share.md)。

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

- **不要把 `?raw` 或 `?download` 这种 copyparty / file_server 习惯的 query 拼到 fetch URL**
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

## 实用备忘

- 基础站点优先顺序：**域名模式 > IP 模式**
- 功能叠加顺序：**先反代，再错误页，再认证 / WebDAV**
- `reload` 只适合改 Caddyfile；**换二进制或改环境变量用 `restart`**
- `tls internal` 场景下，**客户端只导 root CA**
- `caddy-security`：
  - 域名模式：**必须写** `cookie domain`
  - IP 模式：**必须不写** `cookie domain`
  - `JWT_SHARED_KEY`：**必须固定**
- docs-share（S3 + viewer rewrite）：
  - 后端 RustFS S3，鉴权 SigV4 presigned，**自带过期 ≤ 7d**
  - viewer 壳子是 Caddy 本地 file_server（`/srv/viewer/_viewer.html`），**不在桶里**
  - 浏览器和脚本靠 `Accept` 分流：`text/html` → viewer rewrite；其他 → 透传 RustFS
  - viewer JS 必须用 `pathname + search` 把 SigV4 query 透传给反向 fetch
