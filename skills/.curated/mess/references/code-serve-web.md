# `code serve-web` 疑难杂症

> VS Code 把 workbench 跑成浏览器可访问服务（`code serve-web`）时踩到的坑。几条都出在"浏览器 → CLI launcher → server"这条链路上：服务端按 `Accept-Language` 注入的语言包、launcher 自己的 HTTP 库、CDN 上的损坏构件叠加 CLI 的静默重试，都不算编辑器本身的问题。
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

## <a id="web-tarball-cdn-stall"></a>页面永远卡在 "The latest version of the VS Code Server is downloading"

> 2026-09-03 | 多用户 GPU 服务器（模板单元 `code-serve-web@.service` 给每个用户起一个实例，端口按 uid 递增）| CLI 1.129.1 (`/usr/bin/code`) | VS Code Server 1.136.1 / commit `a44adf7f`

### 症状

- 浏览器打开 `code serve-web`，一直停在 "The latest version of the Visual Studio Code Server is downloading, please wait a moment."，占位页返回 HTTP 202。
- service 状态 `running`，journal 每隔几分钟一条 `info Downloading server a44adf7f...`，**中间没有任何 error/warn**，永远等不到 "Starting server"。
- 当天早些时候还在用旧 commit `520fb30` 正常服务；旧 server idle 退出后新版接不上。
- 同机多个用户实例里 3 个同时中招、其余正常——命中按"谁触发了新下载"分布，可以排除整机网络问题。

### 排查关键转折

错的方向（按踩坑顺序）：

1. **「网络/代理问题」** — 用与 service 完全一致的干净 env（`env -i HOME=... VSCODE_CLI_DATA_DIR=...`）curl 官方下载 URL，全速拉完 218MB。但后来发现**测错了对象**：`update.code.visualstudio.com/commit:<hash>/server-linux-x64/stable` 重定向到的是 `vscode-server-linux-x64.tar.gz`，而 serve-web 下载的是另一个构件（见下）。
2. **「常驻进程烂掉了」** — 单元已跑 3 天，怀疑老进程状态劣化；换全新进程 + 全新数据目录在 18080 端口 `--verbose` 复现 → **同样卡死**，排除。
3. **「HTTP/2 / Accept-Encoding / 坏 CDN 边缘」** — curl `--http2`（被协商回 h1）、`-H 'Accept-Encoding: gzip, br'`、`--resolve` 钉死 DNSPod 调度出来的每个边缘 IP（分属腾讯系、电信系运营商）逐一测试，全部全速完成，全部排除。

真正的突破点：

1. **trace 日志里的字节数指纹**：`code serve-web --verbose` 会打 `Downloading server: X/245499233`，而这个总数 ≠ 上述 URL 的 `Content-Length` 228908092 —— CLI 下载的不是我测的那个文件。
2. 对同一 commit 挨个 HEAD 其它构件：`vscode-server-linux-x64-web.tar.gz` 的 `Content-Length` = **245499233**，精确命中。
3. curl 直接下载这个 `-web` 构件 → **148MB 处断流**（exit 124），与 CLI 卡死位置（132–150MB 区间）一致 → 复现成功，锅在 CDN 上的这一个对象。

### 根因

`code serve-web` 跟踪最新 stable（本案 1.136.1 / `a44adf7f`），按需下载 **`vscode-server-linux-x64-web.tar.gz`**。该构件在 `vscode.download.prss.microsoft.com`（DNSPod 动态调度的 "Lego Server" 边缘）上的缓存对象是坏的：响应声称 245,499,233 字节，单连接全速送到 ~80–150MB 后断流（每次断点不定，故障持续数小时，间歇可自愈）。三个致命叠加让它表现为"永远卡住"：

- CLI 下载**没有断点续传**，断流即整趟作废；
- 失败**不打 error 日志**（默认级别下完全静默）；
- 每来一个页面请求就**从头重试一次** → 页面永远 202。

同 commit 的非 `-web` 构件、`update.code.visualstudio.com` 本身、机器网络全部正常——故障面只有这一个 CDN 对象，所以一切"链路正常"的旁证都测不出来。

### 解决

**手工断点续传 + 植入缓存**（对卡住实例无需重启 service；多用户机可用 root 代做后 `chown` 回去）：

