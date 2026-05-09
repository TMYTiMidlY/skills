# Skills

面向 AI 编程助手（Claude Code / GitHub Copilot 等）的实用技能包合集。安装后，AI 能直接处理 Office 文档、PDF、前端页面设计、服务器运维等日常任务。

## 可用的 Skills

### 原创（MIT License，放在 `skills/.curated/` 下）

| Skill | 说明 |
| --- | --- |
| `manage-skills` | 创建、拆分、审查、维护本仓库里 skill 的规范与工作流 |
| `software` | SSH、systemd、格式转换（pandoc / feishu2md / MinerU）、自托管 Markdown 分享客户端、Windows/macOS 操作与激活、远程桌面 / WSL 网络、EasyTier 客户端、Hermes systemd / terminal backend |
| `vps-maintenance` | VPS 初始化、Caddy（含 caddy-security / caddy-webdav）、EasyTier、网络质量检测 |
| `docker-maintenance` | Hermes Docker 后端等受限容器内的环境探测、只读挂载识别、受限 CLI 安装、OAuth device flow、SSH key 生成 |
| `thesis-writer` | 中文学位论文写作与修订：doc 转分章 md、脚注内联、引用核查、GB/T 7714 格式规范 |
| `worktree` | 为实验性改动创建隔离 git worktree（含 submodule 同步）；项目特定构建由上层接管 |
| `mess` | 记录排查过的疑难杂症和踩坑经历 |
| `plan` | 先规划再实施：产出面向另一 AI 的分步可验证实施文档，含设计考量与注意事项 |

### 嫁接自其他仓库

