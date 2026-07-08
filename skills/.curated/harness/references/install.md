# 三大 coding agent 的安装与分发形态（Codex / Claude Code / Copilot CLI）

新手常见的两个困惑，其实是同一件事的两面：

1. **"这三个 AI CLI 都能 `npm install` 装，那它们是不是就是个 JS 小壳、套壳调 API？"**
2. **"既然听说 Claude Code 是用 Bun 编译成独立单文件的，为什么官方又说 npm 安装已弃用（deprecated）？不矛盾吗？"**

根子都在一件事：**它们的"真身"是预编译好的原生程序（native binary，直接由 CPU 执行的机器码，不是要先装 Node 才跑的 JS），npm 只是被借来当"跨平台安装器"。** 你 `npm install` 到的那个包确实只是几 KB 的空壳——"套壳"的直觉没错，只是套的不是 JS 逻辑，而是一层安装器外壳。

这个"壳包 + 平台子包"的**通用打包模式**（`optionalDependencies` + `os`/`cpu`/`libc` 门控、只下匹配平台的那份、musl 分叉当"真身是原生程序"的判据等）属于包管理器话题，讲在 software skill 的 [package-managers.md 第八节](../../software/references/package-managers.md)。**本篇只做三家 coding agent 的具体普查**：各自怎么打包、用什么工具链编、有哪些安装入口、npm "软弃用"到什么程度、采用度如何。Copilot 本体运行时（`npm-loader → index → app.js` 三层进程模型、逆向、补丁）见 [copilot-cli.md](copilot-cli.md)。

> 下面所有版本号 / 体积 / 下载量都是**某次快照**（核对于 2026-07，用 `npm view` / 官方 README / HN Algolia API 实测）。这些包每周都在变、体积还在涨，引用前请自己复核。

## 一、三家打包形态普查（`npm view` 实测）

| | 壳包（`npm i -g` 装的那个） | 壳包 `bin` | 平台二进制子包 | 子包个数 / 是否含 musl | 真身工具链 |
| --- | --- | --- | --- | --- | --- |
| **Codex** | `@openai/codex` | `bin/codex.js` | `@openai/codex@<ver>-<platform>`（用 npm alias 引的**版本变体**） | **6 个，无 musl** | **Rust**（`openai/codex`，Apache-2.0 开源） |
| **Claude Code** | `@anthropic-ai/claude-code` | `bin/claude.exe` | `@anthropic-ai/claude-code-<platform>`（独立命名子包） | **8 个，含 musl** | **Bun `--compile` 单文件**（闭源） |
| **Copilot CLI** | `@github/copilot` | `npm-loader.js` | `@github/copilot-<platform>`（独立命名子包；壳另依赖 `detect-libc`） | **8 个，含 musl** | **Node SEA 单文件**（闭源） |

**体积（量级，别钉死）**：三家的壳都很小（codex ~9.7 KB、copilot ~13 KB、claude-code ~150 KB@2.1.195），平台子包都是**数百 MB**、且**随版本一路上涨**——实测区间约 230–350 MiB，例如 codex 的 linux-x64 从 0.142.4 的 ~279 MiB 到 0.143.0 已涨到 ~333 MiB。所以"壳几 KB / 真身几百 MB"这个**量级差**是稳的，但具体数字每个版本都不一样，引用要连版本一起说。

### libc 分叉：三家并不一致（一个曾写错的点，已订正）

**libc 是 Linux 上最底层的 C 标准库**：主流发行版（Ubuntu / Debian…）用 `glibc`，轻量的 Alpine 用 `musl`，二者不通用。三家处理方式**不同**：

- **Claude Code、Copilot**：为 Linux **同时发 glibc 和 musl 两套** npm 子包（`…-linux-x64` vs `…-linux-x64-musl` / `…-linuxmusl-x64`，实测 `libc=["glibc"]` 对 `libc=["musl"]`），各 8 个平台子包。
- **Codex 例外**：npm 上**只有 6 个平台子包、不含 musl 变体**，其 linux 子包连 `libc` 字段都不声明（实测只有 `os`/`cpu`）。它的 Linux 版是**一个静态链接 musl 的二进制**（GitHub Release 资产 `codex-x86_64-unknown-linux-musl.tar.gz`）——**静态链接后天然能同时跑在 glibc 和 musl 系统上，所以压根不需要分叉**。

> 由此得到一条更准的判据：**"发了 glibc/musl 两套" ⇒ 几乎肯定是原生二进制**（纯 JS 不挑 libc）；但**反过来不成立**——"只发一个 musl 版"也可能是原生程序（静态链接通吃），codex 就是这种。

### 各家真身工具链的判据（Sonnet 5 下载二进制实测确认）

- **Codex = Rust**：`openai/codex` 真开源（Apache-2.0，仓库 `codex-rs/`，语言统计 Rust 占大头），Release 资产名 `codex-x86_64-unknown-linux-musl` 是 Rust 的 target triple（"CPU-厂商-操作系统-libc" 的编译目标命名）。
- **Claude Code = Bun 编成的单文件**：平台二进制里含 `oven-sh/bun` / `oven-sh/webkit` 字面量与 `JSC::DFG::`（JavaScriptCore JIT）符号、**零 V8/Node 标记**。Bun `--compile` 会把 JS 连同 Bun 运行时打进一个自包含可执行文件。⚠️ 注意壳包字段 `bin/claude.exe` 只是 npm 侧的入口占位路径，**别拿这个 `.exe` 命名本身当 Bun 铁证**，真正的证据在平台二进制内容里。
- **Copilot = Node SEA**：平台二进制里含 `../src/node_sea.cc` 与大量 `node::` / `v8::` 符号，指向 **Node.js 官方的 SEA（Single Executable Application，把 Node 运行时 + 脚本打成单文件）**，而非 Bun——与 Claude Code 正相反。这也和 [copilot-cli.md](copilot-cli.md) 记的"官方分发 SEA 二进制"一致。

