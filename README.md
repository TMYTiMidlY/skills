# Skills

给 AI 编程助手（Claude Code / GitHub Copilot 等）增加实用能力的技能包合集。安装后，AI 能直接处理 Office 文档、PDF、前端页面设计、服务器运维等日常任务。

## 可用的 Skills

| Skill | 来源 | 说明 |
| --- | --- | --- |
| `vps-use` | *原创* | 通过 SSH 远程操作 VPS，完成服务器配置和运维任务 |
| `qiuzhi-skill-creator` | [秋芝2046](https://space.bilibili.com/385670211) | 交互式引导创建新的 skill |<!-- skills-table:begin -->
| `slidev` | [slidevjs/slidev](https://github.com/slidevjs/slidev) | Slidev 官方 skill |
| `doc-coauthoring` | [anthropics/skills](https://github.com/anthropics/skills) | 文档协作工作流 |
| `docx` | [anthropics/skills](https://github.com/anthropics/skills) | Word 文档操作 |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills) | 前端界面设计 |
| `pptx` | [anthropics/skills](https://github.com/anthropics/skills) | PowerPoint 文件操作 |
| `xlsx` | [anthropics/skills](https://github.com/anthropics/skills) | Excel 电子表格操作 |
| `pdf` | [anthropics/skills](https://github.com/anthropics/skills) | PDF 文件操作 |

以下 skill 从外部仓库下载，尚未经过适配和验证，放在 `.experimental/` 目录下：

| Skill | 来源 | 说明 |
| --- | --- | --- |
| `doc` | [openai/skills](https://github.com/openai/skills) | Word 文档读写（python-docx） |
| `frontend-skill` | [openai/skills](https://github.com/openai/skills) | 高质量前端页面构建 |
| `gh-address-comments` | [openai/skills](https://github.com/openai/skills) | 处理 GitHub PR 评论 |
| `gh-fix-ci` | [openai/skills](https://github.com/openai/skills) | 修复 GitHub CI 失败 |
| `jupyter-notebook` | [openai/skills](https://github.com/openai/skills) | Jupyter Notebook 创建与编辑 |
| `screenshot` | [openai/skills](https://github.com/openai/skills) | 桌面截图 |
| `slides` | [openai/skills](https://github.com/openai/skills) | 代码驱动的幻灯片制作 |<!-- skills-table:end -->

此外，`skills/.legacy/` 目录下存放已弃用的 skill，仅作归档保留。

### 外部 Skill 的适配规则

来自外部仓库的 skill（标有来源链接的条目）会做以下适配，使其不绑定特定产品：

1. **去品牌化** — 将 `Claude`、`artifacts` 等产品专属概念替换为通用表述（如 `agent`、文件操作）；删除 `claude.ai` 等产品链接。
2. **统一依赖管理** — `python scripts/...` 改为 `uv run scripts/...`；`pip install X` 改为 `uv run --with X`。

## 安装

### 方式一：克隆 + 软链接（推荐）

```bash
git clone https://github.com/TMYTiMidlY/skills.git ~/skills
```

以 `.agents/skills/` 作为唯一的 skill 源，将需要的 skill 链接进去。全局安装就放在 `~/` 下，项目级安装就放在项目根目录下：

```bash
mkdir -p .agents/skills

# 将需要的 skill 逐个链接进来
ln -s ~/skills/skills/<skill-name> .agents/skills/
```

GitHub Copilot、Gemini CLI、Codex、Cline、Warp、Windsurf、Roo Code 等工具原生读取 `.agents/skills/`，无需额外配置。其他工具需要将各自的 skills 目录链接到 `.agents/skills/`：

| 工具 | 自有 skills 目录 | 链接命令 |
| --- | --- | --- |
| Claude Code | `.claude/skills/` | `ln -s .agents/skills .claude/skills` |
| Cursor | `.cursor/skills/` | `ln -s .agents/skills .cursor/skills` |
| Amp | `.config/agents/skills/` | `ln -s .agents/skills .config/agents/skills` |
| Goose | `.config/goose/skills/` | `ln -s .agents/skills .config/goose/skills` |
| Junie | `.junie/skills/` | `ln -s .agents/skills .junie/skills` |
| Kiro CLI | `.kiro/skills/` | `ln -s .agents/skills .kiro/skills` |

其他工具同理，将其 skills 目录链接到 `.agents/skills/` 即可。

**软链接注意事项：**

- 链接到 skill **目录本身**而非内部单个文件，否则相对引用会断裂。
- 同名目录已存在时先删除再建链接，否则 `ln -s` 会建到子目录里。

由于软链接直接指向仓库中的文件，对仓库的任何修改都会即时反映到所有链接位置，无需重新安装或手动同步。日常维护只需在仓库目录中编辑、用 `git pull` 拉取更新即可。

### 方式二：`skills` CLI

```bash
bunx skills add TMYTiMidlY/skills            # 安装全部
bunx skills add TMYTiMidlY/skills --list      # 查看可安装内容
bunx skills add TMYTiMidlY/skills --skill pdf  # 仅安装指定 skill
bunx skills update                             # 更新已安装 skills
```

常用选项：`-g` 全局安装，`-y` 跳过确认。

## 使用

每个 skill 目录下的 `SKILL.md` 说明了触发条件和能力范围。AI 会根据对话内容自动匹配并调用对应的 skill，无需手动指定。

部分 skill 附带 `scripts/` 目录，包含可直接运行的辅助脚本。

想创建自己的 skill？使用 `qiuzhi-skill-creator` 即可通过交互式引导完成。

## AGENTS.md

[AGENTS.md](AGENTS.md) 是一份通用的 AI agent 行为规则，涵盖 Python 环境选择、Git 操作约束、工具使用习惯等偏好设置。适用于 Claude Code、GitHub Copilot 等支持 `AGENTS.md` / `CLAUDE.md` 的工具。

如需让 Claude Code 也读取同一份规则：

```bash
ln -s AGENTS.md CLAUDE.md
```

## 许可

各 skill 的许可证可能不同，请查看对应目录中的 `LICENSE` 或 `LICENSE.txt`。
