# slidev 本地补丁

把上游 `slidevjs/slidev` 的 `skills/slidev` 嫁接到本仓库后，在 `skills/slidev/` 上额外打的本地补丁，用 [quilt](https://savannah.nongnu.org/projects/quilt/) 管理。

`series` 文件是补丁顺序的权威清单（quilt 原生格式），`grafted-skills.json` 不重复记录。

## 当前补丁列表

| 序号 | 文件 | 目的 |
| ---- | ---- | ---- |
| 0001 | `0001-fix-upstream-broken-ref-links.patch` | 修上游两处指错文件名的 reference 链接：`references/syntax-comark.md` → `syntax-mdc.md`，`draggable.md` → `layout-draggable.md`。两者在上游同步 commit 上就是断的，本仓 lychee pre-commit hook 会拦。 |

## 补丁 0001 的上游依据

两条链接在上游同步 commit `d76850d` 的原文里就已经指向不存在的文件，不是嫁接时漏拷：

| 位置 | 上游原文写的 | `references/` 里实际存在的 |
| ---- | ---- | ---- |
| `SKILL.md` L126 | `references/syntax-comark.md` | `syntax-mdc.md` |
| `references/core-components.md` L187 | `draggable.md` | `layout-draggable.md` |

推测成因：上游把 MDC 更名为 Comark 时只改了文件内容（`syntax-mdc.md` 的 frontmatter 已是 `name: comark`）没改文件名；`core-components.md` 那条是漏了 `layout-` 前缀——同一份 `SKILL.md` 的 L109 写的是正确的 `references/layout-draggable.md`，可见属笔误。

补丁只改链接目标，不动正文与展示名（`[syntax-comark]` / `[draggable]` 保持上游措辞），把冲突面压到最小。

上游修好后本补丁即可撤除；撤除前先确认新同步 commit 里两处路径均已更正。

## 工作流

完整 quilt 命令范式（新加补丁、改已有补丁、re-graft）见 `graft-skill` skill 的「本地补丁（quilt）」章节，与 `patches/ppt-master` 共用同一套。

本目录的环境变量：

```bash
REPO=$(git rev-parse --show-toplevel)
cd "$REPO/skills/slidev"
export QUILT_PATCHES="$REPO/patches/slidev" QUILT_PC="$REPO/.quilt-pc/slidev"
```

**改已有补丁**（`.quilt-pc` 已被 gitignore，重新 clone 后不存在，需先 `quilt push -a` 重建状态）：

```bash
quilt add <file>     # 或 quilt edit <file>
# ... 改文件 ...
quilt refresh
```

**Re-graft 时重放补丁**（上游有新版本后）：

```bash
# 1. reverse 回裸 OLD_SYNC：.quilt-pc 存在用 quilt pop -a，不存在按 series 倒序 patch -p1 -R
# 2. rsync 上游 NEW_SYNC 覆盖
# 3. quilt push -a 重放本地 patch；若上游已自行修好这两条链接，补丁会 fail 或变空 —— 直接删补丁与 series 条目
# 4. quilt refresh
# 5. 更新 grafted-skills.json 的 synced_commit / synced_date，跑 update-readme.py
```

## 新增补丁的归档约定

1. 用语义化短名并保留 `0001-` / `0002-` 序号前缀。
2. `quilt refresh` 会自动维护 `series`，不要手改。
3. 在本 README 的「当前补丁列表」加一行。
4. patch 新增单独一个 commit，与依赖它的其他改动分开。

## 不动的边界

`skills/slidev/` 其余内容（各 `references/*.md`、示例代码）保持上游只读，re-graft 后直接用上游版本。本仓不在此 skill 上做中文化或结构重排——那类改动应走 `.curated/` 自有 skill，而不是堆成永远要重放的补丁栈。
