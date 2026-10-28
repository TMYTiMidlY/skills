---
name: manage-skills
description: 创建、安装、维护、重构、审查或合并本地 skill，以及安装和修复 AGENTS.md 等共享指令入口时使用。先探测已有 harness 与实际配置根，再按范围补齐共享目录和兼容链接。
---

# Manage Skills

按任务选择入口：安装、维护和卸载先读[安装与维护](references/installation.md)，写改 skill 先读[写作规范](references/conventions.md)，审查读[审查流程](references/review.md)，单篇深度重构读[重构流程](references/refactor.md)，合并分叉读[合并流程](references/merge.md)。解释和审查本身不授权安装、覆盖或清理。

## <a id="installation"></a>安装与维护

本 skill 负责执行安装、探测与修复。路径表、平台链接方式和命令统一维护在[安装与维护参考](references/installation.md)，README 向用户介绍安装预期并引导调用本 skill。

1. 沿用用户已说明的 skills、用户级或项目级范围，以及实际仓库位置；只询问影响执行的关键缺口。
2. 每次重新[探测已有 harness 与配置根](references/installation.md#environment-discovery)。未发现工具配置目录时跳过其兼容入口；用户明确要求初始化该工具时再创建。
3. 核对现有链接、独立安装和主指令内容，按[差异处理规则](references/installation.md#installation-plan)决定新增、保持、修复或确认冲突；保留用户已有内容。
4. 将选定 skill 链入相应共享目录。分别核对工具对共享 skills 和共享主指令的支持，只为已发现且在授权范围内的工具补齐需要的兼容入口。
5. 按[验收与报告](references/installation.md#validation)核对实际落点与可读性，并分别报告入口配置和真实加载结果。再次运行时只处理新发现的缺项与变化。

### <a id="instruction-installation"></a>通用指令与本机补充

安装或维护 `AGENTS.md` 等主指令入口也走上述探测流程，按[主指令入口表](references/installation.md#instructions-discovery)执行。本机补充统一保存为 `~/.agents/AGENTS.local.md` 普通文件，位置与维护边界见[本机补充](references/installation.md#local-instructions)。

### 卸载与失效链接

仅处理用户指定的安装入口，保留仓库实体和独有内容，按[卸载与失效链接](references/installation.md#uninstall-repair)执行。

## 写 / 改 skill 的规范

写、改、审查、重构任何 skill 都按 [references/conventions.md](references/conventions.md) 的要求来——那是唯一出处，含完整理由与正反例。**别在这里或别的 skill 里重抄规则，要提就写条目名链过去。** 速览（点进 conventions 看细节）：

- **内容**：清楚地表达内容｜不说废话｜命令 / 配置简洁准确｜操作前提与边界明确｜图形界面流程具体｜事实、推断与建议分开｜自然穿插踩坑 / 排障｜个人配置不入正文
- **引用**：补充来源、限制和例外用 `>` 紧跟正文｜来源与置信度就近｜引用做成可点击 Markdown 链接｜同 skill 使用相对路径和显式 `<a id>` 锚点｜跨 skill 只写 skill 名 + 能力边界｜上游链接锁定版本
- **标题**：命名"这节是什么"、不预告结论 / 计数 / 排名｜不编号、不用 §N 交叉引用｜并列小节靠客观属性区分｜改带 `<a id>` 的标题只改文字
- **结构**：渐进式披露三层按需加载、分工清楚｜单文件长度不是拆分理由｜脚本用 `uv` + PEP 723 内联依赖｜不绑定特定 AI 工具名｜frontmatter `name` 与目录名一致｜README 与 skill 状态同步

## 重构已有文档

把一篇已成型的文档（SKILL.md 或 reference）做深度重构：核验事实，理顺标题树、章节归属和来源组织，做到语义不漏、重复不留。核心：**先分别提交标题方案和内容迁移表供审阅，两轮批准后才动手**，全程对照 [references/conventions.md](references/conventions.md) 逐条核对。完整流程与审阅格式见 [references/refactor.md](references/refactor.md)。

## 审查现有 skills

先采用用户已明确的对象、维度和深度，只确认影响工作量或结论的缺口。表达与结构、指令与执行边界、技术事实、许可证与上游状态可以分别审查；完整合规审查才逐条核对 [references/conventions.md](references/conventions.md) 的适用要求并覆盖相关专项检查。默认**只审不改**，报告说明全文 / 抽样覆盖及未核验部分，不把专题审查扩成全量审计。流程与输出要求见 [references/review.md](references/review.md)。

## 解决合并冲突

把两条分叉的 skill 文档分支合到一起（双向分叉、两边各自重构同一大文件、术语 / 定义分歧）时，别当成机械删冲突标记——核心是**理解两边意图后，重建一份一致、不丢信息、无重复的知识**。要点：动手前勘定环境 + 无损预演冲突清单；三方溯源看意图（别急着否掉一侧）；给冲突分类套手法（纯并集 / 干净超集 / 结构分叉选底本 splice / 术语分叉查一手来源）；通读结构抓自动合并在冲突标记之外制造的静默重复；splice 后修交叉引用；只收本次合并该带的、隔离并发 / 脏改动；reference 先于 SKILL.md；大改走重构流程；解决即验。完整方法见 [references/merge.md](references/merge.md)。

## Hermes

Hermes 的 skill 发现机制和本仓这套 `.agents/skills` 软链不一样（走它自己的 `hermes skills` CLI），给 Hermes 装 / 卸 skill 时去 `harness` skill 的 Hermes 运行时章节参考一下。
