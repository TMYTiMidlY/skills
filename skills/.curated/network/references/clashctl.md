# clashctl / Mihomo：shell 与常驻程序的代理环境

[clashctl](https://github.com/nelvko/clashctl) 是 Linux 上的 Mihomo / Clash 安装与管理工具，原名 `clash-for-linux-install`。应用是否使用代理，还取决于自己的启动环境和网络库。本文覆盖 shell 集成、进程环境传递和服务验收；Mihomo 的规则、节点、TUN 与 DNS 机制见 [Mihomo 参考](mihomo.md)。Codex 的账号与 daemon、DSH 的后台及子进程策略由 `harness` skill 负责，通用服务管理由 `software` skill 负责。

> 上游身份见 [项目说明](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/README.md#L1-L8)。本文的上游源码核对使用提交 `4ec42a9f33108a16281bdad4eace7ccce94ae3b2`；这是公共源码快照，不证明任一机器的安装版本，额外部署包装器也须独立核对。

## <a id="entrypoints"></a>入口与部署包装器

先确认 `clashctl` 在当前 shell 中是函数、别名还是可执行文件，再读取对应启动文件与包装脚本。Bash 可用 `type -t clashctl` 与 `type -P clashctl` 分别查看入口类型和 PATH 中的程序位置；函数可能调用后者，二者的权限和副作用应分别核对。安装根目录从实际入口或 `CLASHCTL_HOME` 确认，配置与订阅文件按敏感数据处理。

上游 shell 命令与内核生命周期分别处理：

| 入口 | 上游源码行为 | 操作边界 |
|---|---|---|
| `clashctl on` | 先调用内核启动入口，再导出当前终端的代理变量 | 可能启动内核，需具备相应授权 |
| `clashctl off` | 清除当前 shell 中大小写的 HTTP、HTTPS、ALL 和 NO_PROXY 变量，默认保留内核 | 已运行的子进程保持原环境 |
| `clashctl off --stop` | 清除变量后调用停止内核入口 | 会影响共享该内核的应用，须先协调 |

> 来源：[开启代理](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/on.sh#L3-L16)、[导出代理变量](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/on.sh#L32-L67)、[关闭与停止选项](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/off.sh#L3-L29)。

外层集成要另外审查。在已核对的一种系统级包装结构中，加载脚本只定义函数并导出 `CLASHCTL_HOME`，加载本身不启用代理；管理员程序却在其他子命令成功返回后刷新并重写 shell 参数文件。因此，经该包装器执行的 `status`、`--help`、`--version` 也可能写文件。这是额外集成层的源码行为，不归因于上述公共提交，也不外推到其他安装。

只读检查先读取自己的入口和集成脚本，再直接查询服务管理器、监听与进程元数据；不能仅凭命令名称认定无副作用。加载 shell 集成本身也以已读脚本为准，仅执行已审查且受信任的版本。

环境文件先当数据检查：确认所有者、权限、生成者、变量名和转义格式，再选择合适的解析方式。`source` 和 `eval` 会执行 shell 代码，不自动加载未知来源的 `.env`，也不把 shell 格式文件直接当作 systemd 的 `EnvironmentFile=`。

## <a id="proxy-layers"></a>内核、shell 与应用

| 层次 | 要核对的对象 | 与其他层的关系 |
|---|---|---|
| 代理内核 | Mihomo 进程、配置、实际监听、出站规则 | 内核存活才可能接受连接；active 和监听均不证明目标可达 |
| 当前 shell | 已导出的代理变量及其值 | 只影响此后从该环境启动、且未被覆盖的进程 |
| 实际应用 | 发起请求的进程、网络库、显式代理设置与绕过规则 | 继承变量后，还要由客户端实际采用它们 |

子进程通常继承父进程已导出的环境；启动器使用 `env_clear`、显式替换环境、权限切换或应用不支持代理变量时，应按实际路径核验。环境继承与应用采用是两个检查项，不能仅凭终端里能 `curl` 就断定后台或其子程序使用相同代理。

常驻程序在启动时获得环境快照；新终端执行 `clashctl on/off` 或修改启动文件，不会更新已经运行的 daemon。排障先找到真正发起网络请求的后台和其启动者，再核对相应进程；环境变更需要的重启应在任务自然空闲、获得授权后按实际管理归属处理。

> 例如，Codex TUI 可以连接早已运行的 daemon；DSH 也可能由服务管理器而非当前 shell 启动。两者的具体后台发现、账号隔离与子进程环境策略应继续读取 `harness` skill 对应主题。

## <a id="proxy-variables"></a>代理变量与入口协议

| 变量 | 作用与检查点 |
|---|---|
| `http_proxy` / `HTTP_PROXY` | HTTP 目标的代理；大小写是不同变量，支持情况由客户端决定 |
| `https_proxy` / `HTTPS_PROXY` | HTTPS 目标的代理；变量名中的 HTTPS 描述目标协议，值可以是 `http://` 代理入口 |
| `all_proxy` / `ALL_PROXY` | 部分客户端在没有协议专用变量时使用的兜底，不能覆盖所有客户端或专用设置 |
| `no_proxy` / `NO_PROXY` | 绕过代理的主机、域名或地址列表；匹配语法、CIDR 支持和优先级依客户端而异 |

> curl 8.5.0 接受大小写代理变量，小写优先；HTTP 代理仅接受小写 `http_proxy`。它的 `ALL_PROXY` 是协议专用代理未设置时的兜底，`NO_PROXY` 可覆盖显式 `--proxy`，CIDR 支持自 7.86.0 加入。见 [curl 环境变量](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/page-footer#L6-L42)。这些规则不宜直接外推到所有 SDK。

Mihomo 的 `mixed-port` 在同一监听端口接受 HTTP 和 SOCKS。代理 URL 的 scheme 选择客户端到入口使用的协议：

- `http://`：HTTP 代理；HTTPS 目标通常经 CONNECT 建隧道，目标 TLS 仍由客户端校验。
- `socks5://`：在 curl 中由客户端本地解析目标域名。
- `socks5h://`：在 curl 中把目标域名交给 SOCKS5 代理解析；其他网络库须先确认是否支持该 scheme。

> 入口机制见 [mixed-port 与 TUN](mihomo.md#mixed-port-tun)；curl 的行为见 [代理协议](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/proxy.d#L14-L27)、[SOCKS5 本地解析](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/socks5.d#L13-L25)和 [SOCKS5 代理解析](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/socks5-hostname.d#L13-L25)。HTTP 与 SOCKS5h 改变的是入口协议及解析路径；超时仍须分层核对连接、DNS、TLS、规则和上游响应，不能把单改 scheme 当作通用修复。

需要显式设置应用启动环境时，先核对监听与应用支持，再使用一致的大小写变量。以下以无认证的回环 mixed-port `7890` 为例，实际端口按部署替换：

```bash
export http_proxy='http://127.0.0.1:7890'
export https_proxy="$http_proxy"
export all_proxy='socks5h://127.0.0.1:7890'
export HTTP_PROXY="$http_proxy" HTTPS_PROXY="$https_proxy" ALL_PROXY="$all_proxy"
export no_proxy='localhost,127.0.0.1,::1'
export NO_PROXY="$no_proxy"
```

绕过列表按实际内网需求补充，并在目标客户端验证。宽泛的域名后缀、私网网段或 `*` 可能使请求直连；大小写值冲突时先理清客户端优先级，不依赖偶然选中某一份值。含用户名、密码或私密参数的代理 URL 不写进示例、日志或公开报告。

## <a id="service-environment"></a>systemd 与其他启动器

由 systemd 启动的应用，从其 service 的 `Environment=` 或 `EnvironmentFile=` 明确声明代理，而不是依赖交互式 shell 的启动文件。系统 manager 与用户 manager 各有自己的环境来源，`systemctl --user` 也不是从执行该命令的终端直接启动服务进程。

以下为已授权修改**实际应用 service**时可使用的关键配置；端口与绕过范围仍按部署确认：

```ini
[Service]
Environment="http_proxy=http://127.0.0.1:7890" "HTTP_PROXY=http://127.0.0.1:7890"
Environment="https_proxy=http://127.0.0.1:7890" "HTTPS_PROXY=http://127.0.0.1:7890"
Environment="all_proxy=socks5h://127.0.0.1:7890" "ALL_PROXY=socks5h://127.0.0.1:7890"
Environment="no_proxy=localhost,127.0.0.1,::1" "NO_PROXY=localhost,127.0.0.1,::1"
```

集中维护时可用 `EnvironmentFile=` 指向管理员维护的环境文件，内容为逐行 `NAME=value`，无需 `export`，也不依赖 shell 变量展开。环境文件在进程执行前读取；修改 unit 后的 `daemon-reload` 只重读服务定义，不更改运行中进程的环境。是否以及何时重启应用，须先协调其活跃任务并获得授权。

> 来源：[环境声明与文件语法](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml#L2704-L2800)、[服务进程的环境来源](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml#L3558-L3604)、[daemon-reload](https://www.freedesktop.org/software/systemd/man/255/systemctl.html#daemon-reload)。环境变量本身不适合传递高价值秘密；需要代理认证时按应用支持选用受保护的凭据机制，而非公开完整 `Environment`。

`After=` 表示同一 manager 内的 unit 启动顺序，本身不拉起被依赖服务，也不证明代理端口和外部目标就绪。用户 service 写 `After=mihomo.service`，不能据此等待另一个系统 manager 中的同名服务。需要启动依赖时先确认双方管理范围和服务类型，再设计依赖与有界的就绪检查；外网暂不可用的恢复也要由应用重试或服务策略处理。

> 来源：[unit 顺序与依赖](https://github.com/systemd/systemd/blob/v255/man/systemd.unit.xml#L803-L840)。代理内核的健康、监听和外网可达性应分别验证；`network-online.target` 同样不能替代代理与目标的就绪检查。其他 supervisor、容器和桌面启动器也要在各自的实际启动入口声明环境。

## <a id="validation"></a>分层验收

只读盘点按下表收集证据；启动、停机、重启、改配置和冷启动演练单独取得授权。不要用有写入副作用的 clashctl 包装命令代替只读探查。

| 检查 | 证据与判定范围 |
|---|---|
| 服务当前状态 | 在正确 manager 查询 `ActiveState`、`SubState`、`MainPID`，说明内核当前是否存活 |
| 自动启动策略 | 单独查询 `UnitFileState` 或 `is-enabled`，说明启动接入状态；与 active 分开记录 |
| 实际监听 | 对照监听地址、端口、所属 PID 与应用所在网络命名空间；容器里的回环地址可能不是宿主回环 |
| 实际进程环境 | 核对真正发请求的 PID 和启动时间，只提取代理白名单：`http_proxy`、`https_proxy`、`all_proxy`、`no_proxy` 及对应大写；输出前遮蔽 URI 凭据及私密参数 |
| 实际请求 | 用目标客户端或同网络库的无副作用请求，核对目标、代理选择、DNS、TLS、返回码和耗时；通用 HTTP 探针只覆盖所测链路 |
| 冷启动 | 在获准维护窗口，从新的 shell、应用进程或服务启动路径重验上述项目；新 shell 测试不代替服务冷启动，enabled 也不代替启动实测 |

环境核查按最小披露处理，不打印完整 `env`、完整 `/proc/<PID>/environ`、完整 service `Environment`、认证文件或代理订阅。进程初始环境可帮助定位启动链，应用的显式设置、运行时代理对象和实际请求仍需分别核对。

> systemd 的 active 与 enabled 是独立状态，见 [服务启用与启动](https://www.freedesktop.org/software/systemd/man/255/systemctl.html#enable%20UNIT%E2%80%A6)。无模型请求的网络检查不能证明账号额度、模型权限、流式连接或实际模型任务可用；需要这类验收时，回到 `harness` skill 对应主题并取得任务授权。
