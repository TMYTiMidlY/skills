# Skills

面向 AI 编程助手（Claude Code / GitHub Copilot 等）的实用技能包合集。安装后，AI 能直接处理 Office 文档、PDF、前端页面设计、服务器运维等日常任务。

## 可用的 Skills

### 原创（MIT License，放在 `skills/.curated/` 下）

| Skill | 说明 |
| --- | --- |
| `manage-skills` | 创建、安装、重构、审查和合并本地 skill 的规范与工作流 |
| `harness` | Coding agent runtime 的工具注入、配置发现、会话存储与程序化编排 |
| `git` | Git/jj 提交与历史、隔离工作区、受限网络获取、发版 CI 与 forge/静态站 |
| `software` | 本地软件、CLI 与自托管服务：终端和包管理工具、数据库、对象存储、Docker/PaaS、Overleaf、文档处理与桌面系统排障 |
| `io` | 沿内存、文件系统、挂载、介质和网络块存储定位 I/O 与换页瓶颈 |
| `network` | OpenWrt 设备、外部 Wi-Fi 接入本地网络、客户端代理、泄漏防护、远程接入及 WSL/远端网络管道 |
| `vps-maintenance` | VPS 初始化、安全加固、网络质量检查、反向代理与基础服务部署 |
| `docker-maintenance` | 受限 Docker 容器的环境探测、只读挂载处理、工具安装与无浏览器认证 |
| `docs-writer` | 中文论文、docx 汇报和演示文稿的写作修订、引用核查与配图管理 |
| `mess` | 按症状检索并沉淀疑难杂症的复现、根因与可靠解法 |
| `plan` | 面向其他智能体或执行者的自包含、分步可验证正式实施方案 |
| `dredge-up` | 会话收尾与交接盘点，核对状态并找回压栈遗漏的承诺 |
| `browser-use` | 网页自动化、登录态复用、受保护文件下载与嵌入数据提取 |
| `reversing` | 移动端 App/游戏的静态逆向、规则还原与设备侧数据取证 |
| `wechat-clawbot` | OpeniLink Hub 微信消息、事件接收及 Bot/App 权限管理 |

### 嫁接自其他仓库

