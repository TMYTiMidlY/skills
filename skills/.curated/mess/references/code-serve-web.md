# `code serve-web` 疑难杂症

> VS Code 把 workbench 跑成浏览器可访问服务（`code serve-web`）时踩到的坑。两条都不是编辑器本身的问题，而是这条"浏览器 → CLI launcher → server"链路上的：一条出在服务端按 `Accept-Language` 注入的语言包，一条出在 launcher 自己的 HTTP 库。
>
> 顺带：serve-web 下 "Install from VSIX" 报 `Extension not found` 时怎么绕过，见 [回退式 workaround](pdfjs-tohex.md#vsix-bypass)。

## <a id="nls-blank"></a>页面空白，Console 报 NLS MISSING

> 2026-04-08 | VS Code 1.115.0 | WSL2 Mirrored Networking | Chrome

### 症状

- `code serve-web` 通过 `10.144.18.10:8080` 正常，`127.0.0.1:8080` 页面空白
- Console：`Uncaught Error: !!! NLS MISSING: 17116 !!!`
- Ctrl+Shift+R / 无痕模式均无效

### 排查关键转折

服务端文件完整（17287 条 NLS 消息），curl 验证无误。缓存、Service Worker、CSP、模块加载顺序全部排除。

**突破点**：让用户在 Console 执行 `globalThis._VSCODE_NLS_MESSAGES?.length` → 返回 **17109**（不是 undefined 也不是 17287）。说明数组被加载了，但被替换成了更短的版本。

随后用 `curl -H "Accept-Language: zh-CN"` 请求页面 → 发现服务器根据 Accept-Language 注入了中文 NLS CDN URL → 下载验证中文 NLS 恰好 17109 条。

### 根因

1. Chrome `Accept-Language` 含 `zh-CN` → 服务器注入 `https://www.vscode-unpkg.net/.../zh-cn/nls.messages.js`
2. HTML 先加载英文 NLS（17287 条），再加载中文 NLS（17109 条）→ 中文直接覆盖 `globalThis._VSCODE_NLS_MESSAGES`
3. 中文语言包翻译不完整，缺少 index 17109-17286 → `d(17116, null)` 抛出异常 → 页面崩溃
4. 10.144.18.10 能用是因为该 IP 到 CDN 的请求失败，英文 NLS 保持不变 — “能用”不是因为它做对了什么，而是因为它恰好失败了

### 解决

- VS Code Web 里 `Ctrl+Shift+P` → "Configure Display Language" → `en`
- 或 Chrome 语言设置把 English 排到中文前面
- 或等上游中文语言包补全

## <a id="ws-upgrade-1119"></a>workbench 连不上 server，WebSocket 握手后即断

> 2026-05-09 | VS Code CLI 1.119.0 (commit `8b640eef`) vs 1.115.0 (commit `41dd792b`) | Caddy 2.11.2 + caddy-security + EasyTier | Microsoft VS Code Issue [#315448](https://github.com/microsoft/vscode/issues/315448)（与 [#315003](https://github.com/microsoft/vscode/issues/315003) 同期 1.119 regression）

### 症状

- 浏览器访问反代后的 `code serve-web`，workbench HTML 加载正常，立刻卡在 splash，最终弹：
  > An unexpected error occurred that requires a reload of this page.
  > The workbench failed to connect to the server (Error: Time limit reached)
- 浏览器每 ~10 秒开一条新 management WebSocket（每条都用全新 `reconnectionToken`），无限重试。
- Caddy access log 全部 `status: 101`，`duration: 2–80 ms`，`Sec-WebSocket-Accept` 计算正确。
- **跟反代无关**：本机直接 `curl -i -H 'Upgrade: websocket' http://127.0.0.1:8090/...` 同样复现 — launcher 先回 `HTTP/1.1 101 Switching Protocols` + 合法 `Sec-WebSocket-Accept`，紧接着关连接（`curl: (52) Empty reply from server`），trace 日志同步打 `(upgrade expected but low level API in use)`。这个“幻象 101”是为啥从 caddy log 看一切干净却仍卡死的根源。

### 排查关键转折

错的方向（按踩坑顺序）：

1. **「reconnectionToken 失效，硬刷新就好」** — `Restart=on-failure` 让 service 偶尔重启，旧 tab 拿不到新 token 也会 `Time limit reached`，但本案不是。硬刷新无效就该立刻翻盘。
2. **「Caddyfile 内存配置 ≠ 磁盘文件，下次 reload 就炸」** — 自己 `cat` 时用 `head -300` 截断了 308 行的文件，看不到末尾才加的 :8081 段；其实是一致的。**教训：用 `awk '/marker/,/^}$/'` 或 `wc -l` 确认覆盖完整，别盲目 `head`。**
3. **「Caddy + caddy-security 在 HTTP/2 上 ws upgrade 有 bug」** — 用户当年给 :8080 加了 `protocols h1` 是确实的旁证，但浏览器收到 caddy 不支持 H2 ws upgrade 时会自动降级 H1，新加的 :8081 也用了 H1，无关。
4. **「`header_up -Sec-WebSocket-Extensions` 干扰 ws 协商」** — 不是。
5. **「`--server-base-path /code` 是必需 workaround」** — 来自唯一对照组 1810 ✅ 的启动差异，但本机 WSL 加了 base-path 仍然卡 → 推翻自己。
6. **「`--default-folder` 太大触发扩展加载死循环」** — 1810 唯一不带的参数，但后续证据否决。

真正的突破点：

1. **改 caddy 加 `log code_8081`** 看 :8081 access log → 看到所有 ws upgrade 都是 101 OK + 立刻被关，证明 **caddy 干干净净**。
2. **决定性的“换上游”交叉实验**：把 :8081 反代上游临时从 `10.144.18.88:8080`（本机 WSL）换成 `10.144.18.10:8080`（已知 ✅ 的 1810），其它字节完全一致 → :8081 立刻通。锅 100% 在本机/Ali 的 vscode server，**完全不在 caddy/网络/auth**。
3. **拉 vscode launcher 的 trace 日志**（Ali 上的 service 已启用 `--log trace`，普通用户 `journalctl -u code-serve-web` 不需要 sudo 就能读）→ 看到反复打：
   ```
   debug server (upgrade expected but low level API in use) websocket upgrade failed
   ```
4. **GitHub 全文搜该字串** → 命中 [hyperium/hyper `src/error.rs`](https://github.com/hyperium/hyper/blob/v1.9.0/src/error.rs)，是 hyper crate 的固定错误信息。
5. **`strings` 对比 1.115 vs 1.119 二进制**（cargo 编译路径硬编码在二进制里）→ 看到 `hyper-0.14.32` → `hyper-1.9.0`。bisect 锁定。

### 根因

VS Code 1.119 的 CLI launcher（`/usr/share/code/bin/code-tunnel` 或 standalone `code` tarball，二者 sha256 完全一致）把 hyper 从 **0.14.32** 升级到了 **1.9.0**（同时升 h2、tokio，引入 hyper-util）。

hyper 1.x 把 `Connection: Upgrade` 处理拆成了独立 builder 方法：

- `http1::Builder::serve_connection(io, service)` — 收到 ws upgrade 直接报 `Kind::User(User::ManualUpgrade)`，描述串就是 `"upgrade expected but low level API in use"`
- `http1::Builder::serve_connection_with_upgrades(io, service)` — 才支持 ws upgrade

迁移过程中 launcher 中反代到内部 `server-main.js` unix socket 那段 server 代码漏改 → 浏览器→launcher 这一跳的 ws upgrade 全部被 hyper 自身拒掉。下游 `server-main.js` 自己跑 ws 是好的（直接 curl unix socket 验证 `HTTP/1.1 101 Switching Protocols`），坏的只有 launcher 的 hyper 反代路径。

`--server-base-path`、`--default-folder`、`Sec-WebSocket-Extensions`、HTTP/1.1 vs HTTP/2、浏览器、OS、内核 — 全是无关变量。**唯一起决定作用的就是 launcher 版本**。

### 解决

Pin CLI launcher 到 1.115.0：

```
https://update.code.visualstudio.com/1.115.0/cli-linux-x64/stable
```

- **standalone tarball / pixi 任务**：把 download URL 里的 `latest` 换成 `1.115.0`，重下，重启 service。
- **deb 安装**：装 standalone tarball 到 `/usr/local/bin/code`（不动 deb 包的 `/usr/bin/code`，桌面 app 留着），写 systemd drop-in 把 ExecStart 指过去：
  ```
  /etc/systemd/system/code-serve-web.service.d/20-pin-1.115-standalone-cli.conf
  ```
  ```ini
  [Service]
  ExecStart=
  ExecStart=/usr/local/bin/code serve-web --without-connection-token --accept-server-license-terms --host 127.0.0.1 --port 8080
  ```

修复方向：把 launcher 反代代码里的 `serve_connection(...)` 改成 `serve_connection_with_upgrades(...)`，几个字符的 patch。已提 issue。

### 教训

- **caddy 的 site block 默认不会输出 access log**，要排 ws 必须先临时加 `log <name> { output stdout; format json }`。每次反代后端报怪事先就该把这条加上，别凭空猜。
- **唯一对照组 ✅ 是宝藏**。当全网搜不到匹配症状时，找出“哪台是好的”，然后**把变量按字节列对照表**，逐个排除。本案三台 WSL 用同一条链路只有版本不同，前几轮乱猜参数全部白费，第三栏一列才直接给出答案。
- **看 strings + cargo 编译路径**。Rust 二进制把 cargo 路径嵌死了，无源码也能拿到完整依赖图（含每个 crate 的精确版本号），用来 bisect 极快。
- **「同 commit / 同 sha256 完全等价」是错觉**。本案 standalone tarball 和 deb 包内 binary 二进制完全一致，但跟 1.115.0 standalone tarball 的 commit 同样是 41dd792b 也可能 sha256 不同（不同时间 rebuild）—— 验证版本看 commit + `strings` 看依赖，别只看 sha。

