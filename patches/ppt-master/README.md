# ppt-master 本地补丁

把上游 `hugohe3/ppt-master` 嫁接到本仓库后，在 `skills/ppt-master/` 上额外打的本地补丁，用 [quilt](https://savannah.nongnu.org/projects/quilt/) 管理。

`series` 文件是补丁顺序的权威清单（quilt 原生格式），`grafted-skills.json` 不重复记录。

## 当前补丁列表

| 序号 | 文件 | 目的 |
| ---- | ---- | ---- |
| 0001 | `0001-decouple-templates-and-projects.patch` | 把模板库与项目根目录从 `${SKILL_DIR}/{templates/layouts,templates/brands,projects}` 解耦到环境变量 `PPT_MASTER_TEMPLATES_DIR` / `PPT_MASTER_PROJECTS_DIR`。脚本缺 env 时硬报错，文档要求 AI 先问用户。`templates/{charts,icons}/` 仍是 skill 自带只读资产，不动。 |

## 工作流

完整 quilt 命令范式（包括新加补丁、改已有补丁、re-graft）见 `.agents/skills/graft-skill/SKILL.md` §「本地补丁（quilt）」。

最常用的两段：

**新加一个补丁**（在当前成品状态上叠加，不需要先 pop）：

```bash
REPO=$(git rev-parse --show-toplevel)
cd "$REPO/skills/ppt-master"
QUILT_PATCHES="$REPO/patches/ppt-master" QUILT_PC="$REPO/.quilt-pc/ppt-master" \
  quilt new 0002-<short-name>.patch

QUILT_PATCHES="$REPO/patches/ppt-master" QUILT_PC="$REPO/.quilt-pc/ppt-master" \
  quilt edit some/file.py    # 改文件
# ... 重复多个文件 ...
QUILT_PATCHES="$REPO/patches/ppt-master" QUILT_PC="$REPO/.quilt-pc/ppt-master" \
  quilt refresh              # 把改动写入 patch 文件
```

**Re-graft 时重放补丁**（上游有新版本后）：

```bash
REPO=$(git rev-parse --show-toplevel)
cd "$REPO/skills/ppt-master"

# 1. 撤回当前 patch（如果之前 quilt 跑过；首次 re-graft 时 .quilt-pc 还不存在，跳过这步）
QUILT_PATCHES="$REPO/patches/ppt-master" QUILT_PC="$REPO/.quilt-pc/ppt-master" \
  quilt pop -a 2>/dev/null || true

# 2. rsync 上游新版本覆盖
rsync -a --delete --exclude='.git' /tmp/upstream-ppt-master/skills/ppt-master/ ./

# 3. 重新应用本地补丁（quilt 自动 3-way 处理 context drift；冲突手动解 + quilt refresh）
QUILT_PATCHES="$REPO/patches/ppt-master" QUILT_PC="$REPO/.quilt-pc/ppt-master" \
  quilt push -a

# 4. 更新 grafted-skills.json 的 synced_commit / synced_date，跑 update-readme.py
```

## 新增补丁的归档约定

每次新增补丁后：

1. 用语义化短名（如 `0002-fix-foo-bar.patch`），保留 `0001-`/`0002-` 序号前缀，方便顺序应用。
2. `quilt refresh` 会自动维护 `series` 文件，不要手改。
3. 在本 README 的「当前补丁列表」加一行。
4. 单独一个 commit 提交 patch 新增（与依赖该补丁的其他改动分开），便于审查。

## 不动的边界

- `templates/charts/`、`templates/icons/`、`templates/design_spec_reference.md`、`templates/spec_lock_reference.md` —— 上游只读资产，re-graft 后直接用上游版本，不进 patch。
- `templates/layouts/<sample>/`、`templates/brands/<sample>/` —— 上游示例库，re-graft 后直接用上游版本。用户自己的 layouts/brands 在 `$PPT_MASTER_TEMPLATES_DIR/{layouts,brands}/`，不在本仓。
