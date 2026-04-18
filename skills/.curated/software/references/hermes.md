# Hermes

Hermes 指 [NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent)，一个 Python CLI 的 agent 框架。以下笔记分两类：**systemd 常驻服务**（gateway / dashboard）和 **terminal backend**（agent 执行命令的环境）。

## systemd 常驻服务

Hermes 常见常驻服务分两类：

- `hermes gateway ...`：消息平台 gateway（WeCom、Weixin、Telegram、Slack、Webhook、API Server 等）。
- `hermes dashboard ...`：Web UI dashboard，默认监听 `127.0.0.1:9119`，用于管理配置、API keys、sessions 等。

两者共享同一个 `HERMES_HOME` 时会读写同一套配置和会话数据，但进程、端口、systemd unit 都是独立的。

默认按**系统级 service** 配置：`WantedBy=multi-user.target`，服务以 `<USERNAME>` 普通用户身份运行，开机自启。

## 通用规则

1. **身份决定读写位置**。`HERMES_HOME` 默认按 `$HOME` 推导；以 root/sudo 跑 Hermes 命令可能写到 `/root/.hermes/`，跟服务以 `<USERNAME>` 身份读的 `/home/<USERNAME>/.hermes/` 对不上。
2. **显式传 `HERMES_HOME`**。凡是 system service、profile、sudo 场景，都要显式设置 `HERMES_HOME=<HERMES_HOME>`，避免 root HOME 污染。
3. **服务仍用普通用户运行**。系统级 service 用 `User=<USERNAME>` / `Group=<USERNAME>`，不要让 Hermes 业务进程以 root 长期运行。
4. **PATH 要写完整**。systemd 不继承交互 shell 的 nvm/cargo/brew 等 PATH；service 里要把 Hermes venv、Node/npm、用户 bin 路径写全。

## Gateway system service

官方支持 gateway 安装为后台服务：

```bash
sudo $(which hermes) gateway install --system --run-as-user <USERNAME>
sudo $(which hermes) gateway start --system
```

非 default profile 要显式传 `HERMES_HOME`，否则 sudo 下 HOME 变 `/root` 后可能找不到 profile：

```bash
sudo HERMES_HOME=/home/<USERNAME>/.hermes/profiles/<PROFILE> \
  $(which hermes) gateway install --system --run-as-user <USERNAME>
sudo HERMES_HOME=/home/<USERNAME>/.hermes/profiles/<PROFILE> \
  $(which hermes) gateway start --system
```

service 命名：

- default profile → `hermes-gateway.service`
- profile `<PROFILE>` → `hermes-gateway-<PROFILE>.service`

撤销 system service 推荐直接操作明确 unit，避免 `hermes gateway uninstall --system` 在 profile 不明确时误伤 default：

```bash
sudo systemctl stop <UNIT>.service
sudo systemctl disable <UNIT>.service
sudo trash-put /etc/systemd/system/<UNIT>.service
sudo systemctl daemon-reload
```

多 profile 注意：

- 数据目录 `/home/<USERNAME>/.hermes/profiles/<PROFILE>/` 各自独立，包含 `config.yaml`、`.env`、`auth.json`、sessions、memories、pairing、平台 token 等。
- 每个 profile 跑独立 gateway 进程；平台 token 通常不可共享，例如一个微信/iLink token 对应一个账号。
- pairing store 按 `HERMES_HOME` 定位；`hermes pairing approve` 必须以 gateway runner 同一用户身份和同一 `HERMES_HOME` 执行。

## Dashboard system service

官方 dashboard 文档只提供启动命令和参数，没有提供裸机 systemd install 命令；systemd unit 需要手写，写法参考 gateway service。

Dashboard 默认只监听 localhost：

```bash
hermes dashboard
```

若要给反代节点访问，可绑定到内网/VPN/EasyTier 地址：

```bash
hermes dashboard --host <DASHBOARD_HOST> --port <DASHBOARD_PORT> --no-open --insecure
```

