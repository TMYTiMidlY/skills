# 审查现有 skills（跨 skill 合规扫描）

用户让"审查 / 检查所有 skill 是否合规"时走这套：横扫多个 skill、逐条核对规范、汇总发现。它和 [refactor.md](refactor.md) 的"单篇深度重排"不同——那是对一篇文档深改、先出大纲后动手；这里是跨多 skill 的合规扫描，默认**只报告不改**。

## 审查流程

先向用户确认审查范围（如原创、已适配嫁接、实验性、全部），然后对范围内每个 skill 逐条核对 [conventions.md](conventions.md) 里的每项要求，再加下面「跨 skill 专项检查」。默认**只审不改**：先列出发现交给用户，明确同意后才动手改。

输出格式：按 skill 分段，每段列命中的检查项（带文件 / 行号）与建议；最后给"全部无问题的 skill 清单"，避免用户误以为全仓都有病。

批量修复前先跟用户敲定**改动策略**：统一用哪种新写法、原位置留空壳还是删、是否同步调其他 skill 的交叉引用。

## 跨 skill 专项检查

[conventions.md](conventions.md) 里多是"单个 skill 自身要满足的属性"，看一个 skill 就能核。下面这几项不一样——只有把全仓摆在一起、或对照上游才做得出来，所以单独放在审查流程里，不塞进 conventions。

### 嫁接 skill 的上游 LICENSE

来自外部仓库的 skill（README"嫁接自其他仓库"表里的条目、以及 `grafted-skills.json` 里登记的条目）安装到本仓 `skills/` 目录后，skill 根目录下必须保留一份上游的 LICENSE 文件（原名如 `LICENSE` / `LICENSE.txt` / `LICENSE.md` 都可以，按上游叫什么就叫什么）。适配过程允许改正文、改命令、删个人化片段，但不能顺手把上游 LICENSE 删掉——那等于剥版权声明。

审查时对每个嫁接 skill 目录 `ls` 一遍，缺 LICENSE 的列出来；建议从上游对应 commit（参考 `grafted-skills.json` 的 `synced_commit`）补回原文件，不要自行改写或换成别的协议。

### 嫁接 skill 的上游同步状态

对照 `grafted-skills.json` 里登记的 `repo` / `synced_commit`，看上游从这个 hash 到 HEAD 之间有没有重大更新（新功能 / breaking change / 文档结构调整 / 依赖升级 / 删/改了本仓在用的脚本或 reference）。

走 GitHub API 看 `compare/<synced_commit>...HEAD` 的 commit 数和改动文件清单；如果上游路径就是 `grafted-skills.json` 里的 `path`，只关心这个子目录下的变动即可。

本检查项**只汇报**：列出"自 `synced_commit` 起累计 N 个 commit、影响 M 个文件，看起来有/没有 breaking 改动"，是否 re-graft 由用户决断；审查回合**不要**自动 sync 上游、不要改 `synced_commit`、不要改 skill 文件。

### frontmatter `name` 全局唯一

`.curated/`、`.experimental/`、`.legacy/` 和嫁接根目录加起来不能有重名。Hermes 按 `name` 去重，first-seen wins，后者会被悄悄丢弃。如果同名 skill 落在同一个 external_dir 的不同子目录下（如 `skills/pdf` 和 `skills/.experimental/pdf`），谁先被扫到取决于文件系统遍历顺序，**行为不确定**。

审查时 grep 所有 SKILL.md 的 `name:` 字段，发现重名就报告。
