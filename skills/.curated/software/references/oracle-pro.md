# Oracle Pro / Extended via ChatGPT Web

## 命名

文件名使用 `oracle-pro.md`，不要用 `pro-oracle.md`。

这里的 `pro` 明确指通过 ChatGPT 网页端使用 GPT Pro / GPT-5.5 Pro，而不是泛指“专业版工作流”。

理由：这份 reference 的主语是 `steipete/oracle` 这个工具，`GPT Pro / Extended` 是它在 ChatGPT 网页端上的一个高风险使用场景。按“工具名-主题”的顺序命名，后续也方便并列扩展，例如 `oracle-browser.md`、`oracle-project-sources.md`。

## 适用场景

当本地 CLI / API 暂时不能直接使用 GPT-5.5 Pro，但 ChatGPT 网页端可以使用 Pro 模型时，可以用 `steipete/oracle` 的 browser engine 控制已登录的 ChatGPT 网页会话，把项目 zip、文件或 prompt 发到网页端。

核心目标不是“能点 UI”，而是确保实际发出的 ChatGPT backend payload 符合预期：

```text
model=gpt-5-5-pro
thinking_effort=extended
```

## Windows Chrome 与 WSL

优先使用独立 Chrome profile，避免污染日常浏览器会话：

```powershell
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList @(
  "--remote-debugging-port=9222",
  "--user-data-dir=C:\Users\MY.Tan\.chrome-chatgpt-oracle",
  "https://chatgpt.com/"
)
```

从 WSL 启动 Windows Chrome 时，用 Windows PowerShell：

```bash
'/mnt/c/Program Files/PowerShell/7/pwsh.exe' -NoProfile -Command '<powershell command>'
```

注意区分两种 WSL 网络模式：

- Mirror 模式：WSL 通常可以访问 Windows Chrome 的 `127.0.0.1:9222`。
- NAT 模式：WSL 的 `127.0.0.1` 是 WSL 自己，不能直接访问 Windows loopback 上的 Chrome DevTools。

在 NAT 模式下，即使给 Chrome 加 `--remote-debugging-address=0.0.0.0`，实际也可能仍只监听 `127.0.0.1:9222`。尝试在 Windows 侧开 `172.x.x.1:9223 -> 127.0.0.1:9222` TCP proxy 时，Windows 防火墙可能拦截 WSL 入站访问；添加防火墙规则通常需要管理员权限。

因此，NAT 模式下更稳的路径是：在 Windows 侧运行 Oracle CLI，让它以 `127.0.0.1:9222` 连接 Windows Chrome。

## Windows 侧运行 Oracle 的回退路径

把 WSL 中的 Oracle 工作区复制到 Windows 临时目录：

```powershell
$src="\\wsl.localhost\Ubuntu\home\timidly\oracle"
$dst="$env:TEMP\oracle-win-demo"
robocopy $src $dst /E /XD node_modules .git dist .oracle /XF "*.log"
Set-Location $dst
corepack pnpm install --frozen-lockfile
corepack pnpm run build
```

如果 Windows Node 已安装但 `pnpm` shim 不可写入 `C:\Program Files\nodejs`，`corepack pnpm install` 的 lifecycle 可能在调用裸 `pnpm` 时失败。只要依赖已经装好，可以继续用：

```powershell
corepack pnpm run build
node dist\bin\oracle-cli.js status --browser-tabs
```

指定可见 tab、禁用 archive，便于人工确认页面状态：

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --browser-tab <target-id> `
  --browser-archive never `
  --model gpt-5.5-pro `
  --browser-model-strategy select `
  --browser-thinking-time extended `
  --browser-attachments never `
  --prompt "Reply with exactly: oracle pro extended smoke ok" `
  --write-output "$env:TEMP\oracle-pro-extended-output.md" `
  --no-notify --verbose --heartbeat 5 --force
```

成功时，Oracle 可见输出应类似：

```text
Model picker: Extended Pro
Thinking time: Extended (already selected)
Clicked send button
Answer:
oracle pro extended smoke ok
```

## 常用运行模式

### 上传文件到 ChatGPT Project Sources

如果目标是让多个后续 ChatGPT Project 对话都能看到同一批项目资料，用 `project-sources`，不是普通 `--prompt` consult。

Oracle 项目文档位置：

```text
docs/browser-mode.md -> ChatGPT Project Sources
```

先预览，不碰 ChatGPT：

```powershell
node dist\bin\oracle-cli.js project-sources add `
  --chatgpt-url "https://chatgpt.com/g/g-p-example/project" `
  --browser-manual-login `
  --file .\project.zip `
  --dry-run
```

列出当前 Project Sources：

```powershell
node dist\bin\oracle-cli.js project-sources list `
  --chatgpt-url "https://chatgpt.com/g/g-p-example/project" `
  --browser-manual-login
