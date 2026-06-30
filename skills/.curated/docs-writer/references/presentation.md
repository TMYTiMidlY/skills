# 模式 C：演示文稿（presentation）

PPT 任务的**完整工程流**（SVG 模板 / python-pptx / 设计规范 / 配图重做 / 导出 pptx）由独立的 **`ppt-master` skill** 负责，本 skill **不规定 PPT 工程结构**。docs-writer 在演示文稿层面**只覆盖与论文/汇报共享的能力**，保证多 deliverable 一致：

- **引用核查与文献规范** → 见 `SKILL.md`《引用核查与优化》《文献格式规范 GB/T 7714-2015》
- **配图生成与 AI 标注 + 资产管理** → 见 `SKILL.md`《配图与 AI 标注》《项目资产管理》

> 共享名词（一手来源、single source of truth、codex-image 等）定义见 `SKILL.md`《名词表》。

## 1. 工具选型

| 工具 | 用途 |
|------|------|
| **python-pptx** | 原地修改现有 pptx（替换文本、替换图片、读写页面元素） |
| **SVG 工程源 + 渲染脚本** | 从 SVG 模板批量出 pptx（保设计精度）—— 完整流程在 `ppt-master` |
| **codex-image** | 重做配图（见 `SKILL.md`《配图与 AI 标注》） |

## 2. PPT 与本 skill 的关系（资产共享）

PPT 工程一般有独立的工程目录（含 SVG 源、notes、`design_spec.md` 等，结构由 `ppt-master` 定义）。本 skill 与 PPT 工程的衔接点是**共用一套资产基准**：

- PPT 项目的引用编号、文献条目、配图资产**与 docx/论文共用同一份数据基准** —— 即 `SKILL.md`《项目资产管理》约定的项目级 `images/` 单一源 + 源文献目录 + 统一引用表。
- 与 `ppt-master` 配合时，**不要为 PPT 单独复制一份图**；PPT 工程与 docx/论文一起从同一个 `<project>/images/` 取图，源文献放同一个项目源目录。`ppt-master` 的工程目录约定（`<project>/images/`、`sources/`、`image_manifest.json` 等）与本 skill 的资产管理模式对齐，详见 `SKILL.md`《项目资产管理》的「与 ppt-master 配合」。

具体 PPT 操作流程（建项目、八确认、SVG 生成、导出等）一律走 `ppt-master` skill。
