# Copilot CLI 踩坑

## Copilot CLI 的 `BASH_ENV` 注入只对非交互 bash 生效

> 2026-05-09 | Copilot CLI 1.0.44 | Linux

### 症状

`.envrc` 里 `export BASH_ENV="$PWD/.copilot.env"`，意图把账号 A 的 `GH_TOKEN` 注入到 Copilot 派生的 bash 子进程，但**不污染** Copilot 主进程（避免它把订阅绑到这个 token 的账号身上）。

但 agent 直接在 bash 工具里跑 `gh api user --jq .login`，返回的是 `~/.config/gh/hosts.yml` 里的默认账号（账号 B），不是预期的账号 A。

### 根因

`BASH_ENV` 是 **bash 内置机制**，仅在 bash 以**非交互式**启动时（`bash -c "..."`、`bash script.sh`）才会自动 source。Copilot CLI 的 bash 工具起的是带 TTY 的**交互式** shell，不会触发 `BASH_ENV`。

### 解决

每条命令显式 source 或包一层非交互 bash，二选一：

```bash
source ~/TiMidlY-projects/.copilot.env && gh api user --jq .login
# 或
bash -c 'gh api user --jq .login'
```

不要在 `.envrc` 里直接 `export GH_TOKEN=...`，那样 Copilot 主进程也会拿到这个 token。

### 教训

- `BASH_ENV` 不是 Copilot 的功能，是 bash 的功能；Copilot 子进程是不是非交互的，决定它生不生效。
- 看到"应该有的 env 变量没有"先看 `echo $BASH_ENV` 有没有传过来，再看当前 shell 是不是交互式。

---

## Safety Net plugin 安装后从不触发（schema 错 + marketplace plugin hook 不加载）

> 2026-05-09 | Copilot CLI 1.0.44 | `kenryu42/copilot-safety-net` plugin v1.0.0

### 症状

按官方说明 `/plugin install kenryu42/copilot-safety-net` 装好 Safety Net，重启后仍能成功执行 `rm -rf <cwd 内目录>` 和 `git reset --hard HEAD~1`，没有 BLOCKED 提示。`COPILOT_ALLOW_ALL=1` 也开着。

### 排查弯路

- **第一次猜**：`COPILOT_ALLOW_ALL=1` 绕过了 hook → 错。`rm -rf <cwd 内路径>` 在 Safety Net 设计上**本来就放行**（README "Commands Allowed" 表里 `rm -rf ./... (within cwd)` 列为 allowed），不是 hook 没跑。
- **第二次猜**：还是 `COPILOT_ALLOW_ALL` 的锅 → 还是错。`git reset --hard` 在 Safety Net 黑名单里，理应被拦。
- **真相**：日志里 `~/.copilot/logs/process-*.log` 只有 `Loaded 1 hook(s) from 1 plugin(s)`，整个 session **没有任何一次 hook 实际被调用**。

### 根因（两个 bug 叠加）

1. **plugin 自带的 `hooks/hooks.json` schema 是 Claude Code 的格式，不是 Copilot CLI 的**：
   - 错的（plugin 现状）：`{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type":"command","command":"npx cc-safety-net --copilot-cli"}]}]}}`
   - 对的（Copilot 官方文档）：`{"version": 1, "hooks": {"preToolUse": [{"type":"command","bash":"npx -y cc-safety-net --copilot-cli","timeoutSec":15}]}}`
   - 区别：Copilot 要求 `version: 1`、camelCase `preToolUse`、没有 `matcher`、命令字段叫 `bash` 且在顶层。
   - 作者的另一个仓库 `kenryu42/claude-code-safety-net/.github/hooks/safety-net.json` 才是对的格式，但那个是项目级示例，没打进 plugin。

2. **github/copilot-cli#2540 未修 bug**：从 marketplace / git 装的 plugin 里 `hooks/*.json` 完全不会被 Copilot 加载执行。issue 评论确认：手动把 hook 文件复制到项目 `.github/hooks/` 才会触发。

两个 bug 任意一个不修，Safety Net 都跑不起来。

### 解决

不靠 plugin，自己在项目里写正确格式的 hook：