```

追加上传文件：

```powershell
node dist\bin\oracle-cli.js project-sources add `
  --chatgpt-url "https://chatgpt.com/g/g-p-example/project" `
  --browser-manual-login `
  --file .\project.zip
```

也可以上传多个文件：

```powershell
node dist\bin\oracle-cli.js project-sources add `
  --chatgpt-url "https://chatgpt.com/g/g-p-example/project" `
  --browser-manual-login `
  --file .\docs\architecture.md .\docs\decisions.md
```

`project-sources add` 的行为边界：

- 只打开 ChatGPT Project 的 Sources 面板并追加文件。
- 不选择模型。
- 不发送 prompt。
- v1 是 append-only；不能 delete、replace、sync。
- 每批最多上传 10 个文件。

压缩包可以作为 `--file .\project.zip` 交给浏览器上传输入框；但模型是否能稳定展开、索引和引用压缩包内部文件，取决于 ChatGPT Project Sources 当时的网页端能力。对代码审查和大改动规划，更可靠的做法通常是上传关键源码文件、设计文档，或把仓库整理成一个文本 bundle，而不是只给一个 zip。

### 普通 browser consult 上传附件

如果目标是“这一次对话让 Pro 处理这些文件”，用普通 browser consult：

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --model gpt-5.5-pro `
  --browser-model-strategy select `
  --browser-thinking-time extended `
  --browser-archive never `
  --file .\project.zip `
  --prompt "Review this project archive and propose the implementation plan." `
  --heartbeat 30 --force
```

附件策略：

- `--browser-attachments auto`：默认；小内容先 inline，超过约 60k 字符后转为上传附件。
- `--browser-attachments always`：强制用附件上传。
- `--browser-inline-files`：强制把文件内容 inline，不上传附件。
- `--browser-bundle-files`：上传启用时，把多个 resolved files 合成一个临时 bundle 文件再上传。

大任务建议：

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --model gpt-5.5-pro `
  --browser-thinking-time extended `
  --browser-archive never `
  --browser-attachments always `
  --browser-bundle-files `
  --file ".\src\**\*.ts" `
  --file ".\docs\**\*.md" `
  --file "!.\node_modules\**" `
  --prompt "Use the uploaded project context to design the minimal safe implementation plan." `
  --heartbeat 30 --force
```

普通 consult 的附件上传与 Project Sources 不同：它只属于当前 ChatGPT conversation，不会自动变成 Project Sources。

### 先找可复用 ChatGPT tab

```powershell
node dist\bin\oracle-cli.js status --browser-tabs
```

输出里关注：

- `target id`：传给 `--browser-tab <target-id>`。
- `title` / `url`：也可以用标题片段或完整 URL 作为 `--browser-tab`。
- `model`：只能作为 DOM 辅助信号，不能替代 payload 验证。

### 可见演示，不 archive

用于人工盯着页面确认 Pro / Extended 是否真的选中：

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --browser-tab <target-id> `
  --browser-archive never `
  --model gpt-5.5-pro `
  --browser-model-strategy select `
  --browser-thinking-time extended `
  --prompt "Reply with exactly: oracle pro extended visible demo ok" `
  --no-notify --verbose --heartbeat 5 --force
```

关键点：

- `--browser-tab <target-id>`：复用现有可见 tab；如果这个 tab 已经在 `https://chatgpt.com/c/<id>`，就是在这个 conversation 里继续发。
- `--browser-archive never`：完成后不归档 conversation。
- `--remote-chrome 127.0.0.1:9222`：Windows-local Oracle 连接 Windows Chrome 时使用。

### 一次性单轮对话

只发一个 prompt，不带 `--browser-follow-up`。这是默认 one-shot 模式。

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --model gpt-5.5-pro `
  --browser-model-strategy select `
  --browser-thinking-time extended `
  --file .\project.zip `
  --prompt "Review this project archive and list the top issues." `
  --write-output "$env:TEMP\oracle-one-shot.md" `
  --heartbeat 30 --force
```

默认 `--browser-archive auto` 会 archive 成功的普通 one-shot ChatGPT conversation。若需要回看网页会话，加 `--browser-archive never`。

### 同一次运行内多轮追问

用 `--browser-follow-up`，Oracle 会在同一个 ChatGPT conversation 里等待上一轮回答完成，再提交下一轮：

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --browser-archive never `
  --model gpt-5.5-pro `
  --browser-thinking-time extended `
  --file .\docs\migration.md `
  --prompt "Review this migration plan." `
  --browser-follow-up "Challenge your previous recommendation." `
  --browser-follow-up "Give the final decision." `
  --write-output "$env:TEMP\oracle-multiturn.md" `
  --heartbeat 30 --force
```

限制：

- `--browser-follow-up` 不支持 Deep Research。
- `auto` archive 会跳过 multi-turn；但演示和排障仍建议显式写 `--browser-archive never`。
- 输出 transcript 会按 `Initial response`、`Follow-up 1` 等分段。

