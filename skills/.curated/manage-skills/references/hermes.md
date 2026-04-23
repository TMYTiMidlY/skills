# 为 Hermes 安装 skill

Hermes 有自己的 skill 体系，用 `hermes skills` CLI 单独管理；它不会自动读取其它工具（Claude Code / Cursor / Codex 等）的 skills 目录，想让 Hermes 用上同一个 skill 要单独装一份。

能用 `hermes skills install / uninstall` 搞定的就用命令，别手动摆目录——Hermes 会自己管安全扫描、锁文件和更新追踪。

## 三种 skill 来源

`hermes skills list` 里每条记录都带一个 `Source` 字段：

| 来源 | 含义 | 命令能管吗 |
|------|------|-----------|
| `builtin` | 随 Hermes 发行版打包的 skill | 不能装/卸，只能 `reset`（清除“user-modified”标记） |
| `hub` | 从 registry 拉下来的，走 `install`/`uninstall` 流程 | 可装可卸，有安全扫描与锁文件 |
| `local` | 用户自己放进 Hermes skill 根的 skill | 靠文件系统管理 |

## 从 registry 安装

```bash
hermes skills install <identifier> [--category <category>] [--yes]
```

`<identifier>` 采用 `<registry>/<path>/<name>` 的多级命名，常见形式：

- `skills-sh/<owner>/<repo>/<name>` — skills.sh 第三方索引站（从 GitHub 仓库收录而来；上游是官方仓的条目会标 `trusted`，其余为 `community`）
- `official/<category>/<name>` — Hermes 自带的官方 hub
- 只写 skill 名 — 在所有已知 registry 中搜索

要接入更多来源（如额外的 GitHub 仓库）用 `hermes skills tap add <owner/repo>`。不确定名字时先 `hermes skills search <query>` 找，`hermes skills inspect <identifier>` 预览，再决定是否安装。

## 把本地 skill 装进 Hermes

要让 Hermes 用上某个本地来源（含本仓库）的 skill，按 Hermes 约定的 `<category>/<name>/SKILL.md` 结构，把 skill 放进 Hermes 的 local skill 根——软链（推荐，改动同步）或复制均可。

local 根的具体位置以 `hermes skills env` 的输出为准；分类按 skill 实际主题选，不匹配时 Hermes 会回落到 `local` 但可能影响加载。

> 想让某个项目目录下的 skill 被 Hermes 发现但不移动文件，可在 `~/.hermes/config.yaml` 的 `skills.external_dirs` 里加入该目录；只读发现，不会改写。SSH / 远程 backend 不需要单独配置 skill，Hermes 会把本地 skill 同步到远端。

## 其他管理命令

| 操作 | 命令 |
|------|------|
| 列出已安装 | `hermes skills list [--source all\|hub\|builtin\|local]` |
| 搜索可装 | `hermes skills search <query>` |
| 预览（不装） | `hermes skills inspect <identifier>` |
| 卸载（仅 hub） | `hermes skills uninstall <name>`（需 y 确认） |
| 检查更新 | `hermes skills check` |
| 更新所有 | `hermes skills update` |
| 管理额外 registry | `hermes skills tap {list,add,remove}` |
