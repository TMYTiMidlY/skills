# Agent Skills 官方结构与目录规范

Anthropic「Agent Skills」的可移植 skill bundle 格式：一个 skill 长什么样、哪些是硬要求、`scripts/` / `references/` / `assets/` 各干什么、名字为什么是复数。跨 harness 通用——Claude、Copilot 等都消费这套 Anthropic 式 skill，所以这层格式知识独立于具体 agent。

## 标准目录树

一个 skill bundle 的**唯一硬要求**是 `SKILL.md`（带 YAML frontmatter：`name` + `description`）；其余子目录都是**约定、非 loader 强制**。Anthropic 的 Agent Skills 开放规范（[agentskills.io/specification](https://agentskills.io/specification)，2025-12 发布，也镜像在 `anthropics/skills:spec/agent-skills-spec.md`）给的标准树：

```
skill-name/
├── SKILL.md          # 必需：元数据 + 指令
├── scripts/          # 可选：可执行代码
├── references/       # 可选：按需加载的文档
├── assets/           # 可选：模板 / 静态资源
└── ...               # 其它文件 / 目录随意
```

## 三个可选目录：分野在「进不进上下文窗口」

- **`scripts/`** — agent 用 bash **执行**的代码；只有**运行结果**回流进上下文，脚本本身不占 context。适合确定性、重复性的活（解析 / 转换 / 校验），省 token 也更可靠。
- **`references/`** — agent **按需读进上下文**的文档（详细 API、schema、workflow）。SKILL.md 点名 `references/foo.md`，用到才加载——渐进式披露（progressive disclosure：细节只在需要时才喂进上下文）的主力。
- **`assets/`** — **静态资源**：模板、图片、数据文件、boilerplate。被**引用 / 拷进产物**用，但**不整体读进上下文**。这是它与 `references/` 的关键区别：references 是「给模型读的」，assets 是「给产物用的」。

## 是 `assets/`（复数），不是 `asset/`（单数）

官方规范、[platform.claude.com Agent Skills 概览](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)、`anthropics/skills` 仓库里的真实 skill（如 `skill-creator` 同时用齐 `scripts/` `references/` `assets/`）**一律小写复数**；`asset/` 单数在官方源里**零出现**。`references/` 同理复数。命名对齐主要为可发现性 + 跟生态一致。

## 坑 / 边界

- 子目录名是**语义约定**、不是 loader 解析项——只有 `SKILL.md` frontmatter 是硬格式。名字写错不会「加载不了」，但会丢可发现性、跟生态不一致。
- 反例：`anthropics/skills` 里 `mcp-builder` 用了 `reference/`（单数），属仓库内个别偏差、**不是第二套约定**——规范与其余所有来源都用复数。
- 小 skill 可把 `reference.md` / `forms.md` 直接平铺在根目录（如官方 `pdf` skill），不建 `references/`；规范明说允许「任意附加文件 / 目录」。

## 来源

- [agentskills.io/specification](https://agentskills.io/specification) — Anthropic Agent Skills 开放标准（2025-12），目录树 + 各目录定义原文。
- [platform.claude.com — Agent Skills 概览](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) — 三层内容模型、`references/` 命名。
- [Anthropic Engineering — Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — 设计动机（bundle 附加文件、脚本即工具）。
- [anthropics/skills](https://github.com/anthropics/skills) — 官方参考仓库；`skill-creator` 三目录齐全（`scripts/` `references/` `assets/`）。