### 事后继续同一个网页 conversation

如果上一轮没有 archive，或者 tab 还开着：

1. 用 `status --browser-tabs` 找到目标 tab。
2. 用 `--browser-tab <target-id|url|title-substring|current>` 指定它。
3. 再提交新的 `--prompt`。

```powershell
node dist\bin\oracle-cli.js `
  --engine browser `
  --remote-chrome 127.0.0.1:9222 `
  --browser-tab <target-id> `
  --browser-archive never `
  --model gpt-5.5-pro `
  --browser-model-strategy select `
  --browser-thinking-time extended `
  --prompt "Continue from the previous answer and produce the patch plan." `
  --heartbeat 30 --force
```

这和 API 模式的 `--followup <sessionId>` 不是同一套机制。网页端继续对话的关键是复用同一个 ChatGPT tab / conversation URL。

## Pro Extended 的真实 UI 路径

不要只看 Oracle 日志或按钮文案。历史上出现过两类误判：

- 日志显示 `Pro Extended`，但实际 payload 是 `model=gpt-5-5-pro` + `thinking_effort=standard`。
- 选择了 Extended，但实际 payload 变成 `model=gpt-5-5-thinking` + `thinking_effort=extended`。

正确路径是：

1. 打开 model switcher。
2. 选择 Pro 行：`model-switcher-gpt-5-5-pro`。
3. 在 Pro 行里打开 thinking effort 子菜单：`model-switcher-gpt-5-5-pro-thinking-effort`。
4. 选择 `Extended`。

完成后，composer pill 常见文案是 `Extended Pro`。但 `button.__composer-pill` 的文案只适合作为辅助信号，不能作为最终验证。

不要假设 GPT Pro 一定有 `Heavy` 或 `Light` 可选。即使公开文档或旧代码路径提到更多 thinking-time 档位，当前账号、workspace、A/B 实验、地区或 ChatGPT 页面状态都可能只暴露 `Standard` / `Extended`。自动化应以实际 DOM 菜单项为准；在本机验证过的 GPT Pro 路径是 `Pro` + `Extended`，对应 payload：

```text
model=gpt-5-5-pro
thinking_effort=extended
```

## DOM 验证层级

DOM 验证要分层做，不能只看一个 selector：

1. Model picker 层：确认点击的是 Pro 行，而不是 Thinking 行或菜单容器。
2. Thinking effort 层：确认打开的是 Pro 行下面的 thinking-effort 子菜单。
3. Composer pill 层：确认最终 pill 文案接近 `Extended Pro`。
4. Network payload 层：确认最终发出的 backend payload 是 Pro + Extended。

可接受的 DOM 辅助信号：

```text
model-switcher-gpt-5-5-pro
model-switcher-gpt-5-5-pro-thinking-effort
button.__composer-pill ~= "Extended Pro"
```

不可接受的唯一判断：

```text
button.__composer-pill == "Pro"
button.__composer-pill == "Extended"
Oracle log says "Pro Extended"
```

原因：ChatGPT 的菜单结构可能让“Extended”落到 Thinking 模型上，也可能让“Pro”保持 Standard effort。DOM 验证只能证明 UI 操作路径看起来合理；最终仍必须看 network payload。

## 必须做 payload 验证

对 Pro / Extended 这种网页端状态，DOM 和日志都不是最终事实。最终事实是 ChatGPT 发出的 network payload。

在 browser engine 中监听 CDP `Network.requestWillBeSent`，捕获以下 POST：

```text
/backend-api/f/conversation/prepare
/backend-api/f/conversation
```

验证字段：

```text
model === "gpt-5-5-pro"
thinking_effort === "extended"
```

若捕获不到 payload，或者字段不匹配，要输出硬 warning，例如：

```text
[browser] WARNING: ChatGPT payload verification mismatch: expected model=gpt-5-5-pro thinking_effort=extended, got model=gpt-5-5-thinking thinking_effort=extended
```

对关键改动做外部 smoke capture，最小验收输出：

```text
EXTERNAL_CAPTURE: /backend-api/f/conversation model=gpt-5-5-pro thinking_effort=extended
EXTERNAL_PAYLOAD_OK=true
```

## 安全边界

CDP Network capture 本身是被动读取浏览器请求，主要风险来自暴露 DevTools 端口和自动操作已登录网页会话。

建议：

- DevTools 默认只监听 `127.0.0.1`。
- 不要长期暴露 `--remote-debugging-address=0.0.0.0`。
- WSL NAT 下优先 Windows-local Oracle，而不是对外开 DevTools proxy。
- demo 时使用 `--browser-tab <target-id>` 和 `--browser-archive never`，避免 Oracle 创建的 target 结束后被自动 archive，导致人工无法确认。
- 临时 TCP proxy 和临时 firewall rule 用完要关闭。
