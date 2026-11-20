# Cursor Agent CLI（Cursor 官方编码 agent：runtime / 鉴权 / 额度）

> **harness skill 的 reference。** 面向要在终端或上层 runner 里驱动 Cursor Agent、核对它的登录与 Git 署名、或只读查询 Cursor Pro 周期额度的工程师。覆盖分发形态、OAuth 与 CLI 配置、受限网络下的代理包装、无头参数与原生 worktree、模型档位，以及 `GetCurrentPeriodUsage`。
>
> 命令面以 `2026.11.17-f532c45` 的 `--help` 为记录版本，并在 `2026.11.19-f005e9d` 上复核同一份帮助文本。标 🔬 的是本机实测。帮助文案的用法行写作 `agent`，磁盘上的可执行文件名仍是 `cursor-agent`。

## <a id="distribution"></a>二进制与分发

`~/.local/bin/cursor-agent` 是符号链接，指向 `~/.local/share/cursor-agent/versions/<ver>/cursor-agent`。版本目录随 `agent update` 更换，调用方不要把某一版的绝对路径写死。

该路径上的 `cursor-agent` 是 bash 启动器。它解析自身真实目录后，用同目录自带的 `node` 执行同目录的 `index.js`：

```bash
exec -a "$0" "$NODE_BIN" $NODE_FLAGS "$SCRIPT_DIR/index.js" "$@"
```

启动器要求这套 Node 能接受 `--disable-sigusr1`；两份已安装版本目录里的 `node --version` 都是 `v24.22.1` 🔬。因此分发形态是「版本目录里的 Node 运行时 + JS bundle」，外加同目录的原生插件（`.node`）。

## <a id="auth-and-config"></a>鉴权与配置存储

OAuth 的 access token 与 refresh token 落在 `~/.config/cursor/auth.json`，文件权限 `0600`，JSON 字段名为 `accessToken` 与 `refreshToken` 🔬。复制这个文件即可在另一台机器恢复同一登录；它等同于账号凭据，权限保持 `0600`，内容不进入日志、文档或提交。

CLI / agent 偏好在 `~/.cursor/cli-config.json`。单次调用可以用 `--api-key <key>` 或环境变量 `CURSOR_API_KEY` 覆盖文件里的登录态。默认 API 端点是 `https://api2.cursor.sh`，可用 `--endpoint` 或 `CURSOR_API_ENDPOINT` 改写。流式 agent 后端写在这份配置的服务端缓存里，本机读到的地址是 `https://agentn.global.api5.cursor.sh` 🔬。

提交与 PR 的自动署名由同一份 CLI 配置控制。要抑制 harness 自己追加的 agent trailer，保持：

```json
"attribution": {
  "attributeCommitsToAgent": false,
  "attributePRsToAgent": false
}
```

`attributeCommitsToAgent` 管 commit，`attributePRsToAgent` 管 PR。两项都为 `false` 时，CLI 不自动写入这类 trailer 🔬。仓库若另有 Git hook 剥离 trailer，那是第二道闸，不能代替这里的开关。

## <a id="proxy-wrapper"></a>代理与交互包装

在需要出站代理的网络里，交互式 shell 用函数包住真身：先在 `http_proxy` / `https_proxy` 仍为空时注入代理（例如 `clashctl --shell-on`），再执行 `~/.local/bin/cursor-agent`。调试跟踪若打印 argv，把 `--api-key` 的下一个参数以及 `--api-key=<value>` 换成占位符，避免密钥进 trace。

非交互子进程不读取交互式 `~/.bashrc`，因此其他 harness 拉起 `cursor-agent` 时带不上这个函数。那些调用要在子进程环境里直接导出 `http_proxy` 与 `https_proxy`。

## <a id="headless-and-worktrees"></a>无头调用与 worktree

`-p` / `--print` 把回复打到 stdout，供脚本和非交互使用。这条路径**默认拥有全部工具，包括写文件和 shell**。只读规划用 `--mode plan`（`--plan` 是同一模式的短旗标）；只读问答用 `--mode ask`。这两个模式不再改工作区。

无人值守执行同时加上：

