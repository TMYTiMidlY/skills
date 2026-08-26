# Linux 侧疑难杂症

> Linux 服务器、容器、shell 工具链上尚未自成主题的案例先收在这里；某一类攒够两三条就拆成独立文件。

## <a id="nftables-breaks-caddy"></a>公网 VPS 做 UDP 端口段转发后，Caddy 的 HTTPS/TCP 中断

> 2026-04-26 | Linux VPS | Caddy | nftables | GOST | UDP 端口段转发

### 场景

需要在一台有公网 IP 的 VPS 上，把外部访问的 UDP 端口段转发到内网/隧道里的另一台机器，例如：

```text
VPS_PUBLIC_IP:11000-11009/udp -> 10.144.18.10:11000-11009/udp
```

远端机器已有 Caddy 承载 80/443/TCP，目标内网地址通过 `tun0` 可达。起初选择内核 NAT：`prerouting dnat` + `postrouting masquerade`。

### 症状

- UDP NAT 规则看起来成功安装。
- 但开启相关 nftables 配置后，VPS 上的 HTTPS/TCP 服务异常，外部连接 443/80 不可用。
- 不需要 reload 才坏；实测直接 `stop nftables.service` 后 HTTPS/TCP 立刻恢复，因为 `ExecStop=/sbin/nft flush ruleset` 把这次加载的问题规则清掉了。
- UDP 探测也容易误判：`nc -uvz` 对 UDP 没有握手语义，甚至未配置端口也可能显示 succeeded；普通网卡/UDP 计数还会被背景流量污染。

### 排查关键转折

先检查 `nftables.service` 的 unit：

```ini
ExecStart=/sbin/nft -f /etc/sysconfig/nftables.conf
ExecReload=/sbin/nft 'flush ruleset; include "/etc/sysconfig/nftables.conf";'
ExecStop=/sbin/nft flush ruleset
```

这就是关键：为了一个很小的 UDP 转发启用系统级 `nftables.service`，会把“谁在运行时维护了哪些 netfilter 规则”这件事变得不可控。即使转发规则本身只匹配 UDP，服务启动时加载的规则也可能影响同机已有的 HTTPS/TCP 服务链路、NAT 或防火墙状态；而 stop/reload/restart 的 `flush ruleset` 又会清空整套 nft ruleset。

另一个排查坑是 UDP 测试方式：

- `nc -uvz host port` 对 UDP 不可靠，不能当作“服务可用”的证据。
- 看 `/proc/net/snmp` 的 `Udp/InDatagrams` 或网卡 RX 计数，也可能被背景流量干扰。
- 没有 root 抓包权限时，很难证明某个测试 UDP 包确实到了目标应用；最干净还是在 VPS 或目标机上 `tcpdump udp portrange ...`。

### 根因

问题不是 DNAT 规则匹配了 TCP 443，而是为了安装一小段 UDP 转发，启用了会接管整个规则集的 `nftables.service`。这套 service 启动后加载的 ruleset 可能扰动同机已有的防火墙/NAT 状态，于是 Caddy 承载的 HTTPS/TCP 跟着异常；停止 service 后 `nft flush ruleset` 清掉问题规则，反而让连接恢复。

### 解决

先恢复现有 HTTPS 服务链路；如果问题来自刚启用的 `nftables.service`，停止它通常能立刻清掉问题规则：

```bash
sudo systemctl stop nftables
```

如果 Caddy 自身仍在监听但外部不可达，再重启 Caddy 以及相关网络/反代依赖：

```bash
sudo systemctl restart caddy
```

然后不要继续用系统 `nftables.service` 承载这种小转发：

```bash
sudo systemctl disable nftables
```

如果仍想用内核 NAT，推荐创建自己的独立 nft 表，并通过自定义 systemd oneshot 只做 `nft add table/add chain/add rule`，绝对不要 `flush ruleset`，也不要启用会加载 `/etc/sysconfig/nftables.conf` 的 `nftables.service`。

