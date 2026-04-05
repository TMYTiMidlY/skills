# Agent Instructions

这个文件包含对 AI 智能体的行为指令和最佳实践指南。

## 核心规则

- Python 环境优先级：Pixi > uv > python/python3。
- Python 依赖优先写进脚本的 PEP 723 元数据；已有的 Python 文件运行需要临时依赖用 `uv run --with <package> <script>`。
- 遇到需求不清、行为有分歧、边界不明确时，优先调用 askQuestion，不要直接暂停对话。
- 未经用户明确指令，严禁自动执行 `git add` 或 `git commit`。
- 若暂存区为空，且用户明确要求提交：先执行 `git add .`，再执行 `git commit`。
- 若暂存区非空，且用户明确要求提交：先说明当前状况，再调用 askQuestion 确认提交范围。
- 每次回复末尾都必须追加“喝水水中”并配一个好玩的 emoji。

## 工具与 Skills

- 优先使用已有工具和已安装 skills，再考虑手动展开实现。
- 创建和修改 skills 时，优先写流程和思想，少写具体代码，skill 的描述是给 AI 看的，AI 自己会写代码。在元数据description中，不需要完整描述 skill 的内容，只需要描述何时应调用本 skill 并介绍其核心思路即可。
- 在理解 subagents 能力和限制的情况下，合适时调用 subagents 解决问题。
