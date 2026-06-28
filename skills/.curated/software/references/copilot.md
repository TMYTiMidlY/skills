# GitHub Copilot CLI

Copilot CLI 内部行为的逆向工程与排障笔记。涵盖：进程模型、bash 工具 env 处理、权限与目录信任、Walk-Up（向上查找）机制与各子系统（Custom Instructions / MCP / Skills / Hooks）、git 认证。

大部分章节附 `app.js` 源码摘录与字节偏移；偏移**仅供参考**，混淆后的符号 (`xj` / `_R` / `Nhe` / `bBt` / `sN` / `cKr` …) 是 esbuild 产物的稳定特征，会随版本变化但用关键字面量（`COPILOT_RUN_APP` / `COPILOT_ALLOW_ALL` / `GITHUB_PERSONAL_ACCESS_TOKEN` / `safe.bareRepository` / `AGENTS.md` / `.mcp.json` …）能在新版本里重新定位。源码定位基线为 `@github/copilot@1.0.41` 的 `app.js`（esbuild 混淆产物）。

## 目录

- [进程模型](#进程模型)
  - [三层结构：loader → app.js](#三层结构loader--appjs)
- [安装方式与看源码](#安装方式与看源码)
  - [npm 安装：直接读 node_modules](#npm-安装直接读-node_modules)
  - [二进制发行版（SEA）：读自解包的 cache](#二进制发行版sea读自解包的-cache)
  - [按字面量抠源码片段](#按字面量抠源码片段)
- [Bash 工具](#bash-工具)
  - [Env 黑名单：为何 `git push` 在 agent 里总是 401](#env-黑名单为何-git-push-在-agent-里总是-401)
  - [`BASH_ENV` 只对非交互 bash 生效](#bash_env-只对非交互-bash-生效)
  - [拿不到用户的显示 tty](#拿不到用户的显示-tty)
- [TUI 与终端](#tui-与终端)
  - [滚动与翻页键](#滚动与翻页键)
  - [终端颜色 / 主题（colorMode）](#终端颜色--主题colormode)
- [权限与目录信任](#权限与目录信任)
  - [三套独立机制：`trustedFolders` / `permissions-config` / 会话级 allowed-dir](#三套独立机制trustedfolders--permissions-config--会话级-allowed-dir)
  - [`COPILOT_ALLOW_ALL` ≠ `--allow-all` / `--yolo`](#copilot_allow_all--allow-all--yolo)
  - [`/rewind` 在非 git cwd 直接拒绝](#rewind-在非-git-cwd-直接拒绝)
- [Walk-Up（向上查找）机制总览](#walk-up向上查找机制总览)
  - [核心 walk-up 函数 `bBt`](#核心-walk-up-函数-bbt)
  - [每种配置/指令文件到底会不会 walk-up 到 git root？](#每种配置指令文件到底会不会-walk-up-到-git-root)
  - [子系统总对比表](#子系统总对比表)
  - [通用 workaround：direnv symlink](#通用-workarounddirenv-symlink)
- [Custom Instructions（指令文件）](#custom-instructions指令文件)
  - [指令文件清单与搜索路径](#指令文件清单与搜索路径)
  - [git root 级指令：直接查找](#git-root-级指令直接查找)
  - [cwd 级指令：当 cwd ≠ git root 时额外查找](#cwd-级指令当-cwd--git-root-时额外查找)
  - [中间层指令：`vfi` walk-up](#中间层指令vfi-walk-up)
  - [子目录嵌套 AGENTS.md：`xfi` BFS](#子目录嵌套-agentsmdxfi-bfs)
  - [子目录嵌套 .github/instructions：`Rfi` glob](#子目录嵌套-githubinstructionsrfi-glob)
  - [用户级指令](#用户级指令)
  - [Env 覆盖 `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`](#env-覆盖-copilot_custom_instructions_dirs)
  - [指令注入顺序与合并策略](#指令注入顺序与合并策略)
  - [`--no-custom-instructions` 开关](#--no-custom-instructions-开关)
- [Hooks（preToolUse / Safety Net）](#hookspretooluse--safety-net)
  - [Hooks 发现机制（不做 walk-up）](#hooks-发现机制不做-walk-up)
  - [marketplace 分发的 Safety Net plugin 装了不触发：双 bug](#marketplace-分发的-safety-net-plugin-装了不触发双-bug)
  - [项目级 hook 路径解析停在 git root（多 repo 工作区漏装）](#项目级-hook-路径解析停在-git-root多-repo-工作区漏装)
  - [`cc-safety-net` 自定义规则：user scope vs project scope](#cc-safety-net-自定义规则user-scope-vs-project-scope)
- [MCP 配置](#mcp-配置)
  - [三种 MCP 配置文件的区别](#三种-mcp-配置文件的区别)
  - [`.mcp.json` 上溯停在 git root（多 repo 工作区漏装）](#mcpjson-上溯停在-git-root多-repo-工作区漏装)
  - [`.mcp.json` headers 里 `${VAR}` 展开不生效](#mcpjson-headers-里-var-展开不生效)
- [Skills 发现](#skills-发现)
  - [项目级 `.agents/skills` 上溯停在 git root（与 hooks/mcp 同款）](#项目级-agentsskills-上溯停在-git-root与-hooksmcp-同款)
- [Git 认证 / Credential helper](#git-认证--credential-helper)
  - [Bash 工具 env 黑名单下的 `git push` 对策](#bash-工具-env-黑名单下的-git-push-对策)
  - [用 `GIT_CONFIG_COUNT` env 临时注入 credential helper](#用-git_config_count-env-临时注入-credential-helper)
  - [`gh repo fork` 跨账号 clone 后 push 用错 SSH 身份](#gh-repo-fork-跨账号-clone-后-push-用错-ssh-身份)
- [重试策略 patch（transient API error）](#重试策略-patchtransient-api-error)
  - [症状与根因](#症状与根因)
  - [应用 patch](#应用-patch)
  - [Auto-update 后需要重跑](#auto-update-后需要重跑)
- [Chronicle 搜索给 resume ID：必须给本地 ID](#chronicle-搜索给-resume-id必须给本地-id)
- [运行中发消息：steer（即时插话）vs queue（排队）](#运行中发消息steer即时插话vs-queue排队)
- [`/share html` 对话导出（逆向）](#share-html-对话导出逆向)

---

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

> 典型场景：zellij web 浅色主题下 Copilot 字发淡 = 复用器 OSC 11 回黑被误判深色。修复在 [zellij 参考的「终端默认背景（OSC 11）」](zellij.md)（zellij `≥0.44.3` 修了 web 模式 OSC 11 回黑）。换 `colorMode` 只换调色板映射、不改明暗判定，治标不治本。**诊断时记住 [bash 工具拿不到显示 tty](#拿不到用户的显示-tty)**——OSC 探测命令得让用户在交互 pane 手动跑。

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

## Walk-Up（向上查找）机制总览

Copilot CLI 的多种项目级配置与指令文件共用一套 **walk-up**（从 cwd 向上遍历到 boundary）发现策略。本节是机制层面的统一说明，后面的 Custom Instructions / MCP / Skills / Hooks 各章节落具体规则与排障。

### 核心 walk-up 函数 `bBt`

MCP、Skills 的项目级发现都经过同一个 `bBt` 函数。它从 `startPath`（通常是 cwd）向上走，每层检查目标文件/目录是否存在，**撞到 boundary（通常是 git root）就停**。

```js
// app.js — bBt（简化）
async function bBt(t, e, r, n) {
  // t = startPath (cwd), e = boundary (git root), r = [{kind, relativePaths}], n = trust callback
  let o = [], s = normalize(e), a = normalize(t), l = 0;
  for (;;) {
    let c = l === 0 ? "project" : "inherited";
    for (let d of r) for (let m of d.relativePaths) {
      let p = join(a, m);
      existsSync(p) && o.push({path: p, directory: a, depth: l, source: c});
    }
    if (a === s) break;                          // ★ 撞 boundary 就停
    let u = dirname(a);
    if (u === a || (n && !await n(u))) break;    // 到 fs 根 / 不可信目录
    a = u; l++;
  }
  return o;
}
```

**关键行为**：

- 先 push 当前层，再判断 `a === s`，所以 **boundary 本身那层的文件能被收录**
- `source` 标签：depth 0 = `"project"`，>0 = `"inherited"`
- boundary 不存在（非 git repo）时各子系统行为不同：Skills 回退到 `$HOME`，MCP 只读 cwd 一份

**Custom Instructions 不走 `bBt`**——它有自己一套专用函数（`aKr`/`oKr`/`iKr`/`sKr` 单点查 + `vfi` 扫中间层），效果**等同**于 walk-up 但实现方式不同；见下面 Custom Instructions 章节。**Hooks 完全不 walk-up**，只看固定两处路径。

### 每种配置/指令文件到底会不会 walk-up 到 git root？

逐一回答"如果我在 `<gitRoot>/packages/billing/` 工作，`<gitRoot>/` 下的文件能不能被找到"：

| 文件 | 会 walk-up 到 git root 吗？ | 机制 |
|------|---------------------------|------|
| **AGENTS.md** | ✅ 会 | `oKr(gitRoot)` 直接查 git root；`vfi` 扫中间层；`oKr(cwd)` 查 cwd。三层都找到则**全部注入** |
| **CLAUDE.md** | ✅ 会 | 同 AGENTS.md（`iKr` 替代 `oKr`，额外查 `.claude/CLAUDE.md`） |
| **GEMINI.md** | ✅ 会 | 同 AGENTS.md（`sKr` 替代 `oKr`） |
| **.github/copilot-instructions.md** | ✅ 会 | `aKr(gitRoot)` 直接查 git root；`vfi` 扫中间层；`aKr(cwd)` 查 cwd |
| **.github/instructions/\*.instructions.md** | ✅ 会 | `Rfi` 在 git root 和 cwd 下分别 glob 扫描 |
| **嵌套子目录 AGENTS.md** | ✅ 向**下**扫 | `xfi` 扫子目录（不是向上），生成表格提示让 agent 按需 `view` |
| **.mcp.json** | ✅ 会 | `bBt` 从 cwd 向上逐层扫到 git root，沿途合并（last-wins） |
| **.github/mcp.json** | ✅ 会 | 同 `.mcp.json`，共用 `bBt` |
| **.agents/skills/** | ✅ 会 | `yQe`→`bBt` 从 cwd 向上逐层扫到 git root（无 git 时回退 `$HOME`） |
| **.github/skills/** | ✅ 会 | 同 `.agents/skills/`，共用 `j7e`→`yQe` |
| **.claude/skills/** | ✅ 会 | 同上 |
| **.github/hooks/** | ❌ 不会 | 只查 git root 一层，不做任何 walk-up |

**关键区别**：

- **Instructions（AGENTS.md 等）**：不走统一的 `bBt`，而是 `oKr(gitRoot)` + `vfi(中间层)` + `oKr(cwd)` 三段拼接，**效果等同于** cwd→git root 的完整 walk-up，但实现方式不同
- **MCP / Skills**：走统一的 `bBt` walk-up，一个循环搞定
- **Hooks**：完全不 walk-up

**所有 walk-up 的 boundary 都是 git root**——如果 cwd 在一个独立的子 git repo 里，上溯到子 repo 的 root 就停，看不到父目录。

### 子系统总对比表

| 子系统 | Walk-up | Boundary | 不在 git repo 时 | 用户级路径 | Env 覆盖 |
|--------|---------|----------|------------------|-----------|----------|
| **Custom Instructions**<br>(AGENTS.md 等) | `vfi`：cwd→git root **中间层**<br>（两端分别单独查） | git root | 只读 cwd | `~/.copilot/copilot-instructions.md`<br>`~/.copilot/instructions/` | `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` |
| **MCP** (`.mcp.json`) | `bBt`：cwd→git root 沿途合并 | git root | 只读 cwd 一份，不上溯 | `~/.copilot/mcp-config.json` | — |
| **Skills** (`.agents/skills`) | `bBt`→`yQe`：cwd→git root 沿途收录 | git root；无 git 时回退 `$HOME` | 一路扫到 `$HOME` | `~/.copilot/skills`<br>`~/.agents/skills` | `COPILOT_SKILLS_DIRS` |
| **Hooks** (`.github/hooks`) | ❌ 不上溯，只看 git root 一层 | git root | cwd | `~/.copilot/hooks/`（文件）<br>+ `config.json` 内联 `hooks` 键 | — |

**共同特征**：

- Boundary 都是 git root——子项目如果是独立 git repo，上溯立刻停在子项目根，看不到父目录
- 用户级路径都不受 walk-up boundary 限制

### 通用 workaround：direnv symlink

所有 walk-up 子系统在"父目录套独立子 git repo"场景下都有同样的问题：看不到父目录的配置。通用解法是 direnv 自动维护 symlink：

```bash
# .envrc
link_into_subdirs() {
  local src="$1" rel="$2" sub target excl
  [[ -f "$src" || -d "$src" ]] || return 0
  for sub in "$PWD"/*/; do
    sub="${sub%/}"
    target="$sub/$rel"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      mkdir -p "$(dirname "$target")"
      ln -s "$src" "$target"
    fi
    excl="$sub/.git/info/exclude"
    if [[ -f "$excl" ]] && ! grep -qxF "/$rel" "$excl"; then
      printf '/%s\n' "$rel" >> "$excl"
    fi
  done
}

# 按需调用
link_into_subdirs "$PWD/.github/hooks/safety-net.json" '.github/hooks/safety-net.json'
link_into_subdirs "$PWD/.mcp.json"                     '.mcp.json'
link_into_subdirs "$PWD/.agents/skills"                '.agents/skills'
link_into_subdirs "$PWD/AGENTS.md"                     'AGENTS.md'
```

direnv 本身改不了 copilot 找配置的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**；改 `.envrc` 后要 `direnv allow` 重新授权（基于文件 hash）。或者把配置搬到 user-level 路径（`~/.copilot/`（各子目录如 `~/.copilot/hooks/`、`~/.copilot/skills/`）或 `~/.agents/skills/`），绕过 walk-up boundary 限制。

后面 MCP / Skills / Hooks 章节的"多 repo 工作区漏装"排障节都复用这个 helper，不再重复定义。

---

## Custom Instructions（指令文件）

Custom Instructions 是 Copilot CLI 往 system prompt 里注入的用户/项目自定义指令。**它们不走 `bBt`**，而是用自己的一组专用函数分别处理 git root、cwd、中间层三个位置。

### 指令文件清单与搜索路径

指令文件的 convention 定义（`cKr` 数组）：

```js
// app.js — cKr
cKr = [
  {kind: "copilot", convention: ".github",      filename: "copilot-instructions.md"},
  {kind: "agents",  convention: ".",             filename: "AGENTS.md"},
  {kind: "claude",  convention: ".",             filename: "CLAUDE.md"},
  {kind: "claude",  convention: ".claude",       filename: "CLAUDE.md"},
  {kind: "gemini",  convention: ".",             filename: "GEMINI.md"},
];
```

即 Copilot CLI 能识别以下指令文件（在每个搜索位置）：

| 文件 | 搜索子路径 | 类型标签 |
|------|-----------|---------|
| `copilot-instructions.md` | `.github/` | `copilot` / `repo` |
| `AGENTS.md` | `.`（当前目录根） | `agents` / `model` |
| `CLAUDE.md` | `.` 和 `.claude/` | `claude` / `model` |
| `GEMINI.md` | `.`（当前目录根） | `gemini` / `model` |

这份单文件清单（源码 `cKr` 数组）与 CLI 启动时打印的 "Copilot respects instructions from these locations" 同源；后者还并列了 `.github/instructions/**/*.instructions.md` glob、用户级 `$HOME/.copilot/copilot-instructions.md` / `$HOME/.copilot/instructions/**/*.instructions.md` 和 env `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`（各自见下文小节）。项目级指令文件的写法参考官方文档[add-repository-instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)。

**多种文件全部合并注入，不互斥**：Copilot CLI 主动兼容其他 AI 编码工具的指令文件格式。如果仓库里同时存在 AGENTS.md、CLAUDE.md、GEMINI.md、copilot-instructions.md，**四种全部读取**，各自包裹在 `<custom_instruction>` 标签里按顺序拼接注入 system prompt。不做选择、不做冲突检测，只在 realPath 或 content 完全相同时去重（`rKr`）。

**大小写不敏感**（macOS/Linux 文件名匹配走 `Yq` 函数，先尝试精确匹配，失败后用 `readdir` + `toLowerCase()` 做 case-insensitive fallback）：

```js
// app.js — Yq
function Yq(t, e) {
  let r = join(t, e);
  if (existsSync(r)) return r;         // 精确匹配
  try {
    let n = readdirSync(t), o = e.toLowerCase(),
        s = n.find(a => a.toLowerCase() === o);
    if (s) { let a = join(t, s); if (existsSync(a)) return a; }
  } catch {}
}
```

### git root 级指令：直接查找

每种指令文件各有一个单点查找函数，直接在 git root（`t`）下查文件：

```js
// app.js — 直接查找函数
function aKr(t) {                                      // .github/copilot-instructions.md
  let e = join(t, ".github"),
      r = Yq(e, "copilot-instructions.md");
  return r ? {exists: true, path: r} : $M;             // $M = {exists: false, path: undefined}
}
function oKr(t) { return Yq(t, "AGENTS.md") ... }     // AGENTS.md
function iKr(t) { return Yq(t, "CLAUDE.md") ... }     // CLAUDE.md
function sKr(t) { return Yq(t, "GEMINI.md") ... }     // GEMINI.md
```

在主函数 `Efi` 中，**git root 和 cwd 各调一次**：

```js
// app.js — Efi（简化）
async function Efi(t, e, r, n, o) {
  // t = git root (location), e = enabled, r = cwd, n = settings
  let h = aKr(t),       // git root 下 .github/copilot-instructions.md
      g = oKr(t),       // git root 下 AGENTS.md
      f = iKr(t),       // git root 下 CLAUDE.md
      I = sKr(t);       // git root 下 GEMINI.md

  let y = r && !NR(r, t);     // cwd ≠ git root?
  let C = y ? aKr(r) : $M,    // cwd 下 .github/copilot-instructions.md
      E = y ? oKr(r) : $M,    // cwd 下 AGENTS.md
      S = y ? iKr(r) : $M,    // cwd 下 CLAUDE.md
      _ = y ? sKr(r) : $M;    // cwd 下 GEMINI.md
  // ...
}
```

### cwd 级指令：当 cwd ≠ git root 时额外查找

当 `cwd ≠ git root` 时，每种指令文件会在 cwd 额外查一次。两份都找到时**都注入**，不互相覆盖：

```js
// git root 级 → location: "repository"
Y && oe.push({id: "repo-copilot", label: ".github/copilot-instructions.md",
              sourcePath: ".github/copilot-instructions.md", content: Y,
              type: "repo", location: "repository"});

// cwd 级 → location: "working-directory"
B && C.exists && oe.push({id: "cwd-copilot", label: ".github/copilot-instructions.md",
                          sourcePath: relative(t, C.path), content: B,
                          type: "repo", location: "working-directory"});
```

AGENTS.md / CLAUDE.md / GEMINI.md 同理，git root 的 location 标记 `"repository"`，cwd 的标记 `"working-directory"`。

### 中间层指令：`vfi` walk-up

`vfi` 负责发现 **cwd 与 git root 之间**（不含两端）的指令文件。它从 cwd 的**父目录**开始向上走，到 git root **之前**停止：

```js
// app.js — vfi
function vfi(t, e) {
  // t = cwd, e = git root
  if (!t || NR(t, e)) return [];      // cwd == git root → 没有中间层
  let r = [], n = normalize(e), o = normalize(t),
      s = dirname(o);                  // ★ 从 cwd 的父目录开始
  for (; s !== n && s !== dirname(s); ) {   // ★ 到 git root 之前停
    for (let a of cKr) {               // 遍历 5 种 convention
      let l = a.convention === "." ? s : join(s, a.convention),
          c = Yq(l, a.filename);
      c && r.push({filePath: c, relativePath: relative(e, c),
                   directory: s, kind: a.kind});
    }
    s = dirname(s);
  }
  return r;
}
```

这些中间层文件被读取后，注入 prompt 时标记 `id: "inherited-*"`：

```js
// app.js — 中间层指令注入
let R = vfi(r, t);   // r = cwd, t = git root
// ...读取文件内容后...
for (let it of Le) {
  let Ke = St.kind === "copilot" ? "repo" : "model",
      Re = St.relativePath.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  oe.push({id: `inherited-${Re}`, label: basename(St.filePath),
           sourcePath: St.relativePath, content: bt,
           type: Ke, location: "repository"});
}
```

**注意**：`vfi` 用的是 `cKr`（5 种 convention），所以中间层也能发现 copilot-instructions.md、AGENTS.md、CLAUDE.md、GEMINI.md。

### 子目录嵌套 AGENTS.md：`xfi` BFS

除了向上找，Copilot CLI 还会向**下**扫描子目录中的 `AGENTS.md`（nested instructions）：

```js
// app.js — xfi
async function xfi(t, e = []) {
  // t = git root, e = additional dirs (COPILOT_CUSTOM_INSTRUCTIONS_DIRS)
  let r = [t]; r.push(...e);
  let n = hKr(r);              // 去重
  let s = (await Promise.all(n.map(async l => {
    let c = join(l, "AGENTS.md");
    if (existsSync(c)) try {
      if (!(await stat(c)).isFile()) return null;
      let d = await readFile(c, "utf-8"),
          m = relative(t, c);
      return m === "AGENTS.md" ? null   // ★ 跳过根目录那份（已由 oKr 处理）
             : {path: m, content: truncate(d)};
    } catch { return null; }
    return null;
  }))).filter(l => l !== null);
  return s.length === 0 ? void 0
       : {content: Dfi(s), source: "agents", sourcePath: "AGENTS.md (nested)"};
}
```

但注意 `xfi` **不做递归子目录遍历**——它只在传入的根目录列表的直接子目录（准确说是同级）查 `AGENTS.md`。真正的递归子目录扫描由 `LMr`（child instructions）负责。

嵌套 AGENTS.md 注入 prompt 时**不直接展开内容**，而是生成一个表格提示 agent "需要时用 `view` 工具读取"：

```js
// app.js — Dfi 生成提示表格
function Dfi(t) {
  let e = [];
  for (let r of t) {
    let o = dirname(r.path), s = x3(`${o}/`), a = x3(r.path);
    e.push(`| ${s} | '${a}' | Agent instructions for ${o}/**/* |`);
  }
  return [
    "Here is a list of nested AGENTS.md files ...",
    "Please make sure to follow the rules specified in these files ...",
    "If you have not already read the file, use the `view` tool to acquire it.",
    "| Directory | File Path | Description |",
    "| --------- | --------- | ----------- |",
    ...e
  ].join("\n");
}
```

### 子目录嵌套 .github/instructions：`Rfi` glob

`.github/instructions/**/*.instructions.md` 支持 glob 递归：

```js
// app.js — Rfi + gKr
async function Rfi(t, e, r = []) {
  // t = git root, e = cwd, r = additional dirs
  let n = [t];
  e && !NR(e, t) && n.push(e);    // cwd ≠ git root 时也扫 cwd
  n.push(...r);
  let o = hKr(n);                  // 去重
  return (await Promise.all(o.map(async a => {
    let l = join(a, ".github", "instructions");
    if (!existsSync(l)) return [];
    let c = await gKr(l);         // glob *.instructions.md
    return (await Promise.all(c.map(d => fKr(d, a))))
           .filter(d => d !== null).map(Lfi);
  }))).flat();
}

async function gKr(t) {
  let e = globPattern(join(t, "**", "*.instructions.md"));
  return glob(e, {nocase: true});
}
```

这些文件支持 **frontmatter**，包括 `applyTo`（glob pattern 限定适用范围）、`excludeAgent`（排除特定 agent 类型）、`description`（描述）：

```js
// app.js — bKr (frontmatter 解析)
function bKr(t) {
  let e = parse(t, {schema: Qfi, onUnsupportedFields: "ignore"});
  return e.kind !== "success" ? {excludeAgent: []}
       : {applyTo: e.value.frontmatter.applyTo,
          excludeAgent: e.value.frontmatter.excludeAgent,
          description: e.value.frontmatter.description?.trim() || void 0};
}
```

### 用户级指令

两个固定路径，不做 walk-up（参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference) 的 `copilot-instructions.md`、`instructions/` 条目；`~/.copilot` 是默认 configDir，可被 `COPILOT_HOME` 整体改写）：

| 路径 | 函数 | 注入 id | location |
|------|------|---------|----------|
| `~/.copilot/copilot-instructions.md` | `Nfi(n)` | `home-copilot` | `user` |
| `~/.copilot/instructions/**/*.instructions.md` | `kfi(n)` | `user-copilot-instructions` | `user` |

```js
// app.js — Nfi
function Nfi(t) {
  let e = ma(t, "config"),                       // = ~/.copilot（configDir）
      r = Yq(e, "copilot-instructions.md");
  return r ? {exists: true, path: r} : $M;
}

// app.js — kfi
async function kfi(t) {
  let e = ma(t, "config"),
      r = join(e, "instructions");
  if (existsSync(r)) {
    let n = globPattern(join(r, "**", "*.instructions.md")),
        o = await glob(n, {nocase: true});
    // ...读取、解析 frontmatter、过滤 excludeAgent...
  }
}
```

### Env 覆盖 `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`

```js
// app.js — Efi 开头
let s = process.env.COPILOT_CUSTOM_INSTRUCTIONS_DIRS
          ?.split(",").map(it => it.trim()).filter(it => it.length > 0) ?? [];
```

逗号分隔的绝对路径列表，作为额外的搜索根，传给 `xfi`（嵌套 AGENTS.md）和 `Rfi`（.github/instructions glob）。

### 指令注入顺序与合并策略

主函数 `Efi` 将所有指令源 push 到 `oe` 数组中，**顺序决定在 prompt 中的出现位置**：

```
1. home-copilot          — ~/.copilot/copilot-instructions.md
2. user-copilot-instructions — ~/.copilot/instructions/**/*.instructions.md
3. repo-copilot          — <git-root>/.github/copilot-instructions.md
4. cwd-copilot           — <cwd>/.github/copilot-instructions.md（仅 cwd ≠ git root）
5. model-agents-md       — <git-root>/AGENTS.md
6. model-claude-md       — <git-root>/CLAUDE.md  /  <git-root>/.claude/CLAUDE.md
7. model-gemini-md       — <git-root>/GEMINI.md
8. cwd-model-*           — <cwd>/AGENTS.md, CLAUDE.md, GEMINI.md（仅 cwd ≠ git root）
9. inherited-*           — 中间层（vfi walk-up 结果）
10. .github/instructions  — glob 匹配的 *.instructions.md
11. nested-agents         — 子目录嵌套 AGENTS.md（表格提示）
12. child-instructions    — LMr 递归发现的子目录指令文件
```

最终由 `lKr` 组装成 prompt 文本：

- 前 9 类（非 vscode/nested/child）包裹在 `<custom_instruction>...</custom_instruction>` 标签中
- 后 3 类（vscode/nested/child）作为 `additionalInstructions` 附加

**去重规则**（`rKr`）：同 `realPath`（symlink 解析后）或同 `content` 的文件只保留一份，sourcePath 用 `+` 连接。

### `--no-custom-instructions` 开关

```
copilot --no-custom-instructions
```

跳过整个 `eB()` 调用，不加载任何 custom instructions：

```js
// app.js — kHe
let z = l ? Promise.resolve(void 0) : eB(t, true, r, u, {...});
// l = skipCustomInstructions（来自 --no-custom-instructions）
```

#### 相关 issue / 文档

- 参考官方文档[add-repository-instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)：`.github/copilot-instructions.md`、`.github/instructions/**/*.instructions.md` 的写法与作用域
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：用户级 `~/.copilot/copilot-instructions.md`、`~/.copilot/instructions/`

---

## Hooks（preToolUse / Safety Net）

### Hooks 发现机制（不做 walk-up）

与 MCP / Skills 不同，Hooks **完全不做 walk-up**，只看两个固定位置（参考官方文档[use-hooks](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)）：

1. **项目级**：`<git-root>/.github/hooks/`（在 git repo 内用当前 git root，不在 git repo 则用 cwd）
2. **用户级**：两个来源都读——`~/.copilot/hooks/`（文件 `hooks.json` / `hooks/hooks.json`）+ `config.json`（全局配置）里的内联 `hooks` 键（同 `.github/hooks/*.json` schema）。源码 `loadAllHooks`：用户级 = `<configDir>/hooks` 目录的文件配置，外加 `config.hooks` 内联配置，两者合并。

不向上遍历父目录。这直接导致下文「项目级 hook 路径解析停在 git root」与「`cc-safety-net` 自定义规则 scope」两个排障场景。需要跨子项目共用 hook 时，只能用 user-level 或 symlink。

### marketplace 分发的 Safety Net plugin 装了不触发：双 bug

#### 症状

按官方说明 `/plugin install kenryu42/copilot-safety-net` 装好 Safety Net，重启后仍能成功执行 `rm -rf <cwd 内目录>` 和 `git reset --hard HEAD~1`，没有 BLOCKED 提示。`COPILOT_ALLOW_ALL=1` 也开着。

#### 排查 → 根因

`~/.copilot/logs/process-*.log` 只有 `Loaded 1 hook(s) from 1 plugin(s)`，但整个 session **没有任何一次 hook 实际被调用**。两个 bug 叠加：

**1. plugin 自带的 `hooks/hooks.json` schema 是 Claude Code 的格式，不是 Copilot CLI 的**

错的（plugin 现状）：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type":"command","command":"npx cc-safety-net --copilot-cli"}]
      }
    ]
  }
}
```

对的（Copilot 官方文档）：

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "npx -y cc-safety-net --copilot-cli",
        "timeoutSec": 15
      }
    ]
  }
}
```

区别：Copilot 要求 `version: 1`、camelCase `preToolUse`、没有 `matcher`、命令字段叫 `bash` 且在顶层。

作者的另一个仓库 `kenryu42/claude-code-safety-net/.github/hooks/safety-net.json` 才是正确格式，但那是项目级示例，没打进 plugin。

**2. [copilot-cli#2540](https://github.com/github/copilot-cli/issues/2540) 未修 bug**

从 marketplace / git 装的 plugin 里 `hooks/*.json` 完全不会被 Copilot 加载执行。issue 评论确认：**手动**把 hook 文件复制到项目 `.github/hooks/` 才会触发。

#### 解决

不靠 plugin，自己在项目里写正确格式的 hook：

```json
// <project-root>/.github/hooks/safety-net.json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "npx -y cc-safety-net --copilot-cli",
        "cwd": ".",
        "timeoutSec": 15
      }
    ]
  }
}
```

然后 `copilot plugin uninstall copilot-safety-net`（避免误以为 plugin 在保护）。重启 Copilot 后即生效。

实测 `--allow-all-tools`（含 `COPILOT_ALLOW_ALL=1`）下 Safety Net 仍然能拦 `git reset --hard`。Copilot 的 `preToolUse` hook 在 permission system 之前跑，不会被 allow-all 跳过。

也可以走全局：把同一段 `hooks` 对象写到 `~/.copilot/settings.json` 的 `hooks` 键（参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference) 明确："define hooks inline in your user configuration file (`~/.copilot/settings.json`) using the `hooks` key"；旧版曾放 `config.json` 顶层，启动时自动迁移到 `settings.json`。Copilot CLI v0.0.422+ 支持 user-level hooks）。

#### 教训

- **"支持 Copilot CLI"≠"装上就有用"**：作者的主仓库 `claude-code-safety-net` 是对的，分发的 `copilot-safety-net` plugin 是错的；分清楚两个仓库。
- **`COPILOT_ALLOW_ALL` 不背锅**：它只是关掉 confirm 弹窗，不影响 hook 触发。看到 hook 不跑先去 `~/.copilot/logs/process-*.log` 查有没有 hook 调用记录，再看是 schema 错还是 plugin 加载 bug。
- **验证 cc-safety-net 工具本身是否正常**：直接喂 stdin 测：
  ```bash
  echo '{"toolName":"bash","toolArgs":"{\"command\":\"git reset --hard\"}"}' \
    | npx -y cc-safety-net --copilot-cli
  ```
  正常会输出 `{"permissionDecision":"deny",...}`。注意输入字段是 `toolName` / `toolArgs`（驼峰），且 `toolArgs` 是**字符串化**的 JSON 不是对象。

#### 相关 issue / 文档

- 参考官方文档[use-hooks](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks)：Copilot CLI 的 hooks（仓库级 `.github/hooks/`、用户级 `~/.copilot/hooks/`、`settings.json` 的 `hooks` 键）
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：用户级 `~/.copilot/hooks/` 与内联 `hooks` 键
- [coding agent hooks 规范](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks)：hook 配置 schema（cloud agent 侧）
- safety-net 主仓库 issue：[#24](https://github.com/kenryu42/claude-code-safety-net/issues/24)
- Copilot CLI plugin hook 不加载：[#2540](https://github.com/github/copilot-cli/issues/2540)

---

### 项目级 hook 路径解析停在 git root（多 repo 工作区漏装）

#### 症状

工作区是"父目录套多个独立 git 仓库"结构（如 `~/projects/{repo-a,repo-b,...}`，每个子目录是独立 repo，父目录本身不是 git）。父目录 `.github/hooks/safety-net.json` 配好后，cd 进父目录启动 copilot 正常；但 cd 进任何子项目启动 copilot，hook 完全不触发。

#### 根因

Copilot CLI `getHooksDir` 的查找逻辑：在 git repo 内用 **当前 git root**，否则用 cwd，**不会向上查父目录**。子项目自己是独立 git repo，git root 就是子项目自己，看不到父目录的 hook。env vars 改不了这个路径。

#### 解决：父目录 `.envrc` 自动 symlink

cd 进父目录时，让 direnv 把父目录 hook 软链到所有子目录的 `.github/hooks/`，并把 symlink 写入子项目的 `.git/info/exclude`（不污染 `.gitignore`，不进版本控制）。新增子项目 cd 一次父目录就自动同步。

复用[Walk-Up 总览里定义的 `link_into_subdirs` helper](#通用-workarounddirenv-symlink)：

```bash
# .envrc（link_into_subdirs 定义见 Walk-Up 总览节）
link_into_subdirs "$PWD/.github/hooks/safety-net.json" '.github/hooks/safety-net.json'
```

direnv 本身不能改 copilot 找 hook 的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**。如果不想限定子项目而是想全局生效，把 hook 搬到 `~/.copilot/hooks/safety-net.json` 即可。

#### 教训

- "项目级 hook" = **当前 git root 级**，不是当前工作区根级。多 repo 工作区要么走 user-level hook（`~/.copilot/hooks/`），要么自己分发文件。
- 改 hook 文件 / 加新 symlink 后，**当前 copilot session 不会受影响**（hook 启动时一次性加载），下次启动 copilot 才生效。
- `direnv allow` **基于 `.envrc` 内容 hash 授权**：改一次 `.envrc` 就要重新 allow 一次，hash 不变之后 cd 进出都自动加载，不需要每次 allow。

---

### `cc-safety-net` 自定义规则：user scope vs project scope

#### 场景

父目录 `.safety-net.json` 写了自定义规则（例如禁止所有 `gh` 子命令、要求用 GitHub MCP server 代替）。但子目录是独立 git repo，Copilot 的 cwd 在子仓库里时 safety-net 只从 **cwd** 读 `.safety-net.json`，不向上遍历——规则不生效。

#### 根因

`cc-safety-net` 加载自定义规则的搜索路径只有两个，**不做父目录遍历**：

1. **User scope**：`~/.cc-safety-net/config.json`（始终加载）
2. **Project scope**：`$CWD/.safety-net.json`（仅当前目录）

同名 rule project scope 优先覆盖 user scope，其余合并。

#### 解决

跨项目通用的规则放 user scope：

```bash
mkdir -p ~/.cc-safety-net
# 把规则写入 ~/.cc-safety-net/config.json
```

实际生效范围 = "user scope 规则在全局可见" × "hook 只在装了 `.github/hooks/safety-net.json` 的项目里激活"。所以规则虽然全局定义，但**只在装了 hook 的项目及其子目录内拦截**。

#### 验证

```bash
cd <project-with-hook>
npx -y cc-safety-net --verify-config       # 应显示 user config 里的规则
npx -y cc-safety-net explain "gh repo view"  # 应显示 BLOCKED
```

#### 教训

- **想跨子仓库生效的规则放 user scope**，不要靠 symlink `.safety-net.json`——那是 project scope，只作用于 cwd。
- **hook 文件仍然需要 symlink**（`.github/hooks/safety-net.json`），因为 Copilot 只从 git root 的 `.github/hooks/` 读 hook。见上一节。
- 区分"规则定义在哪"和"hook 在哪激活"：前者决定规则内容，后者决定拦截是否发生。

---

## MCP 配置

### 三种 MCP 配置文件的区别

Copilot 生态里有**三个不同位置**的 MCP 配置文件（其实是四种实例，但只有三种 schema），名字都带 "mcp" 容易搞混，尤其是 `.mcp.json` 和 `.vscode/mcp.json` 格式不兼容但长得像。

#### 对比表

| | `.mcp.json` | `.github/mcp.json` | `.vscode/mcp.json` | `~/.copilot/mcp-config.json` |
|---|---|---|---|---|
| **谁读它** | Copilot CLI / Claude Code / Cursor | Copilot CLI | VS Code（编辑器内 Copilot Chat）| Copilot CLI |
| **设计目的** | 项目级 MCP，跨编辑器通用标准 | 项目级 MCP，GitHub 风格路径 | VS Code workspace 级 MCP | 用户全局 MCP，跨所有项目 |
| **顶层 key** | `mcpServers` | `mcpServers` | `servers`（+可选 `inputs`）| `mcpServers` |
| **位置** | 项目根 / git root | 项目根下 `.github/` | `<workspace>/.vscode/` | `~/.copilot/`（固定）|
| **Walk-up（向上查找）** | ✅ 从 cwd 向上，**停在 git root** | ✅ 同 `.mcp.json`（共用 `bBt` 发现函数）| ❌ 只读当前 VS Code 打开的 workspace folder | ❌ 固定全局路径 |
| **Trust level** | Medium（需 review） | Medium（需 review） | VS Code 内独立管理 | User-defined |
| **变量展开 — `${VAR}` env** | `env` 字段支持；`headers` 字段**名义支持但实测不生效**（#1232）| 同 `.mcp.json` | 通过 `${env:VAR}` 支持 | 同 `.mcp.json` |
| **变量展开 — `${input:...}`** | ❌ 不支持 | ❌ 不支持 | ✅ 支持（弹窗输入，OS keychain 安全存储）| ❌ 不支持 |
| **变量展开 — `${workspaceFolder}`** | ❌ | ❌ | ✅ | ❌ |
| **`envFile`** | ❌ | ❌ | ✅（stdio 类型）| ❌ |
| **优先级** | 高于全局 `mcp-config.json`；低于 `--additional-mcp-config` | 同 `.mcp.json`（同名时与 `.mcp.json` 合并）| VS Code 内独立管理 | 最低（被同名 workspace 配置覆盖）|
| **同名冲突规则** | Copilot CLI: **last-wins**（workspace 覆盖全局）| 同 `.mcp.json` | VS Code 内独立 | 被 workspace 覆盖 |
| **是否入版本控制** | 可以（如不含 secrets）| 可以（`.github/` 本就版本控制友好）| 官方推荐入版本控制 | ❌ 用户私有 |

#### 源码证据

**Copilot CLI walk-up 逻辑**（`app.js` 中 `bBt` 函数，见下节详解）：

```js
function bBt(t, e, r, n) {
  // t = cwd, e = gitRoot (trust boundary)
  let s = normalize(e), a = normalize(t);
  for (;;) {
    // 在 a 找 .mcp.json ...
    if (a === s) break;       // 停在 git root
    let u = dirname(a);
    if (u === a) break;       // 到了根目录
    a = u;
  }
}
```

**VS Code 不做 walk-up**（`mcpWorkbenchService.ts`）：直接用 `workspaceFolder.uri` 拼 `.vscode/mcp.json`，没有任何目录遍历。

**VS Code 变量展开**（`mcpRegistry.ts`）：启动 MCP server 时调用 `_replaceVariablesInLaunch()` → `configurationResolverService.resolveWithInteraction()`，对 launch 对象（含 headers）做完整的变量替换。

#### 各自的设计目的

1. **`.mcp.json`**：Claude Code / Cursor / Copilot CLI 共用的"项目级 MCP 配置"事实标准。Copilot CLI 后来跟进支持这个格式（[#2938](https://github.com/github/copilot-cli/issues/2938)），以兼容 Claude Code 生态。
2. **`.github/mcp.json`**：Copilot CLI 专有的项目级 MCP 配置（Claude Code / VS Code 不读）。遵循 GitHub 的 `.github/` 约定（类似 `.github/copilot-instructions.md`、`.github/workflows/`），跟 `.mcp.json` 同格式同行为。选哪个看团队偏好——跨编辑器通用用 `.mcp.json`，符合 GitHub 目录惯例用 `.github/mcp.json`。
3. **`.vscode/mcp.json`**：VS Code 原生的 MCP 配置，遵循 VS Code 的 `settings.json` / `tasks.json` 等惯例。有完整的变量系统（`inputs` / `${env:}` / `${workspaceFolder}`）。Copilot CLI 曾短暂支持读取这个文件，后改为推荐迁移到 `.mcp.json`，社区有抱怨（[#3019](https://github.com/github/copilot-cli/issues/3019)、[#3059](https://github.com/github/copilot-cli/issues/3059)）。
4. **`~/.copilot/mcp-config.json`**：Copilot CLI 的用户级全局配置。适合放全局性的 MCP server（如 GitHub MCP），不跟随项目走。优先级最低，会被同名 workspace 配置覆盖（参考官方文档[add-mcp-servers](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：项目级 `.mcp.json` / `.github/mcp.json` 优先于用户级 `~/.copilot/mcp-config.json`）。

#### 实际使用建议

- **只用 Copilot CLI**：用 `.mcp.json`，secrets 硬编码（目前没有安全的替代方案，`headers` 里 `${VAR}` 展开不可靠，见下文）
- **只用 VS Code**：用 `.vscode/mcp.json` + `${input:...}` 或 `${env:VAR}`
- **两边都用**：维护两份配置，`.mcp.json`（CLI）+ `.vscode/mcp.json`（VS Code），用 direnv 同步环境变量

#### 相关 issue / 文档

- 参考官方文档[add-mcp-servers](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)：Copilot CLI 加 MCP server、用户级 vs 项目级优先级
- 参考官方文档[cli-plugin-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)：含加载优先级图
- [VS Code MCP 配置参考](https://code.visualstudio.com/docs/copilot/reference/mcp-configuration)
- [VS Code MCP 文档](https://code.visualstudio.com/docs/copilot/chat/mcp-servers)
- Copilot CLI 添加 `.mcp.json` 支持：[#2938](https://github.com/github/copilot-cli/issues/2938)
- 社区抱怨需要两份配置：[#3019](https://github.com/github/copilot-cli/issues/3019)
- VS Code 源码 `mcpWorkbenchService.ts`：workspace folder 直接拼 `.vscode/mcp.json`
- VS Code 源码 `mcpRegistry.ts`：`_replaceVariablesInLaunch()` → `configurationResolverService`
- VS Code 源码 `pluginParsers.ts`：`resolveMcpServersMap()` 兼容 `mcpServers` 和 `servers` 两种 key

---

### `.mcp.json` 上溯停在 git root（多 repo 工作区漏装）

#### 症状

两个反向场景都会出现"父目录 `.mcp.json` 看不到"：

1. **Parent 是 git repo、子项目也各自是独立 git repo**：父目录 `.mcp.json` 注册了 server，在父目录直接 `copilot mcp list` 能看到，但 `cd <subdir> && copilot mcp list` 显示 `No MCP servers configured`。
2. **Parent 不是 git repo、子项目是 git repo**：父目录 `.mcp.json` 含 server-a + server-b，子目录 `.mcp.json` 含 server-c。在子目录起 copilot 只看到 server-c，父目录那两个继承不到。

#### 结论（先说人话）

1. **会不会合并？会。** `bBt` 收集 cwd → git root 之间每一层的 `.mcp.json`，`bLa` 按 depth 倒序合并、cwd 覆盖祖先（last-wins，同名 server 以 cwd 为准）。
2. **触发上溯/合并的前提**（看 `sN` 三个分支）：
   - cwd 在某个 git repo 内 → 上溯到该 repo 的 root，沿途各层合并
   - cwd **不在**任何 git repo 内 → 走 `else` 分支，**只读 cwd 一份**，连 `bLa` 都不调
   - cwd 自己就是 git root → 第一轮 push 完 cwd 那份就 break，parent 一份都拿不到
3. **"没 git root 影响就会合并" 反着的**：git root 不是限制开关，反而是让跨目录合并能发生的**前提**。想让 `~/projects/{a,b,c}/` 都自动继承 `~/projects/.mcp.json` → 在 `~/projects/` `git init` 一下，且 `a/b/c` 自己**不是**独立 git repo（否则它们的 git root 钉在自己身上，看不到 parent）。

VS Code 的 "workspace folder" 概念跟它完全不同，所以从 VS Code 思维转过来反直觉。

#### 代码支撑

```js
async function bBt(t, e, r, n) {
  // t = cwd，e = boundary（git root），r = [{kind:"file", relativePaths:[".mcp.json"]}]，n = trust 检查 callback
  let o = [], s = Q3.normalize(e), a = Q3.normalize(t), l = 0;
  for (;;) {
    let c = l === 0 ? "project" : "inherited";   // 给每条命中打来源标签
    for (let d of r) for (let m of d.relativePaths) {
      let p = Q3.join(a, m);
      wqr(p) && o.push({path: p, directory: a, depth: l, source: c});
    }
    if (a === s) break;                          // ① 停在 git root
    let u = Q3.dirname(a);
    if (u === a || (n && !await n(u))) break;    // ② 或停在 fs 根 / 不可信目录
    a = u; l++;
  }
  return o;
}

async function bLa(t, e, r) {
  let o = await bBt(t, e, [{kind:"file", relativePaths:[".mcp.json"]}], /* trust cb */);
  if (o.length === 0) return {mcpServers:{}};
  let s = [...o].sort((l, c) => c.depth - l.depth);    // 祖先在前
  let a = {mcpServers:{}};
  for (let l of s) a = pre(a, zWo(l.directory));       // last-wins：cwd 覆盖 inherited
  return a;
}

// sN（顶层调度）：
if (!s) d = {...c};                              // 没启用 workspace 加载
else if (a) d = pre(c, await bLa(e, a, o));      // a = gitRoot 存在 → 上溯到 gitRoot
else { let p = zWo(e); d = pre(c, p); ... }      // 不在 git repo 里 → 只读 cwd 一份
```

对照前面三条结论：

- 结论 1 的"合并 + last-wins" → `bLa` 里 `sort((l,c)=>c.depth-l.depth)` + `for...pre(a, zWo(...))`
- 结论 2 的三个分支 → `sN` 里 `if(!s) / else if(a) / else` 三段
- 结论 2 第三种"cwd 自己就是 git root" → `bBt` **先 push 当前层、再判断 `a === s`**，所以 cwd 那份能拿到，但下一轮 `dirname` 之前就 break

#### 解决（多 repo 工作区共用同一份 `.mcp.json`）

复用[Walk-Up 总览里的 `link_into_subdirs` helper](#通用-workarounddirenv-symlink)：

```bash
# .envrc
link_into_subdirs "$PWD/.mcp.json" '.mcp.json'
```

每个子项目都被自动塞一份 `.mcp.json` 软链 + 写进 `.git/info/exclude` 不污染 `git status`。子项目想覆盖 / 加自己的 server 时，可以单独把那一份从软链改成手写文件（合并不会发生，因为子项目的 git root 就是它自己——但反正配置直接照 cwd 那份用就够了）。

#### 教训

- "Workspace MCP" 的 "workspace" 是 **git repo 级**，不是用户主观的"工作区"，更不是 VS Code 概念里的 workspace folder。
- 实测才信结论；只看 `copilot mcp list` 输出容易得出错误判断。读 `app.js` 才能确认它**会**上溯但停在 git root；而"没 git root"反而连 parent 都不看。
- `copilot mcp list` 输出的 `Source:` 列：`Project (.mcp.json)` 是 cwd 那份，`Inherited (...)` 是上溯命中的祖先那份，可以用来快速验证 symlink / 合并实际生效到了哪。
- 同名 server 冲突时 last-wins，cwd 覆盖 inherited；想强制不被父目录覆盖，server 名字起独特一点。

---

### `.mcp.json` headers 里 `${VAR}` 展开不生效

#### 症状

`.mcp.json` 配置 HTTP MCP server 时，`headers` 里用 `${VAR}` 引用环境变量，Copilot CLI 不做展开，把字面量 `Bearer ${MY_GH_PAT}` 发给服务端，导致：

```
Streamable HTTP error: Error POSTing to endpoint: bad request:
Authorization header is badly formatted
```

硬编码 PAT 则正常。

#### 复现矩阵（都不生效）

1. `"Bearer ${VAR}"`（复合字符串） → 字面量发送
2. `"${VAR}"`（纯变量引用，env 值含 `Bearer ` 前缀） → 字面量发送
3. `"$VAR"`（无花括号） → 字面量发送
4. 配置文件放 `~/.copilot/mcp-config.json`（全局） → 同样失败
5. curl 直接用环境变量拼 header → 200（PAT 本身有效）
6. 硬编码到任何位置的配置文件 → 立刻成功

#### 已知 issue

- **[#1232](https://github.com/github/copilot-cli/issues/1232)**：用户 @stefanbosak 精确复现了 `"Authorization": "Basic ${TOKEN}"` 不展开。2026-04-07 官方关闭说已修复，但 @therealvio 在 v0.0.420 + **direnv** 环境下仍报告不工作，无人确认修复生效。
- **[#3100](https://github.com/github/copilot-cli/issues/3100)**：即使 `headers` 里有 `Authorization: Bearer <token>`，CLI 可能先触发 OAuth discovery 流程并失败，header 根本没机会发出去。
- **[#1841](https://github.com/github/copilot-cli/issues/1841)**：Feature request 要求支持 `${input:...}` 语法，仍然 open。
- **[#2960](https://github.com/github/copilot-cli/issues/2960)**：反向佐证——有用户用 `"Bearer ${GRAFANA_MCP_TOKEN}"` **成功展开**了（问题是 token 太长超限制），说明在某些环境下确实能用。

#### 根因推测

可能是以下因素叠加：

1. headers 里复合字符串 `"Bearer ${VAR}"` 的展开逻辑不完整（#1232 最初报的就是这个）
2. direnv 注入的环境变量可能走了不同的进程继承路径（@therealvio 也用 direnv）
3. 全局 vs workspace 配置可能走不同的解析管道
4. `Nhe` 黑名单的 `${VAR}` 展开拦截（见 `Das()`）会主动屏蔽敏感变量名，进一步劝退靠 env 注入 secret 的做法

#### 解决（当前 workaround）

headers 里硬编码 PAT。文件 `chmod 600` + 不入版本控制。

如果用 VS Code，可以走 `.vscode/mcp.json` + `${env:VAR}` 或 `${input:...}`，那套变量系统是 VS Code 原生的 `configurationResolverService`，完全独立于 Copilot CLI 的解析器。

#### 教训

- **官方文档说"supports variable expansion"不等于实际能用**——changelog 说修了、文档说支持，但没有受影响用户确认修复、也没有自动化测试保证回归。实测为准。
- **direnv 是额外变量**——它注入 env 的方式（hook `$PROMPT_COMMAND` / `precmd`）跟直接 `export` 在微妙场景下可能有差异。遇到 env 不生效先排除 direnv 因素。
- **VS Code 和 Copilot CLI 是两套独立的变量系统**——VS Code 的 `${env:VAR}` 走 `configurationResolverService`，经过完整的变量解析管道；Copilot CLI 的 `${VAR}` 走自己的简单字符串替换。不要混用语法。

---

## Skills 发现

Copilot CLI 的 skill 来自三类位置，CLI 内置 `/skills` 帮助与官方文档一致（参考官方文档[add-skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)、[about-agent-skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)）：

- **项目级**（随 cwd→git root walk-up 收录，boundary = git root，无 git 回退 `$HOME`；source `project` / `inherited`）：`.github/skills/`、`.agents/skills/`、`.claude/skills/`
- **个人级**（固定路径；source `personal-copilot` / `personal-agents`）：`~/.copilot/skills/`、`~/.agents/skills/`
- **自定义 / 内置**：`/skills add <dir>` 或 env `COPILOT_SKILLS_DIRS`（逗号分隔绝对路径，source `custom`）；CLI 安装目录的 `builtin-skills/`（source `builtin`）

CLI 内置 `/skills` 帮助原文（`app.js` 字面量）就是这份清单：

```text
Skills are loaded from:
• Project: .github/skills/, .agents/skills/, or .claude/skills/
• Personal: ~/.copilot/skills/ or ~/.agents/skills/
• Custom: Directories added via /skills add
```

个人级 `~/.copilot/skills` 的解析见源码（`COPILOT_HOME` 可整体改写 configDir）：

```js
// app.js — mtt：个人级 skill 根 = configDir/skills
function mtt(t) {
  let e = t?.configDir ?? process.env.COPILOT_HOME ?? join(homedir(), ".copilot");
  return join(e, "skills");        // = ~/.copilot/skills
}
```

**同名时项目级覆盖个人级**（参考官方文档[add-skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)）。Custom agents 同理：个人级 `~/.copilot/agents/`、项目级 `.github/agents/`，同名项目级优先（参考官方文档[create-custom-agents-for-cli](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)）。

⚠️ **`<project>/.copilot/skills` 不是任何一种约定，Copilot CLI 不读它。** 项目级只有 `.github/skills`、`.agents/skills`、`.claude/skills` 三种；`.copilot/skills` 仅在 home（`~/`）下作为**个人级**（`~/.copilot/skills`）才有效。别把个人级路径照搬成项目里的 `<project>/.copilot/skills` 软链——那条不会被发现。

### 项目级 `.agents/skills` 上溯停在 git root（与 hooks/mcp 同款）

#### 症状

工作区是"父目录套子项目"结构，父目录 `.agents/skills/<skill-name>/SKILL.md` 写好了。在父目录起 copilot 能看到 skill；`cd <subdir>` 启动 copilot，`/skills` 里看不到那些 skill，agent 提示词里 `<available_skills>` 也没有。`~/.agents/skills/` 下的 user-level skill 始终能看到，因此现象是"项目级 skill 漏掉、user 级 skill 正常"。

#### 根因

Skill 发现走的是和 `.mcp.json`、`.github/hooks/` 完全相同的 `bBt` walk-up 函数，**boundary 同样是 git root**（即 `projectRoot`），所以子项目自己是 git repo 时上溯立刻停在子项目根，看不到父目录的 `.agents/skills`。

扫的就是本节开头那三类项目级 convention（`.github/skills` / `.agents/skills` / `.claude/skills`，每个独立调一次 `bBt`）；个人级 `~/.copilot/skills`（`personal-copilot`）、`~/.agents/skills`（`personal-agents`）、`builtin-skills/` 与 env `COPILOT_SKILLS_DIRS`（最高优先）走固定路径、不受 walk-up boundary 限制。

#### 代码支撑（`app.js:~676` 附近）

```js
// 项目级三套 convention 的入口
async function j7e(t, e, r, n) {
  // t=".agents" / ".github" / ".claude", e="skills", r=projectRoot, n=cwd
  if (n) {
    let o = r ?? wBt.homedir();          // ★ boundary：projectRoot 否则回退 HOME
    return yQe(t, e, { startPath: n, boundary: o })
  }
  return r ? yQe(t, e, { root: r }) : []
}

async function LIi(t, e=[], r, n=[], o, s={}) {
  // t=projectRoot, o=cwd
  let l = a ? [
    ...await j7e(".github", "skills", t, o),
    ...await j7e(".agents",  "skills", t, o),
    ...await j7e(".claude",  "skills", t, o),
  ] : [];
  let c = a ? [
    { path: GR.join(ma(r,"config"), "skills"),       source: "personal-copilot" },  // 1.0.66 实为 mtt(): join(configDir, "skills") = ~/.copilot/skills
    { path: GR.join(homedir(), ".agents", "skills"), source: "personal-agents"  },
  ] : [];
  let d = [
    ...process.env[Tqr]?.split(",").filter(Boolean) ?? [],   // COPILOT_SKILLS_DIRS
    ...e,                                                     // 调用方传入的 customDirs
  ].map(p => ({path: p.trim(), source: "custom"}));
  return [...l, ...c, ...n, ...d].filter(p => EQe(p.path));
}
```

`yQe` 在 `convention="directory"` 模式下转调 `bBt`（[正是 `.mcp.json` 那条说过的那个 walk-up](#mcpjson-上溯停在-git-root多-repo-工作区漏装)）：

```js
// 简化复述：从 startPath 向上走，每层检查 `${a}/.agents/skills` 存在则收录
let s = normalize(boundary), a = normalize(startPath), l = 0;
for (;;) {
  if (existsSync(join(a, ".agents", "skills"))) o.push({path: ..., source: l===0?"project":"inherited"});
  if (a === s) break;                          // ★ 撞 boundary 就停
  let u = dirname(a);
  if (u === a) break;
  a = u; l++;
}
```

#### 与 hooks/mcp 的差异

| 项                | hooks (`.github/hooks/`)         | mcp (`.mcp.json`)                | skills (`.agents/skills/` 等)                          |
| ----------------- | -------------------------------- | -------------------------------- | ------------------------------------------------------ |
| Walk-up           | 否（只看 git root 一层）         | 是（cwd→git root，沿途合并）     | 是（cwd→git root，沿途收录）                           |
| Boundary          | git root                         | git root                         | git root；**没 git repo 时回退 `$HOME`**               |
| User scope 路径   | `~/.copilot/hooks/`              | `~/.copilot/mcp-config.json`     | `~/.copilot/skills` + **`~/.agents/skills`**           |
| Source 标签       | -                                | `Project` / `Inherited`          | `project` / `inherited` / `personal-agents` / `builtin`|
| Env 覆盖          | -                                | -                                | `COPILOT_SKILLS_DIRS`（逗号分隔，绝对路径）            |

注意 skills 比 hooks/mcp 多了一条 user-level 路径 **`~/.agents/skills`**：它是跨工具共享个人 skill 的中立目录，独立于项目级 `.agents/skills`（后者才走 walk-up、boundary=git root）。

另一个重要细节：**boundary 的 fallback 是 `$HOME` 而不是 `/`**。所以在"父目录不是 git repo、子项目也不是 git repo"（即 cwd 完全不在任何 git repo 内）时，会一路扫到家目录，反而能拿到祖先 `.agents/skills`。一旦 cwd 进入任何 git repo，boundary 就钉到那个 git root 上了。

#### 解决

复用[Walk-Up 总览里的 `link_into_subdirs` helper](#通用-workarounddirenv-symlink)：

```bash
# .envrc（父目录）
link_into_subdirs "$PWD/.agents/skills" '.agents/skills'
```

或者按 skill 粒度软链单个 skill 进子项目：

```bash
mkdir -p <subdir>/.agents/skills
ln -s ../../../.agents/skills/<skill-name> <subdir>/.agents/skills/<skill-name>
```

如果想全局生效（任意 cwd 都能看到），把 skill 软链到 user-level：

```bash
ln -s /path/to/<skill-name> ~/.agents/skills/<skill-name>
```

临时一次性测试可以用 env：

```bash
COPILOT_SKILLS_DIRS=/abs/path/to/.agents/skills copilot
```

#### 验证

```bash
# 启动后在 copilot 里
/skills           # 列表会显示来源标签 (project/inherited/personal-agents/builtin)
/env              # 看 skills 节，确认实际加载的路径
```

或在 prompt 里直接问 agent：列出可用 skills（agent 拿到的 `<available_skills>` 就是 `LIi` 的过滤结果）。

#### 教训

- "项目级 skill" 跟 hook/mcp 一样 = **当前 git root 级**，不是用户主观的工作区根。多 repo 套娃要么 symlink 进每个子 repo，要么挪到 `~/.agents/skills/`。
- **`.agents/skills` 和 `~/.agents/skills` 是两条独立路径**：前者走 walk-up + git root boundary，后者走固定 user-level。这也是为什么 `~/.agents/skills/<x>` 永远在、但项目里 `.agents/skills/<x>` 时有时无。
- 想验证是路径问题还是 SKILL.md 解析问题：先把目标 skill 临时软链到 `~/.agents/skills/`，能出现就是路径问题；仍然不出现就检查 `SKILL.md` frontmatter（`name` 必须匹配 `^[a-zA-Z0-9][a-zA-Z0-9._\- ]*$` 且 ≤64 字符；`description` ≤1024 字符；`user-invocable: false` 会从用户列表里隐藏；`disable-model-invocation: true` 会从模型列表里隐藏）。
- skill 改了之后**当前 session 不会重载**，下次启动 copilot 才生效（`Y3` 内部还有按 `JSON.stringify(args)` 的缓存 `rbe`）。

#### 相关 issue / 文档

- 参考官方文档[add-skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)：项目级/个人级 skill 目录、`SKILL.md` frontmatter、`allowed-tools` 预批
- 参考官方文档[about-agent-skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)：skill 概念与跨产品（CLI / IDE / cloud agent）支持
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：`~/.copilot/` 目录布局（含 `skills/`、`agents/`）
- 参考官方文档[create-custom-agents-for-cli](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)：custom agents 的个人级/项目级目录与优先级

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

## Chronicle 搜索给 resume ID：必须给本地 ID

`/chronicle search` 用 `session_store_sql` 查的是**云端 + 本地两套 session store 合并**的结果（每行带 `_query_source` = `cloud` / `local`）。同一个会话在两套库里 **session ID 不一样**：云端是一份同步副本，本地是 `~/.copilot/session-state/<id>/` 下真正能 resume 的那份。

**`copilot --resume=<id>` 只认本地 ID**——拿云端 ID 去 resume 会直接报 `No session, task, or name matched`。

所以 chronicle 给用户用来 resume 的 ID 时：

- **只给本地 ID**，即 `_query_source = 'local'` 且 `~/.copilot/session-state/<id>/` 目录存在的那个。
- 搜索结果里如果同名会话既有 cloud 又有 local，**优先取 local 行的 ID**，别取 cloud 的。
- 不确定时本地核一下：`ls ~/.copilot/session-state/<id>` 有目录才是可 resume 的。
- 纯 cloud-only（本地无目录）的会话：明说「本机不可 resume，状态在另一台机器上」，别给一个 resume 不了的 ID。

---

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