更简单、容易回滚的方案是用 GOST 做用户态 UDP 端口段转发，独立 systemd 服务，不碰 Caddy/nft/iptables：

```ini
[Unit]
Description=GOST UDP forward 11000-11009
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/gost -L udp://:11000-11009/10.144.18.10:11000-11009
Restart=always
RestartSec=3s

[Install]
WantedBy=multi-user.target
```

常用操作：

```bash
sudo systemctl enable --now gost-dst-udp
sudo systemctl status gost-dst-udp
sudo systemctl restart gost-dst-udp
sudo systemctl disable --now gost-dst-udp
```

### 最终验证

改用 GOST 独立 service 后，实测达到目标效果：

- `gost-dst-udp.service` 为 `active` / `enabled`
- VPS 上 `11000-11009/udp` 全部处于监听状态
- 从另一台公网机器向 `VPS_PUBLIC_IP:11000-11009/udp` 发测试包后，GOST 日志显示每个端口都建立了到目标内网地址的转发：

```text
CLIENT_IP:CLIENT_PORT <-> 10.144.18.10:11000
...
CLIENT_IP:CLIENT_PORT <-> 10.144.18.10:11009
```

日志里出现 `inputBytes`，说明公网 UDP 包确实进入 GOST 并被转发到内网目标。测试包没有业务协议语义，目标服务不回包时可能看到 `outputBytes=0`，这不影响“公网 UDP 端口段已经转发到内网地址”的结论。

### 清理注意

如果之前已经写过 nft 配置，清理时只删/移动自己命名的文件和表：

```text
/etc/sysctl.d/99-udp-forward.conf
/etc/nftables/udp-forward-*.nft
/etc/systemd/system/<custom-forward>.service
```

从 `/etc/sysconfig/nftables.conf` 去掉自己追加的 include 行即可。不要执行 `nft flush ruleset`。

写清理脚本时注意 `set -e` + 不存在的文件会直接中断。移动可选文件要用函数包一层：

```bash
move_if_exists() {
  local path="$1"
  if [[ -e "$path" ]]; then
    mv "$path" "$BACKUP_DIR/"
  fi
}
```

### 教训

- 只转发几个 UDP 端口时，别为了省事启用会接管全局 ruleset 的 `nftables.service`。
- 已有 HTTPS/TCP 服务和防火墙/NAT 状态可能互相依赖，任何 `flush ruleset` 都可能制造看似无关的断流。
- UDP 连通性测试不要相信 `nc -uvz` 的 succeeded；需要抓包或应用层协议响应。
- 对“少量端口段转发、优先易恢复”的场景，GOST 独立 service 往往比 nft/iptables 更好维护。

## <a id="docker-embedded-dns"></a>容器解析不了 compose 服务名，IP 直连正常

> 2026-07-05 | Docker Desktop 29.4.2 on WSL2（1810 = `10.144.18.10`）| 涉及 `forgejo_forgejo`、`dmp_default`、`qatlas-postgres_default` 三个 compose 网络

> 记录原则：根因**没有坐实**，只确认了"是什么"和"怎么修"，如实标注。

### 症状

- 自建 Forgejo 的公网 web 入口返回 HTTP 500（Caddy 反代到内网 `http://10.144.18.10:3000`），页面是 Forgejo 自己吐出的"服务器内部错误"（不是 Caddy 502，说明请求已到达应用层，不是反代或证书问题）。
- `docker logs forgejo` 报：
  ```
  failed to connect to `user=forgejo database=forgejo`: hostname resolving error: lookup db on 127.0.0.11:53: no such host
  ```
- 容器内 `getent hosts db` 解析失败；但 `docker exec forgejo nc -zv <db 容器 IP，如 172.x.x.x> 5432`（同一 Postgres 容器在这个 bridge 网络里的实际 IP，`docker inspect <db 容器> --format '{{.NetworkSettings.Networks.forgejo_forgejo.IPAddress}}'` 可查）**直连是通的**——数据库本身健康，稳定跑了 5 周没问题，纯粹是"给个 compose 服务名解析不出来"。

