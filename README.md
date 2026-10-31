# Skills

面向 AI 编程助手（Claude Code / GitHub Copilot 等）的实用技能包合集。安装后，AI 能直接处理 Office 文档、PDF、前端页面设计、服务器运维等日常任务。

## 可用的 Skills

### 原创（MIT License，放在 `skills/.curated/` 下）

| Skill | 说明 |
| --- | --- |
| `manage-skills` | 创建、安装、维护、重构、审查和合并本地 skills；探测已有 harness，安装或修复 skills 与 AGENTS.md 等指令入口 |
| `harness` | Coding agent 编排框架（harness）知识库：介绍 agent loop、工具注入、配置发现、权限、会话与进程/SDK 接口，以及 model / tool / skill 在 runtime 中的位置；含 Agent Skills 官方规范、跨 harness 加载差异与 Kimi Code `has-sub-skill` 私有扩展 |
| `tool` | Agent tool 的能力边界与执行契约：schema、权限与副作用、错误/重试/取消、CLI / API / MCP adapter；含 Lark CLI 实例 |
| `git` | Git/jj 提交与历史、隔离工作区、受限网络获取、发版 CI 与 forge/静态站 |
| `software` | 本地软件、CLI 与自托管服务：终端和包管理工具、数据库、对象存储、Docker/PaaS、Overleaf、文档处理与 Windows/WSL/macOS/HarmonyOS 环境排障 |
| `io` | 沿内存、文件系统、挂载、介质和网络块存储定位 I/O 与换页瓶颈 |
| `network` | OpenWrt 设备、外部 Wi-Fi 接入本地网络、客户端代理、泄漏防护、WireGuard / EasyTier 组网、远程接入及 WSL/远端网络管道 |
| `vps-maintenance` | VPS 初始化、安全加固、网络质量检查、反向代理与基础服务部署 |
| `docker-maintenance` | 受限 Docker 容器的环境探测、只读挂载处理、工具安装与无浏览器认证 |
| `docs-writer` | 中文论文、docx 汇报和演示文稿的写作修订、引用核查与配图管理 |
| `mess` | 按症状检索并沉淀疑难杂症的复现、根因与可靠解法 |
| `plan` | 面向其他智能体或执行者的自包含、分步可验证正式实施方案 |
| `dredge-up` | 跨工具的会话收尾与交接盘点；确认会话来源，回读原始对话并核对状态，找回遗漏的承诺 |
| `browser-use` | 网页自动化、登录态复用及嵌入数据提取，按任务组合浏览器、直接 HTTP 与文件格式解析工具 |
| `reversing` | 移动端应用、游戏与桌面客户端的逆向取证：规则和数据还原、设备侧取数、原生保护与诊断上报；区分静态能力、配置启用和实际行为 |
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

推荐调用 [manage-skills](skills/.curated/manage-skills/SKILL.md) 完成安装和后续维护。它负责探测本机已有工具，按你选定的范围安装 skills、配置通用指令入口，并核对现有内容与链接。

### 首次使用 manage-skills

```bash
git clone https://github.com/TMYTiMidlY/skills.git "<repo>"
```

将 `<repo>` 换成仓库的实际保存路径。当前助手尚未发现这个 skill 时，可以直接让它读取仓库中的入口并执行，例如：

> 请先读取 `<repo>/skills/.curated/manage-skills/SKILL.md`，用 manage-skills 将 manage-skills、git、harness 安装到用户级共享目录，并为已探测到的 harness 配置通用指令入口。

它会先检查已有工具目录和实际配置根，再决定需要哪些兼容链接；没有发现某个工具目录时会跳过该工具。已有正确链接保持原样，已有独立内容或冲突会先说明并保留。你也可以明确指定项目级范围或其他 skills。

### 后续安装与维护

新装工具、切换账号入口或移动仓库后，再次调用 manage-skills。它会重新探测，只补齐本次发现的缺项、修复可核实的失效链接，并报告新增、保持、冲突和跳过的项目。例如：