```json
// ~/<project-root>/.github/hooks/safety-net.json
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

实测 `--allow-all-tools`（含 `COPILOT_ALLOW_ALL=1`）下 Safety Net 仍然能拦 `git reset --hard`。Copilot 的 preToolUse hook 在 permission system 之前跑，不会被 allow-all 跳过。

也可以走全局：把同一段 `hooks` 对象写到 `~/.copilot/config.json` 顶层（Copilot CLI v0.0.422+ 支持 user-level hooks）。

### 教训

- **Safety Net "支持 Copilot CLI"≠"装上就有用"**：作者的主仓库 `claude-code-safety-net` 是对的，分发的 `copilot-safety-net` plugin 是错的；分清楚两个仓库。
- **`COPILOT_ALLOW_ALL` 不背锅**：它只是关掉 confirm 弹窗，不影响 hook 触发。看到 hook 不跑先去查 `~/.copilot/logs/process-*.log` 里有没有 hook 调用记录，再看是 schema 错还是 plugin 加载 bug。
- **验证 cc-safety-net 工具本身是否正常**：直接喂 stdin 测：
  ```bash
  echo '{"toolName":"bash","toolArgs":"{\"command\":\"git reset --hard\"}"}' \
    | npx -y cc-safety-net --copilot-cli
  ```
  正常会输出 `{"permissionDecision":"deny",...}`。注意输入字段是 `toolName` / `toolArgs`（驼峰），且 `toolArgs` 是**字符串**化的 JSON 不是对象。

### 相关 issue / 文档

- safety-net 主仓库 issue 24：https://github.com/kenryu42/claude-code-safety-net/issues/24
- Copilot CLI plugin hook 不加载：https://github.com/github/copilot-cli/issues/2540
- Copilot CLI hook 配置规范：https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks

---

## 项目级 hook 不会"向上查找"，多 git repo 工作区里子项目漏装

> 2026-05-09 | Copilot CLI 1.0.44 | Linux

### 症状

工作区是"父目录套多个独立 git 仓库"结构（如 `~/TiMidlY-projects/{skills,paseo,...}`，每个子目录是独立 repo，父目录本身不是 git）。父目录 `.github/hooks/safety-net.json` 配好后，cd 进父目录启动 copilot 正常；但 cd 进任何子项目启动 copilot，hook 完全不触发。

### 根因

Copilot CLI `getHooksDir` 的查找逻辑：在 git repo 内用 **当前 git root**，否则用 cwd，**不会向上查父目录**。子项目自己是独立 git repo，git root 就是子项目自己，看不到父目录的 hook。env vars 改不了这个路径。

### 解决：父目录 `.envrc` 自动 symlink

cd 进父目录时，让 direnv 把父目录 hook 软链到所有子目录的 `.github/hooks/`，并把 symlink 写入子项目的 `.git/info/exclude`（不污染 .gitignore，不进版本控制）。新增子项目 cd 一次父目录就自动同步。

骨架：

```bash
ensure_safety_net_symlinks() {
  local hook_src="$PWD/.github/hooks/safety-net.json"
  [[ -f "$hook_src" ]] || return 0
  for sub in "$PWD"/*/; do
    sub="${sub%/}"
    local target="$sub/.github/hooks/safety-net.json"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      mkdir -p "$sub/.github/hooks"
      ln -s "$hook_src" "$target"
    fi
    local excl="$sub/.git/info/exclude"
    if [[ -f "$excl" ]] && ! grep -qxF '/.github/hooks/safety-net.json' "$excl"; then
      printf '/.github/hooks/safety-net.json\n' >> "$excl"
    fi
  done
}
ensure_safety_net_symlinks
```

direnv 本身不能改 copilot 找 hook 的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**。如果不想限定子项目而是想全局生效，把 hook 搬到 `~/.copilot/config/hooks/safety-net.json` 即可。

### 教训

- "项目级 hook" = 当前 **git root 级**，不是当前工作区根级。多 repo 工作区要么走 user-level hook（`~/.copilot/config/hooks/`），要么自己分发文件。
- 改 hook 文件 / 加新 symlink 后，**当前 copilot session 不会受影响**（hook 启动时一次性加载），下次启动 copilot 才生效。
- `direnv allow` **基于 `.envrc` 内容 hash 授权**：改一次 `.envrc` 就要重新 allow 一次，hash 不变之后 cd 进出都自动加载，不需要每次 allow。

## `.mcp.json` 上溯停在 git root（多 repo 工作区里子项目漏装）

> 2026-05-09 | Copilot CLI 1.0.44 | Linux

### 症状

`~/TiMidlY-projects/.mcp.json` 注册了 `ssh-remote` MCP server，在 `~/TiMidlY-projects/` 直接 `copilot mcp list` 能看到 `Workspace servers: ssh-remote (local)`；但 `cd ~/TiMidlY-projects/ssh-remote-mcp && copilot mcp list` 显示 `No MCP servers configured`。

### 根因

读 Copilot CLI 安装包 `app.js`（`~/.local/share/fnm/.../node_modules/@github/copilot/app.js`）里的 `bBt(t, e, [{kind:"file", relativePaths:[".mcp.json"]}])` 函数：

```js
function bBt(t, e, r, n) {
  let o = [], s = Q3.normalize(e), a = Q3.normalize(t), l = 0;
  for (;;) {
    // collect <a>/.mcp.json if present
    if (a === s) break;            // s = git root (or trust boundary)
    let u = Q3.dirname(a);
    if (u === a || (n && !await n(u))) break;
    a = u; l++;
  }
}
```

它从 cwd 沿 `dirname` 一路向上找 `.mcp.json`，**但停在 git root 或 trust 边界**。`~/TiMidlY-projects/<subproject>/` 每个子项目都是独立 git repo，git root = 子项目自身，所以 `~/TiMidlY-projects/.mcp.json` 永远走不到。

> 关键词："上溯只到 git root"——这就是它和 VS Code 的 "workspace folder" 概念不一样的地方，在多 repo 工作区里反直觉。

### 解决

跟 `safety-net.json` 同款 direnv symlink 套路：

```bash
# .envrc 里加
ensure_mcp_symlinks() {
  local mcp_src="$PWD/.mcp.json"
  [[ -f "$mcp_src" ]] || return 0
  local sub target excl
  for sub in "$PWD"/*/; do
    sub="${sub%/}"
    [[ -d "$sub" ]] || continue
    target="$sub/.mcp.json"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      ln -s "$mcp_src" "$target"
    fi
    excl="$sub/.git/info/exclude"
    if [[ -f "$excl" ]] && ! grep -qxF '/.mcp.json' "$excl"; then
      printf '/.mcp.json\n' >> "$excl"
    fi
  done
}
ensure_mcp_symlinks
```

每个子项目都被自动塞一份 `.mcp.json` 软链 + 写进 `.git/info/exclude` 不污染 `git status`。

### 教训

- "Workspace MCP" 的"workspace" 是 **git repo 级**，不是用户主观的"工作区"。
- 实测才信结论；我第一次只看 `copilot mcp list` 就断言"完全不上溯"，是错的——读了 app.js 才发现它**会**上溯，只是停在 git root。
- `copilot mcp list` 输出的 `Source: Workspace (...)` 显示的是**实际命中**的那个文件路径，可以用来快速验证 symlink 起没起。

## `gh repo fork` 跨账号 clone 后 `git push` 用错 SSH 身份

> 2026-05-09 | gh CLI / SSH 默认配置 | Linux

### 症状

工作区按 AGENTS.md 默认账号是 TMYTiMidlY（`.copilot.env` 里 `GH_TOKEN`），跑：

```bash
source ~/TiMidlY-projects/.copilot.env  # GH_TOKEN=TMYTiMidlY
gh repo fork upstream/x --clone --fork-name x
```

fork 操作本身成功（API 调用走 GH_TOKEN，账号没问题），clone 出来的 origin 是 `git@github.com:TMYTiMidlY/x.git`。但后面 `git push origin main` 报：

```
ERROR: Permission to TMYTiMidlY/x.git denied to Agony5757.
```

很迷惑——明明 GH_TOKEN 是 TMYTiMidlY 的。

### 根因

跟 gh CLI 没关系，是 SSH 阶段错配。`~/.ssh/config` 里写的是：

```
Host *
    IdentityFile ~/.ssh/id_ed25519
