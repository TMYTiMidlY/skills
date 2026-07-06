# Copilot CLI 运行时笔记

Copilot CLI 本体行为的逆向与排障笔记：进程模型、bash 工具的环境变量处理、权限与目录信任、TUI 与终端、Git 认证、重试策略 patch、运行中插话（steer），以及会话存储与 `/share html` 导出。

大部分章节附 `app.js` 源码摘录与字节偏移；偏移**仅供参考**，混淆后的符号（`xj` / `_R` / `Nhe` / `bBt` / `sN` / `cKr` …）是 esbuild 产物的稳定特征，会随版本变化但用关键字面量（`COPILOT_RUN_APP` / `COPILOT_ALLOW_ALL` / `GITHUB_PERSONAL_ACCESS_TOKEN` / `safe.bareRepository` / `AGENTS.md` / `.mcp.json` …）能在新版本里重新定位。源码定位基线为 `@github/copilot@1.0.41` 的 `app.js`（esbuild 混淆产物）；部分较新章节用 1.0.64-1 / 1.0.66-1 复核。

## 进程模型

### 三层结构：loader → app.js

```
$ which copilot
~/.local/share/<node-install>/lib/node_modules/@github/copilot/npm-loader.js
                                                                ├── npm-loader.js   (shim)
                                                                ├── index.js        (loader)
                                                                └── app.js          (主逻辑)
```

- `npm-loader.js` 只是把入口转发到 `index.js`。
- `index.js` 负责：自动更新、版本选择（`--prefer-version`）、crash report 收集。spawn `app.js` 子进程时**不做** env 过滤（用一个空 filter Set 的 `U(...)`）。所以 `process.env.GITHUB_PERSONAL_ACCESS_TOKEN` 在 Copilot 主进程内部仍然可读，可能用来：调内部 API、推送遥测前的鉴权。
- `app.js` 是主逻辑：tool registry / hook 解析 / MCP 客户端 / bash pty 工具的 env 过滤都在这一层。

下文所有"`app.js:<offset>`"指的是 `app.js` 这一层文件内的字节偏移。

---
## 安装方式与看源码

> **为什么要"逆向"——因为 Copilot CLI 闭源**。官方只分发混淆 bundle（`@github/copilot` 的 `app.js`，esbuild minified）或 SEA 二进制，**不公开源码**，所以本节讲的都是"怎么把它扒出来读"。三条证据：
> - **许可证是专有 EULA**：`github/copilot-cli` 仓库的 `LICENSE.md`（标题即 "GitHub Copilot CLI License"）在 Scope Limitations 里明令禁止 "Modify… or create derivative works"（禁改、禁衍生）——与开源（OSI）"可改、可分发衍生"的核心定义正相反，是典型闭源许可。
> - **那个 public 仓库里根本没有产品源码**：根目录只有 `README.md` / `changelog.md` / `install.sh` / `LICENSE.md`，没有 `app.js` / `src/`；`install.sh` 只负责去装预编译二进制 / npm 包。"仓库 public ≠ 开源"。
> - **真正分发的就是混淆产物**：即开头"源码定位基线"那个 `app.js`（单文件几千行 / 数 MB），符号名每版都变。
>
> 对照组：OpenAI Codex CLI 是真开源（`openai/codex`，Apache-2.0，完整 Rust 源码）；Claude Code 与 Copilot 一样闭源、minified 分发（社区只能逆向，如 `Yuyz0112/claude-code-reverse`）。

两种安装形态入口不同，但核心都是 `index.js`（loader）→ spawn `app.js`（主逻辑）两层（见上「三层结构」）。下面分别讲在哪、怎么读到 `app.js`。

### npm 安装：直接读 node_modules

```
~/.local/share/<node-install>/lib/node_modules/@github/copilot/
    ├── npm-loader.js   (shim，仅 npm 安装有，转发到 index.js)
    ├── index.js        (loader)
    └── app.js          (主逻辑，esbuild bundle)
```

直接 `view` / 字符串切片 `node_modules/@github/copilot/app.js` 即可，没有解包步骤。

### 二进制发行版（SEA）：读自解包的 cache

