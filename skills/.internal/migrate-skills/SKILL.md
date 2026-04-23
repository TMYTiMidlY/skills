---
name: migrate-skills
description: 从外部仓库引入、同步、去品牌化、改落点、维护来源索引或整理开发者内部 skill 时使用；仅供本仓维护者操作，不对最终用户展示或安装。
---

# Migrate Skills

## 这是什么

这是**维护者内部 skill**，只给本仓 skill 开发者使用，不面向最终用户。

它负责：

- 从外部仓库迁入 skill
- 跟进上游同步
- 做去品牌化与依赖适配
- 决定 skill 应落到 `skills/`、`.experimental/`、`.internal/`、`.legacy/` 的哪一层
- 维护 README 的来源口径与 `grafted-skills.json`

它**不负责**：

- 普通用户的安装 / 卸载 / 软链冲突处理
- 对已有本地 skill 做通用审查与命名整理
- Hermes 本地安装操作本身

这些工作分别交给 `manage-skills` 或对应 skill。

## 暴露规则

`migrate-skills` 本身应放在 `skills/.internal/`：

- 不写进 README 的用户技能表
- 不写进面向用户的安装说明
- 不默认建议链接进 `.agents/skills/`
- 只在仓库维护时由开发者直接使用

## 先决定落点，再迁

| 落点 | 何时使用 | 是否进入 README 用户表 |
|---|---|---|
| `skills/.curated/` | 本仓原创，或已经彻底内化维护的内容 | 是 |
| `skills/` | 外部嫁接且已完成适配、可以对外安装 | 是 |
| `skills/.experimental/` | 先收录但尚未完成适配 / 验证 | 是（实验性表） |
| `skills/.internal/` | 只给仓库维护者使用 | 否 |
| `skills/.legacy/` | 已弃用，仅归档保留 | 否 |

不要为了“先放进去再说”而把内部维护工具塞进面向用户的表里。**开发者内部工具优先放 `.internal/`。**

## 迁移检查清单

### 1. 先确认上游信息

只有在**已确认**时才填写：

- 上游仓库 `repo`
- 上游路径 `path`
- 上游分支 `branch`
- 同步 commit
- 同步时间
- 上游许可证

`grafted-skills.json` 里的 `path` 表示**上游路径**，不是本仓落点。

### 2. 复制后先做适配

来自外部仓库的 skill 默认检查这些点：

- 去品牌化：把 `Claude`、`artifacts` 等产品专属概念改成通用表述
- 删除绑定特定产品的链接（如 `claude.ai`）
- `python scripts/...` 改成 `uv run scripts/...`
- `pip install X` 改成 `uv run --with X`
- 修正跨 skill / 仓库路径硬编码
- 检查 frontmatter `name` 是否与目录名一致、是否全局唯一
- 把长流程挪到 `references/`，保留渐进式披露

### 3. 明确“对外展示”和“内部维护”是两回事

- **对外 skill**：需要进入 README 表格，描述口径要和 skill frontmatter 对齐。
- **内部 skill**：放 `.internal/`，不进入 README 用户表，也不出现在安装示例里。
- 同一个 skill 如果还没决定是否对外，就先放 `.internal/` 或 `.experimental/`，不要先写进用户表再回头撤。

## 来源索引规则

`grafted-skills.json` 只记录**已经确认的外部来源**。不要为了表面完整而虚构来源。

- 来源没确认：**留空，不要猜**
- 还没决定是否公开暴露：先不要写进 README 用户表
- 只迁了代码但还没对齐来源：先补注释或 TODO，再等确认

### 当前特殊规则

- `upload` 这个 skill 的来源**暂时留空**。
- 不要擅自为 `upload` 补填 repo / path / synced_commit / synced_date。
- 如果后续确认了来源，再补齐；在此之前，空着比写错更好。

## 迁完后要同步的地方

按是否对外暴露决定是否更新这些文件：

- skill 自己的 `SKILL.md`
- README 技能表
- `grafted-skills.json`
- 相关说明文字（如“原创 / 嫁接 / 实验性 / 内部”口径）

同步时保持这几个约束：

- README 面向用户的表**不列 `.internal/`**
- `grafted-skills.json` 只写已确认来源
- `description` 与 README 说明口径一致
- 重名检查覆盖 `.curated/`、根目录、`.experimental/`、`.internal/`、`.legacy/`

## 完成时的输出

结束时要明确交代：

- 这个 skill 最终落在哪个目录
- 是否对用户暴露
- README 是否已同步
- `grafted-skills.json` 是否已更新
- 哪些来源字段是**已确认填写**的，哪些是**故意留空**的
