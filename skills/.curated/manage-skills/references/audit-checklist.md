# 审查现有 skills 的检查清单

用户让“审查 / 检查所有 skill 是否合规”时按本清单办。默认**只审不改**：先向用户确认审查范围（如原创、已适配嫁接、实验性、全部），列出发现交给用户，明确同意后才动手改。

## 检查项

- **引用状态**
  - 同 skill 内引用（`references/`、`assets/`、`scripts/`）都用相对路径（如 `references/foo.md`），不写绝对或 `~/...`；且目标真实存在（grep 验证）。
  - **跨 skill 不写任何形式的文件路径**——相对路径（`../<other-skill>/references/x.md`）、绝对路径、`~/...`、“迁移指引”链接（“内容已迁移到 [.../x.md](../.../x.md)”）全部禁止。只写 `<skill 名>` 加能力边界（例：“见 `software` skill 的 GitHub Copilot CLI 章节”）。理由：被引 skill 一旦重构 reference 文件名或拆分合并，所有跨 skill 链接都断；只写 skill 名 + 主题名，读者用 grep / SKILL.md 自己定位，永不断链。**没有“看似对用户更友好就破例”的豁免**——别在审查时被“明示目标对读者更顺手”的直觉劝退。
- **不硬编码仓库 clone 位置**
  - skill 正文、reference、README 里不要把 skills 仓库位置写死为 `~/skills`、`C:\Users\...\skills`、`/home/.../skills` 等具体路径；需要表达仓库根目录时用 `<repo>` 这类占位符，并说明由当前安装位置决定。
- **脚本运行与依赖声明**
  - 正文或 reference 里提到运行同 skill 自带 Python 脚本时，应要求使用 `uv`，脚本路径保持为当前 skill 根目录下的 `scripts/` 相对路径，不写绝对路径、`~/...`、上层跳转路径或绑定本机仓库位置的路径。
  - 脚本的 Python 版本与第三方依赖应放进 PEP 723 内联脚本元数据（inline script metadata），不要把安装命令或临时依赖细节堆进 skill 正文。
- **渐进式披露三层完整、分工清晰**
  - `frontmatter description` → `SKILL.md` → `references/*.md`
  - description：只写“何时触发 + 核心思路一句话”。
  - SKILL.md：短规则 + 各主题入口 + 子文档索引；不堆长流程与整段命令。
  - references/：单主题一文件，长流程 / 踩坑 / 模板。**单文件长度本身不是问题**——只要全篇围绕一个主题，几千行、几十 KB 的 reference 完全合规；不要因为文件“看起来大”就建议拆分，拆分依据永远是“出现了第二个独立主题”。
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
- **嫁接 skill 必须保留上游 LICENSE**
  - 来自外部仓库的 skill（README“嫁接自其他仓库”表里的条目、以及 `grafted-skills.json` 里登记的条目）安装到本仓 `skills/` 目录后，skill 根目录下必须保留一份上游的 LICENSE 文件（原名如 `LICENSE` / `LICENSE.txt` / `LICENSE.md` 都可以，按上游叫什么就叫什么）。
  - 适配过程允许改正文、改命令、删个人化片段，但不能顺手把上游 LICENSE 删掉——那等于剥版权声明。
  - 审查时对每个嫁接 skill 目录 `ls` 一遍，缺 LICENSE 的列出来；建议从上游对应 commit（参考 `grafted-skills.json` 的 `synced_commit`）补回原文件，不要自行改写或换成别的协议。
- **嫁接 skill 是否落后于上游**
  - 对照 `grafted-skills.json` 里登记的 `repo` / `synced_commit`，看上游从这个 hash 到 HEAD 之间有没有重大更新（新功能 / breaking change / 文档结构调整 / 依赖升级 / 删/改了本仓在用的脚本或 reference）。
  - 走 GitHub API 看 `compare/<synced_commit>...HEAD` 的 commit 数和改动文件清单；如果上游路径就是 `grafted-skills.json` 里的 `path`，只关心这个子目录下的变动即可。
  - 本检查项**只汇报**：列出“自 `synced_commit` 起累计 N 个 commit、影响 M 个文件，看起来有/没有 breaking 改动”，是否 re-graft 由用户决断；审查回合**不要**自动 sync 上游、不要改 `synced_commit`、不要改 skill 文件。
- **所有命名空间内 skill 的 frontmatter `name` 必须全局唯一**
  - `.curated/`、`.experimental/`、`.legacy/` 和嫁接根目录加起来不能有重名。
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
