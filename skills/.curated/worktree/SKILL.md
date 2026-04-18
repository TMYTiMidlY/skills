---
name: worktree
description: 用户要做实验性改动 / 对比实现 / 可能失败的大改动，或明确要求"在 worktree 里做 / 开个实验分支"时使用。自动为隔离分支创建 git worktree（含 submodule 同步），避免污染主工作区。本 skill 只覆盖通用的 worktree 骨架，项目特定的构建 / 依赖同步由上层 AGENTS.md 或项目自身的 skill 接管。
---

# Worktree

## 定位

**worktree = 共享 `.git` + 独立工作区 + 独立分支**。拿来隔离可能出错或需要并行的改动，避免 stash / reset 频繁切换。典型用途：尝试有失败风险的大改动、并行跑多个实验分支、用户明确说"在 worktree 里做"。

## 流程

按顺序走，不要跳步。

### 0. 动态推导主仓库路径

**不要硬编码路径**。判别：

- 当前已在 git 仓库里（无论主仓库还是已有 worktree）→ 用 `git rev-parse --git-common-dir` 找共享 `.git`，其上一级就是主仓库。
- 不在任何 git 仓库里 → 认为 cwd 就是主仓库（用于 agent 从项目根调起 skill 的场景）。

```bash
get_main_repo() {
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local common_dir
        common_dir=$(git rev-parse --git-common-dir)
        if [ "$common_dir" = ".git" ]; then
            echo "$PWD"
        else
            dirname "$common_dir"
        fi
    else
        echo "$PWD"
    fi
}
MAIN_REPO=$(get_main_repo)
REPO_NAME=$(basename "$MAIN_REPO")
```

### 1. 检测是否已在 linked worktree 中

```bash
is_linked_worktree() {
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    [ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]
}
```

原理：linked worktree 的 `.git` 是**文件**（指向主仓库 `.git/worktrees/xxx`），主仓库 `git-dir` 和 `git-common-dir` 相同；两者不等就是 linked worktree。

### 2. 不在 worktree 中 → 自动创建

命名约定：

- 时间戳格式 `YYYY-MM-DDTHH-MM-SS`（用 `-` 不用 `:`，跨文件系统兼容）
- worktree 目录：`{主仓库父目录}/{仓库名}.worktrees/cli-worktree-{时间戳}`
- 分支名：`cli/worktree-{时间戳}`

把所有 worktree 统一放到同级的 `<repo>.worktrees/` 下，避免散落；`cli-` 前缀标识 agent 创建的（便于和人工开的 worktree 区分、定期批量清理）。

```bash
TIMESTAMP=$(date +%Y-%m-%dT%H-%M-%S)
WORKTREES_BASE="$(dirname "$MAIN_REPO")/${REPO_NAME}.worktrees"
WORKTREE_DIR="$WORKTREES_BASE/cli-worktree-$TIMESTAMP"
BRANCH_NAME="cli/worktree-$TIMESTAMP"

mkdir -p "$WORKTREES_BASE"
cd "$MAIN_REPO"
git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR"
cd "$WORKTREE_DIR"
```

### 3. 已在 worktree 中 → 沿用当前目录

记录 `NEW=$PWD`，跳到第 4 步。

### 4. 为所有 submodule 同步建立 worktree

**这一步最容易被忽略**。主仓库的 worktree **不会**自动为 submodule 建立对应 worktree——不处理的话，submodule 在 worktree 里回退到主仓库的 submodule 路径，读写会串到主仓库。

```bash
NEW="$PWD"
cd "$MAIN_REPO"
git submodule foreach --recursive '[ -e "'"$NEW"'/$displaypath/.git" ] || git worktree add --detach --force "'"$NEW"'/$displaypath" HEAD'
cd "$NEW" && git submodule update --recursive
```

关键点：

- `$displaypath` 由 `git submodule foreach` 注入，是 submodule 相对主仓库的路径
- 已存在的 submodule worktree 跳过创建（`[ -e ... ] ||`）
- `--detach` 避免分支冲突；随后 `git submodule update --recursive` checkout 到正确 commit
- `--force` 容忍旧元数据残留

### 5. 项目特定的初始化（本 skill 不覆盖）

构建 / 依赖同步 / 环境激活由项目 `AGENTS.md` 或项目自身的 skill 决定。常见步骤：

- 包管理器：`uv sync` / `poetry install` / `npm install`
- 构建：`poe setup && poe build` / `cmake` / `make`
- 环境：`source .venv/bin/activate` / `conda activate`

如果项目需要"一次性 worktree + 构建"的工作流，写一个薄壳 skill 先调本 `worktree` skill、再跑项目自己的构建命令即可。

## 恢复脚本（git 异常 / worktree 元数据污染时）

症状：`git` 报 worktree 相关错误、submodule 状态错乱。通常是 worktree 创建中断导致子仓库 `.git/modules/*/config` 里残留 `worktree =` 行、或 `worktrees/` 目录里有失效条目。清理步骤：

```bash
cd "$MAIN_REPO"

# 1. 清掉子仓库 config 里残留的 worktree = 行
find .git/modules -name "config" -print0 \
  | xargs -0 grep -l "^[[:space:]]*worktree[[:space:]]*=" 2>/dev/null \
  | xargs sed -i '/^[[:space:]]*worktree[[:space:]]*=/d'

# 2. 清掉子仓库 worktrees/ 下的失效条目（trash-put 以便必要时恢复）
for d in $(find .git/modules -type d -name "worktrees"); do
  trash-put "$d"/* 2>/dev/null || true
done
```

清理后从第 0 步重新走一遍。
