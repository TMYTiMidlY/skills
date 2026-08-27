# improve-codebase-architecture 本地补丁

把上游 `mattpocock/skills` 的 `skills/engineering/improve-codebase-architecture` 嫁接到本仓库 `skills/.experimental/improve-codebase-architecture/` 后打的本地补丁，用 [quilt](https://savannah.nongnu.org/projects/quilt/) 管理。

补丁目录路径镜像 `grafted-skills.json` 的 key（`.experimental/improve-codebase-architecture`），与 `patches/ppt-master`、`patches/slidev` 同一套约定。

`series` 文件是补丁顺序的权威清单（quilt 原生格式），`grafted-skills.json` 不重复记录。

## 当前补丁列表

| 序号 | 文件 | 目的 |
| ---- | ---- | ---- |
| 0001 | `0001-delink-cross-skill-grill-with-docs-refs.patch` | 把两处指向 `../grill-with-docs/` 的相对链接改为只写 skill 名与能力边界。上游两个 skill 是同级兄弟、相对路径成立；本仓把 `grill-with-docs` 提升出实验区后层级错开，链接断。 |

## 补丁 0001 的成因

上游把两个 skill 放在同一层：

```
mattpocock/skills:  skills/engineering/grill-with-docs
                    skills/engineering/improve-codebase-architecture
```

所以上游写 `../grill-with-docs/ADR-FORMAT.md` 成立。本仓嫁接后布局不同——`grill-with-docs` 已提升到 `skills/grill-with-docs/`，本 skill 仍在 `skills/.experimental/` 下，相差一层，两条链接全断。

不选「补一层 `../../`」是因为那只修表：任一 skill 再升降级一次又断，且违反 `manage-skills` 规范「跨 skill 不写路径、不链接内部文件，只写 skill 名和能力边界」。改成写 skill 名后，无论两边今后怎么挪都不会再断。

补丁保持上游英文行文，只替换引用写法，把 re-graft 冲突面压到最小。

若今后把本 skill 也提升出 `.experimental/`、与 `grill-with-docs` 恢复同级，本补丁仍应保留——规范要求的是不写跨 skill 路径，而不只是让路径当前可解析。

## 工作流

完整 quilt 命令范式见 `graft-skill` skill 的「本地补丁（quilt）」章节。

本目录的环境变量：

```bash
REPO=$(git rev-parse --show-toplevel)
cd "$REPO/skills/.experimental/improve-codebase-architecture"
export QUILT_PATCHES="$REPO/patches/.experimental/improve-codebase-architecture" \
       QUILT_PC="$REPO/.quilt-pc/.experimental/improve-codebase-architecture"
```

`.quilt-pc/` 已被 gitignore，重新 clone 后不存在；要改已有补丁需先 `quilt push -a` 重建状态。

**Re-graft 时重放补丁**：

```bash
# 1. reverse 回裸 OLD_SYNC：.quilt-pc 存在用 quilt pop -a，不存在按 series 倒序 patch -p1 -R
# 2. rsync 上游 NEW_SYNC 覆盖
# 3. quilt push -a 重放；上游若改写了这两段行文会冲突，按 SKILL.md「冲突处理」分流
# 4. quilt refresh
# 5. 更新 grafted-skills.json 的 synced_commit / synced_date，跑 update-readme.py
```

## 新增补丁的归档约定

1. 用语义化短名并保留 `0001-` / `0002-` 序号前缀。
2. `quilt refresh` 会自动维护 `series`，不要手改。
3. 在本 README 的「当前补丁列表」加一行。
4. patch 新增单独一个 commit，与依赖它的其他改动分开。

## 不动的边界

skill 正文的英文行文、工作流步骤与判断标准保持上游只读。本仓不在此 skill 上做中文化或结构重排——那类改动应走 `.curated/` 自有 skill，而不是堆成永远要重放的补丁栈。
