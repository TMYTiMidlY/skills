# Skills 与通用指令的安装维护

安装、维护或卸载本仓 skills，以及配置 `AGENTS.md` 等主指令入口时读取本文件。`<repo>` 表示实际 skills 仓库根目录，`<target>` 表示本次目标家目录或项目根目录；结合用户已说明的范围确定，未明确的关键范围再询问。

## <a id="environment-discovery"></a>环境探测

每次调用都重新探测，先读取环境与现有入口，再决定写入位置。用户级安装检查当前用户的工具配置根；项目级安装检查目标项目已有的工具目录。可执行文件、启动脚本和运行进程可帮助确认工具与配置根，实际入口以对应进程或启动方式使用的配置为准。

- 自动接入只处理已经存在的工具配置根。某个工具目录不存在时，跳过它的兼容入口并报告；用户明确要求初始化该工具时，才创建所需工具目录。共享 `.agents/` 是本仓安装目标，其存在本身不证明任何特定 harness 已安装。
- 项目级安装按项目已有入口处理；用户级发现结果用于说明本机有哪些工具，不据此向每个项目扩散工具目录。
- 读取 `CODEX_HOME`、`DSH_HOME`、`DSH_AGENTS_HOME`、`CLAUDE_CONFIG_DIR`、`COPILOT_HOME`、`PI_CODING_AGENT_DIR` 等适用覆盖，识别隔离的 `HOME` 与自定义配置根。只查看完成定位所需的配置，不回显认证材料。
- Codex 除默认配置根外，还要核对用户实际使用的账号入口。已初始化的独立目录可能来自启动函数、脚本或 `.cc-switch-launches`；逐个确认对应配置和用途，再检查主文件。共享 `config.toml` 与会话目录不会自动补齐主指令。
- 对每个候选入口使用能识别失效链接的检查，同时核对链接目标、文件类型、可读性和现有内容。工具目录整体是链接时，先确认真实落点，防止在链接内部再建同名子链接。

将发现结果分为已接入、缺少入口、失效链接、存在冲突、未发现工具配置根。新工具以后生成配置目录后，再次调用本 skill 即可重新发现并补齐；本流程在调用时运行。

## <a id="installation-plan"></a>安装范围与差异处理

以用户选定的 skills、目标范围和已有安装为准，分别计算共享 skills、工具兼容目录和主指令入口的差异。用户请求安装或维护时，缺少的授权范围内入口可直接补齐；只咨询或审查时保持只读。

| 现有状态 | 处理 |
| --- | --- |
| 目标缺失，所属工具配置根已存在 | 创建本次所需的链接或下级目录 |
| 链接正确且目标可读 | 保持现状，报告已就绪 |
| 失效链接能核实属于本仓既有安装 | 按删除规则回收旧链接，再按当前源路径重建 |
| 目标是普通文件、已有非链接目录，或指向其他来源 | 保留内容，说明差异并确认迁移或替换范围；其他独立事项继续处理 |
| 同名 skill 或同能力的另一实现已存在 | 说明来源与差异，由用户决定保留哪份 |
| 工具配置根未发现 | 跳过该工具的兼容入口，报告跳过原因 |

维护调用沿用已安装、已选定的 skills，并补齐新发现工具所需的入口；按用户要求扩展或缩小范围。安装共享 skills 与通用主指令分别核对：请求两者时都完成，只请求其中一项时按该项执行。

## <a id="skills-discovery"></a>Skills 目录与安装

源文件按实际仓库位置选择，链接整个 skill 目录，保留其相对引用：

| 来源 | 源路径 |
| --- | --- |
| 原创 | `<repo>/skills/.curated/<name>` |
| 嫁接且已审核 | `<repo>/skills/<name>` |
| 实验性、未审核 | `<repo>/skills/.experimental/<name>` |

先将选定 skill 安装到 `<target>/.agents/skills/<name>`。确认目标缺失后，示例命令为：

```bash
mkdir -p "<target>/.agents/skills"
ln -s "<源 skill 目录的绝对路径>" "<target>/.agents/skills/<name>"
```

下表是本地运行、默认配置下的已核对发现范围；项目级向上查找的边界与同名冲突处理仍按各工具实现。只为已经探测到的工具选择对应操作。

