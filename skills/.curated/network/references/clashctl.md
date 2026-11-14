# clashctl 托管、订阅与应用代理环境

[clashctl](https://github.com/nelvko/clashctl) 是 Linux 上围绕 Mihomo / Clash 内核的安装与管理工具，原名 `clash-for-linux-install`。本文覆盖安装发现、托管订阅、shell 集成、应用启动环境和服务维护；内核的入口、规则、Provider、TUN、DNS 与控制 API 见 [Mihomo 参考](mihomo.md)。具体编码工具的账号、后台和子进程策略由 `harness` skill 负责，通用服务管理由 `software` skill 负责。

> 上游身份与源码基准见 [项目说明](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/README.md#L1-L8)。下文引用的公共源码来自提交 `4ec42a9f33108a16281bdad4eace7ccce94ae3b2`，不代表任一实际安装的版本。另行标明的“系统级包装部署核对”来自一种已核对部署，包装入口、权限和环境文件须在当前机器重新确认。

## <a id="entrypoints"></a>安装发现与入口权限

安装发现先读取入口、权限和服务元数据，再区分托管工具是否存在、内核是否运行及应用是否能用代理。订阅与配置按敏感数据处理，探测不以放宽目录权限为前提。

### <a id="installation-permissions"></a>安装目录与非特权探测

一种系统级部署把安装根目录放在 `/opt/clashctl`，由 `root:root` 持有，权限为 `0700`。普通用户访问内部路径会得到 `Permission denied`；把读取错误当作“没有这个目录”，或仅凭 `test -e /opt/clashctl/<子路径>` 返回失败，都会误判未安装。上游默认安装位置由用户主目录推导，可由 `CLASHCTL_HOME` 覆盖；系统级路径与整树 root-only 是该部署的选择。

> 上游的默认目录与敏感数据保护见 [安装位置](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/install.sh#L966-L980)及 [数据目录权限](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/install.sh#L850-L870)。`/opt/clashctl` 的 `0700` 属系统级包装部署核对结果。

该系统级部署有独立的非特权可见面：

| 对象 | 已核对权限或内容 | 能支持的判断 |
|---|---|---|
| `/usr/local/bin/clashctl` | `0755` 的可执行包装脚本 | 可以读取入口如何定位安装根、分发命令及提权；文件存在不证明内核在线 |
| `/etc/profile.d/clashctl.sh` | `0644` 的 shell 集成文件 | 可以读取函数定义与加载逻辑；实际 shell 仍可能被后续同名函数覆盖 |
| `/etc/clashctl-shell.env` | `0644` 的公开代理导出文件 | 可读取无认证代理参数；只包含允许公开的值，不能用来保存代理密码或订阅凭据 |
| systemd unit 与 drop-in | `ExecStart`、`ExecStartPre`、PID、状态 | 可以确认哪个二进制、资源目录及运行配置被托管；按具体权限读取 |
| 实际监听与控制器响应 | 例如 `127.0.0.1:7890` mixed-port、`127.0.0.1:9090` controller；未带 secret 查询 `/version` 返回 `401` | 监听仅证明有进程接收连接；该 `401` 仅证明 HTTP 端点要求认证，安装身份还需其他证据 |

只读盘点直接使用文件元数据和服务管理器，不调用未知包装器：

```bash
stat -c '%U:%G %a %n' /opt/clashctl /usr/local/bin/clashctl \
  /etc/profile.d/clashctl.sh /etc/clashctl-shell.env
systemctl show mihomo.service -p ActiveState -p SubState -p MainPID \
  -p FragmentPath -p DropInPaths -p ExecStart -p ExecStartPre
ss -ltn
```

上述部署的 `ExecStart=/opt/clashctl/bin/mihomo -d /opt/clashctl/resources -f /opt/clashctl/data/runtime.yaml` 将资源目录与生成运行配置分离，不能仅按 `-d` 猜活动配置。其 drop-in 还在启动前用相同 `-d`、`-f` 加 `-t` 校验配置。必要时用 `systemctl cat mihomo.service` 读取 unit 与 drop-in，输出前遮蔽其中可能存在的敏感值；进程元数据不可读时，保留权限不足这一判断，不自动提权或改权限。

### <a id="shell-entrypoints"></a>shell 入口与部署包装器

Bash 中先运行 `type -a clashctl`，需要区分函数与可执行文件时用 `type -t clashctl`、`type -P clashctl`；发现函数后用 `declare -f clashctl` 查看当前生效的函数体。外部 `which` 通常只搜索 `PATH`，不能代替函数检查。Zsh 中用 `whence -f clashctl` 核对函数，再检查相应启动文件的加载顺序。

已核对的系统级 profile 只定义函数并导出 `CLASHCTL_HOME`，加载本身不启用代理。同一 shell 中后定义的同名函数会覆盖先前定义。例如 `/etc/profile.d/clashctl.sh` 先定义基础函数，`~/.bashrc` 加载它后又再次定义同名函数；仅加载系统 profile 的另一个用户或 Zsh 会得到不同逻辑。因此要核对当前函数体和完整加载链，不能只比较可执行文件路径。安装根目录由实际入口及 `CLASHCTL_HOME` 确认。

在已核对的系统级包装部署中，下列行为需要分开看：

| 调用路径 | 提权与副作用 |
|---|---|
| 普通用户执行包装器的 `status`、`--help`、`--version`、`on --help` 等 | 会先 `exec sudo`，未带 `-n`；可能等待密码，不能作为非特权只读探查 |
| shell 前端处理的 `off`，不带 `--stop`，以及 `off --help` | 在 shell 函数内处理，不进入上述提权路径；仍须以当前函数定义为准 |
| `--shell-on` | 仅在目标服务已 active 时直接读取导出文件；停机时会调用 `start` 并进入提权路径，详见 [静默环境注入](#shell-injection) |
| root 分发的 `on`、`off` 分支，包括 `on --help` | 不调用环境文件刷新逻辑；其他副作用依具体子命令 |
| root 分发的其余命令，成功返回时 | 调用 `_refresh_shell_proxy`，即使命令是 `status`、`--help` 或 `--version`，也可能重写环境文件 |

> 系统级包装部署核对：刷新先在 `/etc/` 下 `mktemp`，以 `printf 'export %s=%q\n'` 生成导出语句，再 `chmod 0644`、`mv` 原子替换 `/etc/clashctl-shell.env`。这属于额外包装层，不归因于公共上游提交。`on|off` 分支与其他成功命令的差异也不能外推到其他部署。

只读排查先读可访问的脚本，再查 `systemctl`、监听和进程元数据。命令名称中带有 `status` 或 `help` 不能替代副作用核对，自动化也不能依赖隐藏 stderr 来绕开交互提权。

### <a id="entry-migration"></a>用户级与系统级入口迁移

从 `$HOME/.clashctl` 迁到系统级安装后，旧 `CLASHCTL_HOME=$HOME/.clashctl` 加载块可能仍在 `~/.bashrc` 定义同名函数。表现为交互终端的 `clashctl sub` 访问旧目录、显示陈旧订阅，而可执行文件查询仍找到 `/usr/local/bin/clashctl`。

迁移时先确认新入口和配置确实生效，再逐项核对旧用户级 `mihomo.service` 已 inactive、disabled，且没有进程、启动器或配置引用旧目录。状态与自启是独立检查项。获得迁移和清理授权后，按当前集成方式调整启动文件，核对新开 shell 的实际函数体；例如改为加载已审查的 `/etc/profile.d/clashctl.sh`。需要清理的旧目录与用户 unit 用 `trash-put` 移入回收站，再对相应用户 manager 执行 `daemon-reload`。保留可恢复的原配置，不把禁用 unit 当成所有旧进程均已退出的证据。

## <a id="subscriptions"></a>订阅与配置生命周期

clashctl 管理订阅输入、配置合成与服务切换。内核的 proxy-provider 装载、筛选和节点覆写能力由 [Provider 与内核配置边界](mihomo.md#providers)解释；这里处理送入内核之前的整份配置及其持久来源。

### <a id="config-lifecycle"></a>原始订阅、Mixin 与运行配置

将配置区分为原始订阅、持久基础配置与 Mixin、生成的 `runtime.yaml`，以及内核内存中的运行态。clashctl 按自己的合成规则把持久输入组合为运行配置；规则、节点与节点组有专门的合并处理，不能把它理解为任意 YAML 的通用深合并。

| 层次 | 维护方式 |
|---|---|
| 原始订阅或本地 profile | 保存来源、名称与更新方式；远程刷新会重新取得该来源的数据 |
| 基础配置与 Mixin | 保存托管所需的持久调整；先核对覆盖顺序及作用于哪些 profile |
| `runtime.yaml` | 由管理工具生成并传给内核；直接修改可能在下次合成时被覆盖 |
| 内核运行态 | API 切组、改模式或 PATCH 的结果；是否写回持久输入需另行处理 |

> 配置合成与服务处理见 [合并实现](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/lib/config.sh#L153-L267)和 [合成后的服务处理](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/lib/config.sh#L275-L300)。内核 API 的持久化边界见 [配置热重载](mihomo.md#config-reload)。

长期调整应落到实际版本支持的持久输入，生成后用与服务相同的资源目录和配置路径校验。GUI 的 profile、merge、script 与生成链由该 GUI 管理，见 [GUI 配置链](mihomo.md#gui-config-chain)，不把其他客户端的文件格式套给 clashctl。

### <a id="subscription-operations"></a>订阅导入、更新与切换

| 操作 | 固定上游快照中的含义 | 验收重点 |
|---|---|---|
| `sub add` | 保存订阅，默认不启用 | 名称、来源、原始内容与权限；保存成功不等于运行中配置已变 |
| `sub use` | 选定订阅，处理配置校验、合成和服务重启 | 实际生成文件、服务状态、监听和新连接；可能影响共享应用 |
| `sub update` | 重新获取已登记的订阅来源 | 来源可达、内容变更与合成结果；可能覆盖直接修改的订阅数据 |

> 见 [订阅保存](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/sub.sh#L480-L575)、[订阅切换](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/sub.sh#L794-L879)和 [订阅刷新](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/sub.sh#L1004-L1026)。具体参数和本地文件导入方式按实际安装源码核对，不假定所有版本支持同一种 `file://` 写法。

操作前记录当前启用项、持久输入和可恢复的内核版本，确认切换或重启的影响范围。订阅操作是配置写入与服务操作，不等同于内核 API 的 selector 切换；裸 `sub` 还可能进入交互流程。下载、校验或切换失败时，停止后续切换，核对磁盘启用记录、运行文件和实际进程是否一致，再按已确认的恢复路径处理。

### <a id="relay-profile"></a>中转订阅的派生与回退

当本机无法直达订阅节点入口、已有私网可达的中转主机能够访问上游时，保留原订阅，基于它生成独立 `<relay-sub>`。网络架构、私网监听与四层映射见 [受限网络下的私网中转](mihomo.md#private-relay)；本节负责派生物如何保存、启用、更新与回退。

派生时先建立节点标识与中转端点的对应关系，只修改有明确映射的节点 `server`、`port`，指向 `<私网IP>` 及对应监听端口。保留节点名称、组引用、鉴权字段、原 TLS 验证身份与客户端指纹，以及 WS Host/path 等协议字段；部分协议用 `servername`，部分用 `sni`，按节点类型核对。没有映射的节点显式选择保留原入口或从派生物排除，同时维护组引用，不能全局替换所有 `server`、`port`。

> 改连接地址后如何保留上层协议身份见 [四层端口段映射](mihomo.md#relay-port-mapping)。TCP 中转不自动承载 UDP/QUIC；不要通过关闭证书校验来掩盖身份字段丢失。

| 托管方式 | 更新与回退的取舍 |
|---|---|
| 直接修改原远程订阅保存的数据 | 操作少，但下一次 `sub update` 或定时刷新可能覆盖改写；回退也更难辨认 |
| 独立的本地派生快照 `<relay-sub>` | 原订阅保留，便于切回；快照不会自动跟随上游新增节点、端点或凭据变化 |
| 从原订阅执行受控变换后再生成派生物 | 可以跟随上游，但须维护映射、字段校验和失败处理；每次生成后都要校验并验收 |

独立改名并不保证不被刷新覆盖。检查 `<relay-sub>` 登记的来源、更新任务与生成链，确保不会从原远程 URL 直接取回未经中转改写的内容。若用 Mixin 表达调整，先确认其能精确作用于目标节点且范围合适；全局 Mixin 可能影响其他 profile。

按当前版本已核对的本地导入方式保存派生物，先校验，再在获准窗口启用。验证实际节点端点、规则链、新连接和必要的既有 SOCKS 监听，衔接 [中转链路验证](mihomo.md#relay-validation)。上游更新时重新取得原订阅，按映射再生成、校验派生物；失败时保留最近一次有效版本。直连恢复或中转不可用时，按订阅切换流程选择原订阅并重验新连接；原路径仍受阻时，切回只恢复原配置，不保证恢复连通。

## <a id="proxy-layers"></a>内核、shell 与应用

| 层次 | 要核对的对象 | 与其他层的关系 |
|---|---|---|
| 代理内核 | 进程、配置、实际监听和出站规则 | 内核存活才可能接受连接；active 和监听不证明目标可达 |
| 当前 shell | 已导出的代理变量与值 | 影响此后从该环境启动、且未被覆盖的进程 |
| 实际应用 | 请求进程、网络库、显式代理设置和绕过规则 | 继承变量后，还要确认客户端实际采用了它们 |

子进程通常继承父进程已导出的环境；启动器使用 `env_clear`、显式替换环境、权限切换，或应用不支持代理变量时，要沿真实启动链核对。终端中的 `curl` 成功只覆盖该客户端和当时的环境。

常驻程序在启动时获得环境快照。新终端执行代理开关或修改启动文件，不会更新已经运行的 daemon。先找到真正发请求的进程和启动者，再核对它的环境、启动时间及显式代理设置；需要重启时，在任务空闲并获得授权后按其实际管理归属处理。

> 编码工具的前端可能连接早已运行的后台，后台也可能由服务管理器启动。具体后台发现、账号隔离和子进程策略继续读取 `harness` skill。

## <a id="proxy-variables"></a>代理变量与入口协议

| 变量 | 作用与检查点 |
|---|---|
| `http_proxy` / `HTTP_PROXY` | HTTP 目标的代理；大小写是不同变量，支持情况由客户端决定 |
| `https_proxy` / `HTTPS_PROXY` | HTTPS 目标的代理；变量名描述目标协议，值可以是 `http://` 代理入口 |
| `all_proxy` / `ALL_PROXY` | 部分客户端在没有协议专用代理时采用的兜底，不能覆盖所有客户端或专用设置 |
| `no_proxy` / `NO_PROXY` | 绕过代理的主机、域名或地址列表，匹配语法与优先级依客户端而异 |

先核对实际监听和应用支持，再修改变量。含用户名、密码或私密参数的代理 URL 不写入示例、公开环境文件、日志或报告。

### <a id="proxy-url-schemes"></a>HTTP、SOCKS 与域名解析

Mihomo 的 mixed-port 接受 HTTP 与 SOCKS，监听机制见 [mixed-port 与 TUN](mihomo.md#mixed-port-tun)。代理 URL 的 scheme 选择客户端到入口使用的协议：

- `http://` 表示 HTTP 代理；HTTPS 目标通常经 CONNECT 建隧道，目标 TLS 仍由客户端校验。
- `socks5://` 在 curl 中由客户端本地解析目标域名。
- `socks5h://` 在 curl 中把目标域名交给 SOCKS5 代理解析；其他网络库需核对是否支持此 scheme。

> curl 的具体行为见 [代理协议](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/proxy.d#L14-L27)、[SOCKS5 本地解析](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/socks5.d#L13-L25)和 [SOCKS5 代理解析](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/socks5-hostname.d#L13-L25)。HTTP/SOCKS5h 改变入口协议及解析路径，超时仍按连接、DNS、TLS、规则和上游响应分层检查。

以下仅用于已决定使用本地 mixed-port、且已确认无认证回环监听为 `7890` 的应用启动环境；端口按部署替换，已有有效设置按应用需求保留：

```bash
export http_proxy='http://127.0.0.1:7890'
export https_proxy="$http_proxy"
export all_proxy='socks5h://127.0.0.1:7890'
export HTTP_PROXY="$http_proxy" HTTPS_PROXY="$https_proxy" ALL_PROXY="$all_proxy"
```

> curl 8.5.0 对其支持的大小写变量优先采用小写；HTTP 代理仅接受小写 `http_proxy`。`ALL_PROXY` 是协议专用代理未设置时的兜底，`NO_PROXY` 可覆盖显式 `--proxy`。见 [curl 环境变量](https://github.com/curl/curl/blob/curl-8_5_0/docs/cmdline-opts/page-footer#L6-L42)，这些优先级不能直接外推到所有 SDK。

### <a id="bypass-variables"></a>no_proxy 与 NO_PROXY

绕过列表按目标客户端支持的语法写入回环地址、所需私网范围和域名。CIDR、后缀与端口匹配的支持各不相同；curl 的 CIDR 支持自 7.86.0 加入。宽泛后缀、私网网段或 `*` 会使相应目标直连，应按实际需要设置并验证。

两份变量应表达同一已确认策略。已有非空值时保留；仅有一份时复制给空的另一份；两份都空时才补最小回环集：

```bash
if [ -z "${no_proxy:-}" ]; then
    export no_proxy="${NO_PROXY:-localhost,127.0.0.1,::1}"
fi
if [ -z "${NO_PROXY:-}" ]; then
    export NO_PROXY="$no_proxy"
fi
```

如果两份非空值冲突，先核对来源、客户端优先级和应有范围，再决定如何对齐，不能无条件用其中一份覆盖另一份。修复异常代理端口时也保留已有完整绕过列表，避免把内网网段和后缀清成仅回环。

### <a id="port-fallback"></a>代理端口回退与存量进程

上游 `set_system_proxy` 从 `runtime.yaml` 提取 `mixed-port`、`port` 和 `socks-port`，用 `${http_port:-${mixed_port}}`、`${socks_port:-${mixed_port}}` 生成地址。Bash `:-` 只在变量未定义或为空时回退，字符串 `"0"` 不为空。因此显式的 `port: 0`、`socks-port: 0` 可导出无效 `http://127.0.0.1:0` 或 `socks5h://127.0.0.1:0`，系统级包装器刷新导出文件时也可能把它们写进去。

> 来源：[端口提取与回退展开](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/on.sh#L32-L52)。

仅使用 mixed-port 时，在实际持久输入中省略这些值为 `0` 的专用端口项并核对合成结果即可，不必在 `~/.bashrc` 额外套一层修补 `:0` 的包装函数；若需在当前环境手工修正异常代理变量，注意保留已有非空的 `no_proxy` / `NO_PROXY`。切换订阅时还要核对已运行进程是否持有独立 `socks-port` 的 `ALL_PROXY`（例如旧监听为 `7891`）；在这些进程获准重启或迁移前保留对应监听，修改环境文件不会改掉它们的已有环境。

## <a id="shell-integration"></a>shell 代理集成

shell 中的代理开关会影响后续应用的启动环境；部署包装器还可能启动或停止内核。交互开关和非交互注入分别核对，不能把“只需导出变量”当成实际命令没有服务副作用。

### <a id="shell-on-off"></a>代理开关与内核生命周期

| 上游入口 | 源码行为 | 操作边界 |
|---|---|---|
| `clashctl on` | 先调用内核启动入口，再导出当前终端代理变量 | 可能启动内核；需确认权限与影响范围 |
| `clashctl off` | 清除当前 shell 大小写 HTTP、HTTPS、ALL 和 NO_PROXY 变量，默认保留内核 | 已运行的子进程保留原环境 |
| `clashctl off --stop` | 清除变量后调用内核停止入口 | 影响共享该内核的应用，须先协调 |

> 见 [开启入口](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/on.sh#L3-L16)、[变量导出](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/on.sh#L32-L67)与 [关闭及停止选项](https://github.com/nelvko/clashctl/blob/4ec42a9f33108a16281bdad4eace7ccce94ae3b2/scripts/cmd/off.sh#L3-L29)。额外部署包装器的提权与刷新差异见 [shell 入口与部署包装器](#shell-entrypoints)。

要影响当前 shell，使用已核对的函数或加载机制；单独启动的子进程无法反向修改父 shell 的环境。对系统级和用户级服务的控制，按 [内核服务控制与维护](#service-control)确认实际 manager。

### <a id="shell-injection"></a>静默环境注入

非交互 CLI 或编码工具启动前，交互式 `clashctl on` 的提示文字可能污染标准输出或结构化协议。已核对的系统级包装器提供 `--shell-on` 输出 `export` 语句，但它先检查 `mihomo.service`；服务未 active 时会调用 `start`，普通用户随即进入未带 `-n` 的交互式 `sudo`。

因此 `eval "$(/usr/local/bin/clashctl --shell-on 2>/dev/null)" || true` 可能在持有 PTY、没有免密 sudo 的进程中吞掉密码提示并一直等输入，尚未到达 `|| true`。服务 active 时免提权不等于该接口在所有状态下都可用于无人值守调用。

> 系统级包装部署核对：`--shell-on` 的服务启动分支是额外集成行为。若仍选择调用它，先检查服务 active 及可信导出文件可读，并考虑服务在检查后退出的竞态。需要严格避免进入该提权分支时，直接加载已经核对的导出文件。

环境文件先当数据检查：核对所有者、权限、生成者、变量名及转义形式，确认当前用户和非受信任用户不能改写它或其父目录。`source`、`.`、`eval` 都会执行 shell 代码。下面的 Bash 片段仅用于已决定采用该部署代理、当前没有需要保留的有效代理设置，且脚本与文件已审查可信的启动路径：

```bash
clashctl_env=/etc/clashctl-shell.env
if systemctl is-active --quiet mihomo.service && [ -r "$clashctl_env" ]; then
    . "$clashctl_env"
else
    printf '%s\n' '代理服务未运行或可信导出文件不可读，停止自动注入。' >&2
    false
fi
```

此处直接加载文件，不调用能自动启动服务的包装器；失败时由启动器明确处理，不隐藏错误继续启动依赖代理的应用。服务 active 仍需结合实际监听验证。已有有效代理时保留其设置；遇到 `:0` 端口问题参见 [端口回退](#port-fallback)，`no_proxy` / `NO_PROXY` 按 [绕过列表](#bypass-variables)保留或补齐，不整份覆盖。

上述导出文件使用 Bash `%q`，例如逗号会输出为 `\,`。Bash 的 `source` / `eval` 会正确还原该转义，Zsh 对这类简单导出形式也能还原；完整文件能否跨 shell 加载仍须按实际内容核对。它不是 systemd 环境文件：`export ` 前缀及 shell 的 `%q` 转义不能直接交给 `EnvironmentFile=`，格式转换见 [systemd 与其他启动器](#service-environment)。

## <a id="service-environment"></a>systemd 与其他启动器

由 systemd 启动的应用，在其 service 的 `Environment=` 或 `EnvironmentFile=` 明确声明代理。系统 manager 与用户 manager 有各自的环境来源；`systemctl --user` 不会让服务进程自动继承执行该命令的终端环境。

以下为已授权修改实际应用 service 时的无认证回环代理示例；端口和绕过范围按部署确认，已有内网绕过策略须保留：

```ini
[Service]
Environment="http_proxy=http://127.0.0.1:7890" "HTTP_PROXY=http://127.0.0.1:7890"
Environment="https_proxy=http://127.0.0.1:7890" "HTTPS_PROXY=http://127.0.0.1:7890"
Environment="all_proxy=socks5h://127.0.0.1:7890" "ALL_PROXY=socks5h://127.0.0.1:7890"
Environment="no_proxy=localhost,127.0.0.1,::1" "NO_PROXY=localhost,127.0.0.1,::1"
```

集中维护时用管理员维护的独立 `EnvironmentFile=`，逐行写 `NAME=value`，无需 `export`，不依赖 shell 变量展开。例如绕过项写成 `no_proxy=localhost,127.0.0.1,::1`，而不是把 Bash `%q` 生成的 `export no_proxy=localhost\,127.0.0.1\,::1` 原样搬入。systemd 有自己的转义规则，不能按 shell 执行导出文件。

环境文件在进程执行前读取。修改 unit 后，`daemon-reload` 只重读服务定义；修改文件或 reload 都不会更新运行中进程的环境。是否及何时重启应用，先协调活跃任务并获得授权。

> 见 [环境声明与文件语法](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml#L2704-L2800)、[服务进程环境来源](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml#L3558-L3604)和 [daemon-reload](https://www.freedesktop.org/software/systemd/man/255/systemctl.html#daemon-reload)。环境变量不适合保存高价值秘密；需要代理认证时按应用支持采用受保护的凭据机制，不公开完整 `Environment`。

`After=` 只表达同一 manager 内的启动顺序，不拉起被依赖服务，也不证明端口或外部目标就绪。用户 service 的 `After=mihomo.service` 不能等待另一个系统 manager 的同名服务。先确认双方归属和服务类型，再设计启动依赖、有界的就绪检查以及失败重试；其他 supervisor、容器与桌面启动器也要在实际启动入口声明环境。

> 见 [unit 顺序与依赖](https://github.com/systemd/systemd/blob/v255/man/systemd.unit.xml#L803-L840)。`network-online.target` 也不能代替代理和业务目标的就绪检查。

## <a id="service-control"></a>内核服务控制与维护

先确认内核由系统 manager、用户 manager 还是其他启动器管理，记录实际 unit、二进制、启动参数、持久输入及生成配置。查询状态直接用正确 manager 的只读接口；停启、重启、订阅切换和内核更新按共享应用的影响范围授权。

已核对的系统级部署用启动前校验防止无效配置反复进入主进程启动：

```ini
[Service]
ExecStartPre=/opt/clashctl/bin/mihomo -t -d /opt/clashctl/resources -f /opt/clashctl/data/runtime.yaml
```

`ExecStartPre` 失败会阻止本轮启动，但服务的 `Restart=` 与启动限速仍须单独核对；它不证明网络、订阅入口或目标可达。维护生成配置时先校验实际持久输入和合成结果，再选择管理工具支持的应用方式，避免并行启动另一套内核占用端口。

更新前保留可恢复的旧二进制与配置，核对新版本配置兼容性及服务运行用户的读取权限；失败时按保存的版本和输入恢复。更新命令以实际安装版本为准，不假定所有部署都有统一的升级子命令。维护后重新核对版本、配置路径、监听与新连接。内核 API 的重载和平台重启竞态见 [配置热重载](mihomo.md#config-reload)与 [进程重启](mihomo.md#process-restart)，不能用一个控制 API 返回成功替代服务验收。

## <a id="validation"></a>分层验收

只读盘点按下表收集证据；启动、停机、重启、改配置和冷启动演练按实际任务授权。不要用有提权或写盘副作用的 clashctl 包装命令代替只读探查。

| 检查 | 证据与判定范围 |
|---|---|
| 服务当前状态 | 在正确 manager 查询 `ActiveState`、`SubState`、`MainPID`，确认内核当前是否存活 |
| 自动启动策略 | 单独查询 `UnitFileState` 或 `is-enabled`，与 active 分开记录 |
| 配置生命周期 | 核对当前订阅、持久输入、生成配置、进程 `-d` / `-f` 与运行态；保存成功不等于进程已采用 |
| 实际监听 | 对照地址、端口、所属 PID 和应用所在网络命名空间；容器回环地址可能不是宿主回环 |
| 实际进程环境 | 找到真正发请求的 PID 及启动时间，仅提取代理变量白名单，并遮蔽 URI 凭据和私密参数 |
| 实际请求 | 用目标客户端或同网络库的无副作用请求验证代理选择、DNS、TLS、返回码和耗时；通用 HTTP 探针只覆盖所测链路 |
| 冷启动 | 在获准维护窗口，从实际 shell、应用或服务启动路径重验；新 shell 测试不代替服务冷启动，enabled 不代替启动实测 |

代理环境白名单为 `http_proxy`、`https_proxy`、`all_proxy`、`no_proxy` 及对应大写。核查按最小披露处理，不打印完整 `env`、完整 `/proc/<PID>/environ`、完整 service `Environment`、认证文件或订阅。进程初始环境、应用的显式配置、运行时代理对象和实际请求分别核对。

> systemd active 与 enabled 是独立状态，见 [服务启用与启动](https://www.freedesktop.org/software/systemd/man/255/systemctl.html#enable%20UNIT%E2%80%A6)。无模型请求的网络检查不能证明账号额度、模型权限、流式连接或实际模型任务可用；这类验收回到 `harness` skill，并遵循相应任务授权。