## 二、安装方案：四条路，npm 已退居二线（照官方 README 核对）

真身既是不依赖 Node 的原生程序，厂商现在都**主推"脚本直装 / Homebrew / winget"直接拉二进制**，`npm` 多作兜底 / 兼容入口：

| | 脚本直装（官方首推） | Homebrew | winget | npm |
| --- | --- | --- | --- | --- |
| **Codex** | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh`；Win：`powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 \| iex"` | `brew install --cask codex` | — | `npm i -g @openai/codex` |
| **Claude Code** | `curl -fsSL https://claude.ai/install.sh \| bash`；Win：`irm https://claude.ai/install.ps1 \| iex` | `brew install --cask claude-code` | `winget install Anthropic.ClaudeCode` | `npm i -g @anthropic-ai/claude-code`（README 标 "Deprecated"） |
| **Copilot CLI** | `curl -fsSL https://gh.io/copilot-install \| bash`（支持 `PREFIX` / `VERSION` 环境变量） | `brew install copilot-cli`（注意**无** `--cask`） | `winget install GitHub.Copilot` | `npm i -g @github/copilot` |

- 三家也都在 **GitHub Releases** 直挂各平台二进制供手动下载。
- **各家把 npm 摆的位置略不同**：Codex README 的包管理器区把 `npm` 列在 Homebrew **之前**（npm 是与 brew 并列的选项，不算"最末兜底"）；Claude Code 明确把 npm 标为 Deprecated；Copilot 三条并列。
- 这些工具本身就是"自带升级、不依赖任何运行时的独立原生程序"，用官方脚本 / brew 一步装好最省事（还免去先装 Node）——这正是"能进包管理器就优先包管理器"这条通则的**边界情形**（见 [package-managers.md 第七节](../../software/references/package-managers.md)）。

## 三、npm "软弃用"（soft deprecation）：文档说别用，技术上照用

Claude Code 的 README 白纸黑字写着 *"Installation via npm is deprecated. Use one of the recommended methods below."*，但：

- **registry 层没有真弃用标记**：`npm view @anthropic-ai/claude-code deprecated` 返回**空**，packument JSON 里也没有 `deprecated` 字段；`npm i -g` 照装、能用、**不弹任何弃用警告**。
- 这就是**软弃用**：只在文档里劝导迁移，却不动 registry 标记，以免砸掉海量还写着 `npm i -g` 的老教程和 CI 脚本（它 npm 周下载量至今仍上千万）。

**解开开头那个"矛盾"（编译成单文件 ⇒ 才敢弃用 npm）**——这是因果，不是自相矛盾：

1. 先用 Bun `--compile` 把它做成**不依赖 Node 的自包含单文件**（"Bun"两个角色别混：`bun build` ＝ 把多个 TS/JS 打包成一个 JS；`bun build --compile` ＝ 再把那个 JS 连同 Bun 运行时编成一个原生可执行文件）。
2. 既然连 Node 都不需要了，就没必要非走 Node 生态的 npm。
3. 所以**单文件化是"因"、弱化 npm 渠道是"果"**，两步顺承。npm 全程只是"快递盒 / 安装入口"，从不是驱动它运行的发动机。

> **旁证**：2026-03 "Claude Code 源码泄露"（[复盘](https://alex000kim.com/posts/2026-03-31-claude-code-source-leak/)）——**疑似**因为它的 npm 包附带了 source map（源码映射文件，本用于把压缩后的代码还原回可读源码），把编译进二进制里的那份 JS 逻辑还原了出来（原文对根因留了保留、指向 Bun issue `oven-sh/bun#28001`，此处不下死结论）。无论细节如何，它印证了"**外壳是原生二进制、芯子里其实是 JS 逻辑**"这一点——两者本就并存，不矛盾。第三方分析，非官方。

## 四、采用度快照（agent 侧，2026-06-29 … 07-05）

npm 周下载量（`api.npmjs.org/downloads`）：

| agent 包 | 周下载量 |
| --- | --- |
| `@anthropic-ai/claude-code` | ~10.95 M |
| `@openai/codex` | ~10.40 M |
| `@github/copilot` | ~1.02 M |

- **只是快照、名次周周变**：仅一周前 Codex 还以 ~13.4 M 领先、反超 Claude；近月 Codex 在 **9.7 M–13.4 M** 间大幅摆动，与 Claude Code（较稳的 10–12 M）的相对排名并不稳定——别把某一周的名次当定论。
- **agent 的 npm 下载量本身低估真实使用**：官方现在主推 curl 脚本 / brew / winget，很多安装根本不经 npm registry。
- pnpm / yarn / bun 等**包管理器客户端**自身的采用度与社区风向，属包管理器话题，见 [package-managers.md 第五节](../../software/references/package-managers.md)。

## 相关

- **通用打包模式**（"壳包 + 平台二进制"：`optionalDependencies`、`os`/`cpu`/`libc` 门控、musl 分叉判据、esbuild / swc / biome / turbo 等泛例）：[package-managers.md 第八节](../../software/references/package-managers.md)。
- **Copilot CLI 本体运行时**（三层进程模型、逆向读 `app.js`、补丁脚本）：[copilot-cli.md](copilot-cli.md)。
- 三家**开源 / 闭源与逆向**差异、worktree 支持对照：本 skill [SKILL.md](../SKILL.md) 与 [worktree.md](worktree.md)。