```
C=a44adf7f53e00964ab890f9f8758a334f1fc15bc
U=https://vscode.download.prss.microsoft.com/dbazure/download/stable/$C/vscode-server-linux-x64-web.tar.gz
# ① 循环续传拼满；长度与 sha256 对照
#    https://update.code.visualstudio.com/api/update/server-linux-x64-web/stable/latest
while [ "$(stat -c%s sw.tar.gz 2>/dev/null)" != 245499233 ]; do timeout 60 curl -C - -o sw.tar.gz "$U"; done
sha256sum sw.tar.gz
# ② 解压植入 serve-web 缓存（注意是裸内容，不带外层目录名），登记 lru.json
tar -xzf sw.tar.gz && mv vscode-server-linux-x64-web ~/.vscode/cli/serve-web/$C
rmdir ~/.vscode/cli/serve-web/$C.staging 2>/dev/null
# 把 $C 插到 ~/.vscode/cli/serve-web/lru.json 数组首位
```

- 完整性双校验：tar.gz 的 sha256 对照官方 API；植入后 `node` 二进制应为 123,656,816 字节。
- 本案用该法批量修了 3 个用户实例（root 代做播种后 `chown` 回各用户，端口下一个请求立即 200）；另一家在播种时恰好撞上健康边缘自愈——**等自愈不可预期，续传植入才是可控手段**。
- 此次播种的完整 commit 为 `a44adf7f53e00964ab890f9f8758a334f1fc15bc`（1.136.1），**只恢复当次缓存，没有根治跟踪 latest 时的自动更新下载问题**。控制版本选择的方式见[固定 CLI 启动版本](#web-pin-launch)与[固定旧版本访问入口](#web-pin-entry)。
- 多用户实例巡检：各实例端口逐个 `curl` 探测，返回 202 即中招。

### <a id="web-latest-recurrence"></a>复发记录（2026-09-09）

六用户的新入口全部返回 202；CLI 仍为 1.129.1，却已经追踪 latest 1.137.0 / commit `645f29cc3176500b4b5762ba887cf2a7f0ffdf2c`。六人的旧 `a44adf7f53e00964ab890f9f8758a334f1fc15bc` 缓存都在，部分实例当天还已下载 1.136.2，因此不能归因为上次播种遗漏；CLI 版本与其选择的 Web Server 版本也不能混为一谈。

> 2026-09-09 现场巡检：同一多用户服务器的六个实例，核对各用户缓存、CLI 版本、HTTP 响应与服务 PID；下述测速和固定入口验证来自同次排查。

本次 curl 测的是 exact web 构件，总长 **233,510,790 字节**：开始约 10 MiB/s，随后降到个位至几十 KiB/s，150 秒只收到约 78 MB，最终由测试设置的 `max-time` 终止。这个结果证明该次下载显著变慢，**不能据此认定新版也是 CDN 坏对象**；新版下载变慢的根因未定，上文的坏对象结论仅对应 2026-09-03 旧案例。

源码中的 latest checker 每小时查询一次；设置 `commit_id` 会禁用这个检查器。只有**版本查询失败**才回退旧记录，**构件下载失败不会回退**到已缓存旧版本；下载端使用 create 新文件，没有断点续传。因此旧缓存仍在与新入口一直 202 可以同时成立。

> 源码依据：[serve_web.rs 的版本检查、固定 commit 与回退分支](https://github.com/microsoft/vscode/blob/8a7abeba6e03ea3af87bfbce9a1b7e48fed567b8/cli/src/commands/serve_web.rs)、[http.rs 的下载文件创建逻辑](https://github.com/microsoft/vscode/blob/8a7abeba6e03ea3af87bfbce9a1b7e48fed567b8/cli/src/util/http.rs)。依据限定于所链接源码版本。

### <a id="web-pin-launch"></a>可选方案：固定 CLI 启动版本

改启动配置，不动现有进程：在现有 `code serve-web` 命令中加入 `--commit-id <已缓存完整commit>`，保留其他参数，等待下次正常启动或经确认的重启生效。选定 commit 前，要逐用户确认对应缓存完整可用；本次可用的共同旧版本是 `a44adf7f53e00964ab890f9f8758a334f1fc15bc`。系统级 systemd 单元可由有权限者通过 drop-in 更新 `ExecStart`。

`systemctl daemon-reload` 只让 systemd 重读单元配置，**不会改变现存 CLI 的启动参数**；该 CLI 没有热修改 `--commit-id` 的接口。这里的下次启动指 CLI / 服务单元重新启动，内部 Server 空闲退出再启动不算。这一方案生效后不再跟踪 latest，但在现有 CLI 退出前不解决当前入口等待新版的问题，后续升级需另行选择和验证 commit。

**不要为了使参数立即生效而未经确认重启。** 本次机器的 systemd 配置为 `KillMode=control-group`，直接 restart 会终止单元控制组内的进程，包括其中的终端、Codex、Claude 等任务，不只是浏览器断线。`nohup` 或被收养为 PPID 1 都不能使进程脱离控制组；也不能把改成 `KillMode=process` 当成任务安全保证。

> 其他机器应核对实际单元、控制组归属和任务状态，不能照搬本机配置结论。

### <a id="web-pin-entry"></a>可选方案：固定旧版本访问入口

保留现有 CLI 进程，将访问入口指向已缓存的旧版本，例如 `/stable-a44adf7f53e00964ab890f9f8758a334f1fc15bc/`，让新打开的页面不必等待新版下载。**CLI 后台仍会检查新版本，已经进行的下载也不保证取消**。这与[固定 CLI 启动版本](#web-pin-launch)相互独立，可以单独使用，也可以先恢复入口，再等待启动配置生效。

若需让域名首页自动使用旧版本，把规则放在**各 code 域名自己的配置文件**中，不另建跨域名的全局规则。在该域名的 `route` 内，按 `authorize → rewrite → reverse_proxy` 排列；已有 `handle` 包裹域名规则时，将 `route` 放在其中。这样既能固定认证与改写的执行顺序，也能保留原域名的匹配范围。只增加首页匹配器与内部 rewrite（服务端改写请求路径），不改变原认证策略、上游及其他参数。

下面仅示意插入位置，`example.com`、认证策略名与上游均为通用示例，不能用它覆盖整份现有配置：

```caddyfile
example.com {
    route {
        authorize with existing_policy

        @cached_home {
            path /
            method GET HEAD
            not {
                header_regexp Upgrade (?i)websocket
            }
        }
        rewrite @cached_home /stable-a44adf7f53e00964ab890f9f8758a334f1fc15bc/

        reverse_proxy 127.0.0.1:8080
    }
}
```

匹配严格限定首页 `/` 的普通 GET/HEAD，排除 `Upgrade: websocket`；已经带版本前缀的资源和 WebSocket 请求都不改。rewrite 目标**不要加问号**，只替换路径，保留原来的 `?folder=...` 等 query。认证仍先于 rewrite 执行；未认证首页请求不会先经过这条改写，检查固定路径的认证回跳时应直接请求固定入口。

修改后先校验完整 Caddy 配置（使用现场实际的 Caddy 二进制及认证插件），确认匹配范围、认证顺序和上游未变，再由**明确获授权的人** reload。用户要求自行 reload 时，只交付已校验的文件；后续获得明确授权后才能代为执行。Caddy reload 不重启 VS Code，也不终止其任务，但可能让 WebSocket 重连，不能承诺零断线。

> reload 超时不一定代表新规则未生效。2026-09-09 至 10 日，Caddy 2.11.4 两次在清理旧 WebSocket 时卡于 `writeCloseControl → netFD.Write`，同时持有配置锁；业务新路由已生效，管理接口却等锁超时。现场按 TCP 四元组断开已确认长期发送阻塞的连接后，管理接口恢复、配置加载完成，Caddy 与 VS Code 主进程均未重启。这类处置也须先获准短暂重连，不能批量杀进程代替定位；诊断流程由 `network` skill 覆盖。对应源码：[同步发送关闭帧及清理连接](https://github.com/caddyserver/caddy/blob/v2.11.4/modules/caddyhttp/reverseproxy/streaming.go#L400-L444)。

本轮现场验证：六个用户固定路径的 HTML 和 CSS 均为 200；固定入口认证返回的 302 中，`redirect_url` 包含固定路径并保留 `folder`；服务 PID 均未变化。后续复用时仍需逐实例验证这些项目，并确认已有版本资源和 WS 路径不被改写，不能仅凭首页 200 推定全部正常。

### 教训

- **先搞清"卡在下载"的到底在下载哪个对象**。update 服务对不同 product（`server-linux-x64` vs `server-linux-x64-web` vs `cli`）给的是不同 URL；curl 测错构件会得出"CDN 正常"的假阴性。CLI trace 里 `Downloading server: X/TOTAL` 的 TOTAL 就是 Content-Length 指纹，拿它去 HEAD 各候选构件对尺寸，一步锁定真实对象。
- **"curl 正常" ≠ 链路正常**：URL、边缘 IP（DNSPod 调度每次可能不同）、请求头要逐字节等同才有对照意义。
- 本故障的日志指纹：service `running` + journal 只有反复的 `Downloading server <commit>`、无任何 error + 页面 202。见到先核对目标 commit、exact web 构件与旧缓存，再按本案区分下载故障和入口选择；仅凭指纹不能认定 CDN 坏对象。
- 顺带小坑：`pkill -f` 的模式若出现在自己命令行里会**把自己杀掉**；杀特定端口进程先 `ss -tlnp` 拿 PID 或运行时拼 pattern。

