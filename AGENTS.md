# Agent Instructions

这个文件包含对 AI 智能体的行为指令和最佳实践指南。

## 核心规则

- Python 环境优先级：Pixi > uv > python/python3。
- Python 依赖优先写进脚本的 PEP 723 元数据；已有的 Python 文件运行需要临时依赖用 `uv run --with <package> <script>`；非必要时不用 `uv pip install`，而是使用 `uv add` 或 `uv run --with`。
- 遇到需求不清、行为有分歧、边界不明确时，优先调用当前环境可用的提问工具向用户确认；如果没有可用工具，也必须用普通对话直接提问，不要直接暂停对话或跳过确认。
- 未经用户明确指令，严禁自动执行 `git add` 或 `git commit`。
- 若暂存区为空，且用户明确要求提交：只暂存用户明确要求提交的文件或改动；如果提交范围不明确，或工作区存在其他未说明改动，先说明当前状况，再按上述提问原则确认提交范围。
- 若暂存区非空，且用户明确要求提交：先说明当前状况，再按上述提问原则确认提交范围。
- 删除文件时使用 `trash-put` 代替 `rm`。恢复误删文件必须由用户手动执行 `trash-restore`，agent 不得自动执行。
- 能用内置工具完成的修改就用内置工具，不要用 shell 命令替代。任务量大时先问用户。
- 每次回复末尾都必须追加”喝水水中”并配一个好玩的 emoji。

## 工具与 Skills

- 优先使用已有工具和已安装 skills，再考虑手动展开实现。当用户提到使用某个或某些 skills 来完成任务时，仔细阅读 skills 中与任务相关部分，严格按 skill 执行。
- 创建和修改 skills 时，优先写流程和思想，少写具体代码，skill 的描述是给 AI 看的，AI 自己会写代码。在元数据description中，不需要完整描述 skill 的内容，只需要描述何时应调用本 skill 并介绍其核心思路即可。
- 在理解 subagents 能力和限制的情况下，合适时调用 subagents 解决问题。

## Cursor Cloud specific instructions

- **仓库性质**：这是一个 AI agent skill 包合集（纯内容仓库），没有可运行的应用服务、构建流程、测试框架或 lint 配置。所有"运行"都是通过 `uv run` 执行各 skill 下的辅助 Python 脚本。
- **环境依赖**：`uv`（Python 包管理/运行）和 `trash-cli`（`trash-put` 命令）已由 update script 安装到 `$HOME/.local/bin`。Python 3.12 系统自带。
- **运行脚本**：遵循 AGENTS.md 核心规则，使用 `uv run scripts/...`（纯标准库脚本）或 `uv run --with <pkg> scripts/...`（有外部依赖的脚本）。不要使用 `pip install`。
- **README 同步**：修改 `grafted-skills.json` 后，运行 `uv run .agents/skills/graft-skill/scripts/update-readme.py` 更新 README 中的 skill 表格。
- **无 lint/test/build**：仓库没有配置 linter、测试框架或构建步骤。验证方式是确认脚本可正常执行、SKILL.md 结构合规（可用 `uv run skills/qiuzhi-skill-creator/scripts/quick_validate.py <skill-dir>` 检查）。
