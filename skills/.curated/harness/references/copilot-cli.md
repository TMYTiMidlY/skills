# Copilot CLI runtime notes

Copilot CLI internals and debugging notes for the CLI process model, local runtime behavior, shell tool environment, permissions, terminal behavior, Git authentication, retry patching, and in-flight steering. The original reverse-engineering notes used stable string literals in the bundled `app.js`; symbol names and byte offsets are version-specific and should be rechecked after CLI upgrades.

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
## 运行中发消息：steer（即时插话）vs queue（排队）

> 源码偏移基线 `@github/copilot@1.0.62` 的 `app.js`（与本文件其余章节的 1.0.41 基线不同，偏移仅供参考）。

Copilot CLI **有**「Copilot 还在跑的时候继续发消息，自己选是立刻插进当前回合、还是排队等这回合结束」的能力。官方 changelog 的原话就是 **"Send messages while Copilot is thinking to steer or queue"**。但触发按键和 Codex 不一样——Codex 是 `Enter` / `Shift+Enter` 二选一，Copilot 这里是 **`Enter` vs `Ctrl+Q`**，而 `Shift+Enter` 在 Copilot 里只是换行。

| 行为 | 按键（Copilot CLI） | 内部 `mode` |
|---|---|---|
| **即时插话**（steer，注入正在跑的 turn） | **普通 `Enter`** | `immediate` |
| **排队**，等当前 turn 结束再发（FIFO） | **`Ctrl+Q`**（kitty keyboard protocol 下提示/用 `Ctrl+Enter`） | `enqueue` |
| 插入换行（多行编辑，**不提交**） | `Shift+Enter`（含 `Alt`/`Super`+`Enter`、`Ctrl+J`） | —— |
| **硬停**当前 turn（真正打断） | `Esc` | —— |

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