`file ~/.local/bin/copilot` 显示 `ELF ... stripped`（~160MB）就是单可执行二进制，JS 源码内嵌为 [SEA](https://nodejs.org/api/single-executable-applications.html)（Single Executable Application）。**不用自己拆 ELF**——CLI 首次运行时把内嵌资源解包成普通文件，落到：

```
~/.cache/copilot/pkg/<platform>/<version>/      # 如 linux-x64/1.0.64-1
    ├── index.js / app.js / sea-loader.js
    ├── copilot-sdk/*.d.ts   (没混淆的 TS 声明，读类型面最省事)
    └── *.wasm / 各 native 模块
```

目录里有 `.extraction-complete` 标记说明解包完成。定位当前版本目录：

```bash
D=~/.cache/copilot/pkg/linux-x64/$(copilot --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+-[0-9]+')
ls "$D"             # app.js index.js copilot-sdk/ ...
wc -l "$D/app.js"   # 1.0.64-1 是 6403 行
```

> macOS 走 `~/Library/Caches/copilot/pkg/...`；也可被 `COPILOT_CACHE_HOME` / `XDG_CACHE_HOME` / `COPILOT_HOME` 改写。

### 按字面量抠源码片段

`app.js` 是 esbuild bundle，**单行极长**（一行几 MB），grep 看不出上下文。实用做法是用 node 做字符串切片，以稳定字面量为锚点、把空白压成一行看：

```bash
node -e '
const fs=require("fs");
const s=fs.readFileSync(process.env.HOME+"/.cache/copilot/pkg/linux-x64/1.0.64-1/app.js","utf8");
let i=s.indexOf("GITHUB_PERSONAL_ACCESS_TOKEN");        // 换成你要找的字面量
console.log(s.slice(i-200,i+200).replace(/\s+/g," "));  // 压成一行看上下文
'
```

- **锚点选永不混淆的字符串常量**：env 名（`COPILOT_ALLOW_ALL`）、错误文案（`no-git-repo`）、配置文件名（`.mcp.json`）、CLI flag（`--allow-all-tools`）、schema key（`preToolUse`）。函数/变量名每版都变，不能当锚点。
- **读类型面优先看 `copilot-sdk/*.d.ts`**：`types.d.ts`（~60KB）、`client.d.ts`、`session.d.ts` 是没混淆的 TypeScript 声明，比从 `app.js` 反推结构清楚得多。

---
## Bash 工具

### Env 黑名单：为何 `git push` 在 agent 里总是 401

#### 现象

- host shell 里 `$GITHUB_PERSONAL_ACCESS_TOKEN`、`$OPENAI_API_KEY`、`$ANTHROPIC_API_KEY` 等等都正常 export
- agent bash 工具里 `echo $GITHUB_PERSONAL_ACCESS_TOKEN` **空字符串**，其他无关变量（`$WEBDAV_PASS`、`$MY_RANDOM_VAR`）正常
- 依赖 `$GITHUB_PERSONAL_ACCESS_TOKEN` 的 credential helper 在 agent 里跑 → password 是空串 → `Invalid username or token. Password authentication is not supported.`

不是 direnv 失效，也不是 `delete process.env[...]`——是 Copilot CLI **故意** 把一组带敏感性的 env 通过 Proxy 屏蔽掉了，且 host shell 看 Copilot 主进程的 `process.env` 没变，但 spawn 出来的 bash 子进程读不到。

#### 调用链

```
bash 工具调用
  → sessionFactory.create({ env: xj({...}) })
  → pty.spawn(shell, args, { env })
```

#### 关键代码

**`xj()`** — shell 工具构造 env 的入口（`app.js:~2016156`）：

```js
function xj(t = {}) {
  let e = new Set(vhe);                            // 黑名单
  let r = { ...t, COPILOT_CLI: "1" };
  // 白名单透传以下 GitHub/Copilot 内部变量：
  if (process.env.GITHUB_COPILOT_GITHUB_TOKEN)
    r.GITHUB_TOKEN = process.env.GITHUB_COPILOT_GITHUB_TOKEN;
  if (process.env.COPILOT_AGENT_CALLBACK_URL)   r.COPILOT_AGENT_CALLBACK_URL = ...;
  if (process.env.COPILOT_AGENT_JOB_ID)         r.COPILOT_AGENT_JOB_ID       = ...;
  if (process.env.GITHUB_VERIFICATION_TOKEN)    r.GITHUB_VERIFICATION_TOKEN  = ...;
  if (process.env.GITHUB_TOKEN_VARNAME)         r.GITHUB_TOKEN_VARNAME       = ...;
  if (process.env.GITHUB_COPILOT_API_TOKEN)     r.GITHUB_COPILOT_API_TOKEN   = ...;
  return _R(r, e);
}
```

`GITHUB_PERSONAL_ACCESS_TOKEN` **不在** 白名单透传里。

**`_R(t, e)`** — 用 Proxy 模拟"剥离过的 env"（`app.js:~1935588`）：

```js
function _R(t, e) {
  let r = Object.create(null);
  if (t) for (let [k, v] of Object.entries(t)) r[k] = v;
  let n = e ?? SIi;
  return new Proxy(process.env, {
    get(_, s) {
      if (typeof s === "string") {
        if (Object.hasOwn(r, s)) return r[s];
        if (!n.has(s)) return process.env[s];    // ← 在黑名单 n 里直接返回 undefined
      }
    },
    has(_, s) { /* 同样过滤 */ },
    ownKeys(_) {
      let s = new Set(Object.keys(process.env));
      for (let a of n) s.delete(a);              // ← 黑名单也从 keys 里抹掉
      ...
    },
    ...
  });
}
```

Node 的 `child_process.spawn` 在 `{env}` 是 Proxy 时会枚举 keys + 取值，黑名单 key 既不出现也读不到 → 子进程完全看不见。

**黑名单 `vhe = [..., ...Nhe]`**：

```js
vhe = [
  // Copilot 内部不应外泄的运行时上下文
  "COPILOT_AGENT_CALLBACK_URL", "COPILOT_AGENT_MODEL", "COPILOT_AGENT_JOB_ID",
  "COPILOT_AGENT_PROMPT",       "COPILOT_AGENT_PUSH",  "COPILOT_FIREWALL_ENABLED",
  "COPILOT_FIREWALL_ALLOW_LIST","GITHUB_COPILOT_INTEGRATION_ID",
  "COPILOT_INTEGRATION_ID_OVERRIDE","COPILOT_AGENT_PREVIOUS_SESSION_IDS",
  "COPILOT_AGENT_EVENT_URL",    "COPILOT_AGENT_EVENT_TYPE",
  "COPILOT_AGENT_USE_CODEQL",   "COPILOT_AGENT_USE_CCR",
  "COPILOT_AGENT_USE_SECRET_SCANNING","COPILOT_AGENT_USE_DEPENDENCY_VULN",
  "NODE_ENV",                   "COPILOT_AGENT_ACTOR",
  "COPILOT_AGENT_ACTOR_ID",     "COPILOT_AGENT_ACTOR_TYPE",
  "COPILOT_API_URL",            "GITHUB_COPILOT_MCP_JSON_FROM_INPUT",
  "COPILOT_PROVIDER_BASE_URL",  "COPILOT_PROVIDER_TYPE",
  "COPILOT_PROVIDER_WIRE_API",  "COPILOT_PROVIDER_AZURE_API_VERSION",
  "COPILOT_PROVIDER_MODEL_ID",  "COPILOT_PROVIDER_WIRE_MODEL",
  "COPILOT_PROVIDER_MODEL_LIMITS_ID","COPILOT_PROVIDER_MAX_PROMPT_TOKENS",
  "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS","GITHUB_TOKEN_VARNAME",
  "COPILOT_OFFLINE",
  ...Nhe                                          // ← 真正的敏感 token 列表
];

Nhe = [
  "GITHUB_COPILOT_GITHUB_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN",
  "GITHUB_COPILOT_API_TOKEN", "CAPI_HMAC_KEY", "CAPI_HMAC_KEY_OVERRIDE",
  "ANTHROPIC_API_KEY", "AIP_SWE_AGENT_TOKEN", "CAPI_AZURE_KEY_VAULT_URI",
  "COPILOT_JOB_NONCE", "GITHUB_MCP_SERVER_TOKEN",
  "OPENAI_BASE_URL", "OPENAI_API_KEY",
  "COPILOT_AGENT_REQUEST_HEADERS",
  "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_ENDPOINT",
  "AZURE_OPENAI_KEY_VAULT_URI", "AZURE_OPENAI_KEY_VAULT_SECRET_NAME",
  "BLACKBIRD_AUTH_METIS_API_KEY", "BLACKBIRD_AUTH_MODEL_BASED_RETRIEVAL_TOKEN",
  "GITHUB_PERSONAL_ACCESS_TOKEN",                 // ← 就是它
  "GITHUB_VERIFICATION_TOKEN",
  "COPILOT_PROVIDER_API_KEY", "COPILOT_PROVIDER_BEARER_TOKEN"
];
```

`Nhe` 同时被复用为日志 redaction 名单（`getSecretValues()`）和 MCP 配置 `${VAR}` 展开拦截名单（`Das()`），是统一的「不该让 agent 看到的密钥」清单。

#### 设计意图

Copilot CLI 跑的是一个 LLM agent。把用户全权 `GITHUB_PERSONAL_ACCESS_TOKEN` 透传给子进程 = 把 GitHub 全权 token 交给 LLM = LLM 可以代表用户做任何事（push 任意仓库、删 repo、读私库、改 settings）。所以：

- **agent 子进程**：只拿到 Copilot 服务端发的、受限的短期 token（透传成 `GITHUB_TOKEN`）
- **用户本人的 PAT**（`GITHUB_PERSONAL_ACCESS_TOKEN`）始终留在 host shell 和 Copilot 主进程，agent 子进程读不到

这是**故意**的安全屏障，不是 bug。

#### 实际后果与对策

依赖 `$GITHUB_PERSONAL_ACCESS_TOKEN` 的 git credential helper 在 agent 里拿到空串 → 401。对策见 [Bash 工具 env 黑名单下的 `git push` 对策](#bash-工具-env-黑名单下的-git-push-对策)。

#### 可见信号

- `env | grep -i token` 在 agent bash 里看不到任何 `*TOKEN*`、`*API_KEY*`、`*HMAC*` 等敏感变量，但能看到 `WEBDAV_PASS`、`MY_OTHER_PASSWORD` 之类非黑名单 → 说明过滤是按名单，不是按词
- `env | grep -i GIT_CONFIG` 通常会看到 `GIT_CONFIG_KEY_<n> / VALUE_<n>` 里有 `safe.bareRepository=explicit`——这是 Copilot CLI 自己塞的一对 git config，**说明 Copilot 在 spawn 时确实改写了 env**

#### 警示

- **明文把 token 贴进聊天**是绕过这个屏障的**唯一**方式，也恰好就是该屏障要防的事。如果发生了，立即 revoke 那个 token。

---

### `BASH_ENV` 只对非交互 bash 生效

#### 症状

`.envrc` 里 `export BASH_ENV="$PWD/.copilot.env"`，意图把额外的 env / secret 注入到 Copilot 派生的 bash 子进程，但**不污染** Copilot 主进程（避免 token 被外层进程也读到）。

但 agent 在 bash 工具里跑 `gh api user --jq .login`、`echo $MY_TOKEN` 之类，发现注入的变量根本没生效。

#### 根因

`BASH_ENV` 是 **bash 内置机制**，仅在 bash 以**非交互式**启动时（`bash -c "..."`、`bash script.sh`、`#!/bin/bash` 脚本）才会自动 source。

Copilot CLI 的 bash 工具起的是**带 TTY 的交互式 shell**（pty.spawn）。交互式 shell 不读 `BASH_ENV`，只读 `~/.bashrc`，所以 `.copilot.env` 永远不被 source。

#### 解决

每条命令显式 source 或包一层非交互 bash：

```bash
source ~/path/to/.copilot.env && gh api user --jq .login
# 或
bash -c 'gh api user --jq .login'
```

更推荐的做法：直接通过 `.envrc` export 到 host shell（让 direnv 在 cd 时自动加载），让 Copilot CLI 主进程继承这些 env，再由它的 bash 工具继承（除非命中上节的黑名单）。这种方案下根本不需要 `BASH_ENV`。

#### 教训

- `BASH_ENV` 不是 Copilot 的功能，是 bash 的功能；Copilot bash 子进程是否非交互，决定它生不生效。
- 看到"应该有的 env 没有"先 `echo $BASH_ENV`、再 `case $- in *i*) echo interactive ;; *) echo non-interactive ;; esac` 看 shell 类型。

### 拿不到用户的显示 tty

bash 工具的标准流是**管道**，不是终端：`fd0 → /dev/null`、`fd1 → pipe`、`fd2 → /dev/null`，`tty` 命令返回 `not a tty`，`/dev/tty` 打开报 `No such device or address`。

后果：**agent 自己发不了 OSC / DA 这类终端查询、也读不到终端应答**——任何"问终端背景色 / 能力探测 / 颜色诊断"的命令都得让用户**在交互 pane 里手动跑**，agent 只能给命令、读用户贴回来的结果。诊断终端颜色/主题问题（见 [colorMode](#终端颜色--主题colormode)）时直接据此分工，别在 agent bash 里反复试 OSC。

---
## TUI 与终端

### 滚动与翻页键

Copilot CLI 跑在 **alternate screen（备用屏，像 vim/less 那样独占整屏、退出后恢复）** 的全屏 TUI，自带 vim 风格 pager：**翻页 PageUp / PageDown**，半页 `Ctrl+U` / `Ctrl+D`，到顶/底 `Home`(或 `g`/`gg`) / `End`(或 `G`)，`/` 搜索、`n`/`N` 跳下/上一个，也吃鼠标滚轮。

**关键坑**：alt-screen 没有终端回滚缓冲（scrollback），Copilot 还打开鼠标追踪，所以**终端复用器（tmux / zellij）自己的"回滚滚动"在 Copilot 界面里滚不动**——根本没东西可滚。要从外部驱动滚动，得把真正的 PageUp / PageDown **按键字节注入当前 pane**（用复用器的 send-keys / write），而不是触发复用器的 scrollback：

| 键 | 转义序列 | 十进制字节 |
|----|----------|-----------|
| PageUp | `ESC [ 5 ~` | `27 91 53 126` |
| PageDown | `ESC [ 6 ~` | `27 91 54 126` |

`/help` 没列这两个键（只列 `ctrl+o/e 展开 timeline`），以源码为准。源码锚点：搜 `1049h`（alt-screen 开关）、`1002h`（鼠标追踪）、`pageup`（输入解码表 + pager handler，多个视图都有这套 handler，所以"注入这两个键"是通用正确的滚动方式）。

### 终端颜色 / 主题（colorMode）

TUI 自带 **5 套真彩色（truecolor，直接发 RGB）调色板**，由 `~/.copilot/settings.json` 的 `colorMode` 选（搜 `"colorblind"` 看这份数组）：

```
default · github · dim · high-contrast · colorblind
```

默认 `default`。`github` 是 GitHub 官方 Dark & Light 配色，但被 feature-flag `COPILOT_GITHUB_THEME` 门控（staff/experimental 才在 `/themes` 里出现）。

#### 主题是正交两层：colorMode × 明暗

排查"字发淡 / 主题不对"必须分清这两层（独立）：

1. **colorMode**（上面 5 个）决定"语义 → 色阶级别"的映射。
2. **明暗（light/dark）** 决定喂进去的色阶：同一个 `textPrimary`，浅色阶给深灰字、深色阶给浅灰字。

明暗不是手选的，是**探测**出来的：

- **主路**：发 **OSC 11**（`\x1B]11;?\x1B\\`，问终端默认背景色）→ 算 `luminance`（亮度）判明暗。
- **备路**：读 `COLORFGBG` 环境变量（形如 `fg;bg`，`bg=15` 白 = 浅）。

**关键坑（实测）**：`COLORFGBG` 只是 OSC 11 **探测失败时**的 fallback；OSC 11 **成功**（哪怕返回错值）就压过 `COLORFGBG`。所以当终端（如某些复用器）对 OSC 11 回了"黑背景"，手动设 `COLORFGBG="0;15"` 也救不回来——Copilot 拿到 OSC 11 的黑就判深色、用浅色字、落在浅背景上发淡。Copilot **没有**"直接钉死 light/dark"的开关（`appearance` 是内置 CSS 词表里的属性名，不是设置项），明暗只能靠这两条探测路。源码锚点搜 `]11;?` / `COLORFGBG` / `luminance`。

> 典型场景：zellij web 浅色主题下 Copilot 字发淡 = 复用器 OSC 11 回黑被误判深色。修复见 `software` skill 的 Zellij 章节（zellij `≥0.44.3` 修了 web 模式 OSC 11 回黑）。换 `colorMode` 只换调色板映射、不改明暗判定，治标不治本。**诊断时记住 [bash 工具拿不到显示 tty](#拿不到用户的显示-tty)**——OSC 探测命令得让用户在交互 pane 手动跑。

---
## 权限与目录信任

### 三套独立机制：`trustedFolders` / `permissions-config` / 会话级 allowed-dir

#### 症状

`~/.copilot/config.json` 的 `trustedFolders` 已经包含 `$HOME`（覆盖整棵 home 树），按直觉子目录任意上溯访问都不应该被拦。但从 `~/projects/<subdir>` 启动 Copilot 后，agent 读 `~/projects/.shared-config.json`（在启动 cwd 的**父目录**）时仍弹：

```
Allow directory access
This action may read the following path outside your allowed directory list.
  ~/projects/.shared-config.json
1. Yes
2. Yes, and add these directories to the allowed list
3. No (Esc)
```

`/allow-all` 开了也没用。

#### 三套机制对照

| 机制 | 存放位置 | 作用 | 持久化 |
|---|---|---|---|
| **启动信任** | `~/.copilot/config.json` 的 `trustedFolders`（`~/.copilot/settings.json` 有镜像副本） | 决定启动 copilot 时是否还弹 "trust this folder for future sessions" 全屏 prompt | ✅ 写盘 |
| **命令 / 写入审批** | `~/.copilot/permissions-config.json` 的 `locations.<launch-cwd>.tool_approvals` | 按 "启动 cwd" 分组的 `kind: commands` / `kind: write` 审批，控制 `shell(...)` / 文件写入的"曾经批过的"放行列表 | ✅ 写盘 |
| **会话级 allowed-dir** | **仅内存**（`events.jsonl` / `permissions-config.json` / `session-state` 都无持久化字段） | 控制每次 file read/write 的目录边界。初始化为启动 cwd 树。`/list-dirs` 查、`/add-dir` 加；弹窗里选 "Yes, and add..." 等价于本次 session 的 `/add-dir` | ❌ 重启即丢 |

持久化文件位置参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：`~/.copilot/config.json`（应用状态）、`settings.json`（用户设置，`trustedFolders` 有镜像）、`permissions-config.json`（工具/目录授权，按启动 cwd 分组）。`~/.copilot` 是默认 configDir，可被 `COPILOT_HOME` 整体改写；`permissions-config.json` 解析优先级 `--config-dir` > `COPILOT_HOME` > 默认。

#### 根因

弹窗 "outside your allowed directory list" 指的是**第三套**——会话级 allowed-dir 列表。它的初始值就是启动 cwd 树，**完全不读 `trustedFolders`**。

所以：

- 在 `~/projects/<subdir>` 启动后，会话 allowed-dir = `{<subdir> 及子树}`，不含 `<subdir>` 的兄弟和父目录。
- 哪怕 `trustedFolders` 里写了 `$HOME`，只能让启动时不弹 trust prompt，**不会**扩展会话 allowed-dir。

#### 解决（按推荐顺序）

1. **从想要的根目录启动**（一劳永逸）：`cd <root> && copilot`
2. **启动后立刻 `/add-dir <path>`**：只对当前 session 有效
3. **弹窗里选 "Yes, and add..."**：等价于上一条
4. **没有"永久 allowed-dir"机制**，CLI 也没有 `--add-dir` 启动 flag

#### 教训

- 官方文档[about-copilot-cli#trusted-directories](https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli#trusted-directories) 说 "Trusted directories control where Copilot CLI can read, modify, and execute files" 听起来涵盖所有文件访问，实际只管启动信任。运行时目录边界是另一套。
- 三套同主题机制位置和作用都不一样（`config.json` / `permissions-config.json` / 内存）；看到字段名带 "trust" 或 "allow" 不能想当然认为是同一回事。
- 从子目录启动 copilot 是隐性陷阱：直觉以为 `trustedFolders` 包含父目录就够了，实际还得让启动 cwd 本身覆盖你想访问的范围。

#### 相关 issue / 文档

- 参考官方文档[about-copilot-cli#trusted-directories](https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli#trusted-directories)：启动信任目录的概念与作用域
- 参考官方文档[use-copilot-cli](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli)：会话中授权访问目录外文件、`/add-dir`
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：`config.json` / `settings.json` / `permissions-config.json` 的存放与解析优先级

---

### `COPILOT_ALLOW_ALL` ≠ `--allow-all` / `--yolo`

#### 症状

`.envrc` 里 `export COPILOT_ALLOW_ALL=1`，期望等价于 `--allow-all` / `--yolo`。实际表现：

- ✅ 命令、写入、MCP 工具不再弹审批
- ✅ cwd 子树内的文件读写正常
- ❌ **cwd 外的路径访问仍弹 "Allow directory access"**

#### 一、env var 只挂在 `--allow-all-tools` 上

CLI 选项注册段：

```js
.addOption(new Aa("--allow-all-tools", "...required for non-interactive mode")
            .env("COPILOT_ALLOW_ALL"))             // ← 唯一带 .env() 的
.option("--allow-all-paths", "Disable file path verification ...")      // 无 env
.option("--allow-all-urls",  "...")                                     // 无 env
.option("--allow-all",       "...alias --yolo")                         // 无 env
```

`.env(name)` 只挂在 `--allow-all-tools`。`--allow-all-paths` / `--allow-all-urls` / `--allow-all` 都**没有任何 env 绑定**，只能通过 CLI flag 启用。

#### 二、commander 对布尔 flag 的 `.env()` 是宽松解析

commander.js 对**布尔型** flag 的 `.env()` 来说，env var 只要是**非空字符串**就视为真——`"1"`、`"true"`、甚至 `"false"` 都会让 flag = true。所以 `COPILOT_ALLOW_ALL=1` 在这条路径上**确实生效**，让 `allowAllTools=true`。

#### 三、`--allow-all` ≡ `--yolo`，且都是"三合一"展开

`app.js:~14164070`：

```js
.option("--allow-all", "Enable all permissions (equivalent to --allow-all-tools --allow-all-paths --allow-all-urls)")
.option("--yolo",      "Enable all permissions (equivalent to --allow-all-tools --allow-all-paths --allow-all-urls)")
```

帮助文本一字不差。运行时 `txr()`（`app.js:~12477961`）把它俩 OR 到同一个变量：

```js
function txr(t) {                          // t = commander 解析后的 options
  let e = t?.allowAll || t?.yolo;          // ← 两个 flag 在这里合流
  return {
    allowAllTools: !!(t?.allowAllTools || e),
    allowAllPaths: !!(t?.allowAllPaths || e),
    allowAllUrls:  !!(t?.allowAllUrls  || e),
  };
}
```

所以 `--yolo` ≡ `--allow-all` ≡ `--allow-all-tools --allow-all-paths --allow-all-urls`。

而 env var 只能让 `allowAllTools` 为真，另外两个保持 false → path verification 闸和 URL 审批闸照常跑。

#### 四、另外 5 处直接 `process.env.COPILOT_ALLOW_ALL === "true"`（严格相等）

不走 commander 的字符串严格比较点，**全部都是绕开 `wZ.isFolderTrusted(...)`** 的判断，分两类用途：

**类一：MCP workspace 配置加载（3 处）**

```js
// bLa：扫 workspace 找 .mcp.json
let n = process.env.COPILOT_ALLOW_ALL === "true"
        ? void 0                                   // 跳过 trust 检查
        : l => wZ.isFolderTrusted(l, r);           // 否则逐个 isFolderTrusted

// 主流程
let Kt = process.env.COPILOT_ALLOW_ALL === "true"
       || a === 1
       || await wZ.isFolderTrusted(s, o);
sN({ ..., includeWorkspaceSources: Kt });

// ACP 模式
let p = process.env.COPILOT_ALLOW_ALL === "true"
     || await wZ.isFolderTrusted(d, t.settings);
sN({ ..., includeWorkspaceSources: p });
```

作用：决定 workspace 里发现的 `.mcp.json` 算不算可信，要不要把它的 MCP server 加载进来。

**类二：启动时 "trust this folder" 弹窗（2 处）**

```js
let Ue = process.env.COPILOT_ALLOW_ALL === "true"
       || await wZ.isFolderTrusted(xa);            // xa = launch cwd
if (!Ue) try {
  (await _Ee(He)).find(H => H.isTrusted && NR(H.workspaceFolder, xa)) && (Ue = true);
} catch {}
Ue ? Su(1) : (Su(2), Qe(true));                    // Su(1)=信任 / Su(2)=弹窗

// catch 兜底
} catch {
  process.env.COPILOT_ALLOW_ALL === "true" ? Su(1) : (Su(2), Qe(true));
}
```

> **5 处的本质都是 `isFolderTrusted` 的短路**——`=== "true"` 通过就跳过 isFolderTrusted，否则走 `wZ.isFolderTrusted(...)` 判断 folder 是否在 `trustedFolders` 里。`=1` vs `=true` 在这里的差距，等价于"当 `trustedFolders` 没覆盖该目录时是否仍然信任它"。

#### 完整对照表

| 代码路径 | 怎么读 env | `=1` 的效果 | `=true` 的效果 |
|---|---|---|---|
| commander → `--allow-all-tools` | 布尔 flag 的 `.env()` 宽松解析 | ✅ 触发 | ✅ 触发 |
| MCP workspace 加载（3 处）→ isFolderTrusted 短路 | `=== "true"` 严格比较 | ❌ 仍走 isFolderTrusted | ✅ 短路 |
| 启动 trust folder 弹窗（2 处）→ isFolderTrusted 短路 | `=== "true"` 严格比较 | ❌ 仍走 isFolderTrusted | ✅ 短路 |
| `--allow-all-paths` / `--allow-all-urls` | 无 env 绑定 | 永远 false | 永远 false |
| `--allow-all` / `--yolo`（互为别名，三合一展开） | 无 env 绑定 | 永远 false | 永远 false |

#### 实际后果

- 如果 launch cwd 已经在 `trustedFolders` 子树下，`isFolderTrusted` 本来就过 → `=1` 和 `=true` 没区别，看不到副作用。
- **新机器 / `trustedFolders` 还空**：`=1` 会让 workspace MCP 不自动加载，并且每次启动都弹 trust 提示；改成 `=true` 才正常。
- **目录访问审批（"outside your allowed directory list"）任何 env 值都救不了**——必须 CLI flag `--allow-all-paths` 或 `--allow-all` / `--yolo`。

#### 解决：三种实操方案

`.envrc` 里只能 `export` env，不能写 alias / 函数（direnv 只把 env 注入回父 shell，shell 内部状态会丢）。三种实操方案：

**方案 A：全局 alias（最简单，但每个 shell 都生效）**

```bash
# ~/.bashrc 或 ~/.bash_aliases
alias copilot='copilot --yolo'
```

**方案 B：PATH-shim wrapper（按目录生效，离开自动撤回）**

工作区里建一个 wrapper 脚本：

```bash
# .bin/copilot（chmod +x）
#!/usr/bin/env bash
# 把自己所在目录从 PATH 摘掉，避免 exec copilot 时无限递归
self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATH="$(printf %s "$PATH" | tr ':' '\n' | grep -vxF "$self_dir" | paste -sd:)"
export PATH
exec copilot --yolo "$@"
```

```bash
# .envrc
PATH_add "$PWD/.bin"
```

进入这个目录时 `which copilot` 指向 wrapper；离开时 direnv 把 `.bin` 从 PATH 撤回。

**方案 C：env var + alias 组合**

```bash
# .envrc：值必须是 "true"（非 "1"），让 5 处 isFolderTrusted 短路也通过
export COPILOT_ALLOW_ALL=true

# 但 path/url 维度还得靠 alias，env 那条路救不了
alias copilot='copilot --allow-all-paths'   # 或 --yolo
```

**权衡**：`--allow-all-paths` / `--yolo` 让 agent 能读到 `~/.ssh/`、`~/.config/` 之类，有风险。不想全开就接受目录弹窗、必要时 `/add-dir` 临时加白。

#### 教训

- **CLI flag 和 env var 不是简单的对应关系**——`COPILOT_ALLOW_ALL` 名字像 `--allow-all`，实际只挂在 `--allow-all-tools`。看名字猜对应一定要去源码确认 `.env()` 绑在哪。
- **commander 的 `.env()` 对布尔 flag 是宽松解析**——任何非空字符串都为真。但**业务代码里直接 `process.env.X === "true"` 又是严格比较**——同一个 env var 两套读法并存时，值只能写官方推荐的（这里就是 `"true"`），别用 `1` 偷懒。
- **`isFolderTrusted` 是目录信任决策的核心函数**——看到目录相关的"为什么有的弹有的不弹"，先去源码搜 `isFolderTrusted` 的所有 caller，每个 caller 的短路条件都可能是个"开后门"的旁路。
- **`--allow-all` 和 `--yolo` 完全等价**——`txr()` 里 OR 到同一个变量，再 OR 进 tools/paths/urls 三个 bool。CLI 没有"yolo 比 allow-all 更狂"之类的差别，纯粹只是别名。

---

### `/rewind` 在非 git cwd 直接拒绝

#### 症状

在非 git 目录（多子项目父目录、自己没有 `.git`）启动 Copilot CLI，`/rewind`（aka `/undo`）拒绝执行，提示大意是"不在 git 仓库里"。即使只想回退几个对话 turn、不在乎文件回滚，也被挡。

#### 排查与根因

每个 session 目录 `~/.copilot/session-state/<id>/rewind-snapshots/backups/` 下放的是被改文件的**完整字节拷贝**（明文 ASCII），`index.json` 列出每次 turn 的快照、`fileCount`、`backupHashes`、可选 `gitCommit/gitBranch/gitStatus`。所以 revert 的源头**完全是文件备份，根本不调 git**。

但 `RewindManager`（变量名 `A6e`）的静态构造硬性短路：

```js
static async create(e, r) {
  let n = await hs(process.cwd());                  // hs() 是 git rev-parse 包装
  if (!n.found) return { ok: false, reason: "no-git-repo" };
  ...
}
```

只要 cwd 不在 git 仓库里，`RewindManager` 直接不创建，**无论你想回退会话还是文件**。这是 Copilot 自己加的硬性前置检查，不是 revert 实现的技术依赖。

git 在 rewind 流程里只是辅助（省空间：tracked 且干净的文件可能不全量备份，靠 commit hash 还原；安全网：rewind 后告诉你"现在偏离了哪个 commit"），都不是必需的。

#### 解决（按推荐度）

1. **空 `.git` 骗过去**（推荐）：在父工作区 `git init` + `echo '*' > .gitignore`。子项目各自的 `.git` 优先匹配，不受影响；父目录 `git status` 永远空，但 `RewindManager.create` 能过 `no-git-repo` 检查。
2. **进具体子项目再启动 copilot**：每个子项目都有自己的 `.git`。缺点：跨子项目的会话必须重起。
3. **`/clear` 或 `/new` 开新会话**：彻底丢上下文，相当于重置而不是 rewind。
4. **官方反馈**：`/feedback` 要求拆开"会话 rewind"和"文件 rewind"，或对 `no-git-repo` 改成 warning 而不是 hard fail。

#### 教训

- **报错文案 ≠ 技术根因**——"不在 git 仓库"听起来像技术限制，扒源码才知道是 product check。
- **找证据先看磁盘 artifact**：`~/.copilot/session-state/<id>/` 下的 `rewind-snapshots/`、`events.jsonl`、`session.db` 是 ground truth，比猜代码逻辑准。
- **空 `.git` 是绕过仓库存在性检查的通用 trick**——很多工具的"必须在 git 仓库里"检查都只看 `git rev-parse --show-toplevel` 是否成功，跟里面有没有内容、有没有 commit 都无关。

---
## Git 认证 / Credential helper

### Bash 工具 env 黑名单下的 `git push` 对策

agent bash 里 `$GITHUB_PERSONAL_ACCESS_TOKEN` 永远为空（黑名单），所以任何依赖该变量名的 git credential helper 都会以空密码失败。三种对策：

#### 1. 换一个不在黑名单里的变量名（推荐）

把 token 存进比如 `MY_GH_PAT`、`<PROJECT>_GH_TOKEN` 这种 Copilot 不识别的名字，credential helper 也改成引用新名字。helper 配置走 `GIT_CONFIG_KEY_n / VALUE_n` env 是干净的（这组 env 不在黑名单里），agent shell 里 `git push` 直接通。

```bash
# .envrc 片段
export MY_GH_PAT="ghp_xxx..."
_n="${GIT_CONFIG_COUNT:-0}"
export "GIT_CONFIG_KEY_$_n=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$_n="
export "GIT_CONFIG_KEY_$((_n+1))=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$((_n+1))=!f(){ test \"\$1\" = get && printf 'protocol=https\nhost=github.com\nusername=<user>\npassword=%s\n' \"\$MY_GH_PAT\"; }; f"
export GIT_CONFIG_COUNT=$((_n+2))
unset _n
```

详细机制见 [用 `GIT_CONFIG_COUNT` env 临时注入 credential helper](#用-git_config_count-env-临时注入-credential-helper)。

#### 2. 用 `gh auth git-credential`

让 agent 端 `gh` 登录账号拥有目标仓写权限即可（`gh` 自己的 token 不在黑名单里，且 `gh auth setup-git` 把 helper 写进 `~/.gitconfig` 就够）。

```bash
gh auth status                # 确认账号有目标仓写权限
gh auth setup-git             # 注入 credential helper 到 ~/.gitconfig
git push                      # 不需要任何 -c 临时参数
```

注意：`gh auth setup-git` 会改全局 `~/.gitconfig`，scope 比方案 1 大；其他项目（可能用别的账号）也会受影响。

#### 3. 让用户在 host shell push

commit 由 agent 做，push 由用户在自己的 terminal 跑。最稳妥但最麻烦。

---

### 用 `GIT_CONFIG_COUNT` env 临时注入 credential helper

#### 场景

希望工作区内 `git push https://github.com/...` 自动用正确账号的 token，但**不想跑 `gh auth setup-git`**——那条命令会把 helper 写进全局 `~/.gitconfig`，对工作区**外**的所有项目（包括用别的账号的）也生效，是 scope 溢出。

#### 关键发现

git 2.31+ 支持用一组 env 变量临时注入配置（scope = `command`，优先级介于命令行 `-c` 和 `~/.gitconfig` 之间）：

```
GIT_CONFIG_COUNT=N
GIT_CONFIG_KEY_<i>   GIT_CONFIG_VALUE_<i>     # i ∈ [0, N-1]
```

git 启动时把这 N 对 `(key, value)` 当成虚拟 config 项注入。用 `git config --show-scope --get-all <key>` 能看到 scope=`command` 的来源。

这组 env 变量名 (`GIT_CONFIG_*`) 不在 Copilot CLI 的 bash 工具 env 黑名单里，所以从 host shell direnv export 之后，能完整传到 agent bash 子进程。

#### 解决：direnv 注入内联 credential helper

放在工作区根 `.envrc`（direnv 自动加载/卸载）：

```bash
export MY_GH_PAT="ghp_xxx..."     # 变量名故意避开 GITHUB_PERSONAL_ACCESS_TOKEN
                                  # （Nhe 黑名单，agent shell 拿不到，详见前面章节）

_n="${GIT_CONFIG_COUNT:-0}"       # 累加，避免覆盖 Copilot 注入的 KEY_0=safe.bareRepository
export "GIT_CONFIG_KEY_$_n=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$_n="                                          # ← 空值，清空之前继承的 helper 链
export "GIT_CONFIG_KEY_$((_n+1))=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$((_n+1))=!f(){ test \"\$1\" = get && printf 'protocol=https\nhost=github.com\nusername=<user>\npassword=%s\n' \"\$MY_GH_PAT\"; }; f"
export GIT_CONFIG_COUNT=$((_n+2))
unset _n
```

效果：

| 加 env 后 | 不加 env |
|---|---|
| `git push` 自动用 `MY_GH_PAT` 认证 | terminal 弹 `Username for 'https://github.com':`，hang 住等输入 |

#### 几个易踩坑点

1. **`credential.helper` 是累加列表不是覆盖**——必须先写一条空值 `helper=`（git 约定：空字符串清空之前所有 helper），再写 `helper=!...`，否则会先调系统 keychain 等继承下来的 helper。
2. **必须 append 到现有 COUNT 后面**——Copilot CLI 自己会注入 `GIT_CONFIG_COUNT=1, KEY_0=safe.bareRepository`；从 0 开始覆盖会让 Copilot 的配置失效。`_n="${GIT_CONFIG_COUNT:-0}"` 是关键。
3. **direnv 配合**：cd 进工作区自动 export 这堆变量，离开自动 unset（direnv 跟踪 .envrc 启停的 env diff，dynamically-named vars 也算）。改 `.envrc` 后要 `direnv allow` 重新授权（基于文件 hash）。
4. **不要用 `GH_TOKEN` / `GITHUB_TOKEN` / `GITHUB_PERSONAL_ACCESS_TOKEN`**——前两个 git / gh CLI 会自动读，第三个在 Copilot CLI 的 bash 工具 env 黑名单（`Nhe`）里 agent shell 读不到。用一个 git/gh/Copilot 都不识别也不过滤的变量名（如 `MY_GH_PAT`），只在 credential helper 里显式引用。
5. **作用域只限工作区**：因为 env 是 direnv 按目录加载，cd 出工作区后 env 自动被 direnv 清掉；其他项目的 git 完全不受影响。

#### 教训

- **想给 git 加临时配置不要改 `~/.gitconfig`**——`-c key=val` 命令行级、`GIT_CONFIG_*` env 级、`.git/config` 仓库级，三种都比改 user-level 干净。
- **`gh auth setup-git` ≠ "用 gh 推 git"**——那只是把 gh 当 helper **持久化**到 `~/.gitconfig` 的快捷脚本；想要等价但不持久的效果，自己注 `GIT_CONFIG_*` 即可。
- **scope=`command` 是 env 注入的标志**——排查"我没在哪写过这条 config 怎么 git 看到了"时，用 `git config --show-scope --show-origin --list` 一目了然。
- **不需要 `gh` 做中间人**——credential helper 可以是任意可执行脚本 / 内联 shell function，直接 printf 即可，比依赖 `gh auth git-credential` 更简单、更可控。

---

### `gh repo fork` 跨账号 clone 后 push 用错 SSH 身份

#### 症状

工作区配的是账号 A，跑：

```bash
gh repo fork upstream/x --clone --fork-name x
```

fork 操作本身成功（API 调用走 `GH_TOKEN` / `gh` 登录态，账号没问题），clone 出来的 origin 是 `git@github.com:<account-a>/x.git`。但后面 `git push origin main` 报：

```
ERROR: Permission to <account-a>/x.git denied to <account-b>.
```

很迷惑——明明 token 是账号 A 的。

#### 根因

跟 `gh` CLI 没关系，是 SSH 阶段错配。`~/.ssh/config` 里通常写的是：

```
Host *
    IdentityFile ~/.ssh/id_ed25519
```

而本机这把默认 key 注册在**账号 B** 名下（账号 A 的 key 可能叫 `id_ed25519_alt`，但 SSH 默认不会拿）。GitHub 看到的是这把 key 对应的账号，所以 push 被拒。

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub        # 看 fingerprint
ssh -T git@github.com                       # → "Hi <wrong-account>!" 一目了然
```

#### 解决

三选一：

| 方案 | 怎么做 | 适合 |
|---|---|---|
| **A**（最简单）| 把 push URL 改 HTTPS 走 token：`git remote set-url --push origin https://github.com/<account-a>/x.git`，然后用 [上节的 GIT_CONFIG_COUNT helper](#用-git_config_count-env-临时注入-credential-helper) 自动 push | 一次性跨账号 fork |
| B | ssh config 加别名：`Host github.com-alt` + `IdentityFile ~/.ssh/id_ed25519_alt`，clone 时把 URL 改成 `git@github.com-alt:<account-a>/x.git` | 长期维护多账号项目 |
| C | `gh config set git_protocol https`，让 gh 默认 clone 用 HTTPS，push 直接走 token | 统一所有 gh 操作 |

#### 教训

- `gh repo fork --clone` 默认走 SSH protocol（看 `gh config get git_protocol`），用的是本机默认 ssh key，跟 `GH_TOKEN` 完全无关。
- "推之前看一眼 `git remote -v` 和 `ssh -T git@github.com`" 是跨账号场景的卫生习惯。
- **`GH_TOKEN` / `gh auth` 的纪律只覆盖 API 操作**（gh CLI 调 REST/GraphQL），**git transport** 是另一条独立通道，要单独管。
- **"能 clone 就以为身份对了"是错觉**：如果你的 SSH 默认账号被对方加为 collaborator，clone 完全 OK，但 push 到 `<别人>/...` 还是会因为没写权限被拒。GitHub 对**完全没访问权限**的私有仓回 `Repository not found`（不告诉你仓存在不存在），对**只读 collaborator** 回真实数据，对**没写权限的 push** 回 `Permission denied`。三种回复对应三种状态，看响应内容能反推自己的身份关系。

---
## 重试策略 patch（transient API error）

### 症状与根因

Copilot CLI 在网络抖动 / HTTP/2 GOAWAY / 模型上游瞬时不可用时，会以以下错误中断当前 turn：

```
✗ Execution failed: Error: Failed to get response from the AI model;
  retried 5 times (total retry wait time: 6.00 seconds)
  Last error: CAPIError: Connection error.
```

5 次重试一共才等了 6 秒，对真实的网络问题完全不够 —— 跟 [github/copilot-cli#2421](https://github.com/github/copilot-cli/issues/2421) 等一堆 issue 是同一类。CLI 内部默认（`app.js` 里的 `initDefaultOptions`）：

- `retryPolicy.maxRetries = 5`
- 非-API 错误（连接挂、HTTP/2 GOAWAY 这类拿不到 HTTP 响应的）每次重试间隔 = `Ke.retryAfter * (0.8 + Math.random() * 0.4)`，retryAfter 可能不到 1 秒。

并且**没有任何 `settings.json` / CLI flag / 环境变量**能改这两个值 —— 实测过完整的 `cli-config-dir-reference` 和 `cli-command-reference`，只有 `--timeout`（作用于工具调用，不是模型 API 请求）和 `continueOnAutoMode`（rate-limit 时切 auto 模式，跟连接错误无关）。要改只能 patch 二进制。

### 应用 patch

脚本：`software/scripts/patch-copilot-cli-retry.sh`

```bash
~/TiMidlY-projects/skills/skills/.curated/software/scripts/patch-copilot-cli-retry.sh
```

它做两件事：

1. `maxRetries: 5 → 10`（重试次数翻倍）。
2. 给非-API 错误的每次等待加一个 4 秒下限（`_t = Math.max(_e * jitter, 4)`）。

综合效果：原来 ~6 秒就放弃，patch 后 ≥40 秒后才放弃。够吃掉大多数瞬态抖动，又不会卡到夸张。

**实现细节**：

- 只 patch `app.js`（CLI 实际跑的那份），不动 `sdk/index.js`（programmatic SDK，CLI 不走它）。
- 用 `node -e` 做正则替换，比 sed 处理 minified JS 安全（变量名跨版本会变，例如 `let Xe=...,ut=Ne*Xe` vs `let It=...,_t=_e*It`，脚本里的正则用反向引用 `\1` 适配）。
- 幂等：每个 patch 点带 `/*tmy-retry-patch*/` marker，已 patch 的文件会跳过。
- 备份：每个 `app.js` 同目录留 `app.js.orig.timidly-bak`，回滚直接 `cp ...bak app.js`。
- 覆盖范围：扫描所有可能的 pkg cache 根（`$COPILOT_CACHE_HOME/pkg` / `$XDG_CACHE_HOME/copilot/pkg` / `~/Library/Caches/copilot/pkg`（macOS）/ `$COPILOT_HOME/pkg` / `~/.copilot/pkg`），把每个版本目录下的 `app.js` 都 patch 掉。

**验证 patch 已生效**：

```bash
grep -oE 'maxRetries:e\?\.retryPolicy\?\.maxRetries\?\?[0-9]+[^,]{0,30}' \
  ~/.cache/copilot/pkg/linux-x64/*/app.js
# 期望看到：??10/*tmy-retry-patch*/  而不是 ??5
```

### Auto-update 后需要重跑

CLI 默认 `autoUpdate: true`（`~/.copilot/settings.json`），后台拉新版本到一个新的 `~/.cache/copilot/pkg/linux-x64/<new-version>/`，loader 自动切到最高版本。**新版本目录里的 `app.js` 是干净的**，需要再跑一次脚本。

判断要不要重跑：

```bash
grep -L 'tmy-retry-patch' ~/.cache/copilot/pkg/linux-x64/*/app.js
# 列出来的就是还没 patch 的版本，列空就说明都 patch 过了
```

可选：把脚本接到一个定时任务 / shell startup hook 里。但因为 patch 是幂等的、且 auto-update 不频繁（基本 days 级），手动跑也够。

> 同款思路适用于任何想调 Copilot CLI 内部常量的场景（比如改 `defaultRetryAfterSeconds` / `maxRetryAfterSeconds` 之类的 rate-limit 配置）。锚点选**字面量唯一的 minified 片段**（带 `e?.retryPolicy?.` 这种独特路径），不要选纯数字（容易撞）。
## 模型 / 思考程度（reasoning effort）：默认档从哪来 & hack 成最高档

### 机制（够用即可）

- **一行选定**：`copilot --model <id> --effort <level>`（`--effort` == `--reasoning-effort`，choices `none/low/medium/high/xhigh/max`；`--context <tier>` 管上下文档位）。三者都是**会话级覆盖、不落盘**。优先级：flag > `COPILOT_MODEL` env（**effort 无对应 env**）> `settings.json`（`model`/`effortLevel`/`contextTier`）> 内置默认。
- **持久默认只在全局** `~/.copilot/settings.json`（无目录级 settings；`$COPILOT_HOME` 可整体挪位）。TUI 里选模型/档位会写回这里——所以「上次选择」就是「默认」。
- **打字版 `/model <id>` 只吃一个 model 参数，且执行时必然把 `effortLevel`/`contextTier` 清空**（→ 回落该模型默认档）。故它塞不进 effort（`/model xxx-max` 会被当非法 model 报错）；会话内单独设档只有无参 `/model` 的两步选择器。
- **每个模型的「默认档」来自 bundle 内静态表 `XAt`（源标签 `"sweagent-capi"`）的 `clientOptions.defaultReasoningEffort`**：按 model→family→vendor 匹配、缺省硬回落 `"medium"`，再过 native `modelResolverPickModelDefaultReasoningEffort` 用该模型 `supportedReasoningEfforts` 校验一遍。**用户不可配**（无 per-model effort 配置键；`subagents.agents.<name>.effortLevel` 只管子代理）。这既是 picker 里 `(default)` 标签的来源，也是 typed `/model` 回落的目标。
- 源码链：`_x → bfe`（读 `XAt` 默认档）供 picker 标签与 `zC` 解析兜底；SDK 客户端另有一份从配置对象直读的 `defaultReasoningEffort`（形如 `…defaultReasoningEffort:t?.defaultReasoningEffort`）。

### hack：让每个模型默认用它支持的最高档

**目的**：免掉每次手选 / 带 `--effort`，让 picker `(default)`、启动/`zC` 解析、以及多数情况下 typed `/model` 的回落都落到该模型最高档（opus/sonnet→`max`、gpt→`xhigh`）。

改根函数 `bfe`（`_x`、`zC` 都经它）。**apply / 备份 / 幂等 marker / 扫所有版本目录 / auto-update 后重跑，规矩全同上文《重试策略 patch》**——只是 marker 用 `tmy-max-effort`、备份用 `app.js.pre-maxeffort.bak`。核心是一条 `node` 正则替换（带反向引用，自动适配跨版本改名的 `bfe`/`ty`/参数名，勿硬编标识符）：

```js
// 锚点：唯一，只命中 bfe 一处（先 dry-run 数匹配数 === 1 再落盘）
/async function (\w+)\((\w+),(\w+),(\w+),(\w+)\)\{return (\w+)\("sweagent-capi",\2,\3,\5\)\.clientOptions\?\.defaultReasoningEffort\?\?"medium"\}/g
// 替换：取 supportedReasoningEfforts 里最高档；取不到就回落原逻辑
'async function $1($2,$3,$4,$5){/*tmy-max-effort*/let _c=$6("sweagent-capi",$2,$3,$5),_s=_c&&_c.supportedReasoningEfforts;if(_s&&_s.length){for(const _o of["max","xhigh","high","medium","low"])if(_s.includes(_o))return _o}return _c?.clientOptions?.defaultReasoningEffort??"medium"}'
```

- **验证**：`node --check` 打过补丁的 `app.js` + `~/.local/bin/copilot --version` 能跑；`grep -l tmy-max-effort ~/.cache/copilot/pkg/linux-x64/*/app.js`；开**新**会话看 picker `(default)` 是否已在顶档（当前已运行的会话不受影响）。
- **局限**：只改 `bfe` 覆盖 picker 标签 + 启动/`zC` 解析。若实测**会话内** typed `/model` 仍回落 medium（native `setModel` 读的是配置对象那份 `defaultReasoningEffort`，不经 `bfe`），再把源码里 `defaultReasoningEffort:<src>?.defaultReasoningEffort` 那 1~2 处 copy 站点也改成取 `supportedReasoningEfforts` 最高档即可。

## 上下文档位（context tier）：让 typed `/model` 默认 long_context

### 机制（与 effort 完全对称，别被「改 settings 就够」骗了）

- **context tier 和 effort 同构**：`--context <tier>`（会话级不落盘）> `settings.json` 的 `contextTier`（合法持久键，值 `default`/`long_context`；`inherit` 只给子代理）> 内置默认（⚠️ 这条优先级只在无头 `-p` 成立；交互 TUI 无视 `--context` 开关，见下条）。`long_context`（分层定价的大窗口档，如 gpt-5.x 的 1.1M）**只在该模型 `billing.token_prices` 里带 `long_context` 时才存在**——不支持的模型只有 `default` 一档，写了也没有第二档。
- **⚠️ 交互 TUI 无视 `--context` 开关，只认 `settings.json` 的 `contextTier`**（实测 1.0.69-1，opus-4.8）：`copilot --context long_context` 进交互 → `/context` 仍 264k；同一开关进无头 `-p` → resolved 窗口 264k→**1M**、prompt 200k→**936k**。源码：CLI action 里 `gn=t.context??l.contextTier` 确实把开关并进了 `contextTier:gn` 传给各 session builder，无头 `createSession({…contextTier:e.contextTier…})` 直接用（认开关）；但**交互 App 有个挂载 effect 只从盘重灌** tier——`(0,bd.useEffect)(()=>{…let De=await rn.load(l)||{};V(De.contextTier)…},[l,r])`（`V`=tier state 的 setter，`[H,V]=useState(SN.EMPTY)`；守卫 `if(r?.getContextTier?.()!==void 0)return`，交互启动时 `r` 没带 tier 故落空 → 走 `rn.load(settings).contextTier`）。**所以交互启动要长上下文＝改 `settings.json` `contextTier: long_context`，别指望 `--context` 开关。**
- **完整修复 = 两件套**：① `settings.json` `contextTier: long_context`（管交互启动即长上下文）＋ ② 下面的 bundle 补丁（管 typed `/model` 切换后不掉档）。缺 ② 时实测：settings 设了 long_context、启动 1M，但 typed `/model gpt-5.4` 再 `/model claude-opus-4.8` 切回 → `/context` 从 1M 掉回 264k，且 `settings.json` 的 `contextTier` 被**物理删掉**（就是下面那句 `contextTier=void 0` 落盘）。补丁后同一测试：切回仍 1M、settings 不被抹。
- **坑与 effort 一模一样**：打字版 `/model <id>` 执行时 `<state>.contextTier=void 0` **落盘清空** settings（连 `effortLevel` 一起清），且 native `me.setModel` 用 3 参调 `RG`（第 4 参 = 新 tier 缺省）→ **同时把本会话内存 state 重置回 default**。所以「先用无参 `/model` 选择器选好 long_context」扛不住之后任何一次 typed `/model` 切模型。**想让 typed `/model` 默认 long_context，纯改 settings 无效、必须 hack**——和 effort 一个道理。曾错误地以为「effort 要 hack、context tier 改 settings 就行」，是假的不对称，别再犯。
- stock 下只有无参 `/model` 两步选择器能设 tier（picker 路径给 `RG` 传满 4 参）；typed `/model <id>` 走清空路径。

### hack：typed `/model` 后落到 long_context（带模型能力守卫）

**apply / 备份 / 幂等 marker / 扫所有版本目录 / auto-update 后重跑，规矩全同《重试策略 patch》**——marker `tmy-lc-default`、备份 `app.js.pre-longcontext.bak`。脚手架（扫版本目录 + 备份 + `node --check` + 写回）与 retry/effort 补丁同构，下面只列**两处锚点 + 守卫**这些逆向出的、无法自行重建的部分。两处都用 `[\w$]+` 匹配标识符（minify 会造含 `$` 的名，`\w` 不含 `$`——effort hack 那条硬编 `\w` 的教训）。

**⚠️ 特性前置守卫（第一大坑，务必先做）**：`long_context` 分层定价是 **1.0.68+** 才有的特性，靠 native `v.modelsIsTieredTokenPrices` 判定。老版本（1.0.66 / 1.0.67）**根本没有这个 native 函数**——注入引用它的守卫会**运行时崩溃**，而 `node --check` **查不出**（语法合法、只是跑到时 undefined）。所以打补丁前必须 `if(!src.includes("modelsIsTieredTokenPrices")) skip`。这坑真实踩过：放松锚点后 6 个版本**全匹配 + node --check 全过**，看着全成功，实际老版本一敲 `/model` 就炸。

**PATCH#1 持久化**（typed `/model` 落盘点，别再清空 tier）：把 `<state>.contextTier=void 0` 改成 `=(<守卫>?"long_context":void 0)`。锚点用反向引用锁死这一段、并从中拿到 model 变量：

```js
// 锚点（\1=state 对象, \2=目标 model id 变量）：
/([\w$]+)\.model=([\w$]+)===([\w$]+)\?void 0:\2,\1\.effortLevel=void 0,\1\.contextTier=void 0/
// 模型对象经该锚点前方就近的 .find(p=>p.id===\2) 捕获，喂给守卫；只把末尾 `\1.contextTier=void 0` 换成守卫三目。
```

**PATCH#2 本会话**（`me.setModel` 的 switch 调用，别再重置回 default）：给 `RG(U,void 0,{…contextTier…})` **补上第 4 参** = 守卫 IIFE（从模型列表 `list.find(m=>m.id===U)` 取模型算 tier），把 stock 的「第 4 参缺省 → 重置 default」改成「支持则 long_context」。

```js
// 锚点定位 setModel 及其模型列表 list，再在其后就近那次 4 参不足的 RG 调用补参：
/setModel:async\(([\w$]+),([\w$]+)\)=>\{let ([\w$]+)=([\w$]+)\?\.type==="success"\?\4\.list:void 0;/
// 补的第 4 参：(()=>{let _m=list.find(x=>x&&x.id===U);...return <守卫>?"long_context":void 0})()
```

**守卫表达式**（两处共用，照抄 native 能力判定 `H7n`，不支持的模型返回 `void 0` → 回落 default 不崩）：

```js
model && model.billing && model.billing.token_prices
  && v.modelsIsTieredTokenPrices(JSON.stringify(model.billing.token_prices))
  && "long_context" in model.billing.token_prices && model.billing.token_prices.long_context
```

### 用真 PTY 实测 TUI hack（可复用手法）

改 bundle 后光 `node --check` + `--version` 不够——得验 typed `/model` 真的落到 long_context。这类「要驱动交互式 TUI、按键、读屏幕」的验证，用 Python stdlib **`pty.fork()`** 起真 PTY（`pexpect` 没装也不必装）：

- 子进程 `os.execvp("copilot",…)` 拿到的是**真控制终端**（非 mock）；`ioctl(fd, TIOCSWINSZ, struct.pack("HHHH",行,列,0,0))` 设窗口、`TERM=xterm-256color`。
- master fd：`select.select([fd])` 读 = 看屏幕；`os.write(fd,ch)` = 敲键盘（`\r` 提交、`\x03` 退出）。
- **逐字符输入（~60ms/字符）**：一次性灌整行会和 TUI 自动补全竞争、把命令截断——这坑踩过。
- 验证：#1 从磁盘读 `settings.json` 看 `contextTier`；#2 正则剥 ANSI 后 grep 稳定串（`Model changed from`、footer 的 `1.1M context`）。**换一个和当前不同、且支持 long_context 的模型**（如 gpt-5.4）强制真切换，别用同款——切了等于没切，区分不出「hack 没生效」vs「本就同档」；`-p "/model"` 一次性喂会走另一条「Already using」路径（不在 app.js 里），也测不到。

**实测结论**：支持的模型（gpt-5.4 / 5.5 / opus-4.8）→ typed `/model` 后 footer 显 `(1M context)`/`(1.1M context)` + settings 落 `long_context`；不支持的（gpt-5-mini）→ 守卫返回 default、不崩。opus-4.8 实测切走再切回，`/context` 从补丁前的 264k 变 **1000k**、`settings.json` `contextTier` 不再被抹。

**脚本**：`software/scripts/patch-copilot-cli-longcontext.py`（幂等；扫版本目录；逐档 `node --check`；**两处锚点都命中才写**，否则整档回滚；pre-1.0.68 无 `modelsIsTieredTokenPrices` 自动跳过；node 自动探测 fnm/nvm/volta/PATH）。规矩全同《重试策略 patch》：备份 `app.js.pre-longcontext.bak`、marker `tmy-lc-default`、**auto-update 后要重跑**：

```bash
grep -L tmy-lc-default ~/.cache/copilot/pkg/linux-x64/*/app.js   # 列出没打的（空=都打了）
python3 <skills>/software/scripts/patch-copilot-cli-longcontext.py --apply
```

**各版本代码分布 & 清理**：1.0.66 / 1.0.67 无 `long_context` 特性（跳过）；1.0.68 / 1.0.69-0 / 1.0.69-1 有。PATCH#2 那个「3 参重置调用」的**函数名逐版本变**（`RG`@1.0.69-1、`u$`@1.0.68、`p$`@1.0.69-0），所以锚点**不能硬编函数名**——用 `<fn>(<id>,void 0,{…contextTier…})`（3 参形式，picker 的 4 参调用天然被排除）。**无自动清理机制**：每次 patch 各版本目录留一份 `app.js.pre-longcontext.bak`，auto-update 只往新版本目录堆，旧备份/旧版本目录都不自动回收，要手动清（loader 只跑最高版本，旧版本目录留着无害）。

## 运行中发消息：steer（即时插话）vs queue（排队）

> 源码偏移基线 `@github/copilot@1.0.62` 的 `app.js`（与本文件其余章节的 1.0.41 基线不同，偏移仅供参考）。

Copilot CLI **有**「Copilot 还在跑的时候继续发消息，自己选是立刻插进当前回合、还是排队等这回合结束」的能力。官方 changelog 的原话就是 **"Send messages while Copilot is thinking to steer or queue"**。但触发按键和 Codex 不一样——Codex 是 `Enter` / `Shift+Enter` 二选一，Copilot 这里是 **`Enter` vs `Ctrl+Q`**，而 `Shift+Enter` 在 Copilot 里只是换行。

| 行为 | 按键（Copilot CLI） | 内部 `mode` |
|---|---|---|
| **即时插话**（steer，注入正在跑的 turn） | **普通 `Enter`** | `immediate` |
| **排队**，等当前 turn 结束再发（FIFO） | **`Ctrl+Q`**（kitty keyboard protocol 下提示/用 `Ctrl+Enter`） | `enqueue` |
| 插入换行（多行编辑，**不提交**） | `Shift+Enter`（含 `Alt`/`Super`+`Enter`、`Ctrl+J`） | —— |
| **硬停**当前 turn（真正打断，双击 `Esc`）；**1.0.69-1 起中断会保留排队消息并接着跑**，见下方「双击 Esc 中断语义变更」 | `Esc`×2 | —— |

⚠️ 关键差异：Copilot 里区分「插话 / 排队」的是 **`Enter` vs `Ctrl+Q`**，不是 Codex 的 `Enter` / `Shift+Enter`。在 Copilot 里 `Shift+Enter` 被占用为换行。

### 证据一：源码（`app.js` v1.0.62）

**1. 键盘 handler**（输入组件 `KLr`，props 含 `disableEnterSubmit:p=!1` —— `p` 是「是否禁用回车提交」，默认 false，**不是**「忙碌」标志）：

```js
// Ctrl+Q 或 Ctrl+Enter → 带 {queued:true} 提交
if(Ye.ctrl&&Ye.code==="q"||Ye.ctrl&&Ye.code==="return"){
  !p&&e.text.trim()&&ae(e.text,{queued:!0});return}
// Shift / Alt / Super + Enter → 插入换行
if((Ye.shift||Ye.alt||Ye.super)&&Ye.code==="return"){e.insertInput("\n");return}
if(Ye.ctrl&&Ye.code==="j"){e.insertInput("\n");return}     // Ctrl+J 也是换行
// 普通 Enter → ae(e.text)（不带 queued）
if(Ye.code==="return"&&!Ye.paste){...ae(...)...}
```

`ae(text, opts)` 透传给 `onSubmit(text, attachments, opts)`。

**2. `{queued}` → `mode` 映射**（onSubmit 实现，~@10366793）：

```js
let lo = $e?.queued ? "enqueue" : "immediate";   // 普通 Enter 无 queued ⇒ immediate
Me.send({prompt:K, attachments:[...], mode:lo, billable:true})
```

**3. 分发 `send(e)`（~@4067874）—— steer/queue 真正分流处**：

```js
if(e.mode==="immediate" && this.isProcessing){      // 正在跑 ⇒ 插话
  this.addImmediateMessage(e); ...; return }
this.enqueueUserMessage(e, e.prepend);              // 否则进 FIFO 队列
!this.isProcessing && (... || await this.processQueue())
```

即：`immediate` 且 `isProcessing`（有 turn 在跑）→ `addImmediateMessage`（steer）；否则进队列。`immediate` 但当前空闲 → 落到 `enqueueUserMessage` + `processQueue`，等价于正常发一条新消息。

**4. 注入时机 —— 是「软插话」不是硬打断**：即时消息进 `ImmediatePromptProcessor`（类 `TFt`，~@3940251），它的 `async* preRequest()`（"ImmediatePromptProcessor: Injecting immediate prompts"）在 agent 循环**每一轮模型请求前**被消费（调用点 ~@2653745 `for(let ze of o?.processors?.preRequest||[])`）。所以 steer 是在**下一个工具调用轮次的边界**注入、引导后续，不会中断正在飞行的那次请求。要真正中断用 `Esc`。

**5. 两条队列在状态层分开**：reducer `kfe={Steering:"steering",Queued:"queued"}`（~@8328483），`SessionPendingMessageSet` 按 kind 分流到 `steeringMessage` vs `queuedMessages`（~@8340241）；队列管理类暴露 `getPendingSteeringMessagesDisplayPrompt()`（"immediate steering queue (interjections sent during a running turn)"）和 `getPendingQueuedItems()` 两组，footer 分别展示。

### 证据二：官方 changelog（包内 `changelog.json`）

- **"Send messages while Copilot is thinking to steer or queue"**（功能本体）
- **"Ctrl+D no longer queues a message; use Ctrl+Q or Ctrl+Enter to queue"**
- "Ctrl+d now favors deleting character after cursor, with queueing moved to ctrl+q (or ctrl+enter)"
- "Queue hint correctly shows ctrl+enter instead of ctrl+q when kitty keyboard protocol is active"
- "Enable steering during plan mode"
- "Messages sent during `/compact` are automatically queued"
- "Ctrl+C and double-Esc remove pending queued messages one at a time instead of all at once"

### 证据三：内置 `/help`

- `ctrl+q - enqueue prompt`
- `shift+enter - insert newline` ← 佐证 `Shift+Enter` 不参与提交分流，只换行

> 注：官方在线文档（docs.github.com 的 use-copilot-cli 页）只提了 `Esc` 停止、`Shift+Tab` plan mode，**没有**明文写 steer/queue 的 `Enter`/`Ctrl+Q` 语义；该语义由 `/help` 键位 + changelog + 源码三方印证。

### 双击 Esc 中断语义变更：1.0.69-1 起「中断后接着跑排队消息」

**现象**：主 turn 在跑、且你已排队一条 prompt，双击 `Esc` 不再是「停掉并丢弃队列」，而是**停掉当前 turn、然后自动把排队的 prompt 接着跑**。

**变更历史**（对比缓存里 6 个版本 `~/.cache/copilot/pkg/linux-x64/*/app.js`，边界干净）：

| 符号 | ≤1.0.68 | 1.0.69-0 | **1.0.69-1** |
|---|---|---|---|
| `interruptMainTurn` | 无 | 无 | **有** |
| `flushQueuedAfterAbort` | 无 | 无 | **有** |
| `"interrupt-main"`（键位 action） | 无 | 无 | **有** |

- **旧行为（≤1.0.69-0）**：双击 `Esc`（这套「首击置 pending、再击才执行」的双击门早在 `≤1.0.68` 就有，提示即 `press esc again to interrupt`）**只走 abort**——agent 循环尾部判定 `if((!e||…)&&itemQueue.length>0)` 里 `e`（aborted）为 true ⇒ 不进 `processQueuedItems` ⇒ turn 直接 idle、排队消息被丢。
- **新行为（1.0.69-1）**：**同一个**双击 `Esc`，中断**之后**改为保留并接着跑排队消息——官方 changelog（包内 `changelog.json`）原话 **"Double-press Esc now interrupts the running main turn (flushing queued messages), or stops background agents when the main agent is idle"**（PR `github/copilot-agent-runtime#11859`），"flushing" 不是丢弃、是**冲出去执行**；同版还多出「主 agent 空闲时双击 Esc → 停后台 agent」一路（`stop-agents`/`cancelAllBackgroundAgents`，旧版无此符号）。

**源码链（`app.js` v1.0.69-1）**：

1. 键位分发把「主 turn 在跑时的双击 Esc」映射到新 action `"interrupt-main"`，写死带 `flushQueued`：
   ```js
   // 键名表：MKr={…,"interrupt-main":"interrupt",…}
   case"interrupt-main":{ he.isRemote
     ? he.abort({reason:nT.UserInitiated})            // 远程 session 仍是纯 abort（可能丢队列）
     : he.interruptMainTurn({flushQueued:!0}) }       // 本地走新逻辑
   ```
2. 新方法 `interruptMainTurn` —— 差异总开关：`flushQueued` 分支只清「系统」待发项、**保留用户排队消息**，并置标志 `flushQueuedAfterAbort`；否则才是老式全清 `clearPendingItems()`（此分支当前无键位触达）：
   ```js
   async interruptMainTurn(e){ return this.isProcessing ? (
     e?.flushQueued
       ? this.flushQueuedAfterAbort = this.clearSystemPendingItems()   // 保留用户队列
       : (this.flushQueuedAfterAbort=!1, this.clearPendingItems()),    // 全丢（未接键位）
     this.cancelProcessing("Session interrupted",…,{preserveBackgroundWork:!0}),
     {interrupted:!0}) : {interrupted:!1} }
   ```
3. abort 收尾时消费该标志，把 `(!e||r)` 从 false 翻成 true，于是队列被跑起来：
   ```js
   let e=…signal.aborted, r=e&&this.flushQueuedAfterAbort; this.flushQueuedAfterAbort=!1;
   if((!e||r)&&this.itemQueue.length>0&&…){ await this.processQueuedItems(); return }
   ```

**社区讨论**：[github/copilot-cli#3692](https://github.com/github/copilot-cli/issues/3692) *"Escape should cancel the current task and focus the pending queued prompt (not discard it)"*（open，`area:input-keyboard`，报告于 v1.0.60-0）——正是这次改动落地的诉求。注意评论里有**反对声**（`@IanGraingerGMSL`：按 Esc 就该全停、别烧 token，"interrupt and send" 应绑到别的键）；另有人（`@jphreid`）抱怨双击 Esc 不灵、常要狂按。

**当前（1.0.69-1）中断/清队列方案速查**：

| 想要的效果 | 操作 |
|---|---|
| 中断当前 turn，**并接着跑**排队的 prompt | **双击 `Esc`**（本地 session；这是新默认，无开关可关） |
| 只清排队消息、**不停**当前 turn | `Ctrl+C`（一次弹一条 `removeMostRecentPendingItem()`，FIFO 逐条删） |
| 中断当前 turn 且**丢弃**队列 | 无直接键位（`clearPendingItems()` 全清分支存在但未接键位）；远程 session 的双击 Esc 走纯 `abort` 仍近似此效果 |
| 主 agent 空闲时双击 Esc | 转为 `stop-agents`：停后台 agent，而非中断主 turn |

## Chronicle 搜索给 resume ID：必须给本地 ID

`/chronicle search` 用 `session_store_sql` 查的是**云端 + 本地两套 session store 合并**的结果（每行带 `_query_source` = `cloud` / `local`）。同一个会话在两套库里 **session ID 不一样**：云端是一份同步副本，本地是 `~/.copilot/session-state/<id>/` 下真正能 resume 的那份。

**`copilot --resume=<id>` 只认本地 ID**——拿云端 ID 去 resume 会直接报 `No session, task, or name matched`。

所以 chronicle 给用户用来 resume 的 ID 时：

- **只给本地 ID**，即 `_query_source = 'local'` 且 `~/.copilot/session-state/<id>/` 目录存在的那个。
- 搜索结果里如果同名会话既有 cloud 又有 local，**优先取 local 行的 ID**，别取 cloud 的。
- 不确定时本地核一下：`ls ~/.copilot/session-state/<id>` 有目录才是可 resume 的。
- 纯 cloud-only（本地无目录）的会话：明说「本机不可 resume，状态在另一台机器上」，别给一个 resume 不了的 ID。

---
## `/share html` 对话导出（逆向）

把 live 会话导出为一份**单文件、可交互**的 HTML 报告——暗色 Primer 主题、按类型筛选、搜索、可折叠条目、侧栏 map、上下条用户消息跳转。下面是想离线复刻同款产物时必须看懂的几件事。

### `/share` 与 `/export`

同一条命令的两个名字——`/export` 是 `/share` 的纯别名（同一个 command 对象、同一份 `args` 解析器、同一份 execute 路径），行为完全一致。子命令 `file` / `html` / `gist` / `research` 都共享。

### 真实数据源 = `~/.copilot/session-state/<id>/events.jsonl`

`/share html` 在 live 会话里从内存 timeline 取条目；写盘的同一份事实就是这份 NDJSON。**离线复刻只读这一份即可**。每行 `{type, data, id, timestamp, parentId}`，时间戳是 ISO+UTC（末尾 `Z`），离线端要自己 `astimezone()` 转本地——share 在浏览器里走 `Date.toLocaleString()`，默认 en-US locale 用 **12 小时制 AM/PM**（"6/26 11:04:21 PM" 其实就是 23:04:21，曾经误导）。

### events → entries 映射

一条事件可能产出**多条** timeline-entry。最反直觉的是 `assistant.message`：它**同时**携带 `reasoningText` + `content` + `toolRequests[]`，要按顺序拆成 reasoning 条目 + copilot 条目，tool 调用则交给后续 `tool.execution_start/complete` 配对。其余几类的常用映射：

| 事件 | 产出 | 备注 |
|---|---|---|
| `user.message.content` | user 条目 | 渲染用 `content`，不是 `transformedContent`（后者注入了 system_reminder）|
| `tool.execution_start` + `tool.execution_complete`（同 `toolCallId`） | **一个** merged-tool 条目 | 不配对的孤儿 complete 也独立产出，详见下"合并"小节 |
| `system.notification` | notification 条目 | 渲染时 `data-type` 是 `notification`（不是 `system_notification`，注意命名）|
| `session.info` (`infoType=model`) | info 条目，text = `data.message` | "Model changed from X to Y" 就是这个 |
| `abort` | info 条目，text = `"Operation cancelled by user"` | bundle 用 `emitEphemeral` 同步发了一条 `session.info(infoType=cancellation)`，**ephemeral 不写盘**——离线只能从 `abort` 自己合成同款文案 |
| `hook.*` / `assistant.turn_*` / `system.message`（system prompt） / `session.start` | 跳过 | UI 噪音 / 巨大无用 |

dispatcher 还能接受这些类型（live 会话偶尔出现，离线 events.jsonl 极少）：`error / warning / handoff / compaction / task_complete / group_tool_call_*`——形状已知，离线复刻可以兜底渲染。

### live-only 条目：离线复刻**注定**少几条

share 输出里有几类 info 是 bundle 直接 `addTimelineEntry()` 进**内存** timeline、从不写盘，离线无法重建：

- `Tip: /cwd`（mascot 启动横幅；bundle 里的 "Tip: " 字面量只在终端 React-Ink UI 里）
- `Session shared successfully to: ...`（`/share` 命令自己的回执；离线场景本就无意义）
- `Response was interrupted ... Retrying...`（重试机制 ephemeral）
- `Operation cancelled by user` 的源头（`session.info` cancellation）也是 ephemeral；离线靠 `abort` 重造文案

对照过真 share HTML：`Tip:` 那条字符串在 events.jsonl 里 **0 次实命中**（任何"命中"都来自 hook.start 把我们自己的 bash 命令文本完整存了进去）。**接受这缺口比硬造一条更诚实**。

### Tool 条目合并

渲染层看到的"每个工具调用一条卡片"是经过合并的结果——bundle 在装配前把 `tool_call_requested` 和它的 `tool_call_completed`（按 `callId`）**配对成单条**：`{kind:"merged-tool", entry:{name, args, intentionSummary, result, …}}`。result 上的 `type ∈ {success, failure, rejected, denied, pending}` 决定边框色 + 图标 + 是否加 `entry-error-bg`。

### Tool 参数的"单行摘要"

`grep`/`glob`/`bash`/`view`/`edit`/`create` 这几个 known 工具有专门的紧凑摘要规则（如 `bash → "$ <command>"`、`grep → "<pattern> in <glob>"`、`view → "<path> (lines N-M)"`），渲染成 inline code。其它工具回退到完整 JSON pretty-print。结果 log 渲染分三档：`result.markdown===true` 用 markdown 渲染；不是 markdown 但看着是 diff（含 `diff --git` 或同时含 `@@`/`+++`/`---`）用 `<pre data-lang="diff">`；其它就是普通 `<pre><code>`。

### 文档壳与每条 entry 的 DOM 契约

整页是**纯字符串模板**装配，没用任何前端框架：

- 文档壳 = doctype + `<html data-color-mode="dark" data-light-theme="light" data-dark-theme="dark">` + 内联 Primer light/dark CSS + sticky header（search box + filter-pills + Compact/Collapse all/Expand all/Map/Theme 按钮）+ `.scroll-container`（sidebar + main + jump-prev/jump-next 浮动按钮）+ 内联 vanilla JS。
- 每条 entry = `<div class="entry [collapsed] border-{type}" data-type="…" data-index="N" id="entry-N">` + `entry-header` + `entry-body`。**`data-type` 是英文且 JS 只读 data-* 属性、不读 label 文字**——所以离线版本汉化标签是安全的，改 `data-type` 才会破。
- 各类型默认折叠态遵循 bundle：`copilot / user / error / task_complete` 默认展开；`reasoning / info / warning / tool / group / handoff / compaction / notification` 默认折叠。

### CSS / JS 资产

CSS 由三段拼成：Primer light + Primer dark + share 自家壳（sticky-header / filter-pills / sidebar / entry / tool 等专属规则）。JS 是一个 vanilla IIFE，负责折叠展开 / 主题切换（`localStorage("copilot-share-theme")`）/ 类型筛选 + 搜索（`/` 聚焦）/ sidebar map / 上下条用户消息跳转 / compact mode / mini 语法高亮 / hash deeplink——0 依赖、0 外网请求。

### 离线复刻的关键陷阱：JS 模板字符串的"双反斜杠"

CSS 和 JS 在 bundle 里都是模板字符串字面量。源码层每个反斜杠都是双写的（`\\u2600`、正则 `\\b`、`\\n`、…），bundle **运行时**模板字符串引擎把 `\\` → `\` 再写进页面。

如果离线抽取**按原始字节复制**这些字面量直接落盘，所有真反斜杠都是双的——**主题按钮看着不响应**（textContent 拿到字面量 `\u2600` 不是 ☀），**搜索/语法高亮的正则全坏**（`\\b` 在正则里=匹配字面反斜杠），`split('\\n')` 不分行。

正确做法：把模板字符串体当作 JS 模板字面量**求值一次**再落盘——拿任何 JS 运行时跑 `\`...\`` 就行，让引擎自己折叠转义。另一个细节：`pFs` 自身的 mini-highlighter 包含一个**字面反引号**（源码里用反斜杠转义），所以"下一个反引号定界"会切错——边界要靠下一个相邻函数（不是下一个反引号）。

### 离线复刻参考实现

`dredge-up` skill（`skills/.curated/dredge-up/`）已经基于上述逆向做了一份**离线**复刻——从 `events.jsonl` 重建时间线、复刻同款 entry DOM、复用 share 抽出的 CSS/JS，并加了 agent 总结注入。要做"离线把会话存档成 HTML"这件事直接用它，不要重新逆向。

## `web_fetch` 的 SSRF 守卫为何拦 fake-ip（及定点放行补丁）

### 现象

Mihomo 开 `enhanced-mode: fake-ip` 时，`web_fetch` 抓**任何**外网域名都报：

```
WebFetchBlockedUrlError: ... resolves to blocked address 198.18.x.x.
URLs must not target loopback, private, or link-local addresses.
```

不是网络不通——是 `web_fetch` **发请求前的一道安全预检**撞上了 fake-ip。对照组：同环境 `curl` 抓同一 URL 正常（`curl` 没这道检查、且会把域名交给代理或经 TUN 走 fake-ip）。

### 机制：SSRF 守卫在联网前先判黑

SSRF（Server-Side Request Forgery，服务端请求伪造——诱导服务端去请求它本不该碰的内网 / 云元数据地址如 `169.254.169.254`、`127.x`、内网面板）。`web_fetch` 的防线是：**先用系统 DNS 解析目标主机名，再把每个解析到的 IP 逐个判黑，命中就在发请求前抛错**。

```js
// app.js（符号名随版本变，锚点用稳定字面量 .networkIsBlockedIp / .hookResolveAndValidateUrl /
//         错误文案 "resolves to blocked address" / env "COPILOT_WEB_FETCH_ALLOW_LOCALHOST"）
async function kNe(t,e={}){                        // resolve + validate
  let r=new URL(t); ...                            // 只放行 http/https
  let a = isIP(host)? [...] : await dns.lookup(host,{all:!0});  // ← 系统 DNS → fake-ip 拿到 198.18.x
  if(e.allowLocalhost && a.every(是127/::1)) return a;
  for(let {address:l} of a)
    if(g4n(l)) throw new Error(`... resolves to blocked address ${l}. URLs must not target ...`);
}
function g4n(t){ return w.networkIsBlockedIp(t) }  // ← native 判黑；198.18.0.0/15 属 RFC2544 保留段 → true
```

fake-ip 模式下 Mihomo 给每个域名都回 `198.18.x.x`（RFC2544 基准测试保留段），**必落黑名单** → 每个外网域名都被拒。**这是 fake-ip 专属坑**：切 `redir-host`（回真实公网 IP）就不触发，没有这个问题。fake-ip 原理见 `network` skill 的 mihomo fake-ip 章节。

### 没有可用的配置开关

唯一相关 env 是 `COPILOT_WEB_FETCH_ALLOW_LOCALHOST=1`，但 `kNe` 里它**只放行 `127.x` / `::1`**，fake-ip 段不在其列；也没有 `allowPrivate` 之类。所以想让 fake-ip 下的 `web_fetch` 可用，**只能改源码**（用户明确要的就是改源码，不是"用 curl 绕过"——curl 是并行手段，不能让 `web_fetch` 本身可用）。

### 关键：判黑逻辑正在从 JS 迁往 native（移动靶）

同一个检查在版本间**换过形态**，patch 前必须先辨形：

| 形态 | 版本（实测） | JS 里长什么样 | 可 patch 点 |
|---|---|---|---|
| **A · JS 判黑** | ~1.0.66-0 | `function <g>(<t>){return <w>.networkIsBlockedIp(<t>)}`，被 resolve+validate helper（`kNe`）调用 | 直接包 `networkIsBlockedIp` |
| **B · native 判黑** | 1.0.66-1→-2 起，含 1.0.69-x | helper（`smt`）只剩 `await <E>.hookResolveAndValidateUrl(...)`，**JS 里已无 `networkIsBlockedIp`、连 `node:dns` 都不 import** | 只能重写 `smt` 自己解析 |

GitHub 把整套"解析 + 判黑"搬进 Rust 绑定了。后果：**每次 `copilot update` 都可能让 patch 失效**，甚至需要重新逆向定位。（本 skill 的经验：1.0.66→1.0.69 期间 CLI 自更新 4 个版本，旧 patch 全部落空。）

### 补丁思路（定点放行，最小爆炸半径）

只放行 fake-ip 池 `198.18.0.0/15`（`198.18.x` / `198.19.x`，本就没有合法内网服务），其余仍交给原判黑——`127/10/192.168/169.254/::1/云元数据`照旧全拦。比"让判黑恒 `false`"安全得多。两形态分别：

- **形态 A**：把 `networkIsBlockedIp(t)` 包成 `/^198\.1[89]\./.test(t)?false:<原调用>`。
- **形态 B**：重写 `smt`——自己 `await import("node:dns/promises")` 解析主机名，**全部**解析成 fake-ip 时直接返回地址（绕过 native）、否则回落 `await <E>.hookResolveAndValidateUrl(...)`（保留真实内网防护）。

工程约束（照搬 `app.js` patch 的通用套路，另见本仓 `software` skill 的 `patch-copilot-cli-retry.sh`）：

- **锚点用稳定字面量**（`.networkIsBlockedIp` / `.hookResolveAndValidateUrl`），用 `\w+` 捕获每版不同的混淆名；别硬编码符号名。
- **幂等 marker** + **备份**原文件；patch 后 `node --check`，语法坏了自动回滚。
- **扫所有 pkg cache 版本目录**（`~/.cache/copilot/pkg/<platform>/<version>/app.js`，SEA 安装；npm 安装见「安装方式与看源码」）。
- **只对新启动的会话生效**——运行中的 `copilot` 已把 `app.js` 载入内存；`copilot update` 拉新版本后**须重跑** patch（新版本目录未打）。
- 验证：patch 后**开新会话**让它 `web_fetch` 任意外网 URL；若错误从 "blocked address" 变成连接 / 代理类错误，说明判黑已绕过、但底层 fetch 对 pinned fake-ip 的出站路径有问题（查 `proxyEnv` / `pinnedAddresses` 与 TUN 直连）。