| Skill | 来源 | 说明 |
| --- | --- | --- |
| `qiuzhi-skill-creator` | [秋芝2046](https://space.bilibili.com/385670211) | 交互式引导创建新的 skill |
| `upstream` | [NightGlow0826](https://github.com/NightGlow0826) | 把本地取证压缩成 handoff 交给网页版 Pro 模型做深度规划 / 架构评审，回来后本地继续执行与验证 |<!-- skills-table:begin -->
| `slidev` | [slidevjs/slidev](https://github.com/slidevjs/slidev) | Slidev 官方 skill |
| `doc-coauthoring` | [anthropics/skills](https://github.com/anthropics/skills) | 文档协作工作流 |
| `docx` | [anthropics/skills](https://github.com/anthropics/skills) | Word 文档操作 |
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills) | 前端界面设计 |
| `pptx` | [anthropics/skills](https://github.com/anthropics/skills) | PowerPoint 文件操作 |
| `xlsx` | [anthropics/skills](https://github.com/anthropics/skills) | Excel 电子表格操作 |
| `pdf` | [anthropics/skills](https://github.com/anthropics/skills) | PDF 文件操作 |
| `frontend-skill` | [openai/skills](https://github.com/openai/skills) | 高质量前端页面构建 |
| `grill-with-docs` | [mattpocock/skills](https://github.com/mattpocock/skills) | 结合项目文档压力测试计划 |
| `grill-me` | [mattpocock/skills](https://github.com/mattpocock/skills) | 通过连续追问压力测试方案 |
| `ppt-master` | [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) | AI 多角色协作生成原生可编辑 PPTX，并创建/复用 Brand、Style、Layout、Deck 模板或填充/增强现有 PPTX |
| `handoff` | [mattpocock/skills](https://github.com/mattpocock/skills) | 把当前对话压缩成 handoff 文档，便于另一个 agent 接手；自动建议下一步可用 skill、去除敏感信息、保存到临时目录 |
| `prototype` | [mattpocock/skills](https://github.com/mattpocock/skills) | 构建可丢弃的原型快速打磨设计：分"可运行 terminal app"（验证状态/业务逻辑）与"多套 UI 变体可切换路由"两条路线 |

以下 skill 从外部仓库下载，尚未经过适配和验证，放在 `.experimental/` 目录下：

| Skill | 来源 | 说明 |
| --- | --- | --- |
| `doc` | [openai/skills](https://github.com/openai/skills) | Word 文档读写（python-docx） |
| `gh-address-comments` | [openai/skills](https://github.com/openai/skills) | 处理 GitHub PR 评论 |
| `gh-fix-ci` | [openai/skills](https://github.com/openai/skills) | 修复 GitHub CI 失败 |
| `jupyter-notebook` | [openai/skills](https://github.com/openai/skills) | Jupyter Notebook 创建与编辑 |
| `screenshot` | [openai/skills](https://github.com/openai/skills) | 桌面截图 |
| `slides` | [openai/skills](https://github.com/openai/skills) | 代码驱动的幻灯片制作 |
| `diagnose` | [mattpocock/skills](https://github.com/mattpocock/skills) | 困难 bug 与性能回归诊断流程 |
| `triage` | [mattpocock/skills](https://github.com/mattpocock/skills) | 基于状态机的问题分诊流程 |
| `improve-codebase-architecture` | [mattpocock/skills](https://github.com/mattpocock/skills) | 识别并改进代码库架构机会 |
| `setup-matt-pocock-skills` | [mattpocock/skills](https://github.com/mattpocock/skills) | 初始化 Matt Pocock 工程 skills 项目上下文 |
| `tdd` | [mattpocock/skills](https://github.com/mattpocock/skills) | 红绿重构测试驱动开发流程 |
| `to-issues` | [mattpocock/skills](https://github.com/mattpocock/skills) | 将计划拆分为可执行 issue |
| `to-prd` | [mattpocock/skills](https://github.com/mattpocock/skills) | 根据上下文生成 PRD |
| `zoom-out` | [mattpocock/skills](https://github.com/mattpocock/skills) | 从更高层次理解代码上下文 |
| `caveman` | [mattpocock/skills](https://github.com/mattpocock/skills) | 超压缩沟通模式 |
| `write-a-skill` | [mattpocock/skills](https://github.com/mattpocock/skills) | 创建结构化 agent skill |
| `humanizer-zh` | [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh) | 去除中文文本中的 AI 生成痕迹（Humanizer 汉化版） |
| `ponytail/ponytail` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 让 agent 当“最懒的资深工程师”：写代码前过 YAGNI→复用→stdlib→原生→一行的阶梯，只写能跑的最少代码；支持 lite/full/ultra 强度 |
| `ponytail/ponytail-review` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 只审过度工程的代码评审：对 diff 逐条标出可删/stdlib/原生/YAGNI/可缩短，结尾给可省行数 |
| `ponytail/ponytail-audit` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 整仓过度工程审计：同 review 的标签体系，扫全代码库而非 diff，按可删量排序 |
| `ponytail/ponytail-debt` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 把代码里的 ponytail: 注释汇成技术债台账，标出没写升级触发条件的条目 |
| `ponytail/ponytail-gain` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 展示 ponytail 的 benchmark 中位数战绩（更少代码/成本、更快）的 ASCII 记分牌 |
| `ponytail/ponytail-help` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | ponytail 各模式/命令的速查卡 |
| `superpowers/brainstorming` | [obra/superpowers](https://github.com/obra/superpowers) | 创造性工作前先对话式挖需求和设计，产出获批准的方案后再开始实现 |
| `superpowers/dispatching-parallel-agents` | [obra/superpowers](https://github.com/obra/superpowers) | 把 2 个以上无共享状态、无顺序依赖的独立任务派发给隔离上下文的子 agent 并行执行 |
| `superpowers/executing-plans` | [obra/superpowers](https://github.com/obra/superpowers) | 在独立会话中执行一份已写好的实施计划，含审阅检查点 |
| `superpowers/finishing-a-development-branch` | [obra/superpowers](https://github.com/obra/superpowers) | 开发完成、测试通过后，给出合并/PR/清理等收尾方式的结构化选项 |
| `superpowers/receiving-code-review` | [obra/superpowers](https://github.com/obra/superpowers) | 收到代码评审意见时要求先做技术核实，不表演性认同或盲目照做 |
| `superpowers/requesting-code-review` | [obra/superpowers](https://github.com/obra/superpowers) | 派发代码评审子 agent，用精心构造的独立上下文评估工作产出而非过程 |
| `superpowers/subagent-driven-development` | [obra/superpowers](https://github.com/obra/superpowers) | 按实施计划逐任务派发全新实现子 agent，每个任务后接一次评审，分支收尾前再做一次整体评审 |
| `superpowers/systematic-debugging` | [obra/superpowers](https://github.com/obra/superpowers) | 遇到任何 bug/测试失败/异常行为时，先系统定位根因再提修复方案，不做随手补丁 |
| `superpowers/test-driven-development` | [obra/superpowers](https://github.com/obra/superpowers) | 先写测试、看它失败，再写能让测试通过的最少实现代码 |
| `superpowers/using-git-worktrees` | [obra/superpowers](https://github.com/obra/superpowers) | 开始需要隔离的功能开发前，优先用平台原生 worktree 工具，没有时降级到手动 git worktree |
| `superpowers/using-superpowers` | [obra/superpowers](https://github.com/obra/superpowers) | 对话开始时的强制入口：规定如何发现和调用 skill，要求任何回复（含澄清提问）前先完成 skill 调用 |
| `superpowers/verification-before-completion` | [obra/superpowers](https://github.com/obra/superpowers) | 声称工作完成/已修复/测试通过前，要求先跑验证命令并确认输出，证据先于断言 |
| `superpowers/writing-plans` | [obra/superpowers](https://github.com/obra/superpowers) | 已有 spec 或需求、动手写代码前，写一份假设工程师零上下文的完整实施计划 |
| `superpowers/writing-skills` | [obra/superpowers](https://github.com/obra/superpowers) | 编写/编辑/验证新 skill 的方法论：把写 skill 本身当作对流程文档做 TDD |
| `worktrunk/worktrunk` | [max-sixty/worktrunk](https://github.com/max-sixty/worktrunk) | worktrunk（`wt` CLI）的配置与排障：用户配置 vs 项目配置的权限边界、10 种 hook 选型、LLM commit message 接外部命令，reference/ 是 worktrunk.dev 文档的同步副本 |
| `worktrunk/wt-switch-create` | [max-sixty/worktrunk](https://github.com/max-sixty/worktrunk) | 以「建 worktree 并把本会话切进去」开启一次任务：分支名/仓库路径/任务三段参数的解析规则，以及宿主原生入口与 `wt` 命令两条创建路径的取舍 |
| `ax` | [yusukebe/ax](https://github.com/yusukebe/ax) | ax CLI —— 抓取网页并抽取结构化数据，替代 curl + 一次性解析脚本 |<!-- skills-table:end -->

`ponytail/`、`superpowers/` 和 `worktrunk/` 与上面其他条目不同：上游本身是一个打包了多个 skill 的仓库（分别是 6 个、14 个和 2 个），不是单一能力，所以嫁接时多套了一层以仓库名命名的目录，保留归属、也不与本仓已有的同类 skill（如 `tdd`、`git`、`diagnose`）合并或去重。前两者还有一点相似：都不满足于"等用户调用"，而是各自想办法让自己在没人主动喊它时也生效——`ponytail` 靠 Claude Code/Codex 等宿主的生命周期 hook 在每次会话/每条消息注入规则；`superpowers` 的 `using-superpowers` 则是在 skill 正文里直接写死"对话开始时必须先调用本 skill，包括在回答任何澄清性提问之前"。两种"强迫生效"的实现层级不同（前者是宿主机制，后者是文档层面的自我指令），但目的一致。`worktrunk/` 则是另一类：它是某个 CLI 工具（`wt`）随仓库分发的官方配套 skill，正文假定该二进制已装好，`reference/` 直接同步自其文档站。

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

## 链接检查（pre-commit + lychee）

仓库里的 skill 文档含大量外链，用 [pre-commit](https://pre-commit.com) 框架挂了一个 [lychee](https://github.com/lycheeverse/lychee)（Rust 写的异步链接检查器）hook，在提交前自动检查改动到的 markdown 里链接是否失效。配置见根目录 `.pre-commit-config.yaml`。

pre-commit 是一个管理 git hook 的框架：按 `.pre-commit-config.yaml` 把每个 hook 克隆进隔离缓存（`~/.cache/pre-commit/`）、各自建运行环境、版本锁定在 `rev`，不污染项目与系统。lychee 这个 hook 跑的是自动下载的预编译二进制，无需 Node / cargo / Docker。

启用（一次性）：

```bash
uv tool install pre-commit   # 或 pixi global install pre-commit / brew install pre-commit
pre-commit install           # 写入 .git/hooks/pre-commit
```

装好后每次 `git commit` 会自动对暂存的 markdown 跑 lychee，发现失效链接就阻止提交。手动全量检查：

```bash
pre-commit run lychee --all-files
```

几点提醒：

- lychee 默认排除 `example.com` 等示例域名与保留 TLD（如 `.invalid`），这是特性不是漏检。
- 文档里 github.com 链接多时，`export GITHUB_TOKEN=<无权限 PAT>` 可抬高限额、避免限流。
- 升级 hook 版本用 `pre-commit autoupdate`（会改写 `.pre-commit-config.yaml` 里的 `rev`）。

## AGENTS.md

[AGENTS.md](AGENTS.md) 是一份通用的 AI agent 行为规则，涵盖 Python 环境选择、Git 操作约束、工具使用习惯等偏好设置。适用于 Claude Code、GitHub Copilot 等支持 `AGENTS.md` / `CLAUDE.md` 的工具。

如需让 Claude Code 也读取同一份规则：

```bash
ln -s AGENTS.md CLAUDE.md
```

## 许可

原创 skill 使用 MIT License，每个目录下附 `LICENSE.txt`。嫁接 skill 的许可证沿用上游，请查看对应目录中的 `LICENSE` 或 `LICENSE.txt`。