```

而本机这把默认 key 注册在 **Agony5757** 名下（TMYTiMidlY 的 key 是 `id_ed25519_second`，但 ssh 默认不会拿）。GitHub 看到的是这把 key 对应的账号，所以 push 被拒。

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub        # 看 fingerprint
ssh -T git@github.com                       # → "Hi Agony5757!" 一目了然
```

### 解决

三选一：

| 方案 | 怎么做 | 适合 |
|---|---|---|
| **A**（最简单）| 把 push URL 改 HTTPS 走 token：`git remote set-url --push origin https://github.com/TMYTiMidlY/x.git`，然后 `git -c credential.helper='!f() { echo "username=x-access-token"; echo "password=$GH_TOKEN"; }; f' push` | 一次性跨账号 fork |
| B | ssh config 加别名：`Host github.com-tmy` + `IdentityFile ~/.ssh/id_ed25519_second`，clone 时把 URL 改成 `git@github.com-tmy:TMYTiMidlY/x.git` | 长期维护多账号项目 |
| C | `gh config set git_protocol https`，让 gh 默认 clone 用 HTTPS，push 直接走 GH_TOKEN | 统一所有 gh 操作 |

### 教训

- `gh repo fork --clone` 默认走 SSH protocol（看 `gh config get git_protocol`），用的是本机默认 ssh key，跟 GH_TOKEN 完全无关。
- "推之前看一眼 `git remote -v` 和 `ssh -T git@github.com`" 是跨账号场景的卫生习惯。
- AGENTS.md 关于 GH_TOKEN 的纪律只覆盖 **API 操作**（gh CLI 调 REST/GraphQL），**git transport** 是另一条独立通道，要单独管。
- **不要被"能 clone 就以为身份对了"骗到**：如果你的 SSH 默认账号被对方加为 collaborator，clone 完全 OK，但 push 到 `<别人>/...` 还是会因为没写权限被拒。GitHub 对**完全没访问权限**的私有仓回 `Repository not found`（不告诉你仓存在不存在），对**只读 collaborator**回真实数据，对**没写权限的 push** 回 `Permission denied`。三种回复对应三种状态，看响应内容能反推自己的身份关系。

---

## 用 `GIT_CONFIG_COUNT` env 把 gh 临时挂成 git credential helper（不污染 `~/.gitconfig`）

> 2026-05-09 | git 2.34 | Copilot CLI 1.0.44

### 症状

希望工作区内 `git push https://github.com/...` 自动用 `gh` CLI 拿 token（按当前 `GH_TOKEN` 决定账号），但**不想跑 `gh auth setup-git`**——那条命令会把 helper 写进全局 `~/.gitconfig`，对工作区**外**的所有项目（包括用别的账号的）也生效，是范围溢出。

### 关键发现

git 2.31+ 支持用一组 env 变量临时注入配置（scope = `command`，优先级介于命令行 `-c` 和 `~/.gitconfig` 之间）：

```
GIT_CONFIG_COUNT=N
GIT_CONFIG_KEY_<i>   GIT_CONFIG_VALUE_<i>     # i ∈ [0, N-1]
```

git 启动时把这 N 对 `(key, value)` 当成虚拟 config 项注入。用 `git config --show-scope --get-all <key>` 能看到 scope=`command` 的来源。

### 解决：direnv 注入 5 个 env 变量

放在工作区根 `.envrc`（direnv 自动加载/卸载）：

```bash
_n="${GIT_CONFIG_COUNT:-0}"     # 累加，避免覆盖 Copilot 注入的 KEY_0=safe.bareRepository
export "GIT_CONFIG_KEY_$_n=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$_n="                                    # ← 空值，清空之前继承的 helper 链
export "GIT_CONFIG_KEY_$((_n+1))=credential.https://github.com.helper"
export "GIT_CONFIG_VALUE_$((_n+1))=!gh auth git-credential"      # ← 启用 gh
export GIT_CONFIG_COUNT=$((_n+2))
unset _n
```

效果：

| 加 env 后 | 不加 env |
|---|---|
| `git push` 直接调 `gh auth git-credential`，gh 用 `GH_TOKEN`（或 hosts.yml active）输出 username + password | terminal 弹 `Username for 'https://github.com':`，hang 住等输入 |

### 几个易踩坑点

1. **`credential.helper` 是累加列表不是覆盖**——必须先写一条空值 `helper=`（git 约定：空字符串清空之前所有 helper），再写 `helper=!gh ...`，否则会先调系统 keychain 等继承下来的 helper。
2. **必须 append 到现有 COUNT 后面**——Copilot CLI 自己会注入 `GIT_CONFIG_COUNT=1, KEY_0=safe.bareRepository`；从 0 开始覆盖会让 Copilot 的配置失效。`_n="${GIT_CONFIG_COUNT:-0}"` 是关键。
3. **direnv 配合**：cd 进工作区自动 export 这堆变量，离开自动 unset（direnv 跟踪 .envrc 启停的 env diff，dynamically-named vars 也算）。改 `.envrc` 后要 `direnv allow` 重新授权（基于文件 hash）。
4. **`GH_TOKEN` 必须能让 gh 用上**——agent 的 `bash` 工具是交互式 shell 不会触发 `BASH_ENV`，但 `bash -c '...'` 是非交互式会自动 source `.copilot.env`，所以用 `bash -c 'gh ...'` 包一层即可，无需手 source。
5. **作用域只限工作区**：因为 env 是 direnv 按目录加载，cd 出工作区后 env 自动被 direnv 清掉；其他项目的 git 完全不受影响。

