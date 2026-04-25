# 审查现有 skills 的检查清单

用户让“审查 / 检查所有 skill 是否合规”时按本清单办。默认**只审不改**：先向用户确认审查范围（如原创、已适配嫁接、实验性、全部），列出发现交给用户，明确同意后才动手改。

## 检查项

- **引用状态**
  - 同 skill 内引用（`references/`、`assets/`、`scripts/`）都用相对路径，不写绝对或 `~/...`；且目标真实存在（grep 验证）。
  - 跨 skill 不给任何文件路径，只写 skill 名加能力边界。
- **不硬编码仓库 clone 位置**
  - skill 正文、reference、README 里不要把 skills 仓库位置写死为 `~/skills`、`C:\Users\...\skills`、`/home/.../skills` 等具体路径；需要表达仓库根目录时用 `<repo>` 这类占位符，并说明由当前安装位置决定。
- **脚本运行与依赖声明**
  - 正文或 reference 里提到运行同 skill 自带 Python 脚本时，应要求使用 `uv`，脚本路径保持为当前 skill 根目录下的 `scripts/` 相对路径，不写绝对路径、`~/...`、上层跳转路径或绑定本机仓库位置的路径。
  - 脚本的 Python 版本与第三方依赖应放进 PEP 723 内联脚本元数据（inline script metadata），不要把安装命令或临时依赖细节堆进 skill 正文。
- **渐进式披露三层完整、分工清晰**
  - `frontmatter description` → `SKILL.md` → `references/*.md`
  - description：只写“何时触发 + 核心思路一句话”。
  - SKILL.md：短规则 + 各主题入口 + 子文档索引；不堆长流程与整段命令。
  - references/：单主题一文件，长流程 / 踩坑 / 模板。
  - 常见病：SKILL.md 堆满命令（该下放）；references 存在但 SKILL.md 没索引（找不到入口）；description 太笼统或太具体。
  - 判定：SKILL.md 读完应当知道“能做什么、哪个 reference 讲什么”，**不应该读完就能完成具体任务**，那说明 references 层缺位。
- **个人配置不入 skill 正文**
  - 凭据 / 域名 / 服务器地址 / 个人样例文件名都不写进 skill 正文。正文只写变量名、占位符和读取位置，真实值放 `~/.env` 或个人笔记。
- **不绑定特定 AI 工具的具体工具名**
  - skill 正文不写 `AskUserQuestion`、`TodoWrite`、`WebFetch`、`Task` 这类特定宿主（Claude Code / Codex / Cursor / Trae 等）独有的工具名。
  - 改写成能力描述：“向用户提问的工具”、“任务清单工具”、“抓网页的工具”，由模型按当前环境自己挑。
  - 只有当 skill 明确只服务单一宿主、且在 description 里讲清楚时才可以保留具体名字。
- **README 与 skill 实际状态同步**
  - README 表格条目的名称 / 来源 / 说明要和 skill 自身的 frontmatter `description` 口径一致。
  - 合并 / 拆分 / 重命名 / 删除 skill 后，README 不能留 stale 条目。
  - 外部索引按其自身语义核对，例如 `grafted-skills.json` 记录上游来源路径，不按本仓落点判断。
- **所有命名空间内 skill 的 frontmatter `name` 必须全局唯一**
  - `.curated/`、`.experimental/`、`.legacy/`、嫁接根目录和维护区加起来不能有重名。
  - Hermes 按 `name` 去重，first-seen wins，后者会被悄悄丢弃。
  - 如果同名 skill 落在同一个 external_dir 的不同子目录下（如 `skills/pdf` 和 `skills/.experimental/pdf`），谁先被扫到取决于文件系统遍历顺序，**行为不确定**。
  - 审查时 grep 所有 SKILL.md 的 `name:` 字段，发现重名就报告。
- **其他结构性检查**
  - frontmatter `name` 与目录名一致。
  - 弃用段落删掉，别留历史遗迹。
  - 任何可疑处照实记下让用户决断。

## 输出格式

按 skill 分段，每段列命中的检查项（带文件 / 行号）与建议；最后给“全部无问题的 skill 清单”，避免用户误以为全仓都有病。

## 批量修复前的确认点

批量修复前先跟用户敲定：

- 统一用哪种新写法
- 原位置留空壳还是删
- 是否同步调其他 skill 的交叉引用