`--insecure` 表示允许绑定到非 localhost。Dashboard 会读写 `.env`，其中可能包含 API keys 和 secrets；如果绑定到非 localhost，必须确保外层有可靠访问控制：

- 只绑定内网/VPN/EasyTier 地址，不随意用 `0.0.0.0`
- 入口反代加认证
- 本机防火墙只允许反代节点访问 dashboard 端口

### 系统级 service 模板

将 `<USERNAME>`、`<HERMES_HOME>`、`<HERMES_AGENT_DIR>`、`<DASHBOARD_HOST>`、`<DASHBOARD_PORT>`、`<NODE_BIN_DIR>` 替换为实际值。

```ini
[Unit]
Description=Hermes Agent Web Dashboard
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=5

[Service]
Type=simple
User=<USERNAME>
Group=<USERNAME>
WorkingDirectory=<HERMES_AGENT_DIR>
Environment="HOME=/home/<USERNAME>"
Environment="HERMES_HOME=<HERMES_HOME>"
Environment="PATH=<HERMES_AGENT_DIR>/venv/bin:<NODE_BIN_DIR>:<HERMES_AGENT_DIR>/node_modules/.bin:/home/<USERNAME>/.local/bin:/home/<USERNAME>/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStartPre=/bin/sh -c 'for i in $(seq 1 30); do ip -o -4 addr show to <DASHBOARD_HOST>/32 | grep -q . && exit 0; sleep 2; done; exit 1'
ExecStart=<HERMES_AGENT_DIR>/venv/bin/python -m hermes_cli.main dashboard --host <DASHBOARD_HOST> --port <DASHBOARD_PORT> --no-open --insecure
Restart=on-failure
RestartSec=30
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

如果 `<DASHBOARD_HOST>` 是 `127.0.0.1`，删除 `--insecure`。

安装：

```bash
sudo install -o root -g root -m 0644 hermes-dashboard.service /etc/systemd/system/hermes-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-dashboard.service
```

验证：

```bash
systemctl status hermes-dashboard.service --no-pager
systemctl is-enabled hermes-dashboard.service
ss -tlnp | grep <DASHBOARD_PORT>
curl -I http://<DASHBOARD_HOST>:<DASHBOARD_PORT>/
journalctl -u hermes-dashboard.service -f
```

如果前面有 Caddy/Nginx 反代，先从反代机器直连 upstream 验证，再测公网入口：

```bash
curl -I http://<DASHBOARD_HOST>:<DASHBOARD_PORT>/
curl -kI https://<PUBLIC_HOST>:<PUBLIC_PORT>/
```

`HEAD` 可能返回 `405 Method Not Allowed`，用 `GET` 再确认首页：

```bash
curl -sS -o /tmp/hermes-dashboard.html -w "%{http_code} %{content_type} %{size_download}\n" http://<DASHBOARD_HOST>:<DASHBOARD_PORT>/
```

### 网络依赖

`bind()` 到具体 IP 时，该 IP 必须已经挂在本机某张网卡上，否则报 `EADDRNOTAVAIL`。`network-online.target` 只表示系统认为网络已上线，不保证 `<DASHBOARD_HOST>` 这个具体地址已经分配好；`After=<某个网络服务>` 也只是等被依赖的 unit 进入 `active`（默认 `Type=simple` 下仅代表进程 fork+exec 完成，不代表 TUN/IP 已就绪），同样不可靠。

模板默认用 `ExecStartPre` 轮询等 IP 就绪：`ip -o -4 addr show to <HOST>/32` 让内核精确匹配，没有正则歧义；30 × 2s = 60s 超时，超时后再交给 `Restart=on-failure` + `RestartSec=` 继续重试。

如果嫌 `ExecStartPre` 麻烦，也可以删掉它只靠 `Restart=on-failure`：地址未就绪时 bind 失败，systemd 按 `RestartSec=` 重启。日志会更吵，但配置更简单。

### 环境变量取舍

模板里的关键项：

- `User` / `Group`：必须，保证不以 root 运行。
- `WorkingDirectory`：建议保留，Hermes 构建和相对路径更稳定。
- `HOME`：建议保留，避免 Hermes 或依赖误用 root HOME。
- `HERMES_HOME`：必须，固定配置和数据目录。
- `PATH`：必须包含 venv 和 `npm` 所在目录；systemd 不继承交互 shell PATH。

### npm / bun

当前 Hermes dashboard 构建逻辑硬编码查找 `npm`，并执行：

```bash
npm install --silent
npm run build
```

所以 service 的 `PATH` 必须包含 `npm` 所在目录，尤其是 nvm 安装的 Node.js。仅安装 bun 不会被 Hermes 自动识别。

想用 bun 有三种选择：

1. 继续让 service 使用 `npm`：最稳，和 Hermes 当前实现一致。
2. 手动用 bun 预构建前端，但 Hermes 启动时仍会尝试找 `npm` 并运行构建逻辑；除非 Hermes 后续改为检测已有 dist 后跳过构建。
3. Patch Hermes 源码，把 `_build_web_ui` 改成优先 `bun install` / `bun run build`，找不到 bun 再回退 npm。升级 Hermes 时需要重新处理补丁。

不要用全局假 `npm` 包装 bun，除非明确验证 `npm install --silent` 和 `npm run build` 在该项目中完全等价；这种做法会影响同一 PATH 下其他 Node 项目。

## Terminal backend（命令执行环境）

Hermes 里的 "backend" 是专有术语：**agent 执行 shell 命令的运行环境**，跟 Hermes 进程本身在哪里跑无关。通过 `~/.hermes/config.yaml` 的 `terminal.backend` 切换；可选值定义在源码 `hermes-agent/hermes_cli/config.py` 的 DEFAULTS 里：`local` / `docker` / `ssh` / `modal` / `daytona` / `singularity`。

切换与查看：

```bash
hermes config set terminal.backend ssh      # 或 docker / local / ...
hermes config show                          # "◆ Terminal / Backend:" 字段验证
```

`hermes config` 可用子命令：`show` / `edit` / `set` / `path` / `env-path` / `check` / `migrate`。

### 数据流（通吃所有 backend）

LLM 请求从本机 Hermes 进程发出（本机网络出口 + 本机 `.env` 里的 API key），LLM 返回的 tool_call 才被转发到 backend 执行。于是：

- `$HOME`、`pwd`、临时 env、出网 IP 全以 backend 为准；
- API 凭据永远留在本机 `.env`，不会下发到远端或容器；
- 本机代理只影响 LLM 调用那一段，不影响 backend 内部命令的网络行为。

### SSH backend

连接参数一律走 `~/.hermes/.env`，Hermes 官方 `.env` 模板里预留了一段 `SSH REMOTE EXECUTION` 注释（在 `TERMINAL TOOL CONFIGURATION` 块之后），把示例占位符替换成实际值即可：

```
TERMINAL_SSH_HOST=<hostname 或 ~/.ssh/config 别名>
TERMINAL_SSH_USER=<USERNAME>
TERMINAL_SSH_PORT=22
TERMINAL_SSH_KEY=<私钥绝对路径>
TERMINAL_SSH_PERSISTENT=true
```

Hermes 底下调用系统 `ssh` 子进程，所以 `~/.ssh/config` 会被读；但要避免 `-i` / `-p` 命令行参数与 ssh config 规则打架 —— **`TERMINAL_SSH_HOST` 填真实 hostname + 其他字段写全** 是最稳的方式。

执行模型是 **spawn-per-call**：每次 `execute()` 新起一个 `ssh ... bash -c '<脚本>'` 子进程，由 ControlMaster socket（`/tmp/hermes-ssh/*.sock`, `ControlPersist=300`）复用 TCP 免握手。session 连续感靠两招伪造：init 时 dump 远端 env/函数/alias 到 `/tmp/hermes-snap-<sid>.sh`，每条命令前 `source` 后回写；CWD 用 `__HERMES_CWD_<sid>__` marker 搭在 stdout 里回传，输出给 LLM 前裁掉标记行。文件同步走 `FileSyncManager`（mtime+size 指纹、5 秒节流、批量走 `tar | ssh | tar xf` 单流上传）。长跑任务仍需 `tmux` / `nohup`，因为 spawn 的 ssh 一退，子进程收 SIGHUP。

### vs. remote 技术路线对比

共同点：都靠 OpenSSH ControlMaster（socket + `ControlPersist`）复用 TCP。差异全在"无状态 ssh 之上怎么补语义"：

| 维度 | Hermes SSH backend | remote |
|---|---|---|
| session 语义 | 快照伪造：init 时 dump env/func/alias 到 `/tmp/hermes-snap-<sid>.sh`，每条命令 `source` 后回写；CWD 靠 stdout marker 带外回传 | 不补：每次 `ssh <host> <cmd>` 独立；跨命令需要 `cd x && cmd` 自己拼 |
| 文件传输 | `FileSyncManager` 托底：mtime+size 变更检测、5 秒节流、批量走 `tar \| ssh 'tar xf -'` 单流 | 手动 `scp`；复杂编辑"scp 下 → 本地 Edit → scp 上" |
| sudo | `SUDO_PASSWORD` env + 命令改写（`_transform_sudo_command`） | 脚本落本地 `/tmp` → scp → `ssh -t <host> sudo bash` |
| ControlPersist | 300s | 10m |

本质区别：Hermes 把 ssh 当**透明执行面**，所以必须重建 cwd/env 连续性 + 文件同步；remote 把 ssh 当**显式远程调用**，每条命令自带完整上下文、文件走 scp，反而简单透明。

### Docker backend

所有参数走 `config.yaml` 的 `terminal.*`，字段默认值即官方推荐（源码 `hermes_cli/config.py:386-408`）：镜像 `nikolaik/python-nodejs:python3.11-nodejs20`，资源 `container_cpu/memory/disk = 1 / 5120MB / 51200MB`，`container_persistent: true`，`persistent_shell: true`，`docker_mount_cwd_to_workspace: false`（开启会把宿主机 cwd 挂进容器、削弱隔离）。

三个容易混的 env 字段：

| 字段 | 作用域 | 取值方式 | 何时用 |
|---|---|---|---|
| `env_passthrough` | 所有 backend | 从 Hermes 进程环境读值，透给 backend session | 通用 |
| `docker_forward_env` | docker only | 从宿主机当前进程读值并转发 | Hermes 跑在能 source rc 的交互 shell 下 |
| `docker_env` | docker only | 显式 key-value 字典 | Hermes 跑 systemd 这种环境干净的 unit |

源码注释（`config.py:388-392`）原话举的典型例子就是用 `docker_env` 解决 systemd 下 agent socket：`{"SSH_AUTH_SOCK": "/run/user/1000/ssh-agent.sock"}`，同时用 `docker_volumes` 把这个 socket 文件挂进容器同路径，容器里 ssh 就能复用宿主机 agent。

### Session 级 backend 隔离：走 profile，不要走环境变量

想"让某些 session 跑在远端 backend，主对话/默认 profile 保持 local"，**唯一正确的做法是建独立 profile**：

```bash
hermes profile create vps --clone --no-alias   # 克隆默认 profile 的 config/.env/SOUL
hermes -p vps config set terminal.backend ssh  # 只改 vps profile 的 backend
```

之后使用：

```bash
hermes -p vps chat -q "<prompt>" --yolo -Q      # 一次性子会话，跑在 RackNerd
hermes profile use vps                          # 或把 vps 设成 sticky 默认
```

`-p / --profile` 是 `main.py:83-134` 里的 pre-parser 实现，在任何 hermes 模块 import 之前就把 `HERMES_HOME` 指到 `~/.hermes/profiles/<name>/`，然后从 argv 里剥掉；效果等价于 `HERMES_HOME=... hermes ...` 但少手写一截。`hermes --help` 里不显示这个 flag，但它稳定存在。

**反面教材（踩过）**：`TERMINAL_ENV=ssh hermes chat ...` 这种纯环境变量 override **不生效**。原因在 `cli.py:442-455`：只要 `config.yaml` 里存在 `terminal:` section（几乎总是存在，默认就会被 `hermes setup` 写入），这段代码会把 yaml 里的 `terminal.backend` 反向**覆盖**进程的 `TERMINAL_ENV`，拿到 terminal_tool 那里读的时候早已变回 `local`。所以 backend 切换必须改 `config.yaml`（直接改或 `config set`），不能靠临时 env var。

**`HERMES_HOME=... hermes ...` 这种显式写法**只在极个别场景有用 —— 典型是 `sudo` 或其他清 env 的环境下，`sudo -E` 不够用、或者被 `secure_path` 干掉了 `-p` 解析前的 rc 初始化 —— 日常切 profile 走 `-p`/`profile use` 即可。

### 编程调用 / 后台子会话的两个关键 flag

想让 Hermes 被脚本或主 agent 的 `Bash` 工具启动、一把跑完就退，不阻塞在审批/交互上，`hermes chat` 几乎必须带这两个：

- `--yolo`：跳过所有"危险命令"审批。Hermes 默认 `approvals.mode=manual`，非交互调用中任何会触发审批的工具调用都会无限等待，子进程看起来就是"卡住"。知道输入是受信 prompt 就加。
- `-Q` / `--quiet`：抑制 banner、spinner、tool preview 动画，最终只输出 assistant 的最终回复 + 一段 `session_id: ...`。不加的话 stdout 会混入 Rich 的 ANSI 控制字符和进度框线，难以被脚本解析。

组合起来的一次性子会话模版：

```bash
hermes -p <profile> chat -q "<指令>" --yolo -Q
```

指令里让 LLM "**把原始 stdout 放在代码块里回我，别加解释**"，再把结果从代码块里切出来，就是最稳的 stdout 获取方式 —— 比让它自然语言描述执行结果可解析得多。

### SSH_AUTH_SOCK 继承（关键坑）

Hermes 自己不做 agent 发现，完全**继承父进程环境变量**。

| 启动方式 | agent 可见性 | 处理 |
|---|---|---|
| 交互 shell 里 `hermes` | ✅ `.bashrc` export 了就行 | 默认 OK |
| systemd unit（dashboard/gateway） | ❌ unit 不 source rc | 在 service 里加 `Environment="SSH_AUTH_SOCK=/run/user/<UID>/ssh-agent.socket"` |
| cron / 非交互 | ❌ 同上 | 同上，或确保 key 文件免 passphrase |

辅助判定规则：

- 私钥**没 passphrase** 时，Hermes SSH backend 靠 `-i $TERMINAL_SSH_KEY` 直读 key 文件即可连通，agent 有没有都无所谓；验证方法：`SSH_AUTH_SOCK= ssh -o BatchMode=yes -o IdentitiesOnly=yes -i <key> <host> true`，返回 0 表示没 passphrase。
- key 有 passphrase 时，上面的继承链才真正关键，systemd 场景必须补 `Environment=` 或 `EnvironmentFile=`。

## Provider 实测记录

### MiniMax Coding Plan（`minimax-cn`）

hermes 内置 `minimax-cn` provider 默认 `base_url=https://api.minimaxi.com/anthropic`（Anthropic 协议兼容）。用户 Coding Plan key（`sk-cp-` 前缀）实测：

- ✅ `POST /anthropic/v1/messages`：200，`MiniMax-M2.7` 正常对话
- ✅ `POST /v1/text/chatcompletion_v2`：200（原生协议）
- ✅ `POST /v1/chat/completions`：200（OpenAI 兼容）
- ❌ `POST /anthropic`（裸路径、无 `/v1/messages` 后缀）：nginx 404

曾见过报错 `hermes` 端显示 endpoint 为 `https://api.minimaxi.com/anthropic` 返 404，原因是 `.env` 里把 `MINIMAX_CN_BASE_URL` 写成了原生全路径 `/v1/text/chatcompletion_v2`，与 provider 内部 Anthropic 协议构造方式冲突，最终拼出裸 `/anthropic` 发请求。**`MINIMAX_CN_BASE_URL` 要么不设（用默认），要么指向 Anthropic 协议的基路径 `/anthropic`**，别指向原生全路径。

另：Coding Plan 某些机型（如 `MiniMax-M2.7-highspeed`）会返 HTTP 500 `your current token plan not support model (2061)`，与端点无关，是套餐白名单问题。

### Gemini（Google AI Studio）OpenAI 兼容端点与 `AQ.` 前缀 key

hermes `gemini` provider 硬编码 `inference_base_url=https://generativelanguage.googleapis.com/v1beta/openai`（`hermes_cli/auth.py` 附近），内部按 OpenAI 协议（`Authorization: Bearer` + `/chat/completions`）构造请求；`GEMINI_BASE_URL` 仅能覆盖 base_url，**不能切协议模式**。

实测某账号 key 以 `AQ.` 开头（约 53 字符，非经典 `AIza...` 39 字符，`oauth2/tokeninfo` 验证返 `invalid_token`），在同一 key 上行为如下：

| 请求 | 鉴权 | 结果 |
|---|---|---|
| `POST /v1beta/openai/chat/completions` | `Authorization: Bearer <AQ.key>` | ❌ HTTP 400 `"Multiple authentication credentials received. Please pass only one."` |
| `GET /v1beta/openai/models` | 同上 | ❌ HTTP 400 同错 |
| `POST /v1beta/models/<model>:generateContent?key=<AQ.key>` | URL 参数 | ✅ 200，多轮对话正常 |
| `GET /v1beta/models` | `x-goog-api-key: <AQ.key>` | ✅ 200 |
| `POST /v1beta/models/<model>:generateContent` + Bearer | `Authorization: Bearer <AQ.key>` | ❌ HTTP 401 `"Expected OAuth 2 access token"` |

关键点：**即使 curl 只发一个 `Authorization` header、无任何其它 auth 形式**，OpenAI 兼容网关仍返 400 "multiple credentials"。推断是 Google 网关对 `AQ.` 前缀同时走了 OAuth + API key 两套解析都命中导致互斥。经典 `AIza...` key 走 Bearer 正常，外部未见公开报告此现象。

因此 hermes gemini provider + `AQ.` key 组合下无可行直连路径。绕过方式：
1. 去 aistudio.google.com/app/apikey 重建 key，看能不能拿到 `AIza...` 格式
2. 本地 proxy 协议转换（LiteLLM / [gemini-openai-proxy](https://github.com/zhu327/gemini-openai-proxy)），`GEMINI_BASE_URL=http://127.0.0.1:<port>/v1`，proxy 内部用 `x-goog-api-key` 走原生端点
3. 换走 OpenRouter 之类聚合器，直接用对方 key

### hermes auth 重置命令速查

| 目的 | 命令 |
|---|---|
| 清除 provider "配额耗尽" 标记（不删凭证） | `hermes auth reset <provider>` |
| 删除指定凭证（并自动清理 `.env` 对应行） | `hermes auth remove <provider> <id\|label>` |
| OAuth 类（仅 `nous` / `openai-codex`）重登 | `hermes logout --provider <p>` 然后 `hermes login` |

`hermes auth remove` 会顺带把 `.env` 里该 env var 一起清掉，不用手动删。api_key 类 provider 下次启动从 env 重建；OAuth 类（如 `openai-codex` 的 device_code）必须重新 `hermes login`。避免直接删整个 `auth.json`（会连带干掉 copilot 的 `gh auth token` 和 openai-codex 的 OAuth 态）。