### 教训

- **想给 git 加临时配置不要改 `~/.gitconfig`**——`-c key=val` 命令行级、`GIT_CONFIG_*` env 级、`.git/config` 仓库级，三种都比改 user-level 干净。
- **`gh auth setup-git` ≠ "用 gh 推 git"**——那只是把 gh 当 helper **持久化**到 `~/.gitconfig` 的快捷脚本；想要等价但不持久的效果，自己注 `GIT_CONFIG_*` 即可。
- **scope=`command` 是 env 注入的标志**——排查"我没在哪写过这条 config 怎么 git 看到了"时，用 `git config --show-scope --show-origin --list` 一目了然。

## `/rewind` 在非 git 仓库的 cwd 里直接拒绝

> 2026-05-09 | Copilot CLI 1.0.44 | Linux

### 症状

在 `~/TiMidlY-projects`（多子项目父目录、自己没有 `.git`）启动 Copilot CLI，`/rewind`（aka `/undo`）拒绝执行，提示大意是"不在 git 仓库里"。即使我只是想回退几个对话 turn、根本不在乎文件回滚，也被挡。

### 排查弯路

- **第一次猜**：rewind 用 git 做工作区快照（git stash / write-tree 之类），所以非 git 没法做 → **错的方向**。
- **看证据**：每个 session 目录下有 `~/.copilot/session-state/<id>/rewind-snapshots/backups/`，里面是被改文件的**完整字节拷贝**（明文 ASCII），index.json 列出每次 turn 的快照、`fileCount`、`backupHashes`、可选 `gitCommit/gitBranch/gitStatus`。所以 revert 的真正源头**完全是文件备份，根本不调 git**。
- **挖 app.js**：grep `rewindCommand → L7n` 顺到 `RewindManager`（变量名 `A6e`）的静态构造：

  ```js
  static async create(e, r) {
    let n = await hs(process.cwd());
    if (!n.found) return { ok: false, reason: "no-git-repo" };
    ...
  }
  ```

  `hs()` 是 `git rev-parse` 包装。**只要 cwd 不在 git 仓库里，RewindManager 直接不创建**，无论你想回退会话还是文件。

### 根因

Copilot 自己加的硬性前置检查，不是 revert 实现的技术依赖。/rewind 同时做两件事：回退 turn + 还原文件，**两件事绑死走同一套代码**，被 `no-git-repo` 短路掉。

git 在 rewind 流程里只是辅助：
- 省空间：tracked 且干净的文件可能不全量备份，靠 commit hash 还原
- 安全网：rewind 后告诉你"现在偏离了哪个 commit"

但这都不是必需的——backups/ 自己就够还原。

### 解决（按推荐度排）

1. **空 `.git` 骗过去**（推荐）：在父工作区 `git init` + `echo '*' > .gitignore`。子项目各自的 `.git` 优先匹配，不受影响；父目录 `git status` 永远空，但 `RewindManager.create` 能过 `no-git-repo` 检查。
2. **进具体子项目再启动 copilot**：每个子项目都有自己的 `.git`。缺点：跨子项目的会话必须重起。
3. **`/clear` 或 `/new` 开新会话**：彻底丢上下文，相当于重置而不是 rewind。
4. **官方反馈**：`/feedback` 要求拆开"会话 rewind"和"文件 rewind"，或对 `no-git-repo` 改成 warning 而不是 hard fail。

### 教训

- **报错文案 ≠ 技术根因**——"不在 git 仓库"听起来像技术限制，扒源码才知道是 product check。
- **找证据先看磁盘 artifact**：`~/.copilot/session-state/<id>/` 下的 `rewind-snapshots/`、`events.jsonl`、`session.db` 是 ground truth，比猜代码逻辑准。
- **app.js 是 minify 的单文件**，但只要拿到关键变量名（`rewindCommand → L7n`、`L7n` 的实现里点到 `A6e` 类）就能顺藤摸瓜找到真正的 check。
- **空 `.git` 是绕过仓库存在性检查的通用 trick**——很多工具的"必须在 git 仓库里"检查都只看 `git rev-parse --show-toplevel` 是否成功，跟里面有没有内容、有没有 commit 都无关。

---

## 三种 MCP 配置文件的区别

> 2026-05-09 | Copilot CLI 1.0.44 | VS Code (Stable) | Linux

### 背景

Copilot 生态里有**三个不同位置**的 MCP 配置文件，schema 不同、行为不同、为不同目的而存在。因为名字都带"mcp"容易搞混，尤其是 `.mcp.json` 和 `.vscode/mcp.json` 格式不兼容但长得像。

### 对比表

