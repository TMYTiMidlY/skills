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
