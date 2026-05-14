# GitHub Copilot CLI

Copilot CLI 内部行为的逆向工程与排障笔记。涵盖：进程模型、bash 工具 env 处理、权限与目录信任、Hook（preToolUse / Safety Net）、MCP 配置、git 认证。

大部分章节附 `app.js` 源码摘录与字节偏移；偏移**仅供参考**，混淆后的符号 (`xj` / `_R` / `Nhe` / `bBt` / `sN` …) 是 esbuild 产物的稳定特征，会随版本变化但用关键字面量（`COPILOT_RUN_APP` / `COPILOT_ALLOW_ALL` / `GITHUB_PERSONAL_ACCESS_TOKEN` / `safe.bareRepository` …）能在新版本里重新定位。

## 目录

- [进程模型](#进程模型)
  - [三层结构：loader → app.js](#三层结构loader--appjs)
- [Bash 工具](#bash-工具)
  - [Env 黑名单：为何 `git push` 在 agent 里总是 401](#env-黑名单为何-git-push-在-agent-里总是-401)
  - [`BASH_ENV` 只对非交互 bash 生效](#bash_env-只对非交互-bash-生效)
- [权限与目录信任](#权限与目录信任)
  - [三套独立机制：`trustedFolders` / `permissions-config` / 会话级 allowed-dir](#三套独立机制trustedfolders--permissions-config--会话级-allowed-dir)
  - [`COPILOT_ALLOW_ALL` ≠ `--allow-all` / `--yolo`](#copilot_allow_all--allow-all--yolo)
  - [`/rewind` 在非 git cwd 直接拒绝](#rewind-在非-git-cwd-直接拒绝)
- [Hooks（preToolUse / Safety Net）](#hookspretooluse--safety-net)
  - [marketplace 分发的 Safety Net plugin 装了不触发：双 bug](#marketplace-分发的-safety-net-plugin-装了不触发双-bug)
  - [项目级 hook 路径解析停在 git root（多 repo 工作区漏装）](#项目级-hook-路径解析停在-git-root多-repo-工作区漏装)
  - [`cc-safety-net` 自定义规则：user scope vs project scope](#cc-safety-net-自定义规则user-scope-vs-project-scope)
- [MCP 配置](#mcp-配置)
  - [三种 MCP 配置文件的区别](#三种-mcp-配置文件的区别)
  - [`.mcp.json` 上溯停在 git root（多 repo 工作区漏装）](#mcpjson-上溯停在-git-root多-repo-工作区漏装)
  - [`.mcp.json` headers 里 `${VAR}` 展开不生效](#mcpjson-headers-里-var-展开不生效)
- [Git 认证 / Credential helper](#git-认证--credential-helper)
  - [Bash 工具 env 黑名单下的 `git push` 对策](#bash-工具-env-黑名单下的-git-push-对策)
  - [用 `GIT_CONFIG_COUNT` env 临时注入 credential helper](#用-git_config_count-env-临时注入-credential-helper)
  - [`gh repo fork` 跨账号 clone 后 push 用错 SSH 身份](#gh-repo-fork-跨账号-clone-后-push-用错-ssh-身份)

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

- 官方文档说 "Trusted directories control where Copilot CLI can read, modify, and execute files" 听起来涵盖所有文件访问，实际只管启动信任。运行时目录边界是另一套。
- 三套同主题机制位置和作用都不一样（`config.json` / `permissions-config.json` / 内存）；看到字段名带 "trust" 或 "allow" 不能想当然认为是同一回事。
- 从子目录启动 copilot 是隐性陷阱：直觉以为 `trustedFolders` 包含父目录就够了，实际还得让启动 cwd 本身覆盖你想访问的范围。

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

## Hooks（preToolUse / Safety Net）

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

也可以走全局：把同一段 `hooks` 对象写到 `~/.copilot/config.json` 顶层（Copilot CLI v0.0.422+ 支持 user-level hooks）。

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

- safety-net 主仓库 issue 24：https://github.com/kenryu42/claude-code-safety-net/issues/24
- Copilot CLI plugin hook 不加载：https://github.com/github/copilot-cli/issues/2540
- Copilot CLI hook 配置规范：https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks

---

### 项目级 hook 路径解析停在 git root（多 repo 工作区漏装）

#### 症状

工作区是"父目录套多个独立 git 仓库"结构（如 `~/projects/{repo-a,repo-b,...}`，每个子目录是独立 repo，父目录本身不是 git）。父目录 `.github/hooks/safety-net.json` 配好后，cd 进父目录启动 copilot 正常；但 cd 进任何子项目启动 copilot，hook 完全不触发。

#### 根因

Copilot CLI `getHooksDir` 的查找逻辑：在 git repo 内用 **当前 git root**，否则用 cwd，**不会向上查父目录**。子项目自己是独立 git repo，git root 就是子项目自己，看不到父目录的 hook。env vars 改不了这个路径。

#### 解决：父目录 `.envrc` 自动 symlink

cd 进父目录时，让 direnv 把父目录 hook 软链到所有子目录的 `.github/hooks/`，并把 symlink 写入子项目的 `.git/info/exclude`（不污染 `.gitignore`，不进版本控制）。新增子项目 cd 一次父目录就自动同步。

```bash
# .envrc
link_into_subdirs() {
  local src="$1" rel="$2" sub target excl
  [[ -f "$src" ]] || return 0
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
link_into_subdirs "$PWD/.github/hooks/safety-net.json" '.github/hooks/safety-net.json'
```

direnv 本身不能改 copilot 找 hook 的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**。如果不想限定子项目而是想全局生效，把 hook 搬到 `~/.copilot/config/hooks/safety-net.json` 即可。

#### 教训

- "项目级 hook" = **当前 git root 级**，不是当前工作区根级。多 repo 工作区要么走 user-level hook（`~/.copilot/config/hooks/`），要么自己分发文件。
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
4. **`~/.copilot/mcp-config.json`**：Copilot CLI 的用户级全局配置。适合放全局性的 MCP server（如 GitHub MCP），不跟随项目走。优先级最低，会被同名 workspace 配置覆盖。

#### 实际使用建议

- **只用 Copilot CLI**：用 `.mcp.json`，secrets 硬编码（目前没有安全的替代方案，`headers` 里 `${VAR}` 展开不可靠，见下文）
- **只用 VS Code**：用 `.vscode/mcp.json` + `${input:...}` 或 `${env:VAR}`
- **两边都用**：维护两份配置，`.mcp.json`（CLI）+ `.vscode/mcp.json`（VS Code），用 direnv 同步环境变量

#### 相关 issue / 文档

- VS Code MCP 配置参考：https://code.visualstudio.com/docs/copilot/reference/mcp-configuration
- VS Code MCP 文档：https://code.visualstudio.com/docs/copilot/chat/mcp-servers
- Copilot CLI plugin 参考（含加载优先级图）：https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
- Copilot CLI 添加 `.mcp.json` 支持：https://github.com/github/copilot-cli/issues/2938
- 社区抱怨需要两份配置：https://github.com/github/copilot-cli/issues/3019
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

跟 `safety-net.json` 同款的 direnv symlink 套路（[见上方 `link_into_subdirs` 通用函数](#项目级-hook-路径解析停在-git-root多-repo-工作区漏装)）：

```bash
# .envrc 里加（复用上节定义的 link_into_subdirs）
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