| | `.mcp.json` | `.github/mcp.json` | `.vscode/mcp.json` | `~/.copilot/mcp-config.json` |
|---|---|---|---|---|
| **谁读它** | Copilot CLI / Claude Code / Cursor | Copilot CLI | VS Code（编辑器内 Copilot Chat）| Copilot CLI |
| **设计目的** | 项目级 MCP，跨编辑器通用标准 | 项目级 MCP，GitHub 风格路径 | VS Code workspace 级 MCP | 用户全局 MCP，跨所有项目 |
| **顶层 key** | `mcpServers` | `mcpServers` | `servers` (+可选 `inputs`) | `mcpServers` |
| **位置** | 项目根 / git root | 项目根下 `.github/` | `<workspace>/.vscode/` | `~/.copilot/`（固定） |
| **Walk-up（向上查找）** | ✅ 从 cwd 向上，**停在 git root** | ✅ 同 `.mcp.json`（共用 `bBt` 发现函数） | ❌ 只读当前 VS Code 打开的 workspace folder | ❌ 固定全局路径 |
| **Trust level** | Medium（需 review） | Medium（需 review） | VS Code 内独立管理 | User-defined |
| **变量展开 — `${VAR}` env** | `env` 字段支持；`headers` 字段**名义支持但实测不生效**（#1232）| 同 `.mcp.json` | 通过 `${env:VAR}` 支持 | 同 `.mcp.json` |
| **变量展开 — `${input:...}`** | ❌ 不支持 | ❌ 不支持 | ✅ 支持（弹窗输入，OS keychain 安全存储）| ❌ 不支持 |
| **变量展开 — `${workspaceFolder}`** | ❌ | ❌ | ✅ | ❌ |
| **`envFile`** | ❌ | ❌ | ✅（stdio 类型）| ❌ |
| **优先级** | 高于全局 `mcp-config.json`；低于 `--additional-mcp-config` | 同 `.mcp.json`（同名时与 `.mcp.json` 合并） | VS Code 内独立管理 | 最低（被同名 workspace 配置覆盖）|
| **同名冲突规则** | Copilot CLI: **last-wins**（workspace 覆盖全局）| 同 `.mcp.json` | VS Code 内独立 | 被 workspace 覆盖 |
| **是否入版本控制** | 可以（如果不含 secrets）| 可以（`.github/` 本就版本控制友好）| 官方推荐入版本控制 | ❌ 用户私有 |

### 源码证据

**Copilot CLI walk-up 逻辑**（`app.js` 中 `bBt` 函数）：

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

### 各自的设计目的