| Harness | 用户级 `~/.agents/skills/` | 项目级 `.agents/skills/` |
| --- | --- | --- |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/skill/skill-filesystem/README.zh.md#L29-L67) | 是 | 是 |
| [Codex](https://learn.chatgpt.com/docs/build-skills) | 是 | 是 |
| [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) | 是 | 是 |
| [Gemini CLI](https://geminicli.com/docs/cli/skills/) | 是 | 是 |
| [Cursor](https://cursor.com/docs/skills) | 是 | 是 |
| [Amp](https://ampcode.com/docs/customize/skills) | 是 | 是 |
| [pi](https://github.com/earendil-works/pi/blob/8479bd8/packages/coding-agent/src/core/skills.ts#L295-L306) | 是 | 是 |
| [Cline](https://github.com/cline/cline/blob/f817e59f698f01487920c00ede2dbecad5c0fa50/apps/vscode/src/core/storage/skill-directories.ts#L1-L41) | 是 | 是 |
| [Warp](https://docs.warp.dev/agents/capabilities/skills) | 是 | 是 |
| [Windsurf / Cascade](https://docs.windsurf.com/windsurf/cascade/skills) | 是 | 是 |
| [Roo Code](https://docs.roocode.com/features/skills) | 是 | 是 |
| [Claude Code](https://code.claude.com/docs/en/skills#choose-where-skills-load) | 使用 `~/.claude/skills/` | 使用 `.claude/skills/` |

原生读取共享目录的工具直接使用已安装的 skills。Claude Code 等使用自有目录的工具，在其配置根已存在且目标缺失时，将自有 skills 目录链接到相应共享目录。例如用户级 Claude Code：

```bash
ln -s ../.agents/skills "$HOME/.claude/skills"
```

其他已知的自有安装入口如下。操作前按所用版本核对原生共享发现能力，已有共享支持时优先使用共享目录。

| 工具 | 用户级兼容目录 | 项目级兼容目录 |
| --- | --- | --- |
| Goose | `~/.config/goose/skills/` | `.goose/skills/` |
| Junie | `~/.junie/skills/` | `.junie/skills/` |
| [Kiro CLI](https://kiro.dev/docs/skills/) | `~/.kiro/skills/` | `.kiro/skills/` |

> Goose、Junie 的目录见 [`skills` CLI 的工具映射](https://github.com/vercel-labs/skills/blob/cc5fb50a1b3235bc30c330fa03471d5b2c69363b/src/agents.ts#L379-L431)，用于选择兼容安装位置。Hermes 使用专门的 skill 安装与外部目录机制，转由 `harness` skill 核对其当前行为。

同名目录已存在时，先清点内容并处理差异，再决定整体链接或保留工具内的独立安装。相对链接按链接所在目录解析；不确定时使用绝对路径。项目级 Copilot CLI 使用 `.github/skills`、`.agents/skills` 或 `.claude/skills`，个人级 `~/.copilot/skills` 的路径不照搬为项目入口。

Windows 在本地 NTFS 目录间链接整个 skill 目录时，可在已获准且 symlink 不可用的情况下使用 junction；文件入口仍按文件链接处理：

```powershell
New-Item -ItemType Junction -Path "<target>\.agents\skills\<name>" -Target "<源 skill 目录>"
```

Junction 用于目录挂接，按 `<name>/SKILL.md` 访问会落到实际 skill 目录。网络路径或文件入口按平台支持选择相应链接方式；安装后核对解析结果与可读性。

## <a id="instructions-discovery"></a>主指令入口

Skills 与主指令分别发现。下表的配置根必须先经过[环境探测](#environment-discovery)；其存在才进入自动补齐范围。默认路径以当前进程的用户家目录为准，覆盖变量与实际账号入口优先。

| Harness | 已有配置根的默认位置 | 主指令安装入口 | 原生读取 `~/.agents/AGENTS.md` |
| --- | --- | --- | --- |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L28-L68) | `~/.dsh`，或实际 `DSH_HOME` | `~/.agents/AGENTS.md`，或实际 `DSH_AGENTS_HOME` 下的入口 | 是 |
| [Codex](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/codex-home/src/instructions/mod.rs#L40-L83) | `~/.codex` 和已核实的独立 `CODEX_HOME` | 各实际配置根下的 `AGENTS.md` | 否 |
| [Claude Code 本地 CLI](https://code.claude.com/docs/en/memory#choose-where-to-put-claude-md-files) | `~/.claude`，或实际 `CLAUDE_CONFIG_DIR` | 该根下的 `CLAUDE.md` | 否 |
| [GitHub Copilot CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#custom-instructions-locations) | `~/.copilot`，或实际 `COPILOT_HOME` | 该根下的 `copilot-instructions.md` | 否 |
| [Gemini CLI](https://geminicli.com/docs/cli/gemini-md/) | `~/.gemini` | `~/.gemini/GEMINI.md`，按默认上下文文件名 | 否 |
| [Amp](https://ampcode.com/docs/customize/agents-md) | `~/.config/amp`，或核实的实际配置根 | 该根下的 `AGENTS.md` | 否 |
| [pi](https://github.com/earendil-works/pi/blob/8479bd8/packages/coding-agent/src/core/resource-loader.ts#L67-L120) | `~/.pi/agent`，或实际 `PI_CODING_AGENT_DIR` | 该根下的 `AGENTS.md` | 否 |
| [Cursor](https://cursor.com/docs/rules) | `~/.cursor` 或项目已有的 `.cursor` | 用户规则通过设置管理；项目内可用根目录 `AGENTS.md` | 未列为用户级入口 |

用户级安装通用指令时，将共享主文件链接到 `<repo>/AGENTS.md`；需要兼容入口的已发现工具，再将其主指令文件链接到同一份规则。也可直接链接仓库中的实体。链接前检查原有内容；Codex 非空 `AGENTS.override.md` 的优先级也要核对。

```bash
# 确认共享入口缺失后安装
mkdir -p "$HOME/.agents"
ln -s "<repo>/AGENTS.md" "$HOME/.agents/AGENTS.md"

# 仅当实际 CODEX_HOME 已存在、目标主文件缺失时执行
ln -s "$HOME/.agents/AGENTS.md" "<实际 CODEX_HOME>/AGENTS.md"
```

DSH 共用通用规则时只需共享主文件；`~/.dsh/AGENTS.md` 留给可选的 DSH 专用要求，已有独有内容时保留。项目级安装使用项目实际支持的 `AGENTS.md`、`CLAUDE.md` 等入口；项目已有规则先保留并核对合并范围。仅有项目级入口的工具按项目处理，避免把项目能力描述成全局文件发现能力。

> Claude Code 新版可按设置读取项目级 `AGENTS.md`；用户级兼容安装仍使用上表入口。更深入的配置发现与版本差异由 `harness` skill 维护，安装时按所用版本核实。

> 上表针对本地会话。Claude Cowork 等运行形态对工作目录外链接有额外限制，文件链接与导入边界见[官方共享文件说明](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools)。按实际运行形态验收，用户级入口可用性单独核对。

## <a id="local-instructions"></a>本机补充

本机相关内容统一保存在 `~/.agents/AGENTS.local.md` 普通文件中，由本仓主指令要求模型继续读取。安装时检查其位置与可读性，保留已有内容；确有本机内容需要保存时再创建，维护要求遵循主指令。该文件独立于各工具配置根，仓库根目录与各工具入口均无需另建补充副本或链接。

## <a id="uninstall-repair"></a>卸载与失效链接

卸载只回收用户指定的安装链接，保留仓库实体、工具内的独立安装和其他工具入口。使用当前环境要求的回收站工具；确认目标确属本次卸载范围后，例如：

```bash
trash-put "<target>/.agents/skills/<name>"
```

维护时检查既有共享目录中的链接，即使目标已不存在也要识别到该入口。路径重命名导致的本仓失效链接，核实当前源目录后回收旧入口并重建；来源不明或包含独有内容的目标先保留并确认。

## <a id="validation"></a>验收与报告

- 核对选定 skills 的目录链接、`SKILL.md` 可读性和相对引用；工具侧目录新建的非链接条目只留在该位置，检查真实落点后再判断是否属于仓库维护。
- 分别核对共享 skills、各实际配置根的主文件、override 与本机补充。可用时用 harness 的原生目录或上下文查看功能确认发现结果；将入口已配置、主文件已注入、本地补充已实际读取分别报告。
- 报告本次新增、修复、保持不变、存在冲突和跳过的项目。再次运行时重新探测，仅处理当前差异；已正确的入口保持原样。
- 用户只要求说明安装方法时给出发现结果与操作方案；用户要求执行时完成授权范围内的安装和验证，再报告实际结果。