- `--trust`：不再询问是否信任当前工作区。
- `--yolo`：等价于 `-f` / `--force`，自动放行命令，显式拒绝规则仍然生效。

`--output-format` 只在 `--print` 下生效，取 `text`、`json` 或 `stream-json`。`--stream-partial-output` 再要求格式为 `stream-json`，按文本增量往外吐。

会话先用 `create-chat` 拿到 chat id，再用 `--resume <chatId>` 接回去。工作区用 `--workspace <dir>` 指定目录或已保存的工作区名；`--add-dir <dir>` 可重复，用来加额外根目录。

原生 worktree 旗标是 `-w` / `--worktree [name]`。省略名字时 CLI 自己生成。目录落在 `~/.cursor/worktrees/<repo>/<name>`。`--worktree-base <branch>` 指定基线，默认当前 HEAD。仓库可以在 `.cursor/worktrees.json` 里放 setup 脚本；`--skip-worktree-setup` 跳过它们。

> 与 [worktree.md](worktree.md) 里三家宿主的差别：Claude Code 的 `--worktree` 建在仓库内 `.claude/worktrees/<value>/`，默认基线是 `origin/HEAD`。Cursor 的工作树在家目录下按仓库名分目录，默认基线是当前 HEAD。Codex 与 Copilot CLI 没有同等的原生建树旗标。

## <a id="model-selection"></a>模型与推理档位

`cursor-agent models` 与 `--list-models` 列出当前账号可用的模型 id。选用方式有两种：

- **扁平 id**：档位直接写进名字。例如 `grok-4.7-xhigh` 与 `grok-4.7-xhigh-fast`，以及 `muse-wonder-1.0-max`、`claude-opus-5-5-max`、`gemini-4-neon-xhigh`。带 `-fast` 的是另一条独立 id。
- **方括号参数**：`--model '<family>[context=...,effort=...,fast=false]'`。帮助文本给出的例子是 `--model 'claude-opus-4-8[context=1m,effort=high,fast=false]'`。整段用引号包住，避免 shell 拆开方括号。

`--list-models` 末尾也会重复这条方括号语法 🔬（`2026.11.19-f005e9d`）。

## <a id="period-usage"></a>周期额度接口

Cursor Pro 的当前账期用 Dashboard RPC 只读查询，不需要打开网页：

```sh
token=$(python3 -c 'import json, pathlib; print(json.loads((pathlib.Path.home()/".config/cursor/auth.json").read_text())["accessToken"])')
curl -sS -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
  -d '{}' \
  https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage
```

`Authorization` 使用 `auth.json` 里的 access token。请求体是空对象 `{}`。把 token 留在变量里，不写入命令回显、文档或提交 🔬。

与两个额度池直接对应的字段：

| 字段 | 池 | 读法 |
|---|---|---|
| `planUsage.autoPercentUsed` | **Cursor Models** | 成员名单以响应里的 `autoBucketModels` 为准 |
| `planUsage.apiPercentUsed` | **Other Models** | 不在 `autoBucketModels` 里的模型走这个百分比 |
| `planUsage.totalPercentUsed` | 两池合计 | 两个池仍各看各的百分比 |
| `billingCycleStart` / `billingCycleEnd` | 账期 | 纪元毫秒；JSON 里可能是字符串 |
| `planUsage.includedSpend` / `bonusSpend` / `limit` | 花费与包含额度 | 与百分比一起返回；`bonusSpend` 是套餐包含量之外、提供方另给的用量 |

2026-11-21 本机响应里，`autoBucketModels` 共 48 个 id，家族为 `default`、`composer-*`、`grok-4.5*`、`grok-4.6*`、`grok-4.7*`（含 `grok-4.7-xhigh` 与对应 `-fast`）、`cursor-grok-*`、`vega*`。同一次 `--list-models` 里的 `muse-wonder-1.0-*`、`claude-*`、`gemini-*`、`gpt-*` 不在这份名单中，因此算在 **Other Models**（`apiPercentUsed`）里。名单以当次响应为准，换账期或换计划后要重读 `autoBucketModels`。

> 百分比相对回合结束有延迟。本机观测是回合完成后大约 3–10 秒，`planUsage` 才计入这一轮；刚结束就读，会把尚未入账的消耗看成还没发生。
