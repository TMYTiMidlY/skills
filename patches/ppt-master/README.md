# ppt-master 本地补丁

把上游 `hugohe3/ppt-master` 嫁接到本仓库后，在 `skills/ppt-master/` 上额外打的本地补丁，用 [quilt](https://savannah.nongnu.org/projects/quilt/) 管理。

`series` 文件是补丁顺序的权威清单（quilt 原生格式），`grafted-skills.json` 不重复记录。

## 当前补丁列表

| 序号 | 文件 | 目的 |
| ---- | ---- | ---- |
| 0001 | `0001-decouple-templates-and-projects.patch` | 把可写模板库（`brands` / `styles` / `layouts` / `decks`）与项目根目录解耦到 `PPT_MASTER_TEMPLATES_DIR` / `PPT_MASTER_PROJECTS_DIR`。模板注册器和 Confirm UI 都读用户库；`project_manager` 与 Native Enhance 都读用户项目根。缺 env 时硬报错，但 `--help` 和显式项目目录仍可用。skill 内的模板、图标、图表、schema、scaffold 保持上游只读样例/资产。 |
| 0002 | `0002-fix-grafted-doc-links.patch` | 把两处指向上游仓库级 `docs/rules/code-style.md` 的相对链接改为固定到同步 commit 的 GitHub 链接；只嫁接 `skills/ppt-master` 时仍可访问，而无需额外引入上游整仓文档。 |

## 当前适配面

- `scripts/config.py`：统一解析两个环境变量，并沿用上游
  `~/.ppt-master/.env` 查找机制。
- `scripts/register_template.py`：四种 kind 的目录与索引都延迟解析到用户模板库，
  不在 import / `--help` 时要求环境变量。
- `scripts/confirm_ui/server.py`：Stage-1 模板候选从用户库四个索引读取；
  icon 预览继续读取 skill 自带只读资源。
- `scripts/project_management/*`、`project_manager.py`：默认项目根和
  `import-sources` 可移动边界使用 `PPT_MASTER_PROJECTS_DIR`；显式 `--dir`
  优先。
- `scripts/native_enhance_pptx_core.py`：独立的 Native Enhance `init`
  同样使用用户项目根，避免绕回仓库内 `projects/`。
- 相关 workflow / reference / README：写入路径改为用户目录，并把本次触及的
  Python 命令统一为 `uv run`。
- 例外：`SKILL.md` 的 `python3 scripts/attribution_guard.py` 是上游完整性检查
  的精确 marker，必须原样保留，不能机械改成 `uv run`。

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

**Re-graft 时重放补丁**（上游有新版本后）—— 完整流程见 `.agents/skills/graft-skill/SKILL.md` §「本地补丁（quilt）」→ Re-graft。关键骨架：

```bash
REPO=$(git rev-parse --show-toplevel)
cd "$REPO/skills/ppt-master"

# 1. reverse 回裸 OLD_SYNC：.quilt-pc 存在用 quilt pop -a，不存在按 series 倒序 patch -p1 -R
# 2. rsync 上游 NEW_SYNC 覆盖
# 3. quilt push -a 重放本地 patch；失败按 SKILL.md「冲突处理」分流（context drift vs 结构性重写）
# 4. 解完后 quilt refresh
# 5. 更新 grafted-skills.json 的 synced_commit / synced_date，跑 update-readme.py
```

## 新增补丁的归档约定

每次新增补丁后：

1. 用语义化短名（如 `0002-fix-foo-bar.patch`），保留 `0001-`/`0002-` 序号前缀，方便顺序应用。
2. `quilt refresh` 会自动维护 `series` 文件，不要手改。
3. 在本 README 的「当前补丁列表」加一行。
4. 单独一个 commit 提交 patch 新增（与依赖该补丁的其他改动分开），便于审查。

## 不动的边界

- `templates/charts/`、`templates/icons/`、`templates/schemas/`、
  `templates/scaffolds/`、`templates/design_spec_reference.md`、
  `templates/spec_lock_reference.md` —— 上游只读资产，re-graft 后直接用上游版本。
- `templates/{brands,styles,layouts,decks}/<sample>/` —— 上游示例 workspace，
  可通过显式路径使用，但不作为可写用户库。用户自己的四种模板放在
  `$PPT_MASTER_TEMPLATES_DIR/{brands,styles,layouts,decks}/`。