### 排查关键转折

- 第一反应容易误判成"Postgres 挂了"或"网络路由/防火墙坏了"，但 IP 直连成功已经排除这两种可能，问题被精确限定在 DNS 这一层（Docker 每个 bridge 网络自带的内置 DNS `127.0.0.11`）。
- 顺手查了同一台机器上另外两个不相关项目的网络（`dmp_default`、`qatlas-postgres_default`），**同样解析不出各自的 compose 服务名**——说明不是 forgejo 自己配置错了，而是这台机器上"服役较久的网络"整体性地方 DNS 出了问题。
- 关键对照实验：`docker network create dns-test-scratch` 建一个全新网络，挂一次性容器测 DNS，**完全正常**。→ 证明不是 Docker Desktop 整体宕掉，是"存量网络"的内置 DNS 状态损坏，新建网络不受影响。这一步是从"盲猜重启大法"转向"精确定位"的关键。

### 根因

只确认到"存量网络的内置 DNS 状态损坏、新建网络正常"这一层，**没有坐实"为什么会损坏"**。翻了 `dmesg`（当晚无相关内核错误）和 Windows 事件日志找过侧面证据：这台 WSL2 本身 37 天没重启过；但 Windows 宿主过去 14 天里**几乎每晚 21-23 点有一次疑似睡眠/唤醒事件**（`Microsoft-Windows-Kernel-General` Id=1），包括故障当晚 21:07 那次——离用户报告 500 错误就差几小时。"Docker Desktop 在 WSL2 睡眠/唤醒后，存量网络的内置 DNS 状态损坏、新建网络不受影响"是社区里的已知模式，能合理解释现象，但没有 Docker Desktop 自己的崩溃/重启日志、也没有"DNS 从好变坏"的精确时间戳能一锤定音，**只能算最可能的假说，不是实锤结论**。

### 解决

```bash
cd <项目目录> && docker compose down && docker compose up -d
```
重建该项目的 network 即可，对 forgejo、dmp 两个项目一次性有效。数据不受影响（用的是 bind mount `./data:/data`，不是具名 volume，`down` 默认不删数据）。

