# Agent Instructions

这个文件包含对 AI 智能体的行为指令和最佳实践指南。

## 核心规则

- Python 环境优先级：Pixi > uv > python/python3。
- Python 依赖优先写进脚本的 PEP 723 元数据；已有的 Python 文件运行需要临时依赖用 `uv run --with <package> <script>`；非必要时不用 `uv pip install`，而是使用 `uv add` 或 `uv run --with`。
- 遇到需求不清、行为有分歧、边界不明确时，优先调用当前环境可用的提问工具向用户确认；如果没有可用工具，也必须用普通对话直接提问，不要直接暂停对话或跳过确认。
- 未经用户明确指令，严禁自动执行 `git add` 或 `git commit`。
- 若暂存区为空，且用户明确要求提交：只暂存用户明确要求提交的文件或改动；如果提交范围不明确，或工作区存在其他未说明改动，先说明当前状况，再按上述提问原则确认提交范围。
- 若暂存区非空，且用户明确要求提交：先说明当前状况，再按上述提问原则确认提交范围。
- 删除文件时**强制使用 `trash-put` 代替 `rm`，无任何例外**。即使跨 filesystem（NTFS / drvfs / CIFS / FUSE / overlay 等）也用 `trash-put`：
  - 跨 filesystem 时 trash-cli 会在挂载点根目录建 `.Trash-<UID>/`，文件留在源 filesystem 内可恢复；不会自动跨 filesystem 拷回本地，不影响"可恢复"这一核心保证。
  - NTFS / Windows 盘没有 freedesktop trash spec，trash-cli 仍会在该卷的挂载点根目录建 `.Trash-<UID>/` 落实回收站语义；Windows 端虽然不会出现在资源管理器回收站，但 agent 仍能从该目录恢复——比 `rm` 安全得多。
  - 唯一允许用 `rm` 的情形：**用户在本轮对话中显式批准**（"用 rm"/"直接 rm 删"/"不用 trash"等明确措辞）。仅"删掉"/"清理"/"remove"等中性措辞不构成授权，必须先用 `trash-put`。
  - 即使是自己刚 create 的零信息临时文件（如 `.ps1` marker、check probe），也用 `trash-put`，**不要自行判断"反正没价值"绕开规则**。
  - 恢复误删文件必须由用户手动执行 `trash-restore`，agent 不得自动执行。
- 修改任何文本文件时，能用内置工具完成就必须用内置工具，不要用 shell 命令替代；改动必须清晰、可审查、可回滚，不要用不透明的原地批量改写绕过审查。任务量大时先问用户。
- 如果目标文件权限或沙箱限制导致不能直接修改，应申请权限或准备临时文件让用户安装，不要为了绕过权限而改用难以审查的方式。
- 每次回复末尾都必须追加”喝水水中”并配一个好玩的 emoji。

## 工具与 Skills

- 优先使用已有工具和已安装 skills，再考虑手动展开实现。当用户提到使用某个或某些 skills 来完成任务时，仔细阅读 skills 中与任务相关部分，严格按 skill 执行。
- 创建和修改 skills 时，优先写流程和思想，少写具体代码，skill 的描述是给 AI 看的，AI 自己会写代码。在元数据description中，不需要完整描述 skill 的内容，只需要描述何时应调用本 skill 并介绍其核心思路即可。
- 在理解 subagents 能力和限制的情况下，合适时调用 subagents 解决问题。
