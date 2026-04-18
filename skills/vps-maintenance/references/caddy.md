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

### Caddyfile 配置：两种模式

#### 域名模式（推荐）

```caddyfile
example.com {
    reverse_proxy localhost:8000
}
```

ACME 自动签 Let's Encrypt 证书，**80 端口必须从公网可达**（HTTP-01 challenge）。多域名平铺，每个 site block 独立。

#### IP 模式（无域名 / 未备案）

```caddyfile
{
    auto_https disable_redirects
    default_sni <主 IP>
}

https://<主 IP>:8000 {
    tls internal
    reverse_proxy localhost:8000
}
```

注意事项：

1. **`auto_https disable_redirects`**：Caddy 默认会为每个 https 站点在 80 端口起 HTTP→HTTPS 重定向，多端口配置下产生"不知该跳哪个端口"的歧义；`tls internal` 也不需要 80 端口做 ACME 验证，关掉省事。
2. **`default_sni`**：客户端通过 IP 直连时 SNI 为空（RFC 6066 规定 SNI 只能是 hostname），Caddy 找不到匹配 connection policy 会回 TLS alert 80，default_sni 是兜底。([caddyserver/caddy#6344](https://github.com/caddyserver/caddy/issues/6344))
3. **非标端口建议写 `https://` 前缀**：技术上不必需（带 hostname/IP 的 `host:port` 会自动开 HTTPS），但显式写 https 提高可读性、避免误读。
4. **`tls internal`** + 客户端装 Caddy local root CA，见下文。

### 安装 Caddy local root CA（tls internal 场景）

使用 Caddy 时，本机 PKI 三层证书都在 `/var/lib/caddy/.local/share/caddy/` 下，默认 lifetime（[官方文档](https://caddyserver.com/docs/caddyfile/directives/tls) / [#3427](https://github.com/caddyserver/caddy/issues/3427)）：

| 层级 | lifetime | 文件 |
|---|---|---|
| Root | 10 年 | `pki/authorities/local/root.crt` ← **客户端装这个** |
| Intermediate | 7 天 | `pki/authorities/local/intermediate.crt` |
| Leaf | 12 小时 | `certificates/local/<host>/<host>.crt` |

intermediate 和 leaf 都自动续签覆盖，装它们意味着持续重导。装 root 后整条链（含未来续签的 intermediate、新增 host 的叶子）一次性都信任；TLS 握手时 Caddy 会把 intermediate 一起发给客户端，无需单独导入。

服务端从上表 root 路径导出到家目录：

```bash
sudo cp /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt ~/caddy-root.crt
sudo chown $USER ~/caddy-root.crt
```

`scp` 拉回客户端，按客户端 OS 导入到系统/浏览器证书库。

> **校验是不是 root**：`openssl x509 -in caddy-root.crt -noout -subject -issuer`，**Subject == Issuer** 就是自签 root。

### Caddyfile 修改流程

```bash
sudo nano /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

> 改 Caddyfile 用 `reload`；换二进制或环境变量用 `restart`。**失败的 reload 会让 systemd 卡在 reloading，下一次 reload 也跟着 fail**——遇到这种情况直接 `restart`。

### error_pages snippet 用法

`error-pages` 服务跑在 `localhost:4040`（安装见 [安装 error-pages](#安装-error-pages)），在 Caddyfile 里用 snippet 集中定义，再 `import` 到需要的站点：

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

`handle_errors` 是 Caddy 内置的错误捕获指令，`{err.status_code}` 是 placeholder，`error-pages` 按路径返回对应错误页。snippet 名外面套小括号 `(name)`，引用时 `import name`。

### 常见坑

- **一个服务一个端口** 比合并到 443 子路径更省心，能避开 caddy-security 的 `/assets/*` 跟后端 `/assets/*` 类静态资源路径的冲突。
- **端口被本机进程占用**（典型场景：Docker 在 `127.0.0.1:port`）给该 site 显式 `bind <eth0 ip> <tun0 ip>`，而不是默认 `0.0.0.0`，否则 Caddy 整个 reload 因 `address already in use` 失败。
- **`caddy validate` 读不到 systemd 注入的环境变量**：无论是 sudo shell 下的 env placeholder，还是 `systemctl edit caddy` 设置的 `Environment=...`，validate 命令都是命令行直接启的不经过 systemd，这些变量都不可见。跑 validate 前在当前 shell 里手动 `export` 一遍即可（值随便填，validate 只检查能否解析占位符）。
- **自定义 Caddy 二进制下载**：`caddyserver.com/api/download` 下载到的内容如果不对（比如只有 22 字节的 `Contact: ...` 拒绝文本），是因为没带 User-Agent 被拒了，加一个 `-A "Mozilla/5.0"` 重试即可。
- **RHEL 系没有 `dpkg-divert`**：替换系统自带 caddy 时用 `alternatives` 管理多版本，具体用法查发行版文档。
- **公网端口记得在云平台安全组放行**。中国大陆 Aliyun ECS 的未备案封锁另见 [quality-check.md 的 Aliyun 未备案封锁实测](quality-check.md#aliyun-未备案封锁实测)。

### 安装 caddy-security 扩展

从 [Caddy Download Page](https://caddyserver.com/download) 下载含 caddy-security 扩展的可执行文件（勾选 `github.com/greenpau/caddy-security`），然后按[官方文档](https://caddyserver.com/docs/build#package-support-files-for-custom-builds-for-debianubunturaspbian)替换系统自带的 caddy：

```bash
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy
sudo mv ./caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo systemctl restart caddy
```

- `dpkg-divert`：将原始 `/usr/bin/caddy` 移至 `/usr/bin/caddy.default`，防止 APT 升级时覆盖自定义二进制。
- `update-alternatives`：通过优先级管理多版本，custom（50）优先于 default（10）。以后可用 `update-alternatives --config caddy` 切换版本。

官方完整示例：[authcrunch GitHub OAuth Caddyfile](https://github.com/authcrunch/authcrunch.github.io/blob/main/assets/conf/oauth/github/Caddyfile)。

#### Cookie scoping 机制（理解配置的前提）

caddy-security 用 cookie 在浏览器和 portal 之间携带 JWT。Cookie 作用域由 `Domain` 属性决定：

| `Domain` 设置 | 浏览器行为 |
|---|---|
| **不设** | host-only，只发回设它的精确 host，子域名拿不到 |
| `Domain=example.com` | 发回给 `example.com` 及所有子域名 |

**关键反直觉点：cookie 不区分端口**（RFC 6265 明确不把端口算进 scope）。`host:443` 设的 host-only cookie，浏览器**也会**发到 `host:8080`、`host:9220`。

由此 caddy-security 的 `cookie domain` 在两种模式下行为相反：

- **域名模式必写** `cookie domain example.com`：否则子域名收不到 cookie，登录后访问 `app.example.com` 拿不到 JWT，死循环。
- **IP 模式必须不写**：RFC 6265 不允许 `Domain=<IP>`。host-only + 忽略端口的特性刚好让同一 IP 的所有端口共享 cookie。

由此 **IP 访问的认证体系和域名访问的认证体系彼此独立**：cookie scope 互不相通（域名 cookie 进不到 IP host，反之亦然），且 GitHub OAuth App 的 callback URL 是固定的——所以每个体系各用一套独立的 GitHub OAuth App，不要试图跨复用。

#### Caddyfile 模板：域名模式

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

#### IP 模式差异片段

只列出和域名模式不一样的部分（global options 的 `auto_https disable_redirects` / `default_sni` / `tls internal` 见 [IP 模式](#ip-模式无域名--未备案)）：

```caddyfile
authentication portal myportal {
    ...
    # 不要写 cookie domain（RFC 6265 不允许 Domain=IP）
    trust login redirect uri domain regex ^<主 IP>(:[0-9]+)?$ path prefix /
    ...
}

authorization policy admin_policy {
    set auth url https://<主 IP>/login
    ...
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

#### 概念速查

- **`crypto default token lifetime` / `cookie lifetime`**：分别是 JWT exp 和浏览器 cookie Max-Age，**必须设成一样**。默认 token 是 900 秒（15 分钟），太短，登录后很快过期。
- **`crypto key sign-verify <key>`**：JWT 签名密钥。**不显式配置时插件每次启动生成临时新密钥，重启等于全员强制重登**；用 `{env.JWT_SHARED_KEY}` 绑定固定 env 才能跨重启保留 token。authorization policy 里用 `crypto key verify` 引用同一个 key 只验签。详见 [AuthCrunch auth-cookie 文档](https://docs.authcrunch.com/docs/authenticate/auth-cookie)。
- **`transform user` + `allow roles`**：前者给登录用户打角色（`authp/` 只是命名约定，字符串随便起），后者 `allow roles A B` 是 **OR**——任一角色满足即放行。
- **`trust login redirect uri`**：白名单"哪些 redirect_url 允许写入回跳 cookie"。**IP 模式关键坑**：Go 的 `url.Host` 把端口包含在内，匹配非标端口必须写 `(:[0-9]+)?` 让正则吃掉端口，否则登录后回不到原页面。不配置 = 全部静默丢弃。([caddy-security#455](https://github.com/greenpau/caddy-security/issues/455))

#### 配置 OAuth 环境变量

```bash
sudo systemctl edit caddy
```

添加以下内容：

```ini
[Service]
Environment="GITHUB_CLIENT_ID=你的ID"
Environment="GITHUB_CLIENT_SECRET=你的密钥"
Environment="JWT_SHARED_KEY=你的JWT密钥"
```

> `JWT_SHARED_KEY` 填一串足够长的随机字符串即可，为什么必须显式配置见前面概念速查。

然后重载并重启：

```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
# 验证变量是否加载成功
sudo systemctl show caddy --property=Environment
```

## 无额外认证的文档分享私链（WebDAV + Markdeep viewer）

**定位**：用一段长随机串当访问凭据（capability URL）的文档私链分享。**没有登录页、没有 OAuth、不接 caddy-security**——URL 本身即凭据，拿到链接的人能读，没拿到的一律 404。上传侧单独挂一个 basic_auth 保护，和读取侧共享同一份存储目录。

链接发给别人浏览器打开自动走 Markdeep viewer 渲染；脚本 `curl` 拿到的是 raw 原文；自己用 rclone / `curl -T` 上传。viewer 壳子在 [`../assets/md-viewer.html`](../assets/md-viewer.html)。

> 客户端上传命令、分享链接使用方式、Markdeep 写作惯例（引用 vs 脚注、GFM 兼容性、研报长文模板）见 `software` skill 的 `doc-share` reference，本节只覆盖服务端配置。

### 安装 caddy-webdav 扩展

系统自带的 caddy 二进制**不带** WebDAV handler，必须自行替换。从 [Caddy Download Page](https://caddyserver.com/download) 下载含 caddy-webdav 扩展的可执行文件（勾选 `github.com/mholt/caddy-webdav`；如果已经装过 caddy-security 又想把两个插件合进同一个二进制，下载时两个都勾）。然后按[官方文档](https://caddyserver.com/docs/build#package-support-files-for-custom-builds-for-debianubunturaspbian)替换系统自带的 caddy：

```bash
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy   # 首次替换才需要；已做过此步直接跳
sudo mv ./caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo systemctl restart caddy
```

- `dpkg-divert` + `update-alternatives` 语义同 caddy-security 扩展安装节，不重复解释。
- 验证：`caddy list-modules | grep webdav` 应输出 `http.handlers.webdav`；没输出说明二进制没带上插件，回去重下。

### 思路

- 上传：内置 `basic_auth`（v2.10+ 新名）+ `webdav` handler。**用 `webdav { prefix /dav }` 保留前缀**，不要 `handle_path` 剥掉——否则 PROPFIND/MOVE 返回的 href 不完整，rclone 等客户端会迷路。
- 下载：一段长随机串当 "secret path" 前缀（capability URL），配合 `uri strip_prefix` 让 `file_server` 从真实目录服务；这样上传和下载路径可以共用同一份存储，`rclone put /dav/foo.md` 写进来立刻在 `/<token>/foo.md` 可见。
- 浏览器 vs CLI 分流：matcher 叠加 `path *.md` + `header Accept *text/html*`。浏览器分支 `rewrite * /_viewer.html`（**不要附 `?src={uri}`**，见下面"rewrite 是内部重写"那条），viewer 里 `location.pathname` 就是原始 URL；viewer `fetch(location.pathname)` 默认 Accept 不含 text/html，天然回落到 raw 分支不会递归。
- 渲染：viewer 里 **Markdeep**（LaTeX 公式、`*******` 画 ASCII 图表、TOC、admonition 开箱即用）。结构完全仿照 Markdeep 自身的 `.md.html` 格式：viewer 先 fetch 原始 md 写入 `document.body.textContent`，再动态加载 Markdeep CDN——此时 `document.readyState === 'complete'`，Markdeep 立刻同步处理 body；处理完后 `s.onload` 里把导航条（面包屑 + 下载按钮）插回 `body` 首位。

### 踩过的坑

- **`rewrite` 是服务端内部重写，浏览器地址栏不变**。viewer 从 URL 拿 src 不能靠 `?src={uri}`，得用 `location.pathname`。
- **浏览器按 URL 缓存响应、不看 Accept**。首访 `Accept: text/html` 拿到 viewer.html 被缓存，viewer 里 fetch 同 URL 也吃缓存。三重修：Caddy 两个分支都发 `Vary: Accept`，viewer 分支加 `Cache-Control: no-cache`，fetch 加 `cache: 'no-store'`。
- **`path /<TOKEN>/*` 不匹配 bare token**（无尾斜杠），`/x` ≠ `/x/*`。加 `redir /<TOKEN> /<TOKEN>/ 301`。
- **`<base href>` 把 `#anchor` 解析成 `base-origin/#anchor`**：TOC 的锚点链接 `<a href="#section">` 在有 base 的情况下会导航到目录页而非当前文件内滚动。在 `document` 上用 capture 阶段监听 click，拦截 `getAttribute('href').charAt(0) === '#'` 的链接，改成 `location.hash = h`。其他相对/绝对链接经过 base 解析都正确，无需拦截。
- **tocStyle**：`"auto"` `"short"` `"medium"` `"long"` `"none"` 五个字面量，无官方文档，从 `markdeep.min.js` 源码 grep 得到。当前 viewer 用 `"auto"`（Markdeep 按文档长度自动决定）。
- **禁用标题自动序号**：Markdeep 默认用 CSS counter 给标题和 TOC 条目都加序号（1. 1.1 …），没有原生配置项关闭。viewer 里扩展了一个自定义选项 `noSectionNumbers`：为 `true` 时注入 CSS 同时隐藏正文标题的 `::before` counter 内容和 TOC 里的 `.tocNumber` span；改为 `false` 两处编号都恢复。
- **CDN 用 `casual-effects.com/markdeep/latest/markdeep.min.js`**：作者 Morgan McGuire 官方站。
- **微信 WebView 无法下载文件**：微信平台层面拦截所有文件下载。viewer 检测 `MicroMessenger` UA，点下载按钮改为弹出蒙层引导用户「在浏览器中打开」后再下载；其他浏览器正常 `download` 属性下载。
- 404 用 `error "..." 404` 而非 `respond`，才会触发 `handle_errors` 走 error-pages。

### 凭据与权限

- Token：`openssl rand -hex 16` 生成 32 位十六进制。
- basic_auth 密码：明文 `openssl rand -base64 18`；用 `caddy hash-password --plaintext '<pwd>'` 算 bcrypt 写进 Caddyfile（Caddyfile 里 `$` 是字面量，不用转义）。
- Caddy 以 `caddy` 用户跑，WebDAV PUT 需要对目标目录 `w+x`。`chown caddy:caddy /data/share` 最干净；如果还想自己 ssh 上去 `cp`，建共用组 + `chmod 2775`（SGID 让新文件继承组）。

### 撤销与过期

换 token 后 `systemctl reload caddy`——没有单条撤销/过期语义；要那种能力改用 sftpgo（自带 share 链接管理）或 `caddy-signed-urls` 插件（签名 + expires，但 README 自标 not production）。

