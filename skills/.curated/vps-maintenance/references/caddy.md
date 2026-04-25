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
| 需要“拿到链接即可读”的文档私链 | `caddy-webdav` + Markdeep viewer | URL 本身作为凭据；上传口单独做 `basic_auth` |

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
  中国大陆 Aliyun ECS 的未备案封锁另见 [`quality-check.md` 的 Aliyun 未备案封锁实测](quality-check.md#aliyun-未备案封锁实测)。

## 安装带插件的 Caddy 二进制

APT 安装的系统自带 Caddy **不包含** `caddy-security`、`caddy-webdav` 这类第三方扩展。需要插件时，做法是：

- 去 [Caddy Download Page](https://caddyserver.com/download) 勾选所需插件；
- 下载**一个包含全部所需插件**的新二进制；
- 用它替换系统自带的 `/usr/bin/caddy`。

> 已经装过一个插件、后面还想加另一个插件时，不是再叠一层，而是**重新下载一个同时包含两者的新二进制**。

替换步骤：

```bash
sudo dpkg-divert --divert /usr/bin/caddy.default --rename /usr/bin/caddy   # 首次替换才需要
sudo mv ./caddy /usr/bin/caddy.custom
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.default 10
sudo update-alternatives --install /usr/bin/caddy caddy /usr/bin/caddy.custom 50
sudo systemctl restart caddy
```

说明：

- `dpkg-divert`：把原始 `/usr/bin/caddy` 移到 `/usr/bin/caddy.default`，防止 APT 升级时覆盖自定义二进制。
- `update-alternatives`：管理多版本，`custom`（50）优先于 `default`（10）。
- 以后可用 `sudo update-alternatives --config caddy` 切换版本。
- **`dpkg-divert` 只做一次**。之后你只需要覆盖 `/usr/bin/caddy.custom` 并重启服务。

额外坑：

- 如果直接请求 `caddyserver.com/api/download` 拿到的内容不对（比如只有 22 字节的 `Contact: ...` 拒绝文本），通常是**没带 User-Agent 被拒**。加一个 `-A "Mozilla/5.0"` 重试即可。
- **RHEL 系通常没有 `dpkg-divert`**。替换系统自带 caddy 时用发行版自己的 `alternatives` 机制，具体写法查对应文档。

## `caddy-security`：GitHub OAuth 认证

### 安装

从 [Caddy Download Page](https://caddyserver.com/download) 下载带 `github.com/greenpau/caddy-security` 的二进制，然后按上一节的方法替换系统自带 Caddy。

官方完整示例可参考：[authcrunch GitHub OAuth Caddyfile](https://github.com/authcrunch/authcrunch.github.io/blob/main/assets/conf/oauth/github/Caddyfile)

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

## 无额外认证的文档私链（WebDAV + Markdeep viewer）

> 这一套的定位是：**用 capability URL 做只读分享**。  
> 没有登录页、没有 OAuth、不接 `caddy-security`。URL 本身就是凭据：拿到链接的人能读，没拿到的一律 `404`。
>
> 上传口单独挂一个 `basic_auth` 保护，和读取口共享同一份存储目录。
>
> 浏览器打开链接时自动进 Markdeep viewer 渲染；脚本 `curl` 拿到的是 raw 原文；自己用 `rclone` / `curl -T` 上传。
>
> viewer 壳子在 [`../assets/md-viewer.html`](../assets/md-viewer.html)。  
> 客户端上传命令、分享链接用法、Markdeep 写作惯例见 `software` skill 的 `doc-share` reference（`references/doc-share.md`）；本节只覆盖服务端配置。

### 安装 `caddy-webdav`

从 [Caddy Download Page](https://caddyserver.com/download) 下载带 `github.com/mholt/caddy-webdav` 的二进制；如果已经装过 `caddy-security`，要重新下载一个**同时勾选两个插件**的二进制，然后按上面的“带插件二进制”流程替换系统 Caddy。

验证：

```bash
caddy list-modules | grep webdav
```

正常应看到：

```text
http.handlers.webdav
```

### 先准备 viewer、token、密码和目录

安装 viewer 壳子：

```bash
sudo install -D -m 0644 ../assets/md-viewer.html /opt/md-viewer/_viewer.html
```

生成 token 与上传密码：

```bash
openssl rand -hex 16        # 32 位十六进制 token，做 capability URL
openssl rand -base64 18     # 上传口明文密码
```

把上传口明文密码转成 Caddyfile 里的 bcrypt：

```bash
caddy hash-password --plaintext '<pwd>'
```

目录权限建议：

```bash
sudo mkdir -p /data/share
sudo chown caddy:caddy /data/share
```

说明：

- `basic_auth` 是 Caddy v2.10+ 的新指令名；旧文档里可能还会看到 `basicauth`。
- Caddy 以 `caddy` 用户跑，WebDAV 的 `PUT/MOVE/DELETE` 需要目标目录可写。
- `chown caddy:caddy /data/share` 最干净。
- 如果还想自己 SSH 上去 `cp`，就建一个共用组，并配 `chmod 2775`，用 SGID 让新文件继承组。

### 最小可用模板

下面的模板假设：

- 上传口走 `/dav/*`
- 文档分享口走 `/<TOKEN>/*`
- viewer 壳子放在 `/opt/md-viewer/_viewer.html`
- 原始文件都存到 `/data/share`

```caddyfile
share.example.com {
    # 可选：如果前面定义过 error_pages snippet，再取消下面这行
    # import error_pages

    # bare token 不匹配 /<TOKEN>/*，补一个尾斜杠
    @token_root path /<TOKEN>
    redir @token_root /<TOKEN>/ 301

    # 上传：basic_auth + WebDAV，共享同一份存储目录
    handle /dav/* {
        basic_auth {
            <USER> <BCRYPT_HASH>
        }

        webdav {
            root /data/share
            prefix /dav
        }
    }

    # viewer 壳子本身
    handle /_viewer.html {
        root * /opt/md-viewer
        header Cache-Control "no-cache"
        header Vary "Accept"
        file_server
    }

    # 浏览器访问 .md：返回 viewer 壳子
    @md_browser {
        path_regexp md ^/<TOKEN>/.*\.md$
        header Accept *text/html*
    }
    handle @md_browser {
        header Cache-Control "no-cache"
        header Vary "Accept"
        rewrite * /_viewer.html
        root * /opt/md-viewer
        file_server
    }

    # 其他请求：返回 raw 文件
    # 包括：
    # - curl 直接请求
    # - viewer 内部 fetch(location.pathname)
    # - 非 .md 的附件下载
    handle /<TOKEN>/* {
        header Vary "Accept"
        root * /data/share
        uri strip_prefix /<TOKEN>
        file_server
    }

    # 其他路径一律 404，才能让 handle_errors 接管
    handle {
        error "Not Found" 404
    }
}
```

### 这套设计为什么这么配

- **上传口必须用 `webdav { prefix /dav }` 保留前缀**  
  不要用 `handle_path` 先把 `/dav` 剥掉；否则 `PROPFIND` / `MOVE` 返回的 `href` 不完整，`rclone` 这类客户端会迷路。

- **下载口用 secret path + `uri strip_prefix`**  
  这样上传和下载可以共享同一份目录。`rclone put /dav/foo.md` 写进去后，`/<TOKEN>/foo.md` 会立刻可见。

- **浏览器和 CLI 用 `Accept` 分流**  
  浏览器分支匹配 `.md` + `Accept: text/html`，内部 `rewrite` 到 `/_viewer.html`；  
  viewer 里再 `fetch(location.pathname)` 拉原始 Markdown。这个 fetch 默认 `Accept` 不含 `text/html`，自然会落到 raw 分支，不会递归套 viewer。

- **viewer 壳子采用 Markdeep 自己的工作方式**  
  先把原始 Markdown 塞进 `document.body.textContent`，再动态加载 Markdeep CDN；Markdeep 会同步处理整页内容。  
  处理结束后，再把导航条（面包屑、下载按钮等）插回 `body` 首位。

- **404 要用 `error`，不要用 `respond`**  
  只有这样才会触发前面的 `handle_errors`，由 `error-pages` 服务统一接管。

### 这套方案踩过的坑

- **`rewrite` 是服务端内部重写，浏览器地址栏不变**  
  viewer 不能靠 `?src={uri}` 取原文地址，要直接看 `location.pathname`。

- **浏览器按 URL 缓存响应，不看 `Accept`**  
  首访 `Accept: text/html` 可能把 viewer 壳子缓存下来，之后 viewer 内 `fetch()` 同 URL 时也吃缓存。  
  这里靠三件事一起修：
  - viewer 分支发 `Vary: Accept`
  - raw 分支也发 `Vary: Accept`
  - viewer 分支额外发 `Cache-Control: no-cache`，前端 fetch 再加 `cache: 'no-store'`

- **`path /<TOKEN>/*` 不匹配 bare token**  
  `/x` 不等于 `/x/*`，所以要单独加：
  ```caddyfile
  redir /<TOKEN> /<TOKEN>/ 301
  ```

- **`<base href>` 会把 `#anchor` 解析成 `base-origin/#anchor`**  
  TOC 里的 `<a href="#section">` 会跳目录页而不是当前文档内滚动。  
  解决方式是在 `document` 上用 capture 阶段监听 click，拦截 `href` 以 `#` 开头的链接，改成 `location.hash = h`。其他相对/绝对链接仍交给 `<base href>` 处理。

- **`tocStyle` 没官方文档**  
  可用字面量是 `"auto"`、`"short"`、`"medium"`、`"long"`、`"none"`，是从 `markdeep.min.js` 源码里 grep 出来的。当前 viewer 用 `"auto"`。

- **Markdeep 默认给标题和 TOC 都加自动序号**  
  官方没有直接关掉的配置项。viewer 里扩了一个自定义选项 `noSectionNumbers`：  
  设为 `true` 时，注入 CSS 同时隐藏正文标题的 `::before` counter 内容和 TOC 里的 `.tocNumber`；改回 `false` 两处编号都会恢复。

- **CDN 用 `casual-effects.com/markdeep/latest/markdeep.min.js`**  
  这是作者 Morgan McGuire 的官方站。

- **微信 WebView 无法下载文件**  
  这是微信平台层面的下载拦截。viewer 检测 `MicroMessenger` UA 后，下载按钮要改成弹出蒙层，引导用户“在浏览器中打开”；其他浏览器再正常用 `download` 属性。

### 撤销与过期

这一套**没有**单条撤销 / 过期语义。

做法只有：

- **换 token**，然后 `sudo systemctl reload caddy`
- 必要时移动或删除底层文件

如果你需要：

- 单链接撤销
- 链接过期时间
- 后台管理

那就不要用 capability URL 这套，改用：

- `sftpgo`：自带 share 链接管理
- `caddy-signed-urls`：签名 + `expires`，但 README 自标 `not production`

## 实用备忘

- 基础站点优先顺序：**域名模式 > IP 模式**
- 功能叠加顺序：**先反代，再错误页，再认证 / WebDAV**
- `reload` 只适合改 Caddyfile；**换二进制或改环境变量用 `restart`**
- `tls internal` 场景下，**客户端只导 root CA**
- `caddy-security`：
  - 域名模式：**必须写** `cookie domain`
  - IP 模式：**必须不写** `cookie domain`
  - `JWT_SHARED_KEY`：**必须固定**
- WebDAV 私链：
  - 上传口和分享口共用同一份目录
  - capability URL 本身就是凭据
  - 浏览器和脚本靠 `Accept` 分流