# Antigravity CLI / Desktop（agy）

Google Antigravity 的终端 CLI（`agy`）与桌面版（Antigravity App / IDE），共用同一后端引擎。CLI 为 Go 编译的闭源二进制，GitHub 仓库 [google-antigravity/antigravity-cli](https://github.com/google-antigravity/antigravity-cli) 仅含 issue tracker 和 CHANGELOG，无源码。

## CLI 能力

**安装**：`curl -fsSL https://antigravity.google/cli/install.sh | bash`，二进制在 `~/.local/bin/agy`。

**模型**：通过 `agy models` 或 `/model` 选择，包含 Gemini 4 Argon / 3.8 Flash、Claude Opus / Sonnet 5.5、GPT-OSS 120B。每模型支持 low / medium / high 推理档位。

**常用旗标**：

| 旗标 | 作用 |
|---|---|
| `--print` / `-p` | 单次非交互执行 |
| `--conversation <id>` | 恢复指定会话 |
| `--model <name>` | 指定模型 |
| `--mode auto` | 自动审批模式（安全命令不询问） |
| `--output-format stream-json` | 机器可读输出 |

**关键斜杠命令**：`/context` 查看上下文用量、`/compact` 手动压缩、`/resume` 列出并恢复会话、`/usage` 查看额度、`/plan` 规划模式。

## 鉴权存储与多账号

### 存储位置

登录凭据是一个 JSON 文件：

```text
~/.gemini/antigravity-cli/antigravity-oauth-token
```

包含 `token.access_token`、`token.refresh_token`、`token.expiry` 和 `id_token`（含账号邮箱）。文件权限 600。WSL 环境下自动走文件存储（日志显示 "Using file-based token storage because WSL environment detected"）；有桌面密钥环的系统可能走 Secret Service（`service=gemini, username=antigravity`）。

**整个登录态就这一个文件**——复制它即可在别处恢复登录，已实测验证（含 refresh token 自动续期）。会话数据库、配置、缓存均不是恢复鉴权所必需。

### 并行进程覆盖问题

多个 agy 进程共用同一凭据文件时，各自在内存中持有不同账号的凭据，token 刷新后写回同一文件，**最后写入者决定下一个新进程读到哪个账号**。`--conversation` 只选会话，不绑定鉴权。

已运行进程不受磁盘文件替换影响——必须退出旧进程才能彻底切换。

### 双账号隔离（已验证方案）

agy 不提供只重定向自身数据目录的环境变量（不像 Codex 有 `CODEX_HOME` 只改工具数据路径、不影响 git/SSH 等其他 `$HOME` 引用）。**唯一已验证的隔离方式是整个替换 `HOME`**——这意味着 git、SSH、工具配置也跟着换，需要额外软链回来。二进制中的 `ANTIGRAVITY_APP_DATA_DIR`、`ANTIGRAVITY_GEMINI_DIR`、`JETSKI_APP_DATA_DIR` 属于插件子命令入口，不改变主 CLI 数据目录。

在 `.bashrc` 中定义包装函数（类似 `codex-gth`）：

```bash
agy-alt() {
    HOME="$HOME/.agy-homes/<account>" command agy "$@"
}
```

隔离 HOME 内部结构（`~/.agy-homes/<account>/`）：

| 路径 | 类型 | 说明 |
|---|---|---|
| `.gemini/antigravity-cli/antigravity-oauth-token` | 独立文件 | 该账号的凭据，**不能软链** |
| `.gemini/antigravity-cli/settings.json` | 软链 → 真实 HOME | 共享主题、默认模型 |
| `.gemini/config` | 软链 → 真实 HOME | 共享 MCP、skills、projects |
| `.gitconfig` / `.ssh` / `.config` | 软链 → 真实 HOME | 共享 git 身份和工具配置 |
| `conversations/` / `brain/` / `implicit/` 等 | 软链 → 真实 HOME | 共享会话历史和压缩数据 |

这样两个入口各自刷新各自凭据、不互相覆盖，同时共享全部历史和配置。

> 并发写 `conversation_summaries.db`（SQLite WAL 模式）在正常使用下安全；避免从两个入口同时打开同一会话即可。

第三方切换工具（[agyw](https://github.com/tranquocthong/agy-switcher)、[agy-cli-manager](https://github.com/zcop/agy-cli-manager)、[agyswap](https://pypi.org/project/agyswap-cli/)）均为全局切换型——切换前须退出所有 agy 进程，不支持并行。

## 上下文压缩

**1M 模型实际只用到 ~256K**。客户端硬编码 `max_context_tokens = 256000`（1M 的 25%），在上下文增长到 250K–270K 时自动压缩到 15K–30K，此后循环。此阈值无法通过 settings.json、环境变量或 CLI 旗标修改。

**两种丢弃机制**：压缩（compaction）产生 CHECKPOINT 标记和散文摘要；预截断（truncation）在发送前静默裁剪早期历史，无任何标记。

**Desktop 版额外问题**：Claude 模型（200K 窗口）有时完全不触发压缩，直接报 `prompt is too long` 终止会话。

**缓解**：把关键决策和协议约束写入 `AGENTS.md` 或项目文档——系统规则每轮完整重注入，不受压缩影响。加入"修改文件前必须先读当前内容"的规则可降低压缩后"修复"已解决问题（Ghost Revert）的风险。

详细排查过程和社区证据见 `mess` skill 的 [antigravity-cli.md](../mess/references/antigravity-cli.md)。 🔬 本机 60 条会话实测，压缩峰值全部在 250K–270K 区间。

## 会话数据

| 路径 | 内容 |
|---|---|
| `~/.gemini/antigravity-cli/conversations/<id>.db` | 完整对话轨迹（SQLite，`steps` + `gen_metadata` 表） |
| `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl` | 每条 API 调用的 token 计数和内容 |
| `~/.gemini/antigravity-cli/conversation_summaries.db` | 会话索引（标题、状态、workspace） |

查看历史会话的上下文用量：读 transcript.jsonl 最后一条有 `input_tokens` 的记录，`input_tokens + cache_read_tokens` 即为当时的上下文大小。恢复会话用 `agy --conversation=<id>` 或在 TUI 中 `/resume`。