`qatlas-postgres` 那次 `docker compose down` 连续两次卡在 daemon 级错误 `tried to kill container, but did not receive an exit event`（容器本身仍 running/healthy，没有数据风险），改用 `docker rm -f <name>` 强制移除后再 `docker compose up -d` 解决——这个停止失败究竟是否与本次 DNS 故障同源，没有确凿证据，值得下次复现时留意（也可能是另一件事：见 [Postgres 崩溃恢复卡在 end-of-recovery checkpoint 不动](nas.md#pg-checkpoint-slow)）。

### 教训

- **诊断三件套**：`getent hosts <目标>` 解析失败 + 同目标 IP 直连成功（排除路由/防火墙）+ 全新网络 DNS 正常（排除 Docker Desktop 全局宕机）→ 精确定位到"个别存量网络的内置 DNS 状态损坏"，而不是病急乱投医式地重启整个 Docker Desktop 或宿主机。
- 修复动作本身很轻（`down/up` 重建网络），但**遇到停不掉的容器不要用 `docker kill <name>`**——Copilot CLI 的 bash 工具安全策略会把它当成裸 `kill` 命令拦截（"must specify at least one numeric PID"），需要改用 `docker rm -f <name>`（内部等效于强制 SIGKILL 后移除）。
- 一台机器上一次性检查"是不是所有存量网络都中招"很值——本次三个项目一起中招，如果只查 forgejo 一个，会漏掉 dmp/qatlas-postgres 也需要顺手修。

## <a id="envrc-subdir-links"></a>子仓库 `git status` 冒出几十个 untracked 分发软链

> 2026-07-10 | direnv + git `core.excludesFile` | 工作区根 `.envrc` 向各子仓库分发 Copilot 配置软链

工作区根有个 direnv `.envrc`，里面 `link_into_subdirs` 把根上的 `.agents/skills`、`.mcp.json`、`.github/hooks/safety-net.json`、`.github/instructions/global.instructions.md` 软链分发到**每个直接子目录**（`for sub in "$PWD"/*/`），让每个子仓库各有一份配置。这些分发链本应被工作区级 `core.excludesFile`（`<workspace-root>/.timidly-excludes`）忽略、不进任何 git diff。

### 症状

- 在某个子仓库 `<child-repo>` 里 `git status`，冒出**几十个 untracked**：`<subdir>/.agents/`、`<subdir>/.github/`，遍布该仓库**每一个子目录**，全是本该被忽略的分发软链。
- `core.excludesFile` 确认生效（`git config --show-origin core.excludesFile` 指向 `.timidly-excludes`），但 `git check-ignore -v <subdir>/.agents/skills` 返回 **NOT ignored**。

### 排查关键转折

1. **anchored pattern**：`.timidly-excludes` 里的忽略项大多**含斜杠**（`.agents/skills`、`.github/hooks/safety-net.json`…）。gitignore 语义下，含斜杠的 pattern **锚定到仓库根**——只匹配 `<repo>/.agents/skills`，匹配不到 `<repo>/<subdir>/.agents/skills`。唯一不含斜杠的 `.mcp.json` 是 unanchored、匹配任意深度，所以子目录里的 `.mcp.json` 软链**没**进 `git status`——这一对照正好点出"斜杠=锚定"是漏出主因。
2. **软链指向暴露触发方式**：漏出的软链指向 `<child-repo>/.agents/skills`（上一层），说明 `link_into_subdirs` 是以 `$PWD=<child-repo>` 跑的。但 `<child-repo>` 自己没有 `.envrc`。→ 只可能是**有人在 `<child-repo>` 里手动 `source <workspace-root>/.envrc`**：direnv 正常加载会先 cd 到 `.envrc` 所在目录（`$PWD`=工作区根，只分发到各子仓库根这一层），而手动 `source` 保持 cwd 不变、`$PWD` 停在子仓库里，于是 `for sub in "$PWD"/*/` 把链铺进了子仓库的**每个子目录**，深了一层。

### 根因

两层叠加：

- `link_into_subdirs` 用 `$PWD` 定分发目标；手动 `source` 从子目录执行时 `$PWD` 被错设成该子目录 → 链铺深一层。
- 工作区 `core.excludesFile` 的忽略项 anchored（含斜杠）、只覆盖仓库根那一层 → 深一层的分发链没被忽略 → 漏进 `git status`（unanchored 的 `.mcp.json` 反而被正确挡住，是旁证）。

### 解决

**清理**：先确认要删的全是软链（`find <subdir>/.agents <subdir>/.github -type f` 输出为空 = 无独有实体文件），再 `trash-put` 掉这些 `.agents`/`.github`/`.mcp.json`，根级 canonical 不动。

**防复发**：给 `link_into_subdirs` 加 early-return guard——用 `${BASH_SOURCE[0]}` 解析出 `.envrc` **自身所在目录**，只有当前 `pwd -P` 等于它才分发，否则跳过并打一行提示：

```bash
link_into_subdirs() {
  local src="$1" rel="$2" sub target root
  [[ -e "$src" ]] || return 0
  root="$(cd "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
  if [[ -n "$root" && "$(pwd -P)" != "$root" ]]; then
    [[ -n "$_warned" ]] || { echo "envrc: cwd '$(pwd -P)' != workspace root '$root'; skip link_into_subdirs" >&2; _warned=1; }
    return 0
  fi
  for sub in "$PWD"/*/; do ... done
}
```

- direnv 正常加载：cd 到 `.envrc` 目录 → `pwd==root` → 照常分发。
- 手动 `source` 从子目录：`pwd!=root` → 跳过 + 提示，不再乱铺。
- **fail-safe**：`${BASH_SOURCE[0]}` 取不到 → `root` 空 → 条件为假 → 落到"照常跑"，绝不误伤正常 direnv 流程。
- guard 放函数内，未来新增的分发调用自动受保护。

#### 测试踩坑

验证 guard 时若**从一个空临时目录** `source` 真 `.envrc`，会得到假的"没跳过也没分发"假象——因为函数在 guard **之前**有 `[[ -e "$src" ]] || return 0`，空目录里 `$PWD/.github/...` 不存在 → 到达 guard 前就早退了。必须**构造带真实 `.github/hooks/safety-net.json` 等源文件 + 一个 child 子目录**的假仓库来测：source 真文件（cwd≠真根）应打印提示且 child 下 0 链；source 副本（cwd=副本自身根）应无提示且 child 下生成 4 条链。

## <a id="npm-idealtree-slow"></a>`npx` 长时间停在 `idealTree`，约 15 分钟后才开始监听

> 2026-08-23 | Linux | Node.js | npm/Arborist | `npx @deepseek-ai/dsh` | 大型 peer-dependency 图

### 症状

执行：

```bash
npx --yes @deepseek-ai/dsh@latest web
```

很长时间没有 stdout，目标端口也没有监听；npm 进程持续吃掉约一个 CPU 核，debug log 停留在：

```text
silly idealTree buildDeps
```

隔离测试在 95 或 150 秒终止时，`_npx` 安装树仍为 0 文件，看起来与死循环或不收敛完全一样。测试命令先发终止信号、再等待 5 秒强制结束，因此最终的 137 是测试器杀进程的结果，不是 OOM 证据。

同一命令后来在真实用户环境中最终成功：

```text
npm warn deprecated node-domexception@1.0.0: Use your platform's native DOMException instead
dsh web: http://127.0.0.1:3080
dsh web: opening the default browser; pass --no-open to disable
```

这迫使结论从“npm 求解卡死/不收敛”改成“npm 求解极慢且没有进度反馈；至少这次最终收敛”。

### 两轮环境不能混为一谈

未在测试期限内完成的隔离实验使用 Node 24/26、npm 11.17.0、独立 HOME/cache/npmrc；成功的现场使用 Node 22.23.1、npm 11.18.0 和真实用户 cache，`@latest` 当时解析为 `dsh@0.1.1-rc.2`。多个变量一起变化，因此不能把成功归因于某一个 Node/npm 版本或 cache 状态；同样，也不能用前一组 150 秒结果外推所有环境永久不收敛。

### 排查关键转折

#### 1. 以父子进程启动时间测“安装耗时”，不要拿仍在运行的父进程 elapsed 当启动耗时

成功现场的进程链是：

```text
bash
└─ npm exec @deepseek-ai/dsh@latest web
   └─ sh -c 'dsh' web
      └─ node ~/.npm/_npx/<hash>/node_modules/.bin/dsh web
```

Web 服务会常驻前台，所以几小时后 `npm exec` 仍活着是正常的。真正有判别力的是 npm 父进程与 dsh 子进程的内核 start tick：两者相差 89,019 tick，本机 `CLK_TCK=100`，即 **890.19 秒（14 分 50.19 秒）**。这段才是从敲下命令到 npm 终于执行 dsh 的时间。

#### 2. 用 `_npx` 文件 birth time 把依赖求解与落盘分开

同一现场的时间线：

| 事件 | 时间 |
|---|---|
| `npm exec` 进程启动 | 02:19:01 |
| npm debug log 创建 | 02:19:03.076 |
| `_npx/<hash>/node_modules` 创建 | 02:33:39.717 |
| `node_modules/.bin/dsh` 创建 | 02:33:52.769 |
| dsh Node 子进程启动 | 02:33:52 |
| npm debug log 最后写入 | 02:33:52.921 |

也就是说，前约 14 分 39 秒连 `node_modules` 目录都没有；安装树只在最后约 13 秒出现。`0 files` 在这个阶段不能说明 npm 没工作，因为依赖图求解主要发生在内存里。

#### 3. TCP 活动给“真正监听”建立上界

Linux 不暴露监听 socket 的墙钟创建时间，事后无法精确还原 `listen()` 到毫秒。但同步采样时，dsh 进程年龄为 22,782 秒，一条从初始页面保留下来的 TCP 连接距最后一次发送为 22,778.996 秒；该连接在 dsh 启动约 3 秒后已经发送数据，服务必然更早开始监听。因此从 npx 启动到监听可收紧为约 **14 分 50 秒至 14 分 53 秒**，而不是把 dsh 常驻数小时的 elapsed 当作启动耗时。

#### 4. CPU 时间与日志共同把慢点定位在 npm 阶段

应用子进程启动前，npm 父进程累计约 14 分 54 秒 CPU，接近整个等待窗口；dsh 启动后几秒内已有 HTTP/TCP 活动。npm debug log 又在早期进入 `idealTree buildDeps`，而安装树直到最后十几秒才落盘。综合证据说明绝大多数延迟发生在 npm 的依赖树构造阶段，而不是 DSH 自身启动或端口监听。

### 已坐实与未坐实

已坐实：

- 这次成功运行从 npx 到监听约需 14 分 50～53 秒。
- 延迟主体位于 npm 执行 dsh 之前；dsh 自身数秒内可服务。
- 95/150 秒超时不足以证明永久不收敛。
- `exit 137` 来自测试器的强制结束时，不能据此诊断 OOM。

仍未坐实：

- Arborist 究竟慢在哪一条 peer-dependency 环、哪一轮 fixed point，尚无 profiler 或源码级证据。
- Node 22/npm 11.18、真实 HOME、混合 cache 中哪个因素让这次最终完成，现有对照不能拆分。
- “全命中 cache 仍慢”只能排除纯下载瓶颈，不能单独证明某个具体求解器 bug。

### 处置

如果目标是判断“会不会最终完成”，超时窗口必须覆盖已观测的 15 分钟量级，并同时观察 CPU、npm debug log、`_npx` 安装树与目标端口；150 秒只够确认体验很差，不够判定不收敛。不要先清空 `~/.npm`：cache 与依赖图求解是两层问题，清 cache 会丢掉可复用下载，却未必缩短 `idealTree`。

如果目标是尽快可用，不值得为证明 npm 最终会完成而等 15 分钟。Linux 实测同版本 `pnpm dlx` 冷启动约 47 秒，第二次约 1.028 秒，并能正常启动 Web 与创建 PTY；长期运行则用项目本地 pnpm 安装加 lockfile。这个结论只覆盖 `pnpm dlx`/本地安装，不能外推到 `pnpm add -g` 的链接布局。

### 教训

- **超时是删失数据，不是失败类型。** “150 秒时仍在 idealTree”只说明完成时间大于 150 秒；没有更长观察或求解器终止证据，不能写成“不收敛”。
- **先分 npm 与应用。** 父子进程 start tick、可执行文件 birth time、端口首次活动能把“安装慢”和“服务启动慢”拆开。
- **安装树为 0 不等于无进展。** Arborist 可以长时间只在内存中算图，最后才集中落盘。
- **137 先查是谁发的 SIGKILL。** 若测试器明确在宽限期后强杀，就不要再拿它猜 OOM；OOM 需要内核日志或 cgroup 证据。
- **修正文案要保留原始观测。** 正确改法是把“卡死”降级为“在测试窗口内未完成”，不是反过来否认当时单核、无 stdout、无端口、安装树为空这些真实现象。
