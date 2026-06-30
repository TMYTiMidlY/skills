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

