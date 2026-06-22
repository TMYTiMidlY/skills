# GitHub Copilot CLI

Copilot CLI 内部行为的逆向工程与排障笔记，按"排查对象"分章：进程与环境变量、bash 执行模型、权限与目录信任、配置/指令发现（walk-up）、TUI 与终端、git 认证、运维。每章先讲机制（人话 + 怎么在源码里找到证据），具体踩坑排障放在后面。

**源码定位基线**：`@github/copilot@1.0.64-1` 的 `app.js`（esbuild 混淆产物，单文件 6403 行 / 8.5MB）。本文结论均按此版本核对过。**混淆符号名（`RR` / `Lg` / `k7e` / `cFn` …）每次发版都会变，不要照抄**；要在新版本里复定位，搜永不混淆的字面量（env 名、错误文案、配置文件名、CLI flag、schema key）。怎么解包二进制、怎么按字面量抠源码片段，见 [安装方式与看源码](#安装方式与看源码)。

## 目录

- [安装方式与看源码](#安装方式与看源码)
  - [三层结构：loader → app.js](#三层结构loader--appjs)
  - [npm 安装：直接读 node_modules](#npm-安装直接读-node_modules)
  - [二进制发行版（SEA）：读自解包的 cache](#二进制发行版sea读自解包的-cache)
  - [按字面量抠源码片段](#按字面量抠源码片段)
- [进程与环境变量](#进程与环境变量)
  - [Env 黑名单：为何 `git push` 在 agent 里总是 401](#env-黑名单为何-git-push-在-agent-里总是-401)
  - [黑名单清单](#黑名单清单)
  - [设计意图与可见信号](#设计意图与可见信号)
- [bash 工具执行模型](#bash-工具执行模型)
  - [非交互、不读 rc、注入若干 env](#非交互不读-rc注入若干-env)
  - [`BASH_ENV` 生效、`~/.bashrc` 不生效](#bash_env-生效bashrc-不生效)
  - [拿不到用户的显示 tty](#拿不到用户的显示-tty)
- [权限与目录信任](#权限与目录信任)
  - [三套独立机制](#三套独立机制)
  - [`COPILOT_ALLOW_ALL` ≠ `--allow-all` / `--yolo`](#copilot_allow_all----allow-all----yolo)
  - [`/rewind` 需要 git 仓库且至少一个 commit](#rewind-需要-git-仓库且至少一个-commit)
- [配置与指令发现（Walk-Up）](#配置与指令发现walk-up)
  - [机制总览与子系统对比](#机制总览与子系统对比)
  - [Custom Instructions（指令文件）](#custom-instructions指令文件)
  - [MCP 配置](#mcp-配置)
  - [Skills 发现](#skills-发现)
  - [Hooks（preToolUse / Safety Net）](#hookspretooluse--safety-net)
  - [通用 workaround：direnv symlink](#通用-workarounddirenv-symlink)
- [TUI 与终端](#tui-与终端)
  - [滚动与翻页键](#滚动与翻页键)
  - [终端颜色 / 主题（colorMode）](#终端颜色--主题colormode)
- [Git 认证 / Credential helper](#git-认证--credential-helper)
  - [env 黑名单下的 `git push` 对策](#env-黑名单下的-git-push-对策)
  - [用 `GIT_CONFIG_COUNT` 注入内联 credential helper](#用-git_config_count-注入内联-credential-helper)
  - [`gh repo fork` 跨账号 push 用错 SSH 身份](#gh-repo-fork-跨账号-push-用错-ssh-身份)
- [运维](#运维)
  - [重试策略 patch（transient API error）](#重试策略-patchtransient-api-error)
  - [Chronicle 搜索给 resume ID：必须给本地 ID](#chronicle-搜索给-resume-id必须给本地-id)

---

## 安装方式与看源码

Copilot CLI 有两种安装形态，**入口不同但核心都是 `index.js`（loader）→ spawn `app.js`（主逻辑）两层**。下面分别讲在哪、怎么读到 `app.js`。

### 三层结构：loader → app.js

```
index.js  (loader)   自动更新 / 版本选择(--prefer-version) / crash report 收集
   │  spawn 子进程，传 COPILOT_RUN_APP=1
   ▼
app.js    (主逻辑)   tool registry / 指令解析 / MCP 客户端 / bash 工具 env 过滤
```

- `index.js` 用一个 `Proxy(process.env)` 包装来 spawn `app.js`，但它这层的**默认过滤集是空 Set**（源码里 `at=new Set`）——即 loader **不做** env 过滤。所以 `process.env.GITHUB_PERSONAL_ACCESS_TOKEN` 在 Copilot 主进程内部仍可读（用来调内部 API、遥测鉴权）。
- `app.js` 才是真正做 env 过滤、tool 调度的地方。**下文所有"在源码里搜 X"都指 `app.js`**，除非特别说明。

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

## 进程与环境变量

### Env 黑名单：为何 `git push` 在 agent 里总是 401

#### 现象

- host shell 里 `$GITHUB_PERSONAL_ACCESS_TOKEN`、`$OPENAI_API_KEY`、`$ANTHROPIC_API_KEY` 等都正常 export
- agent bash 工具里 `echo $GITHUB_PERSONAL_ACCESS_TOKEN` 是**空字符串**，但无关变量（`$WEBDAV_PASS`、自起名的 `$MY_RANDOM_VAR`）正常
- 依赖 `$GITHUB_PERSONAL_ACCESS_TOKEN` 的 git credential helper 在 agent 里跑 → 密码是空串 → `Invalid username or token. Password authentication is not supported.`

不是 direnv 失效，也不是 `delete process.env[...]`——是 Copilot CLI **故意**把一组敏感 env 通过 Proxy 屏蔽掉了：host shell 看主进程的 `process.env` 没变，但 spawn 出来的 bash 子进程读不到。

#### 机制

bash 工具构造子进程 env 时，用一个 `Proxy(process.env)` 模拟"剥离过的环境"：黑名单里的 key，`get` 返回 `undefined`、`has` 返回 false、`ownKeys` 里也抹掉。Node 的 `child_process.spawn` 在 `{env}` 是 Proxy 时会枚举 keys + 取值，黑名单 key 既不出现也读不到 → 子进程完全看不见。

**源码怎么找**：搜 `COPILOT_CLI:"1"` 落到 env 构造函数（构造 `new Set([...内部上下文, ...electron标志])` 当黑名单，再白名单透传几个内部 token）；搜 `new Proxy(process.env` 落到 Proxy 屏蔽函数。

白名单透传的是 Copilot 内部、受限的变量（如把 `GITHUB_COPILOT_GITHUB_TOKEN` 透传成 `GITHUB_TOKEN`），**用户本人的 `GITHUB_PERSONAL_ACCESS_TOKEN` 不在透传里**。

### 黑名单清单

黑名单 = 一组「内部运行时上下文变量」+ 一份「敏感 token 清单」。后者搜 `GITHUB_PERSONAL_ACCESS_TOKEN` 就能定位整段数组，1.0.64-1 是 24 项：

```
GITHUB_COPILOT_GITHUB_TOKEN, GITHUB_TOKEN, COPILOT_GITHUB_TOKEN,
GITHUB_COPILOT_API_TOKEN, CAPI_HMAC_KEY, CAPI_HMAC_KEY_OVERRIDE,
ANTHROPIC_API_KEY, AIP_SWE_AGENT_TOKEN, CAPI_AZURE_KEY_VAULT_URI,
COPILOT_JOB_NONCE, GITHUB_MCP_SERVER_TOKEN, OPENAI_BASE_URL, OPENAI_API_KEY,
COPILOT_AGENT_REQUEST_HEADERS, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_ENDPOINT,
AZURE_OPENAI_KEY_VAULT_URI, AZURE_OPENAI_KEY_VAULT_SECRET_NAME,
BLACKBIRD_AUTH_METIS_API_KEY, BLACKBIRD_AUTH_MODEL_BASED_RETRIEVAL_TOKEN,
GITHUB_PERSONAL_ACCESS_TOKEN, GITHUB_VERIFICATION_TOKEN,
COPILOT_PROVIDER_API_KEY, COPILOT_PROVIDER_BEARER_TOKEN
```

这份 token 清单还被复用为**日志 redaction（脱敏）名单**和 **MCP 配置 `${VAR}` 展开拦截名单**——是统一的「不该让 agent 看到的密钥」清单。另有一批 `COPILOT_AGENT_*` / `COPILOT_PROVIDER_*` 内部上下文变量（搜 `COPILOT_AGENT_REASONING_EFFORT` 可看到那段数组）也在黑名单里。

### 设计意图与可见信号

把用户全权 `GITHUB_PERSONAL_ACCESS_TOKEN` 透传给子进程 = 把 GitHub 全权 token 交给 LLM = LLM 可代表用户做任何事（push 任意仓库、删 repo、读私库、改 settings）。所以这是**故意**的安全屏障：

- **agent 子进程**：只拿到 Copilot 服务端发的、受限的短期 token（透传成 `GITHUB_TOKEN`）
- **用户的 PAT**：始终留在 host shell 和主进程，agent 子进程读不到

**可见信号**（在 agent bash 里实测）：

- `env | grep -i token` 看不到黑名单里那 24 个确切名字，但你自己起名的 `*_TOKEN`（如 `MY_GH_PAT`）照样透传 → 证实过滤是**按确切名单**，不是 `*TOKEN*` 模式匹配。
- `env | grep GIT_CONFIG` 会看到 Copilot 用 `GIT_CONFIG_COUNT` + `GIT_CONFIG_KEY_<n>` / `GIT_CONFIG_VALUE_<n>` 注入的几对 git config，说明 spawn 时确实改写了 env。1.0.64-1 注入 4 对：

  ```
  KEY_0 = credential.https://github.com.helper   VALUE_0 = (空，清掉已有 helper)
  KEY_1 = credential.https://github.com.helper   VALUE_1 = !f(){ ... }; f   (内联 helper)
  KEY_2 = core.excludesFile                        VALUE_2 = <某 excludes 文件>
  KEY_3 = safe.bareRepository                      VALUE_3 = explicit
  ```

  具体几对/哪些 key 由底层动态算（搜 `gitComputeSecurityEnvPatch`，实现不在 `app.js` 而在更底层模块，静态看不全）——**别照抄，直接 `env | grep GIT_CONFIG` 看当前真实值**。其中 `credential.*.helper` 那两对若出现内联 helper，多半是你自己 direnv 注入的 [git push 对策](#用-git_config_count-注入内联-credential-helper) 在生效。

> **唯一能绕过这个屏障的方式是明文把 token 贴进聊天**——而那恰好就是屏障要防的事。一旦发生，立即 revoke 那个 token。

---

## bash 工具执行模型

### 非交互、不读 rc、注入若干 env

agent 的 bash 工具实际是这样起的（在 agent shell 里 `ps -o args -p $PPID` 能看到父进程，或 `echo $-` 看 flags）：

```
/bin/bash --norc --noprofile -c "<命令>"
```

- **非交互**（`$-` 是 `hBc`，无 `i`）：所以一切"仅交互 shell 才做"的事都不发生。
- **`--norc --noprofile`**：**不读** `~/.bashrc`、`~/.bash_profile`、`/etc/profile`。想在每条命令前生效的 env，靠 rc 文件是不行的。
- **每条命令是独立子进程**：工作目录、环境变量、shell 变量、`cd`、`export` 都**不跨命令保留**。需要连续状态就用 `&&` 串成一条，或显式 `cd`。
- spawn 时还会注入 `CLAUDE_PROJECT_DIR` / `COPILOT_PROJECT_DIR`（= 工作目录），并按 [env 黑名单](#env-黑名单为何-git-push-在-agent-里总是-401)剥离敏感变量。

**源码怎么找**：搜 `--norc`，落到 shell 参数构造器（bash → `["--norc","--noprofile"]`，PowerShell → `["-nop","-nol"]`），命令本体作为 `-c` 的参数传入。

### `BASH_ENV` 生效、`~/.bashrc` 不生效

`BASH_ENV` 是 bash 内置机制：**非交互式** bash 启动时（`bash -c`、`bash script.sh`、`#!/bin/bash` 脚本）会自动 source 它指向的文件。Copilot 的 bash 工具正是非交互式，所以：

- ✅ **`BASH_ENV` 会被 source** —— 在 `.envrc` 里 `export BASH_ENV="$PWD/.copilot.env"`，可把额外 env / secret 注入到 agent 派生的每条 bash 命令，而不污染 Copilot 主进程。
- ❌ **`~/.bashrc` 不会被读**（`--norc`）—— 别指望把东西写进 `.bashrc` 给 agent 用。

验证 `BASH_ENV` 是否真生效：

```bash
# .copilot.env: export PROBE=ok
echo "[$PROBE]"      # agent bash 里应输出 [ok]
```

> 更省心的替代：直接通过 `.envrc` export 到 host shell（direnv 在 `cd` 时自动加载），让 Copilot 主进程继承，再由 bash 工具继承（除非命中黑名单）。这样根本不需要 `BASH_ENV`。

### 拿不到用户的显示 tty

bash 工具的标准流是**管道**，不是终端：`fd0 → /dev/null`、`fd1 → pipe`、`fd2 → /dev/null`，`tty` 命令返回 `not a tty`，`/dev/tty` 打开报 `No such device or address`。

后果：**agent 自己发不了 OSC / DA 这类终端查询、也读不到终端应答**——任何"问终端背景色 / 能力探测 / 颜色诊断"的命令都得让用户**在交互 pane 里手动跑**，agent 只能给命令、读用户贴回来的结果。诊断终端颜色/主题问题（见 [colorMode](#终端颜色--主题colormode)）时直接据此分工，别在 agent bash 里反复试 OSC。

---

## 权限与目录信任

### 三套独立机制

排查"明明信任了为什么还弹窗"时，必须分清三套同主题但**位置和作用都不同**的机制：

| 机制 | 存放位置 | 作用 | 持久化 |
|---|---|---|---|
| **启动信任** | `~/.copilot/config.json` 的 `trustedFolders`（`settings.json` 有镜像副本） | 决定启动 copilot 时是否还弹 "trust this folder for future sessions" 全屏 prompt | ✅ 写盘 |
| **命令 / 写入审批** | `~/.copilot/permissions-config.json` 的 `locations.<launch-cwd>.tool_approvals` | 按"启动 cwd"分组的 `commands` / `write` 审批，控制曾经批过的放行列表 | ✅ 写盘 |
| **会话级 allowed-dir** | **仅内存**（无任何持久化字段） | 控制每次 file read/write 的目录边界。初始化为启动 cwd 树。`/list-dirs` 查、`/add-dir` 加 | ❌ 重启即丢 |

**典型症状**：`trustedFolders` 已含 `$HOME`，但从 `~/projects/<subdir>` 启动后，agent 读 `~/projects/.shared-config.json`（启动 cwd 的**父目录**）仍弹 "Allow directory access"，`/allow-all` 也没用。

**根因**：弹窗 "outside your allowed directory list" 指的是**第三套**——会话级 allowed-dir。它的初始值就是启动 cwd 树，**完全不读 `trustedFolders`**。所以哪怕 `trustedFolders` 写了 `$HOME`，也只让启动时不弹 trust prompt，不会扩展会话 allowed-dir。

**解决（按推荐顺序）**：

1. **从想要的根目录启动**（一劳永逸）：`cd <root> && copilot`
2. **启动后 `/add-dir <path>`**：只对当前 session 有效（弹窗里选 "Yes, and add..." 等价于此）
3. 没有"永久 allowed-dir"机制，也没有 `--add-dir` 启动 flag

> 官方文档说 "Trusted directories control where Copilot CLI can read, modify, and execute files" 听起来涵盖所有文件访问，实际 `trustedFolders` 只管启动信任；运行时目录边界是会话级那套。源码里这三套分别搜 `trustedFolders` / `permissions-config` / `add-dir`。

### `COPILOT_ALLOW_ALL` ≠ `--allow-all` / `--yolo`

`.envrc` 里 `export COPILOT_ALLOW_ALL=1` 期望等价于 `--allow-all` / `--yolo`，实际：

- ✅ 命令、写入、MCP 工具不再弹审批
- ✅ cwd 子树内文件读写正常
- ❌ **cwd 外的路径访问仍弹 "Allow directory access"**

原因有三层：

**一、env var 只挂在 `--allow-all-tools` 上。** CLI 选项里只有 `--allow-all-tools` 带 `.env("COPILOT_ALLOW_ALL")`；`--allow-all-paths` / `--allow-all-urls` / `--allow-all` 都**没有 env 绑定**，只能用 CLI flag。（搜 `--allow-all-tools` 看 option 注册。）

**二、`--allow-all` ≡ `--yolo`，三合一展开。** 两者帮助文本一字不差，运行时 OR 到同一变量，再 OR 进 `allowAllTools` / `allowAllPaths` / `allowAllUrls` 三个 bool。（搜 `allowAllTools:` 看那个合流函数。）所以 env 只能让 `allowAllTools` 为真，path / url 两闸照常跑。

**三、值必须是 `"true"` 不能是 `"1"`。** commander 对布尔 flag 的 `.env()` 是宽松解析（任何非空串都为真），所以 `=1` 能让 `--allow-all-tools` 生效。但另有 **8 处**业务代码用严格比较 `process.env.COPILOT_ALLOW_ALL === "true"` 来**短路 `isFolderTrusted`**（搜 `COPILOT_ALLOW_ALL` 数一下），分两类：决定 workspace 里发现的 `.mcp.json` 算不算可信、决定启动时弹不弹 trust 窗。`=1` 走不到这些短路。

**实际后果**：

- launch cwd 已在 `trustedFolders` 子树下 → `isFolderTrusted` 本来就过，`=1` 和 `=true` 没区别。
- **新机器 / `trustedFolders` 还空**：`=1` 会让 workspace MCP 不自动加载、每次启动都弹 trust；改成 `=true` 才正常。
- **目录访问审批任何 env 值都救不了**——必须 CLI flag `--allow-all-paths` 或 `--allow-all` / `--yolo`。

**实操方案**（`.envrc` 只能 export env，不能写 alias / 函数）：

```bash
# 方案 A：全局 alias（最简单，每个 shell 都生效）
alias copilot='copilot --yolo'                    # ~/.bashrc

# 方案 B：env + alias 组合
export COPILOT_ALLOW_ALL=true                     # .envrc，值必须是 true
alias copilot='copilot --allow-all-paths'         # path 维度只能靠 flag
```

也可以在工作区 `.bin/` 放个 `exec copilot --yolo "$@"` 的 wrapper，用 `.envrc` 的 `PATH_add "$PWD/.bin"` 按目录生效、离开自动撤回（注意 wrapper 里把自己所在目录从 PATH 摘掉避免递归）。

> **权衡**：`--allow-all-paths` / `--yolo` 让 agent 能读到 `~/.ssh/`、`~/.config/` 之类，有风险。不想全开就接受目录弹窗、必要时 `/add-dir` 临时加白。`isFolderTrusted` 是目录信任决策的核心函数，排查"为什么有的弹有的不弹"先搜它的所有 caller，每个 caller 的短路条件都可能是个旁路。

### `/rewind` 需要 git 仓库且至少一个 commit

#### 症状

`/rewind`（aka `/undo`）在两种情况下直接拒绝：

- 非 git 目录（cwd 没有 `.git`）→ 提示大意"不在 git 仓库里"。
- git 仓库但**还没有任何 commit** → 提示 *"the repository has no commits yet. Make an initial commit to enable rewind."*

即使只想回退几个对话 turn、不在乎文件回滚，也被挡。

#### 根因

每个 session 目录 `~/.copilot/session-state/<id>/rewind-snapshots/backups/` 下放的是被改文件的**完整字节拷贝**，`index.json` 列出每次 turn 的快照。所以 revert 的源头**完全是文件备份，根本不调 git**。

但 `RewindManager` 的静态构造有两道硬性前置检查（搜错误文案 `no-git-repo` / `no-commits` 定位）：

1. `git rev-parse` 找不到仓库 → `{ok:false, reason:"no-git-repo"}`
2. `git rev-parse HEAD` 失败（无 commit）→ `{ok:false, reason:"no-commits"}`

两道都过不了就不创建 `RewindManager`，无论你想回退会话还是文件。git 在 rewind 流程里只是辅助（省空间 + 安全网），不是 revert 的技术依赖，但这两个 product check 是硬门槛。

#### 解决（按推荐度）

1. **父工作区造一个有 commit 的空仓库**（推荐）：在父目录 `git init`、`echo '*' > .gitignore`、`git add -A && git commit -m init`（关键：**必须有这个首 commit**，光 `git init` 过不了 `no-commits`）。子项目各自的 `.git` 优先匹配、不受影响；父目录 `git status` 永远空，但两道检查都能过。
2. **进具体子项目再启动 copilot**：每个子项目有自己的 `.git` 和历史。缺点：跨子项目的会话要重起。
3. **`/clear` 或 `/new` 开新会话**：彻底丢上下文，相当于重置而非 rewind。

> **报错文案 ≠ 技术根因**——"不在 git 仓库"听起来像技术限制，扒源码才知道是 product check。找证据先看磁盘 artifact：`~/.copilot/session-state/<id>/` 下的 `rewind-snapshots/`、`events.jsonl`、`session.db` 是 ground truth。

---

## 配置与指令发现（Walk-Up）

Copilot CLI 的多种项目级配置/指令文件，发现策略都基于 **walk-up**（从 cwd 向上遍历，撞到 boundary 就停）。本节先给统一机制和对比表，再逐个子系统落规则与排障。

### 机制总览与子系统对比

**核心 walk-up**：MCP、Skills 的项目级发现共用同一个 walk-up 函数（搜 `"inherited"` 能定位：它给 depth 0 打标签 `"project"`、>0 打 `"inherited"`）。从 startPath（cwd）向上走，每层检查目标文件/目录是否存在，**撞 boundary（git root）就停**。关键细节：**先 push 当前层、再判断是否到 boundary**，所以 boundary 那层的文件能被收录。

**Custom Instructions 不走这个统一函数**——它有自己一套（git root 单点查 + 中间层向上扫 + cwd 单点查），但**效果等同**于 cwd→git root 的完整 walk-up。**Hooks 完全不 walk-up**，只看固定路径。

逐个回答"在 `<gitRoot>/packages/billing/` 工作时，`<gitRoot>/` 下的文件能不能被找到"：

| 子系统 | Walk-up | Boundary | 不在 git repo 时 | 用户级路径 | Env 覆盖 |
|--------|---------|----------|------------------|-----------|----------|
| **Custom Instructions**<br>(AGENTS.md 等) | ✅ 中间层向上扫，两端单独查 | git root | 只读 cwd | `~/.copilot/copilot-instructions.md`<br>`~/.copilot/instructions/` | `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` |
| **MCP** (`.mcp.json`) | ✅ cwd→git root 沿途合并 | git root | 只读 cwd 一份 | `~/.copilot/mcp-config.json` | — |
| **Skills** (`.agents/skills` 等) | ✅ cwd→git root 沿途收录 | git root；无 git 回退 `$HOME` | 一路扫到 `$HOME` | `~/.copilot/skills`<br>`~/.agents/skills` | `COPILOT_SKILLS_DIRS` |
| **Hooks** (`.github/hooks`) | ❌ 只看 git root 一层 | git root（非 git 用 cwd） | cwd | `config.json` 内联 `hooks` 键 | — |

**共同特征**：

- **Boundary 都是 git root**——子项目如果是独立 git repo，上溯立刻停在子项目根，看不到父目录。这是后面所有"多 repo 工作区漏装"排障的同一个根因。
- **用户级路径不受 walk-up boundary 限制**，永远可见。

### Custom Instructions（指令文件）

往 system prompt 注入的用户/项目自定义指令。Copilot CLI **主动兼容其他 AI 编码工具的指令文件格式**，识别以下文件（搜 `GEMINI.md` 能看到这份 convention 数组）：

| 文件 | 搜索子路径 | 说明 |
|------|-----------|------|
| `copilot-instructions.md` | `.github/` | Copilot 原生 |
| `AGENTS.md` | `.`（目录根） | 通用 agent 约定 |
| `CLAUDE.md` | `.` 和 `.claude/` | Claude Code |
| `GEMINI.md` | `.`（目录根） | Gemini |

**全部合并注入，不互斥**：仓库里同时存在这几种，**全部读取**，各自包裹在 `<custom_instruction>` 标签里按顺序拼接。不做选择、不做冲突检测，只在 realPath 或 content 完全相同时去重。文件名**大小写不敏感**（先精确匹配，失败后 `readdir` + `toLowerCase` fallback）。

发现范围分四处，效果等同完整 walk-up：

1. **git root 级**：每种文件在 git root 各查一次 → location `repository`
2. **cwd 级**（当 cwd ≠ git root）：在 cwd 额外查一次 → location `working-directory`；与 git root 那份**都注入**，不互相覆盖
3. **中间层**：cwd 与 git root **之间**（不含两端）逐层向上扫 → id `inherited-*`
4. **嵌套子目录 `AGENTS.md`**：向**下**扫子目录（搜 `nested AGENTS.md`），注入时**不展开内容**，而是生成一个表格提示 agent "需要时用 `view` 工具读取"

另外 `.github/instructions/**/*.instructions.md` 支持 glob 递归（在 git root 和 cwd 下分别扫），这些文件支持 **frontmatter**：`applyTo`（glob 限定适用范围）、`excludeAgent`（排除特定 agent 类型）、`description`（搜 `applyTo` / `excludeAgent` 定位解析）。

**用户级指令**（两个固定路径，不 walk-up）：

| 路径 | 注入 location |
|------|------|
| `~/.copilot/copilot-instructions.md` | `user` |
| `~/.copilot/instructions/**/*.instructions.md` | `user` |

**Env 覆盖**：`COPILOT_CUSTOM_INSTRUCTIONS_DIRS`（逗号分隔的绝对路径）作为额外搜索根，传给嵌套 AGENTS.md 和 `.github/instructions` glob。

**注入顺序**（决定在 prompt 中出现的位置）大致是：用户级 → git root 级 copilot-instructions → cwd 级 → git root 级 AGENTS/CLAUDE/GEMINI → cwd 级同类 → 中间层 inherited → `.github/instructions` → 嵌套 AGENTS.md 表格 → 递归子目录指令。同 realPath / content 去重。

**关闭**：`copilot --no-custom-instructions` 跳过整个加载。

### MCP 配置

生态里有**三个不同位置**的 MCP 配置文件（名字都带 "mcp" 容易混），加上 Copilot 专有的 `.github/mcp.json`：

| | `.mcp.json` | `.github/mcp.json` | `.vscode/mcp.json` | `~/.copilot/mcp-config.json` |
|---|---|---|---|---|
| **谁读它** | Copilot CLI / Claude Code / Cursor | Copilot CLI | VS Code 编辑器内 | Copilot CLI |
| **顶层 key** | `mcpServers` | `mcpServers` | `servers`（+`inputs`）| `mcpServers` |
| **Walk-up** | ✅ cwd→git root | ✅ 同左（共用发现函数）| ❌ 只读 workspace folder | ❌ 固定全局 |
| **`${VAR}` env 展开** | `env` 字段支持；`headers` 字段**实测不可靠**（#1232）| 同左 | `${env:VAR}` 支持 | 同左 |
| **`${input:...}` / `${workspaceFolder}`** | ❌ | ❌ | ✅（弹窗输入，keychain 存储）| ❌ |
| **同名冲突** | last-wins（cwd 覆盖祖先/全局）| 同左 | VS Code 内独立 | 被 workspace 覆盖 |

源码：`.mcp.json` / `.github/mcp.json` 两个文件名搜得到（它俩共用 walk-up 发现函数与合并逻辑）。VS Code 那套是另一个进程、另一套变量系统，不要混用语法。

#### `.mcp.json` 上溯停在 git root（多 repo 工作区漏装）

**症状**：父目录 `.mcp.json` 注册了 server，在父目录 `copilot mcp list` 能看到，但 `cd <subdir> && copilot mcp list` 看不到（subdir 是独立 git repo）。

**结论**（反直觉，但实测 + 读源码都成立）：

1. **会合并**：walk-up 收集 cwd→git root 每层的 `.mcp.json`，按 depth 倒序合并、cwd 覆盖祖先（last-wins）。
2. **触发合并的前提是有 git root**：
   - cwd 在某 git repo 内 → 上溯到该 repo root，沿途合并
   - cwd **不在**任何 git repo → 只读 cwd 一份，不上溯
   - cwd 自己就是 git root → push 完 cwd 那份就停，parent 拿不到
3. 所以想让 `~/projects/{a,b,c}/` 都继承 `~/projects/.mcp.json` → 在 `~/projects/` `git init`，且 `a/b/c` 自己**不是**独立 git repo（否则它们的 git root 钉在自己身上）。

> `copilot mcp list` 输出的 `Source:` 列：`Project (.mcp.json)` 是 cwd 那份，`Inherited (...)` 是上溯命中的祖先——可快速验证合并实际生效到哪。多 repo 套娃的通用解见 [direnv symlink](#通用-workarounddirenv-symlink)。

#### `.mcp.json` headers 里 `${VAR}` 展开不生效

**症状**：HTTP MCP server 的 `headers` 里用 `${VAR}` 引用环境变量，CLI 把字面量 `Bearer ${MY_GH_PAT}` 原样发出 → `Authorization header is badly formatted`。硬编码 PAT 则正常。复合字符串、纯变量、无花括号、全局配置文件，**都不可靠**。

**已知 issue**：[#1232](https://github.com/github/copilot-cli/issues/1232)（headers 不展开，官方称已修但有人在 direnv 环境下仍复现）、[#3100](https://github.com/github/copilot-cli/issues/3100)（可能先触发 OAuth discovery 导致 header 没机会发）、[#2960](https://github.com/github/copilot-cli/issues/2960)（反向佐证：某些环境确实能展开）。叠加因素还包括：敏感变量名会被 [token 黑名单](#黑名单清单)的 `${VAR}` 展开拦截主动屏蔽。

**workaround**：headers 里硬编码 PAT，文件 `chmod 600` + 不入版本控制。用 VS Code 的话走 `.vscode/mcp.json` + `${env:VAR}` / `${input:...}`（那是 VS Code 原生变量系统，独立于 CLI）。

### Skills 发现

走与 MCP 相同的 walk-up（boundary = git root），扫 3 个项目级 convention（搜 `COPILOT_SKILLS_DIRS` 附近能看到这份数组）：

- `.github/skills` · `.agents/skills` · `.claude/skills`

外加用户级固定路径与 env：

- `~/.copilot/skills` → source `personal-copilot`
- `~/.agents/skills` → source `personal-agents`
- `COPILOT_SKILLS_DIRS`（逗号分隔绝对路径，最高优先）+ `builtin-skills/`（CLI 安装目录）

#### 项目级 skill 上溯停在 git root

**症状**：父目录 `.agents/skills/<name>/SKILL.md` 写好了，在父目录起 copilot 能看到；`cd <subdir>`（独立 git repo）启动则 `/skills` 里看不到。`~/.agents/skills/` 下的 user-level skill 始终可见——现象是"项目级漏掉、user 级正常"。

**根因**：boundary 是 git root，子项目自己是 git repo 时上溯立刻停在子项目根。

**一个重要细节**：boundary 的 fallback 是 **`$HOME` 而不是 `/`**。所以"父目录和子项目都不是 git repo"（cwd 完全不在任何 git repo 内）时，会一路扫到家目录，反而能拿到祖先 `.agents/skills`；一旦 cwd 进入任何 git repo，boundary 就钉到那个 git root。

**解决**：[direnv symlink](#通用-workarounddirenv-symlink) 把 `.agents/skills` 软链进每个子项目；或软链单个 skill 到 `~/.agents/skills/<name>` 让它全局可见；临时测试用 `COPILOT_SKILLS_DIRS=/abs/path copilot`。

**验证**：启动后 `/skills` 看来源标签（project / inherited / personal-agents / builtin）。skill 不出现先判断是路径问题还是 `SKILL.md` 解析问题——临时软链到 `~/.agents/skills/` 能出现就是路径问题；仍不出现就查 frontmatter（`name` 须匹配 `^[a-zA-Z0-9][a-zA-Z0-9._\- ]*$` 且 ≤64 字符，`description` ≤1024，`user-invocable: false` 从用户列表隐藏，`disable-model-invocation: true` 从模型列表隐藏）。

> `.agents/skills`（walk-up + git root boundary）和 `~/.agents/skills`（固定 user-level）是两条独立路径——这也是为什么 `~/.agents/skills/` 下的 skill 永远在、而项目里 `.agents/skills/<x>` 时有时无。skill 改了**当前 session 不重载**，下次启动才生效。

### Hooks（preToolUse / Safety Net）

Hooks **完全不 walk-up**，只看两个固定位置：

1. **项目级**：`<git-root>/.github/hooks/`（在 git repo 内用当前 git root，否则用 cwd）
2. **用户级**：写在 `~/.copilot/config.json` 顶层的内联 `hooks` 键（与 `.github/hooks/*.json` 同 schema）

支持的事件类型不止 `preToolUse`——1.0.64-1 包含 `preToolUse` / `preMcpToolCall` / `postToolUse` / `preEdits` / `postEdits` / `preCommit` / `prePRDescription` / `postResult` / `permissionRequest` / `userPromptSubmitted` / `sessionStart` / `stop`（搜 `preMcpToolCall` 能看到 schema 定义那段）。

正确的 Copilot 格式（注意 `version: 1`、camelCase 事件名、命令字段叫 `bash` 在顶层、无 `matcher`）：

```json
// <project-root>/.github/hooks/safety-net.json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      { "type": "command", "bash": "npx -y cc-safety-net --copilot-cli", "timeoutSec": 15 }
    ]
  }
}
```

#### marketplace 分发的 Safety Net plugin 装了不触发

**症状**：`/plugin install kenryu42/copilot-safety-net` 装好后，`rm -rf <cwd内目录>`、`git reset --hard HEAD~1` 仍能执行，没有 BLOCKED。`~/.copilot/logs/process-*.log` 只有 `Loaded 1 hook(s)` 但整个 session 没有任何一次 hook 实际被调用。

**双 bug**：

1. plugin 自带的 `hooks/hooks.json` 是 **Claude Code 格式**（`PreToolUse` 大驼峰、有 `matcher`、命令在嵌套 `hooks` 数组里），Copilot 不认。
2. [copilot-cli#2540](https://github.com/github/copilot-cli/issues/2540)：从 marketplace / git 装的 plugin 里 `hooks/*.json` **根本不会被加载执行**；只有**手动**复制到项目 `.github/hooks/` 才触发。

**解决**：不靠 plugin，自己在项目里写上面那段正确格式的 hook，然后 `copilot plugin uninstall copilot-safety-net`（避免误以为 plugin 在保护）。重启 Copilot 生效。

> 实测 `--allow-all-tools`（含 `COPILOT_ALLOW_ALL`）下 Safety Net 仍能拦 `git reset --hard`——`preToolUse` hook 在 permission system 之前跑，不被 allow-all 跳过。验证 cc-safety-net 工具本身：`echo '{"toolName":"bash","toolArgs":"{\"command\":\"git reset --hard\"}"}' | npx -y cc-safety-net --copilot-cli`，正常输出 `{"permissionDecision":"deny",...}`（输入字段 `toolName`/`toolArgs` 驼峰，`toolArgs` 是字符串化 JSON）。相关：[hook 配置规范](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks)。

#### 项目级 hook 路径解析停在 git root（多 repo 工作区漏装）

**症状**：父目录套多个独立 git 仓库（父目录本身不是 git）。父目录 `.github/hooks/safety-net.json` 配好后，cd 进父目录启动正常，cd 进任何子项目启动则 hook 不触发。

**根因**：hook 查找在 git repo 内用**当前 git root**，否则用 cwd，**不向上查父目录**。子项目自己是独立 git repo，看不到父目录的 hook。

**解决**：[direnv symlink](#通用-workarounddirenv-symlink) 把父目录 hook 软链到所有子目录的 `.github/hooks/`；或挪到 user-level（`config.json` 内联 `hooks`）。改 hook 文件 / 加新 symlink 后**当前 session 不受影响**（hook 启动时一次性加载），下次启动才生效。

#### `cc-safety-net` 自定义规则：user scope vs project scope

`cc-safety-net` 加载自定义规则**不做父目录遍历**，只两个搜索路径：

1. **User scope**：`~/.cc-safety-net/config.json`（始终加载）
2. **Project scope**：`$CWD/.safety-net.json`（仅当前目录）

同名 rule project scope 覆盖 user scope，其余合并。**想跨子仓库生效的规则放 user scope**，别靠 symlink `.safety-net.json`（那是 project scope，只作用于 cwd）。注意区分"规则定义在哪"（user/project scope）和"hook 在哪激活"（仍需每个项目装 `.github/hooks/safety-net.json`）——规则全局定义，但只在装了 hook 的项目内拦截。验证：`npx -y cc-safety-net --verify-config` / `npx -y cc-safety-net explain "gh repo view"`。

### 通用 workaround：direnv symlink

所有 walk-up 子系统在"父目录套独立子 git repo"场景下都看不到父目录配置。通用解是 direnv 自动维护 symlink（cd 进父目录时把父目录配置软链进各子目录，并写入子项目 `.git/info/exclude` 不污染 `git status`）：

```bash
# .envrc
link_into_subdirs() {
  local src="$1" rel="$2" sub target excl
  [[ -f "$src" || -d "$src" ]] || return 0
  for sub in "$PWD"/*/; do
    sub="${sub%/}"; target="$sub/$rel"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      mkdir -p "$(dirname "$target")"; ln -s "$src" "$target"
    fi
    excl="$sub/.git/info/exclude"
    if [[ -f "$excl" ]] && ! grep -qxF "/$rel" "$excl"; then
      printf '/%s\n' "$rel" >> "$excl"
    fi
  done
}

link_into_subdirs "$PWD/.github/hooks/safety-net.json" '.github/hooks/safety-net.json'
link_into_subdirs "$PWD/.mcp.json"                     '.mcp.json'
link_into_subdirs "$PWD/.agents/skills"                '.agents/skills'
link_into_subdirs "$PWD/AGENTS.md"                     'AGENTS.md'
```

direnv 本身改不了 copilot 找配置的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**。或者把配置搬到 user-level 路径，绕过 walk-up boundary。改 `.envrc` 后要 `direnv allow` 重新授权（基于文件 hash）。

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

## Git 认证 / Credential helper

### env 黑名单下的 `git push` 对策

agent bash 里 `$GITHUB_PERSONAL_ACCESS_TOKEN` 永远为空（[黑名单](#黑名单清单)），任何依赖该变量名的 credential helper 都会以空密码失败。三种对策：

1. **换一个不在黑名单里的变量名（推荐）**：token 存进 `MY_GH_PAT`、`<PROJECT>_GH_TOKEN` 这种 Copilot 不识别的名字，credential helper 也引用新名字。配置走 `GIT_CONFIG_KEY_n / VALUE_n`（这组 env 不在黑名单里），agent shell 里 `git push` 直接通。详见下节。
2. **用 `gh auth git-credential`**：让 agent 端 `gh` 登录账号有目标仓写权限，`gh auth setup-git` 把 helper 写进 `~/.gitconfig`。注意它改全局 gitconfig，scope 比方案 1 大。
3. **让用户在 host shell push**：commit 由 agent 做，push 由用户在自己 terminal 跑。最稳但最麻烦。

### 用 `GIT_CONFIG_COUNT` 注入内联 credential helper

**场景**：希望工作区内 `git push` 自动用正确账号 token，但**不想跑 `gh auth setup-git`**（那会把 helper 写进全局 `~/.gitconfig`，对工作区外所有项目也生效）。

**机制**：git 2.31+ 支持用一组 env 临时注入配置（scope = `command`，优先级介于命令行 `-c` 和 `~/.gitconfig` 之间）：

```
GIT_CONFIG_COUNT=N
GIT_CONFIG_KEY_<i>   GIT_CONFIG_VALUE_<i>     # i ∈ [0, N-1]
```

这组变量名不在 Copilot 的 env 黑名单里，所以从 host shell direnv export 后能完整传到 agent bash。

**解决**（放工作区根 `.envrc`）：

```bash
export MY_GH_PAT="ghp_xxx..."     # 变量名故意避开 GITHUB_PERSONAL_ACCESS_TOKEN（黑名单，agent 拿不到）

_n="${GIT_CONFIG_COUNT:-0}"       # 累加，避免覆盖 Copilot 已注入的几对
export "GIT_CONFIG_KEY_$_n=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$_n="                                          # 空值，清空之前继承的 helper 链
export "GIT_CONFIG_KEY_$((_n+1))=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$((_n+1))=!f(){ test \"\$1\" = get && printf 'protocol=https\nhost=github.com\nusername=<user>\npassword=%s\n' \"\$MY_GH_PAT\"; }; f"
export GIT_CONFIG_COUNT=$((_n+2))
unset _n
```

**几个易踩坑点**：

1. **`credential.helper` 是累加列表不是覆盖**——必须先写一条空值 `helper=`（git 约定：空串清空之前所有 helper），再写 `helper=!...`，否则会先调系统 keychain 等继承下来的 helper。
2. **必须 append 到现有 COUNT 后面**——Copilot 自己会注入几对（见 [可见信号](#设计意图与可见信号)）；从 0 覆盖会让它的配置失效。`_n="${GIT_CONFIG_COUNT:-0}"` 是关键。
3. **不要用 `GH_TOKEN` / `GITHUB_TOKEN` / `GITHUB_PERSONAL_ACCESS_TOKEN`**——前两个 git/gh 会自动读，第三个在黑名单里 agent 读不到。用一个三方都不识别的名字（如 `MY_GH_PAT`），只在 helper 里显式引用。
4. **scope=`command` 是 env 注入的标志**——排查"我没在哪写过这条 config 怎么 git 看到了"用 `git config --show-scope --show-origin --list` 一目了然。

### `gh repo fork` 跨账号 push 用错 SSH 身份

**症状**：工作区配的是账号 A，`gh repo fork upstream/x --clone` 成功（API 走 `GH_TOKEN`，账号没问题），但 `git push origin main` 报 `Permission to <account-a>/x.git denied to <account-b>`。

**根因**：跟 `gh` 无关，是 SSH 阶段错配。`~/.ssh/config` 里 `Host * → IdentityFile ~/.ssh/id_ed25519`，而这把默认 key 注册在**账号 B** 名下。`gh repo fork --clone` 默认走 SSH protocol，用的是本机默认 ssh key，跟 `GH_TOKEN` 完全无关。

```bash
ssh -T git@github.com    # → "Hi <wrong-account>!" 一目了然
```

**解决**三选一：

| 方案 | 怎么做 | 适合 |
|---|---|---|
| **A**（最简单）| push URL 改 HTTPS 走 token：`git remote set-url --push origin https://github.com/<account-a>/x.git` + [上节 GIT_CONFIG helper](#用-git_config_count-注入内联-credential-helper) | 一次性跨账号 fork |
| B | ssh config 加别名 `Host github.com-alt` + 对应 IdentityFile，clone URL 改 `git@github.com-alt:...` | 长期多账号项目 |
| C | `gh config set git_protocol https`，gh 默认走 HTTPS + token | 统一所有 gh 操作 |

> `GH_TOKEN` / `gh auth` 只覆盖 **API 操作**；**git transport** 是另一条独立通道。"推之前看一眼 `git remote -v` 和 `ssh -T git@github.com`"是跨账号场景的卫生习惯。GitHub 对完全无权限的私有仓回 `Repository not found`、对只读 collaborator 回真实数据、对没写权限的 push 回 `Permission denied`——三种回复对应三种身份状态。

---

## 运维

### 重试策略 patch（transient API error）

**症状与根因**：网络抖动 / HTTP/2 GOAWAY / 模型上游瞬时不可用时，CLI 以如下错误中断当前 turn：

```
✗ Execution failed: Error: Failed to get response from the AI model;
  retried 5 times (total retry wait time: 6.00 seconds)
  Last error: CAPIError: Connection error.
```

5 次重试一共才等 6 秒，对真实网络问题不够（同 [copilot-cli#2421](https://github.com/github/copilot-cli/issues/2421) 一类）。CLI 内部默认 `maxRetries = 5`，非-API 错误（连接挂、GOAWAY 这类拿不到 HTTP 响应的）每次间隔 = `retryAfter * (0.8 + random*0.4)`，retryAfter 可能不到 1 秒。**没有任何 `settings.json` / CLI flag / 环境变量**能改这两个值（`--timeout` 作用于工具调用不是模型 API；`continueOnAutoMode` 是 rate-limit 时切 auto 跟连接错误无关）——要改只能 patch。

**应用 patch**：

```bash
~/TiMidlY-projects/skills/skills/.curated/software/scripts/patch-copilot-cli-retry.sh
```

做两件事：`maxRetries: 5 → 10`；给非-API 错误的每次等待加 4 秒下限。综合效果：原来 ~6 秒放弃，patch 后 ≥40 秒才放弃。

**实现要点**：

- 只 patch `app.js`（CLI 实际跑的那份），不动 `sdk/index.js`。
- 用 `node -e` 正则替换（minified JS 变量名跨版本会变，脚本用反向引用适配）。
- 幂等：每个 patch 点带 `/*tmy-retry-patch*/` marker，已 patch 的跳过。
- 备份：同目录留 `app.js.orig.timidly-bak`，回滚 `cp ...bak app.js`。
- 覆盖所有可能的 pkg cache 根（`$COPILOT_CACHE_HOME/pkg` / `$XDG_CACHE_HOME/copilot/pkg` / macOS `~/Library/Caches/copilot/pkg` / `$COPILOT_HOME/pkg` / `~/.copilot/pkg`）。

**验证**：搜锚点 `retryPolicy?.maxRetries`（patch 后应看到 `??10/*tmy-retry-patch*/` 而非 `??5`）。

**Auto-update 后需重跑**：CLI 默认 `autoUpdate: true`，后台拉新版本到新的 `pkg/.../<new-version>/`，loader 自动切最高版本，**新目录的 `app.js` 是干净的**。判断要不要重跑：`grep -L 'tmy-retry-patch' ~/.cache/copilot/pkg/linux-x64/*/app.js`（列出来的就是没 patch 的）。patch 幂等，手动跑也够。

> 同款思路适用于任何想调 CLI 内部常量的场景（如 `defaultRetryAfterSeconds`）。锚点选**字面量唯一的 minified 片段**（带 `e?.retryPolicy?.` 这种独特路径），不要选纯数字（容易撞）。

### Chronicle 搜索给 resume ID：必须给本地 ID

`/chronicle search` 用 `session_store_sql` 查的是**云端 + 本地两套 session store 合并**的结果（每行带 `_query_source` = `cloud` / `local`）。同一会话在两套库里 **session ID 不一样**：云端是同步副本，本地是 `~/.copilot/session-state/<id>/` 下真正能 resume 的那份。

**`copilot --resume=<id>` 只认本地 ID**——拿云端 ID 去 resume 会报 `No session, task, or name matched`。所以给用户用来 resume 的 ID 时：

- **只给本地 ID**（`_query_source = 'local'` 且 `~/.copilot/session-state/<id>/` 目录存在）。
- 同名会话既有 cloud 又有 local 时，**优先取 local 行的 ID**。
- 不确定就本地核一下：`ls ~/.copilot/session-state/<id>` 有目录才可 resume。
- 纯 cloud-only（本地无目录）的会话：明说「本机不可 resume，状态在另一台机器上」，别给一个 resume 不了的 ID。

