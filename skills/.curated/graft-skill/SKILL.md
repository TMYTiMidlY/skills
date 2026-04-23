---
name: graft-skill
description: 管理从外部 GitHub 仓库嫁接（引入）的 skill。当用户要引入、转正、同步、移除外部 skill，或维护 grafted-skills.json / README 来源表时使用；主要面向仓库维护者与 skill 开发者。
---

# Graft Skill

## 适用范围

这个 skill 处理的是**外部 skill 生命周期**，包括：

- 从外部仓库引入 skill
- 把试验区 skill 转正
- 跟踪上游更新并同步
- 移除不再保留的外部 skill
- 维护 `grafted-skills.json` 与 README 的来源口径
- 对引入内容做去品牌化和依赖适配

它**不负责**：

- 普通用户的安装 / 卸载 / 软链冲突处理
- 对本仓已存在 skill 做通用审查、拆分和命名整理

这些工作交给 `manage-skills`。

## 配置文件

`grafted-skills.json` 记录所有外部 skill 的来源和同步状态。key 是 skill 名称；试验区条目带 `.experimental/` 前缀。

```json
{
  "pdf": {
    "repo": "anthropics/skills",
    "path": "skills/pdf",
    "branch": "main",
    "synced_commit": "1ed29a0",
    "synced_date": "2026-02-06T21:19:32Z",
    "description": "PDF 文件操作"
  },
  ".experimental/slides": {
    "repo": "openai/skills",
    "path": "skills/.curated/slides",
    "branch": "main",
    "synced_commit": "b53e5e6",
    "synced_date": "2026-03-05T23:09:22Z",
    "description": "代码驱动的幻灯片制作"
  }
}
```

字段说明：

- `repo`：上游 GitHub 仓库（owner/name）
- `path`：skill 在上游仓库中的路径
- `branch`：跟踪的分支
- `synced_commit`：当前同步到的上游 commit SHA（短 SHA）
- `synced_date`：该 commit 时间（ISO 8601）
- `description`：README 表格里使用的简要说明

**每次修改 `grafted-skills.json` 后，都要同步 README 中 `<!-- skills-table:begin/end -->` 之间的外部 skill 表格。**

## 引入

1. 安装 skill：`bunx skills add {repo} --skill {skill-name} -a github-copilot -y`
   - 列出可用 skill：`bunx skills add {repo} --list`
2. 将 `.agents/skills/{skill-name}/` 移到 `skills/.experimental/{skill-name}/`。
3. 获取上游最新 commit（用于填写 `synced_commit` 和 `synced_date`）：
   ```bash
   gh api "repos/{repo}/commits?path={path}&sha={branch}&per_page=1" --jq '.[0] | {sha: .sha[0:7], date: .commit.author.date}'
   ```
4. 在 `grafted-skills.json` 中添加条目，key 写 `.experimental/{skill-name}`。
5. 与用户协作审阅和修改：按本仓约定做去品牌化、依赖统一和结构整理。

## 转正

1. 将 `skills/.experimental/{skill-name}/` 移到 `skills/{skill-name}/`。
2. 更新 `grafted-skills.json` 中的 key，去掉 `.experimental/` 前缀。
3. 同步 README 外部 skill 表格。

## 修改

对已引入的外部 skill 做本地修改时，直接编辑本仓库中的文件。同步时通过 git diff 识别本地改动和冲突。

## 检查更新

对 `grafted-skills.json` 中的每个条目，查询自上次同步以来的 commit：

```bash
gh api --paginate "repos/{repo}/commits?path={path}&since={synced_date}&sha={branch}&per_page=100" \
  --jq '.[] | {sha: .sha[0:7], date: .commit.author.date, message: .commit.message | split("\n")[0]}'
```

注意 `since` 是包含性的，需排除 `synced_commit` 本身。

## 同步

用户确认要同步后：

1. 逐个查看新 commit 的 diff：
   ```bash
   gh api "repos/{repo}/commits/{sha}" \
     --jq '.files[] | select(.filename | startswith("{path}/")) | {filename, status, patch}'
   ```
2. 与本地文件对比，无冲突直接应用，有冲突展示给用户决定。
3. 更新 `synced_commit` 和 `synced_date`。
4. 同步 README 外部 skill 表格。

## 移除

1. 删除 skill 目录。
2. 从 `grafted-skills.json` 中移除条目。
3. 同步 README 外部 skill 表格。

## 适配规则

来自外部仓库的 skill 默认检查这些点：

- 去品牌化：将 `Claude`、`artifacts` 等产品专属概念改成通用表述
- 删除绑定特定产品的链接（如 `claude.ai`）
- `python scripts/...` 改成 `uv run scripts/...`
- `pip install X` 改成 `uv run --with X`
- 修正跨 skill / 仓库路径硬编码
- 检查 frontmatter `name` 是否与目录名一致、是否全局唯一
- 把长流程挪到 `references/`，保留渐进式披露

## 特殊规则

- `upload` 这个 skill 的来源**暂时留空**。
- 不要擅自为 `upload` 补填 `repo` / `path` / `synced_commit` / `synced_date`。
- 如果后续确认了来源，再补齐；在此之前，空着比写错更好。

## 注意事项

- 本地修改优先，同步时不能盲目覆盖。
- 用 `gh api` 而非裸 `curl`，自带认证和分页。
- `grafted-skills.json` 记录的是**上游路径**，不是本仓落点。
- README 表格只呈现对外公开的 skill；来源没确认时宁可留空，也不要猜。
