---
name: graft-skill
description: 管理从外部 GitHub 仓库嫁接（引入）的 skill。当用户要添加、移除、修改外部 skill，或提到"检查更新"、"同步上游"、"upstream"时触发。
---

# Graft Skill

从外部 GitHub 仓库嫁接 skill 到本仓库，管理其完整生命周期：引入 → 试验 → 转正 → 修改 → 同步 → 移除。

## 仓库内 `.claude/skills` 的语义

仓库里 `.claude/skills` 本身是 symlink，**整体**指向 `.agents/skills`：

```
<repo>/.claude/skills  →  ../.agents/skills
```

所以在仓库工作时，`<repo>/.claude/skills/<x>` 和 `<repo>/.agents/skills/<x>` 是同一实体。两者的**公开区**才是 `<repo>/skills/`（分发给其他项目）。

| 操作（在 `<repo>/` 仓库内） | 落点 | 同步 |
|---|---|---|
| 在 `.claude/skills/` 下 `mkdir myskill` | 穿透 → `.agents/skills/myskill/`（维护区，不在公开分发区） | ✅ |
| 在 `.claude/skills/<x>/` 下新建 `reference/` | 穿透 → `.agents/skills/<x>/reference/` | ✅ |
| 把路径 `.claude/` 换成 `.agents/` | 指向同一目录，**完全等价** | ✅ |
| 直接在 `<repo>/skills/<name>/` 下写 | 公开分发区 | ✅ |

**判断方法**：`readlink -f <path>` 看落点。落在 `.agents/skills/` → 维护区；`skills/` → 公开区；仓库外 → 不进 git。

**新增公开 skill 的正确做法**：在 `<repo>/skills/<name>/` 下建实体，而不是通过 `.claude/skills/` 新建（否则会写到维护区）。

## 配置文件

`grafted-skills.json` 记录所有外部 skill 的来源和同步状态。key 是 skill 名称（试验区带 `.experimental/` 前缀）：

```json
{
  "slidev": {
    "repo": "slidevjs/slidev",
    "path": "skills/slidev",
    "branch": "main",
    "synced_commit": "d76850d",
    "synced_date": "2026-03-11T23:54:58Z",
    "description": "Slidev 官方 skill"
  }
}
```

**每次修改 `grafted-skills.json` 后，运行 `scripts/update-readme.py` 更新 README。** 脚本替换 `<!-- skills-table:begin/end -->` 之间的内容。

## 引入

1. 安装 skill：`bunx skills add {repo} --skill {skill-name} -a github-copilot -y`
   - 列出可用 skill：`bunx skills add {repo} --list`
2. 将 `.agents/skills/{skill-name}/` 移到 `skills/.experimental/{skill-name}/`。
3. 获取上游最新 commit（用于填写 `synced_commit` 和 `synced_date`）：
   ```
   gh api "repos/{repo}/commits?path={path}&sha={branch}&per_page=1" --jq '.[0] | {sha: .sha[0:7], date: .commit.author.date}'
   ```
4. 在 `grafted-skills.json` 中添加条目，key 写 `.experimental/{skill-name}`。
5. 与用户协作审阅和修改（适配本仓库约定、调整描述等）。

## 转正

1. 对 skill 内容做适配修改，使其不绑定特定 AI 产品：
   - **去品牌化**：将 `Claude`、`artifacts` 等产品专属概念替换为通用表述（如 `agent`、文件操作）；删除 `claude.ai` 等产品链接。
   - **统一依赖管理**：`python scripts/...` 改为 `uv run scripts/...`；`pip install X` 改为 `uv run --with X`。
2. 将 `skills/.experimental/{skill-name}/` 移到 `skills/{skill-name}/`。
3. 更新 `grafted-skills.json` 中的 key，去掉 `.experimental/` 前缀。

## 修改

直接编辑本仓库中的文件。同步时通过 git diff 识别本地改动和冲突。

## 检查更新

对 `grafted-skills.json` 中的每个条目，查询自上次同步以来的 commit：

```
gh api --paginate "repos/{repo}/commits?path={path}&since={synced_date}&sha={branch}&per_page=100" \
  --jq '.[] | {sha: .sha[0:7], date: .commit.author.date, message: .commit.message | split("\n")[0]}'
```

注意 `since` 是包含性的，需排除 `synced_commit` 本身。

## 同步

用户确认要同步后：

1. 逐个查看新 commit 的 diff：
   ```
   gh api "repos/{repo}/commits/{sha}" \
     --jq '.files[] | select(.filename | startswith("{path}/")) | {filename, status, patch}'
   ```
2. 与本地文件对比，无冲突直接应用，有冲突展示给用户决定。
3. 更新 `synced_commit` 和 `synced_date`。

## 移除

1. 删除 skill 目录。
2. 从 `grafted-skills.json` 中移除条目。

## 注意事项

- 本地修改优先，同步时不能盲目覆盖。
- 用 `gh api` 而非裸 `curl`，自带认证和分页。
