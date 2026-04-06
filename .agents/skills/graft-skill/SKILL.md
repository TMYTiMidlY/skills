---
name: graft-skill
description: 管理从外部 GitHub 仓库嫁接（引入）的 skill。当用户要添加、移除、修改外部 skill，或提到"检查更新"、"同步上游"、"upstream"时触发。
---

# Graft Skill

从外部 GitHub 仓库嫁接 skill 到本仓库，管理其完整生命周期：引入 → 试验 → 转正 → 修改 → 同步 → 移除。

## 配置文件

项目根目录的 `upstream-skills.json` 记录所有外部 skill 的来源和同步状态。每个条目的 key 是 skill 名称（不含 `skills/` 前缀，因为所有 skill 都在 `skills/` 目录下；试验区的 key 带 `.experimental/` 前缀）：

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

字段说明：
- `repo`：GitHub 仓库（owner/name）
- `path`：skill 在上游仓库中的子目录路径
- `branch`：跟踪的分支
- `synced_commit`：本地最后同步到的上游 commit SHA（短 SHA）
- `synced_date`：该 commit 的时间（ISO 8601）
- `description`：简要说明

## README 同步

每次引入、转正、同步、移除操作后，运行脚本自动更新 README 中的外部 skill 表格：

```
python3 .agents/skills/graft-skill/scripts/update-readme.py
```

脚本读取 `upstream-skills.json`，生成表格并替换 `README.md` 中 `<!-- skills-table:begin -->` 和 `<!-- skills-table:end -->` 之间的内容。

## 引入外部 skill

1. 用 `bunx skills add` 将 skill 安装到 `.agents/skills/` 目录：
   ```
   bunx skills add {repo} --skill {skill-name} -a github-copilot -y
   ```
   如果需要列出可用 skill：`bunx skills add {repo} --list`
2. 将下载的 skill 从 `.agents/skills/{skill-name}/` 移动到试验区 `skills/.experimental/{skill-name}/`。
3. 用 `gh api` 获取该 skill 在上游仓库中对应路径的最新 commit SHA 和日期，用于记录同步位置：
   ```
   gh api "repos/{repo}/commits?path={path}&sha={branch}&per_page=1" --jq '.[0] | {sha: .sha[0:7], date: .commit.author.date}'
   ```
4. 在 `upstream-skills.json` 中添加条目，key 写 `.experimental/{skill-name}`。
5. 运行 `scripts/update-readme.py` 更新 README。
6. 与用户协作审阅和修改（适配本仓库约定、调整描述等）。

## 转正

用户确认试验区的 skill 没问题后：

1. 将 `skills/.experimental/{skill-name}/` 移动到 `skills/{skill-name}/`。
2. 更新 `upstream-skills.json` 中的 key 从 `.experimental/{skill-name}` 改为 `{skill-name}`。
3. 运行 `scripts/update-readme.py` 更新 README。

## 修改外部 skill

对已引入的外部 skill 做本地修改时，直接编辑本仓库中的文件即可。同步时通过 git diff 识别本地改动和冲突。

## 检查更新

对 `upstream-skills.json` 中的每个条目：

1. 用 `gh api` 查询该路径下自上次同步以来的 commit：
   ```
   gh api --paginate "repos/{repo}/commits?path={path}&since={synced_date}&sha={branch}&per_page=100" \
     --jq '.[] | {sha: .sha[0:7], date: .commit.author.date, message: .commit.message | split("\n")[0]}'
   ```
2. 排除 `synced_commit` 本身（`since` 是包含性的），只看更新的 commit。
3. 没有新 commit 则报告已是最新；有则列出变动摘要。

## 同步更新

用户确认要同步某个 skill 后：

1. 逐个查看新 commit 对该路径的 diff：
   ```
   gh api "repos/{repo}/commits/{sha}" \
     --jq '.files[] | select(.filename | startswith("{path}/")) | {filename, status, patch}'
   ```
2. 将上游变动与本地文件对比，识别冲突。
3. 不冲突的变动直接应用；冲突部分展示给用户决定。
4. 更新 `synced_commit` 和 `synced_date`。
5. 运行 `scripts/update-readme.py` 更新 README。

## 移除外部 skill

1. 删除本仓库中对应的 skill 目录。
2. 从 `upstream-skills.json` 中移除该条目。
3. 运行 `scripts/update-readme.py` 更新 README。

## 注意事项

- `since` 参数是包含性的，查询结果会包含 `synced_commit` 本身，需过滤。
- 本地修改优先，同步时不能盲目覆盖。
- 用 `gh api` 而非裸 `curl`，自带认证和分页。