| Skill | 来源 | 说明 |
| --- | --- | --- |
| `qiuzhi-skill-creator` | [秋芝2046](https://space.bilibili.com/385670211) | 交互式引导创建新的 skill |<!-- skills-table:begin -->
| `remote` | [TMYTiMidlY/ssh-remote-mcp](https://github.com/TMYTiMidlY/ssh-remote-mcp) | ssh-remote-mcp 配套 skill：MCP 模式 + Plain 模式两套远端操作流程 |
| `slidev` | [slidevjs/slidev](https://github.com/slidevjs/slidev) | Slidev 官方 skill |
| `doc-coauthoring` | [anthropics/skills](https://github.com/anthropics/skills) | 文档协作工作流 |
| `docx` | [anthropics/skills](https://github.com/anthropics/skills) | Word 文档操作 |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills) | 前端界面设计 |
| `pptx` | [anthropics/skills](https://github.com/anthropics/skills) | PowerPoint 文件操作 |
| `xlsx` | [anthropics/skills](https://github.com/anthropics/skills) | Excel 电子表格操作 |
| `pdf` | [anthropics/skills](https://github.com/anthropics/skills) | PDF 文件操作 |
| `frontend-skill` | [openai/skills](https://github.com/openai/skills) | 高质量前端页面构建 |

以下 skill 从外部仓库下载，尚未经过适配和验证，放在 `.experimental/` 目录下：

| Skill | 来源 | 说明 |
| --- | --- | --- |
| `doc` | [openai/skills](https://github.com/openai/skills) | Word 文档读写（python-docx） |
| `gh-address-comments` | [openai/skills](https://github.com/openai/skills) | 处理 GitHub PR 评论 |
| `gh-fix-ci` | [openai/skills](https://github.com/openai/skills) | 修复 GitHub CI 失败 |
| `jupyter-notebook` | [openai/skills](https://github.com/openai/skills) | Jupyter Notebook 创建与编辑 |
| `screenshot` | [openai/skills](https://github.com/openai/skills) | 桌面截图 |
| `slides` | [openai/skills](https://github.com/openai/skills) | 代码驱动的幻灯片制作 |
| `diagnose` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 困难 bug 与性能回归诊断流程 |
| `grill-with-docs` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 结合项目文档压力测试计划 |
| `triage` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 基于状态机的问题分诊流程 |
| `improve-codebase-architecture` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 识别并改进代码库架构机会 |
| `setup-matt-pocock-skills` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 初始化 Matt Pocock 工程 skills 项目上下文 |
| `tdd` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 红绿重构测试驱动开发流程 |
| `to-issues` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 将计划拆分为可执行 issue |
| `to-prd` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 根据上下文生成 PRD |
| `zoom-out` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 从更高层次理解代码上下文 |
| `caveman` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 超压缩沟通模式 |
| `grill-me` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 通过连续追问压力测试方案 |
| `write-a-skill` | [smll-ai/mattpocock-skills](https://github.com/smll-ai/mattpocock-skills) | 创建结构化 agent skill |<!-- skills-table:end -->

此外，`skills/.legacy/` 目录下存放已弃用的 skill，仅作归档保留。

### 外部 Skill 的适配规则

来自外部仓库的 skill（标有来源链接的条目）会做以下适配，使其不绑定特定产品：

1. **去品牌化** — 将 `Claude`、`artifacts` 等产品专属概念替换为通用表述（如 `agent`、文件操作）；删除 `claude.ai` 等产品链接。
2. **统一依赖管理** — `python scripts/...` 改为 `uv run scripts/...`；`pip install X` 改为 `uv run --with X`。

### 嫁接记录与本机安装记录

`grafted-skills.json` 记录的是外部 skill 的**上游来源**，用于回看、同步或对比上游版本。其中 `path` 是 skill 在上游仓库中的路径，不表示它在本仓库里的落点；本仓实际位置以 README 表格和 `skills/` 目录为准。

来源尚未确认时，宁可暂时留空，也不要猜测填值。

`skills-lock.json` 是本机安装状态，由 `skills` CLI 这类安装工具维护，记录当前机器安装过哪些 skill。它和 `grafted-skills.json` 不是同一类文件：前者管本机安装，后者管本仓嫁接来源。

## 安装

### 方式一：克隆 + 软链接（推荐）

```bash
git clone https://github.com/TMYTiMidlY/skills.git <repo>
```

以 `.agents/skills/` 作为唯一的 skill 源，将需要的 skill 链接进去。全局安装就放在 `~/` 下，项目级安装就放在项目根目录下。skill 按类别分布在三个位置，按来源链接：

```bash
mkdir -p .agents/skills

# 原创：skills/.curated/
ln -s <repo>/skills/.curated/<skill-name> .agents/skills/

# 嫁接（已人工审核过）：skills/
ln -s <repo>/skills/<skill-name> .agents/skills/

# 实验性（未人工审核）：skills/.experimental/
ln -s <repo>/skills/.experimental/<skill-name> .agents/skills/
```

GitHub Copilot、Gemini CLI、Codex、Cline、Warp、Windsurf、Roo Code 等工具原生读取 `.agents/skills/`，无需额外配置。其他工具需要将各自的 skills 目录链接到 `.agents/skills/`：

| 工具 | 自有 skills 目录 | 链接命令 |
| --- | --- | --- |
| Claude Code | `.claude/skills/` | `ln -s ../.agents/skills .claude/skills` |
| Cursor | `.cursor/skills/` | `ln -s ../.agents/skills .cursor/skills` |
| Amp | `.config/agents/skills/` | `ln -s ../../.agents/skills .config/agents/skills` |
| Goose | `.config/goose/skills/` | `ln -s ../../.agents/skills .config/goose/skills` |
| Junie | `.junie/skills/` | `ln -s ../.agents/skills .junie/skills` |
| Kiro CLI | `.kiro/skills/` | `ln -s ../.agents/skills .kiro/skills` |

其他工具同理，将其 skills 目录链接到 `.agents/skills/` 即可。

**软链接注意事项：**

- 链接到 skill **目录本身**而非内部单个文件，否则相对引用会断裂。
- 同名目录已存在时先删除再建链接，否则 `ln -s` 会建到子目录里。
- symlink 的目标相对路径按**链接所在目录**解析；不确定层级时可改用绝对路径。

由于软链接直接指向仓库中的文件，对仓库的任何修改都会即时反映到所有链接位置，无需重新安装或手动同步。日常维护只需在仓库目录中编辑、用 `git pull` 拉取更新即可。

**同步规则：**穿透 symlink 对 skill 目录**内部**的读写会落到仓库实体、被 git 跟踪；在工具侧 skills 目录新建的**非 symlink** 条目只活在本地、不进仓库。判断：`readlink -f <path>` 看终点是否落在仓库内。

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

原创 skill 使用 MIT License，每个目录下附 `LICENSE.txt`。嫁接 skill 的许可证沿用上游，请查看对应目录中的 `LICENSE` 或 `LICENSE.txt`。