1. **`.mcp.json`**：Claude Code / Cursor / Copilot CLI 共用的"项目级 MCP 配置"事实标准。放在项目根目录，版本控制友好。Copilot CLI 后来跟进支持这个格式（[#2938](https://github.com/github/copilot-cli/issues/2938)），以兼容 Claude Code 生态。

2. **`.github/mcp.json`**：Copilot CLI 专有的项目级 MCP 配置（Claude Code / VS Code 不读）。遵循 GitHub 的 `.github/` 约定（类似 `.github/copilot-instructions.md`、`.github/workflows/`），跟 `.mcp.json` 同格式同行为。选哪个看团队偏好——想跨编辑器通用用 `.mcp.json`，想符合 GitHub 目录惯例用 `.github/mcp.json`。

3. **`.vscode/mcp.json`**：VS Code 原生的 MCP 配置，遵循 VS Code 的 `settings.json` / `tasks.json` 等惯例放在 `.vscode/` 下。有完整的变量系统（`inputs` / `${env:}` / `${workspaceFolder}`）。Copilot CLI 曾短暂支持读取这个文件，后来改为推荐迁移到 `.mcp.json`，社区有抱怨（[#3019](https://github.com/github/copilot-cli/issues/3019)、[#3059](https://github.com/github/copilot-cli/issues/3059)）。

4. **`~/.copilot/mcp-config.json`**：Copilot CLI 的用户级全局配置。适合放全局性的 MCP server（如 GitHub MCP），不跟随项目走。优先级最低，会被同名 workspace 配置覆盖。官方文档明确说："Project-level MCP configurations (in `.mcp.json` or `.github/mcp.json`) take precedence over user-level definitions when server names conflict."

### 实际使用建议

- **如果只用 Copilot CLI**：用 `.mcp.json`，secrets 硬编码（目前没有安全的替代方案，`headers` 里 `${VAR}` 展开不可靠）
- **如果只用 VS Code**：用 `.vscode/mcp.json` + `${input:...}` 或 `${env:VAR}`
- **如果两边都用**：维护两份配置，`.mcp.json`（CLI）+ `.vscode/mcp.json`（VS Code），用 direnv 同步环境变量

### 相关 issue / 文档

- VS Code MCP 配置参考：https://code.visualstudio.com/docs/copilot/reference/mcp-configuration
- VS Code MCP 文档：https://code.visualstudio.com/docs/copilot/chat/mcp-servers
- Copilot CLI plugin 参考（含加载优先级图）：https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
- Copilot CLI 添加 `.mcp.json` 支持：https://github.com/github/copilot-cli/issues/2938
- 社区抱怨需要两份配置：https://github.com/github/copilot-cli/issues/3019
- VS Code 源码 `mcpWorkbenchService.ts`：workspace folder 直接拼 `.vscode/mcp.json`
- VS Code 源码 `mcpRegistry.ts`：`_replaceVariablesInLaunch()` → `configurationResolverService`
- VS Code 源码 `pluginParsers.ts`：`resolveMcpServersMap()` 兼容 `mcpServers` 和 `servers` 两种 key

---

## Copilot CLI `.mcp.json` 的 headers 里 `${VAR}` 展开不生效

> 2026-05-09 | Copilot CLI 1.0.44 | Linux + direnv

### 症状

`.mcp.json` 配置 HTTP MCP server 时，`headers` 里用 `${VAR}` 引用环境变量，Copilot CLI 不做展开，把字面量 `Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}` 发给服务端，导致：

```
Streamable HTTP error: Error POSTing to endpoint: bad request:
Authorization header is badly formatted
```

硬编码 PAT 则正常。

### 排查过程

1. **尝试 `"Bearer ${VAR}"`（复合字符串）** → 失败，字面量发送
2. **尝试 `"${VAR}"`（纯变量引用，env 变量值含 `Bearer ` 前缀）** → 同样失败
3. **尝试 `"$VAR"`（无花括号）** → 同样失败
4. **放到 `~/.copilot/mcp-config.json`（全局配置）试** → 同样失败
5. **curl 直接用环境变量拼 header** → 200，说明 PAT 本身有效
6. **硬编码到任何位置的配置文件** → 立刻成功

### 已知 issue

- **[#1232](https://github.com/github/copilot-cli/issues/1232)**：用户 @stefanbosak 精确复现了 `"Authorization": "Basic ${TOKEN}"` 不展开。2026-04-07 官方关闭说已修复，但用户 @therealvio 在 v0.0.420 + **direnv** 环境下仍报告不工作，无人确认修复生效。
- **[#3100](https://github.com/github/copilot-cli/issues/3100)**：即使 `headers` 里有 `Authorization: Bearer <token>`，CLI 可能先触发 OAuth discovery 流程并失败，header 根本没机会发出去。
- **[#1841](https://github.com/github/copilot-cli/issues/1841)**：Feature request 要求支持 `${input:...}` 语法，仍然 open。
- **[#2960](https://github.com/github/copilot-cli/issues/2960)**：反向佐证——有用户用 `"Bearer ${GRAFANA_MCP_TOKEN}"` **成功展开**了（问题是 token 太长超限制），说明在某些环境下确实能用。

### 根因推测

可能是以下因素叠加：

1. headers 里复合字符串 `"Bearer ${VAR}"` 的展开逻辑不完整（#1232 最初报的就是这个）
2. direnv 注入的环境变量可能走了不同的进程继承路径（@therealvio 也用 direnv）
3. 全局 vs workspace 配置可能走不同的解析管道

### 解决（当前 workaround）

headers 里硬编码 PAT。文件 `chmod 600` + 不入版本控制。

如果用 VS Code，可以走 `.vscode/mcp.json` + `${env:VAR}` 或 `${input:...}`，那套变量系统是 VS Code 原生的 `configurationResolverService`，完全独立于 Copilot CLI 的解析器。

### 教训

- **官方文档说"supports variable expansion"不等于实际能用**——changelog 说修了、文档说支持，但没有受影响用户确认修复、也没有自动化测试保证回归。实测为准。
- **direnv 是额外变量**——它注入 env 的方式（hook `$PROMPT_COMMAND` / `precmd`）跟直接 `export` 在微妙场景下可能有差异。遇到 env 不生效先排除 direnv 因素。
- **VS Code 和 Copilot CLI 是两套独立的变量系统**——VS Code 的 `${env:VAR}` 走 `configurationResolverService`，经过完整的变量解析管道；Copilot CLI 的 `${VAR}` 走自己的简单字符串替换。不要混用语法。

---

## `trustedFolders` 与会话级 "allowed directory list" 是两套独立机制（在子目录启动后访问父目录文件被拦）

> 2026-05-10 | Copilot CLI 1.0.44 | Linux

### 症状

`~/.copilot/config.json` 的 `trustedFolders` 已经包含 `/home/agony`（覆盖整棵 home 树），按直觉子目录任意上溯访问都不应该被拦。但从 `~/TiMidlY-projects/<subdir>` 启动 copilot 后，agent 读 `~/TiMidlY-projects/.safety-net.json`（在启动 cwd 的**父目录**）时仍弹：

```
Allow directory access
This action may read the following path outside your allowed directory list.
  /home/agony/TiMidlY-projects/.safety-net.json
1. Yes
2. Yes, and add these directories to the allowed list
3. No (Esc)
```

`/allow-all` 也开过，没用。

### 排查过程

1. **先核对 `trustedFolders`**：`/home/agony` 确实在里面（`config.json` 和 `settings.json` 两份镜像都有），按官方文档 "Trusted directories control where Copilot CLI can read, modify, and execute files" 的字面意思应该覆盖整棵子树。但实际并没有。
2. **查 `~/.copilot/permissions-config.json`**：只有 `locations.<dir>.tool_approvals`（`kind: commands` / `kind: write`），按启动 cwd 分组，**没有任何目录白名单字段**。
3. **查当前 session 的 `~/.copilot/session-state/<id>/events.jsonl`**：扫了一遍，跟目录有关的 key 只有 `cwd`，没有任何 `allowedDir` / `additionalDirectory` / `trustedFolders` 字段。
4. **结论**：弹窗说的 "allowed directory list" 是**第三套机制**，跟 `trustedFolders`（启动信任）和 `permissions-config.json`（命令/写审批）都没关系。

### 三套独立机制对照表

| 机制 | 存放位置 | 作用 | 持久化 |
|---|---|---|---|
| **启动信任** | `~/.copilot/config.json` 的 `trustedFolders`（`~/.copilot/settings.json` 有镜像副本） | 决定启动 copilot 时是否还弹 "trust this folder for future sessions" | ✅ 写盘 |
| **命令 / 写入审批** | `~/.copilot/permissions-config.json` 的 `locations.<launch-cwd>.tool_approvals` | 按"启动 cwd"分组的 `kind: commands` / `kind: write` 审批，控制 `--allow-tool='shell(...)' / write` 类放行 | ✅ 写盘 |
| **会话级 allowed-dir** | **仅内存**（events.jsonl / permissions-config.json / session-state 都没有持久化字段） | 控制每次 file read/write 的目录边界。初始化为启动 cwd 树。`/list-dirs` 查、`/add-dir` 加。**弹窗里选 "2. Yes, and add..." 等价于本次 session 的 `/add-dir`** | ❌ 重启即丢 |

### 根因

弹窗 "outside your allowed directory list" 指的是**第三套**——会话级 allowed-dir 列表。它的初始值就是启动 cwd 树，**完全不读 `trustedFolders`**。所以：

- 在 `/home/agony/TiMidlY-projects/<subdir>` 启动后，会话 allowed-dir = `{<subdir> 及子树}`，不含 `<subdir>` 的兄弟和父目录。
- 哪怕 `trustedFolders` 写了 `/home/agony`，只能让启动时不弹"trust this folder"信任 prompt，**不会**扩展会话 allowed-dir。

`/allow-all`（CLI flag `--allow-all` / `--yolo`）**确实包含 `--allow-all-paths`**——CLI 层面是会绕过目录 sandbox 的（见下一节"`COPILOT_ALLOW_ALL` env var ≠ `--allow-all` flag"）。但这跟 `trustedFolders` 仍然是两套独立机制：trustedFolders 是"启动信任 + isFolderTrusted 短路依据"，`--allow-all-paths` 是"运行时彻底关闭 path 检查"。

### 解决（按推荐顺序）

1. **从想要的根目录启动 copilot**（一劳永逸）：
   ```bash
   cd ~/TiMidlY-projects && copilot
   ```
2. **启动后立刻 `/add-dir`**：
   ```
   /add-dir /home/agony/TiMidlY-projects
   ```
   只对当前 session 有效。
3. **弹窗里选 2**：等价于上一条。
4. **没有"永久 allowed-dir"机制**，CLI 也没有 `--add-dir` 启动 flag；想自动化只能写 wrapper 在交互里塞 `/add-dir`。

### 教训

- **官方文档措辞会骗人**："Trusted directories control where Copilot CLI can read, modify, and execute files" 听起来涵盖所有文件访问，实际上**只管启动信任**。运行时的目录边界是另一套。
- **三套同主题机制位置和作用都不一样**——`config.json` / `permissions-config.json` / 内存——不要看到字段名带 "trust" 或 "allow" 就以为是同一回事。
- **CLI flag 与 env var 不等价**：`--allow-all` / `--yolo` 包含 `--allow-all-paths`、能彻底跳过目录审批；但 env var `COPILOT_ALLOW_ALL` **只对应 `--allow-all-tools`**，不会扩展到 paths。详见下一节。
- **从子目录启动 copilot 是隐性陷阱**：直觉上 `trustedFolders` 包含父目录就够了，实际还得让启动 cwd 本身覆盖你想访问的范围，否则每次跨边界都要审批。

---

## Safety Net 自定义规则：user scope 让规则跨子仓库生效

> 2026-05-10 | cc-safety-net (npx) | Copilot CLI 1.0.44

### 场景

在 `~/TiMidlY-projects/` 放了 `.safety-net.json`，自定义规则禁止所有 `gh` 子命令（要求用 GitHub MCP server 代替）。但子目录 `ssh-remote-mcp/` 是独立 git repo，Copilot 的 cwd 在子仓库里时 safety-net 只从 **cwd** 读 `.safety-net.json`，不向上遍历——规则不生效。

### 根因

cc-safety-net 加载自定义规则的搜索路径只有两个，**不做父目录遍历**：

1. **User scope**：`~/.cc-safety-net/config.json`（始终加载）
2. **Project scope**：`$CWD/.safety-net.json`（仅当前目录）

同名 rule project scope 优先覆盖 user scope，其余合并。

### 解决

把跨项目通用的规则放 user scope：

```bash
mkdir -p ~/.cc-safety-net
# 把规则写入 ~/.cc-safety-net/config.json
```

实际生效范围 = "user scope 规则在全局可见" × "hook 只在装了 `.github/hooks/safety-net.json` 的项目里激活"。所以规则虽然全局定义，但**只在项目及其子目录内拦截**（因为 hook 是项目级的，通过 `.envrc` 的 `link_into_subdirs` symlink 到每个子仓库）。

### 验证

```bash
cd ~/TiMidlY-projects/ssh-remote-mcp
npx -y cc-safety-net --verify-config   # 应显示 user config 里的规则
npx -y cc-safety-net explain "gh repo view"  # 应显示 BLOCKED
```

### 当前配置

- **User scope** `~/.cc-safety-net/config.json`：`block-gh-cli` 规则，封禁所有 `gh` 子命令
- **Hook 激活点**：`TiMidlY-projects/.github/hooks/safety-net.json`（通过 `.envrc` symlink 到子仓库）
- **Project scope** `TiMidlY-projects/.safety-net.json`：同一规则的旧副本，可清理

### 教训

- **想跨子仓库生效的规则放 user scope**，不要靠 symlink `.safety-net.json`——那是 project scope，只作用于 cwd。
- **hook 文件仍然需要 symlink**（`.github/hooks/safety-net.json`），因为 Copilot 只从 git root 的 `.github/hooks/` 读 hook。
- 区分"规则定义在哪"和"hook 在哪激活"：前者决定规则内容，后者决定拦截是否发生。

---

## `COPILOT_ALLOW_ALL` env var ≠ `--allow-all` flag（只对应 `--allow-all-tools`，且 5 处直读 env 走严格 `=== "true"`）

> 2026-05-10 | Copilot CLI 1.0.44 | Linux

### 症状

`.envrc` 里 `export COPILOT_ALLOW_ALL=1`，期望等价于 `--allow-all` / `--yolo`。实际表现：

- ✅ 命令、写入、MCP 工具不再弹审批
- ✅ cwd 子树内的文件读写正常
- ❌ **cwd 外的路径访问仍弹 "Allow directory access"**

### 排查（直接看 `app.js` 源码）

#### 一、env var 只挂在 `--allow-all-tools` 上

CLI 选项注册段：

```js
.addOption(new Aa("--allow-all-tools", "...required for non-interactive mode")
            .env("COPILOT_ALLOW_ALL"))      // ← 唯一带 .env() 的
.option("--allow-all-paths", "Disable file path verification ...")     // 无 env
.option("--allow-all-urls",  "...")                                    // 无 env
.option("--allow-all", "...alias --yolo")                              // 无 env
```

`.env(name)` 只挂在 `--allow-all-tools` 上。`--allow-all-paths` / `--allow-all-urls` / `--allow-all` 都**没有任何 env 绑定**，只能 CLI flag。

#### 二、commander 对布尔 flag 的 `.env()` 是宽松解析

commander.js 对**布尔型** flag 的 `.env()` 来说，env var 只要是**非空字符串**就视为真——`"1"`、`"true"`、甚至 `"false"` 都会让 flag = true。所以 `COPILOT_ALLOW_ALL=1` 在这条路径上**确实生效**，让 `allowAllTools=true`。

#### 三、`--allow-all` / `--yolo` 在 options 对象层解包成三个 bool

```js
function txr(t) {           // t = commander 解析后的 options
  let e = t?.allowAll || t?.yolo;
  return {
    allowAllTools: !!(t?.allowAllTools || e),
    allowAllPaths: !!(t?.allowAllPaths || e),
    allowAllUrls:  !!(t?.allowAllUrls  || e),
  };
}
```

env var 只能让 `allowAllTools` 为真，另外两个保持 false → path verification 闸照常跑。

#### 四、源码里另有 5 处直接 `process.env.COPILOT_ALLOW_ALL === "true"`，全是 `isFolderTrusted` 短路

不走 commander 的字符串严格比较点，**全部都是绕开 `wZ.isFolderTrusted(...)`** 的判断，分两类用途：

**类一：MCP workspace 配置加载（3 处）**

```js
// bLa：扫 workspace 找 .mcp.json
let n = process.env.COPILOT_ALLOW_ALL === "true"
        ? void 0                                  // 跳过 trust 检查
        : l => wZ.isFolderTrusted(l, r);          // 否则逐个 isFolderTrusted

// 主流程
let Kt = C2.env.COPILOT_ALLOW_ALL === "true"
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
let Ue = Hu.env.COPILOT_ALLOW_ALL === "true"
       || await wZ.isFolderTrusted(xa);            // xa = launch cwd
if (!Ue) try {
  (await _Ee(He)).find(H => H.isTrusted && NR(H.workspaceFolder, xa)) && (Ue = true);
} catch {}
Ue ? Su(1) : (Su(2), Qe(true));                    // Su(1)=信任 / Su(2)=弹窗

// catch 兜底
} catch {
  Hu.env.COPILOT_ALLOW_ALL === "true" ? Su(1) : (Su(2), Qe(true));
}
```

作用：决定要不要弹"do you trust this folder for future sessions"全屏 trust 提示。

> **5 处的本质都是 `isFolderTrusted` 的短路**——`=== "true"` 通过就跳过 isFolderTrusted，否则就走 `wZ.isFolderTrusted(...)` 判断 folder 是否在 `trustedFolders` 里。所以 `=1` vs `=true` 在这里的差距，等价于"当 `trustedFolders` 没覆盖该目录时是否仍然信任它"。

### 完整对照表

| 代码路径 | 怎么读 env | `=1` 的效果 | `=true` 的效果 |
|---|---|---|---|
| commander → `--allow-all-tools` | 布尔 flag 的 `.env()` 宽松解析 | ✅ 触发 | ✅ 触发 |
| MCP workspace 加载（3 处）→ isFolderTrusted 短路 | `=== "true"` 严格比较 | ❌ 仍走 isFolderTrusted | ✅ 短路 |
| 启动 trust folder 弹窗（2 处）→ isFolderTrusted 短路 | `=== "true"` 严格比较 | ❌ 仍走 isFolderTrusted | ✅ 短路 |
| `--allow-all-paths` / `--allow-all-urls` | 无 env 绑定 | 永远 false | 永远 false |

### 实际后果

- 如果你的 launch cwd 已经在 `trustedFolders` 子树下（比如 `/home/agony` 在里面），那 isFolderTrusted 本来就过——`=1` 和 `=true` 没区别，你看不到副作用。
- **新机器 / `trustedFolders` 还空**：`=1` 会让 workspace MCP 不自动加载，并且每次启动都弹 trust 提示。这时改成 `=true` 才正常。
- **目录访问审批（"outside your allowed directory list"）任何 env 值都救不了**——必须 CLI flag `--allow-all-paths` 或 `--allow-all` / `--yolo`。

### 解决

```bash
# .envrc：值改成 true，让 5 处 isFolderTrusted 短路也通过（一致性更好，没坏处）
export COPILOT_ALLOW_ALL=true

# 想免目录审批必须 alias，env var 没办法
alias copilot='copilot --yolo'                    # 全开
# 或只开 paths，保留 URL 审批：
alias copilot='copilot --allow-all-paths'
```

权衡：`--allow-all-paths` 让 agent 能读到 `~/.ssh/`、`~/.config/` 之类，确实有风险。不想全开就接受目录弹窗、必要时 `/add-dir` 临时加白。

### 教训

- **CLI flag 和 env var 不是简单的对应关系**——`COPILOT_ALLOW_ALL` 名字像 `--allow-all`，实际只挂在 `--allow-all-tools` 上。看名字猜对应一定要去源码确认 `.env()` 绑在哪。
- **commander 的 `.env()` 对布尔 flag 是宽松解析**——任何非空字符串都为真。但**业务代码里直接 `process.env.X === "true"` 又是严格比较**——同一个 env var 两套读法并存时，值只能写官方推荐的（这里就是 `"true"`），别用 `1` 偷懒。
- **`isFolderTrusted` 是 Copilot CLI 里目录信任决策的核心函数**——看到目录相关的"为什么有的弹有的不弹"，先去源码搜 `isFolderTrusted` 的所有 caller，每个 caller 的短路条件都可能是个"开后门"的旁路。
- **官方 help 文本是一手依据**——`COPILOT_ALLOW_ALL` 的 help 字符串明明写 "allow all **tools**"，但很多人（包括我自己）会望文生义当成"allow all everything"。help 写啥就是啥。