> 使用 manage-skills 维护现有用户级安装，重新探测已存在的 harness，补齐缺少的 skills 和主指令入口。

链接直接指向仓库实体，通常拉取仓库更新后即可使用新内容。安装和修复的执行流程、目录映射及验证方法统一维护在 [manage-skills 安装参考](skills/.curated/manage-skills/references/installation.md)。

### <a id="shared-skills"></a>共享 skills 的接入方式

本仓将选定 skills 链接到用户级 `~/.agents/skills/` 或项目级 `.agents/skills/`。DSH、Codex、Copilot CLI、Gemini CLI、Cursor、Amp、pi、Cline、Warp、Windsurf、Roo Code 已有共享目录发现机制；Claude Code 通过自己的 skills 目录接入。具体到所用版本、项目范围和其他工具，由 manage-skills 按[发现范围表](skills/.curated/manage-skills/references/installation.md#skills-discovery)判断。

Skills 和通用指令使用不同的发现规则，安装时需要分别处理，见[共享指令与发现入口](#agent-instructions)。

### 通过 skills CLI 引入 manage-skills

也可以先用 `skills` CLI 安装入口，再调用 manage-skills 完成其余安装与指令配置：

```bash
bunx skills add TMYTiMidlY/skills --list
bunx skills add TMYTiMidlY/skills --skill manage-skills -g
```

`-g` 安装到用户级范围；实际入口与通用指令仍由 manage-skills 检查。

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

## <a id="agent-instructions"></a>共享指令与发现入口

[AGENTS.md](AGENTS.md) 是通用规则的实体文件，[CLAUDE.md](CLAUDE.md) 是它的兼容软链接。调用 manage-skills 安装通用指令时，它会检查已发现工具的实际入口，让各工具复用这一份规则。

### <a id="shared-agent-instructions"></a>共享 AGENTS.md 的支持范围

用户级共享主文件是 `~/.agents/AGENTS.md`。安装时大致会遇到以下情况，完整路径、探测条件与命令由 manage-skills 的[主指令入口表](skills/.curated/manage-skills/references/installation.md#instructions-discovery)维护：

| Harness | 安装时的接入方式 |
| --- | --- |
| DSH | 直接使用共享主文件；DSH 专用文件仅保留独有要求 |
| Codex、Copilot CLI、Gemini CLI、Amp、pi | Skills 可用共享目录，主指令仍需各自入口的兼容链接；Codex 独立账号入口分别检查 |
| Claude Code 本地 CLI | Skills 与主指令都通过自身目录的兼容入口接入 |
| Cursor | Skills 可用共享目录；主指令按用户设置或项目级规则处理 |

manage-skills 只为已发现且在本次范围内的工具补齐所需入口。工具配置目录尚未出现时跳过，之后再次调用即可重新发现；已有主文件、override 和独有规则先核对再处理。

### <a id="local-instructions"></a>本地规则

本机相关内容统一保存为普通文件 `~/.agents/AGENTS.local.md`。仓库根目录保留通用的 `AGENTS.md` 与兼容链接 `CLAUDE.md`；本地补充的实体放在用户家目录。

工具通过上述各自入口加载同一份主规则，主规则再要求模型读取固定的 `~/.agents/AGENTS.local.md`。因此兼容链接用于主指令入口，本地补充只保留这一份普通文件。

本地补充的更新范围、篇幅与组织要求见 [AGENTS.md](AGENTS.md)：保留本机配置与可复用经验，按清楚的主题精炼记录，并优先索引已有文档。

manage-skills 会检查补充文件的位置和可读性，并区分入口已配置、主文件已注入和补充已实际读取，执行细节见[本机补充](skills/.curated/manage-skills/references/installation.md#local-instructions)。

## 许可

原创 skill 使用 MIT License，每个目录下附 `LICENSE.txt`。嫁接 skill 的许可证沿用上游，请查看对应目录中的 `LICENSE` 或 `LICENSE.txt`。
