# DeepSeek Harness（dsh）运行时

本文从使用者和集成者视角说明 DeepSeek Harness 的产品定位、安装与运行、Cordis 插件框架、Agent 执行、内置扩展、程序化入口和权限边界。本文只给出安装、卸载和选择工作模式所需的插件概念；插件怎样组成运行环境、叠加配置、协作和清理，以及怎样开发和分发，见 [DeepSeek Harness Plugin 开发](dsh-dev.md)。现成扩展与社区项目见 [DeepSeek Harness Plugin 调研记录](dsh-plugin-research.md)。

## <a id="product-position"></a>产品定位

DeepSeek Harness（`dsh`）是 DeepSeek 开源的 agent harness（把模型、工具调用、会话、权限和界面组织成可执行 Agent 的运行壳）。它建立在 Cordis 插件框架上：模型适配、system prompt、工具、agent loop、Session、持久化、沙箱、审批和界面可以独立组合，由不同运行配置选择实际启用的能力。

项目处于 developer preview（开发者预览），会继续发生兼容性破坏；Session 格式也没有跨版本兼容承诺。仓库采用 MIT 许可，官方安装入口是 npm 包 [`@deepseek-ai/dsh`](https://registry.npmjs.org/%40deepseek-ai%2Fdsh)。

> 来源：[DeepSeek Harness 的产品定位、预览状态、运行入口与许可](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/README.md#L5-L57)；[Cordis 插件框架的核心概念](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/cordis-primer.zh.md#L1-L13)。

## <a id="install-and-run"></a>安装与运行

运行要求是 Node.js `^22.19.0 || >=24.0.0`。npm 包提供已经构建的 CLI；源码 checkout 需要先生成 Host、Client 和前端产物。没有版本号的包规格会跟随 registry 的 dist-tag，显式的 `<version>` 则固定这次安装或运行所用的发布版本。

### 安装方式

| 安装方式 | 命令 | 依赖解析时机 | 使用场景 |
|---|---|---|---|
| npm 临时运行 | `npx @deepseek-ai/dsh@<version> web` | 尚无可复用的 `_npx` 安装树时 | 官方快速启动入口 |
| pnpm 临时运行 | `pnpm dlx @deepseek-ai/dsh@<version> web` | 尚无对应的 dlx 临时项目时 | 临时验证；当前发布版已通过 Linux Web 与 PTY smoke test |
| npm 全局安装 | `npm install --global @deepseek-ai/dsh@<version>`，随后运行 `dsh web` | 安装或升级阶段 | 需要固定可执行路径的服务 |
| 源码构建 | `pnpm install && pnpm run build`，随后运行 `pnpm dsh web` | checkout 的安装与构建阶段 | 源码开发、锁文件复现或源码审计 |

源码模式以仓库根 `package.json` 的 `packageManager` 字段确定 pnpm 版本。`pnpm run build` 生成 CLI 所需的 Host、Client 和前端产物；`pnpm dsh web` 使用已有产物。

> 来源：[官方 npm 与源码运行方式](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/README.md#L13-L37)；[Node 与 pnpm 版本约束](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/package.json#L1-L10)；[CLI 的可执行入口](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/package.json#L11-L18)。

#### npm 首次安装异常

本节记录 dsh 预发布版本曾出现的一类 npm 首次安装异常：`npx` 在建立 `_npx` 安装树时长时间没有进度。它是一段历史取证，用于保留当时的症状、定位过程、证据边界和失败 workaround；当前环境是否复现需要另行验证。正常完成安装后，同一 cache 与 package spec 下的后续 `npx` 调用可以复用安装树，`npm install -g` 也只在安装或升级时解析依赖。

| 实测 | 条件 | 结果 |
|---|---|---|
| 隔离 `npx --yes @deepseek-ai/dsh@0.1.1-rc.2 --version` | Node 24、npm 11.17.0、Arborist 9.8.0、独立 HOME 与空 cache | 150 秒观察窗内未完成，停在 `idealTree`，`_npx` 安装树仍为空 |
| 更换 Node 后重复 | Node 26；npm、npx、Arborist 版本及相关文件哈希与上一轮相同 | 155 秒内仍未完成，安装树仍为空 |
| 复用上一轮下载 cache | 128 个 cache hit、0 个 miss | 95 秒内仍停在相同阶段；下载命中没有跳过依赖树构造 |
| 真实用户环境首次运行 | Node 22.23.1、npm 11.18.0、已有混合 cache | 最终成功；npm 父进程启动约 14 分 50 秒后才出现 dsh 子进程，dsh 自身启动只占最后几秒 |

同一套隔离测试还覆盖了从 `0.0.1-rc.1` 到 `0.1.1-rc.2` 的多个版本；除早期版本另有未发布 package 的 404 外，其余版本都在 150 秒观察窗内停留于 `idealTree`。当时记录到的慢解析跨越多个预发布版本，最后一次核对落在 `dsh-v0.1.1-rc.2`。

当时的运行状态把耗时进一步定位到 npm：进程持续占用约一个逻辑核，磁盘计数停止增长，npm timing 最后停在 `idealTree:buildDeps` 与 `placeDep ROOT @deepseek-ai/dsh-base`。一段 Node Inspector CPU profile 中，`URL`、Arborist 的 `getBundler` 和 `SemVer` 占主要 self samples；调用链集中在 `CanPlaceDep → satisfiedBy → depValid` 与 `canPlacePeers → inBundle → getBundler`。

当时核对的 `0.1.1-rc.2` 内部依赖闭包包含 199 个 package、1472 条内部边，其中 1138 条是 peer dependency；`@deepseek-ai/cordis` 被 192 个内部包引用，图中还存在强连通环。这些观测把瓶颈定位为 Arborist 在 CPU 上反复进行 peer placement、bundle 归属与 package spec/semver 判断；具体哪一条 peer 环或哪一次 fixed point 决定总耗时，当时没有锁定。

几组对照进一步限定了当时的结论：Node 24 与 26 的相同 npm/Arborist 实现都出现慢解析，单独更换 Node 没有消除现象；只有下载 cache、尚无完整 `_npx` 安装树时，npm 仍会重建 `idealTree`；真实环境最终成功则说明求解可以收敛。当时能确认的是“首次依赖树构造曾出现极慢且缺少进度反馈的异常”，具体触发条件没有归因到单一变量。

当时用 `legacy-peer-deps` 绕过 peer placement，可以在约 67 秒内完成安装，却在启动时缺少 `@deepseek-ai/cordis-plugin-group`：`dsh-app-boot` 会静态 import 该包，而 manifest 只把它声明为 peer，跳过 peer 安装便没有补齐运行时依赖。`install-strategy=nested`、`shallow` 与隔离 npm 12 也没有在各自观察窗内完成。作为另一条包管理器路径，`pnpm dlx` 的冷 store 用时约 47 秒、热 store 约 1 秒，并通过 Web 与 PTY smoke test；这项对照只验证了当时的 pnpm 路径可用。

当时的官方 packed-install gate 把所有 workspace tarball 同时列为顶层依赖，预先满足了许多 peer，也补齐了按包名动态加载的 package；普通用户只安装 `@deepseek-ai/dsh` 时解析的是另一张依赖图。因此这份历史记录把 packed-install CI 与单包 consumer 视为两个独立的验证边界。

> 来源：[官方安装入口](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/README.md#L13-L37)；[`dsh` 聚合包依赖](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/package.json#L20-L103)；[`dsh-app-boot` 的 peer 声明](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/boot/app-boot/package.json#L31-L61)；[packed-install consumer 的构造](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/scripts/release/verify-packed-install.ts#L88-L109)；相关用户报告见 [Discussion #176](https://github.com/deepseek-ai/deepseek-harness/discussions/176)、[#223](https://github.com/deepseek-ai/deepseek-harness/discussions/223) 和 [#1032](https://github.com/deepseek-ai/deepseek-harness/discussions/1032)。

### 安装脚本授权

普通 npm 安装使用官方命令即可；`@deepseek-ai/dsh` 本身不要求用户把一批依赖手工加入 `--allow-scripts`。npm 的该选项是 lifecycle script（安装期脚本）白名单，授权对象应是实际拥有脚本、且部署确实需要执行脚本的依赖。

源码构建使用仓库自己的 pnpm 策略。固定 tag 中的 `pnpm-workspace.yaml` 记录已经审核的 `allowBuilds` 条目，也显式拒绝随依赖带入但不需要执行的脚本；部署直接沿用该文件，避免把 npm warning 翻译成另一套全量授权。

> 来源：[官方源码的 `allowBuilds`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/pnpm-workspace.yaml#L35-L55)。

### Web 与 headless

| 运行形态 | 启动方式 | 适用场景 |
|---|---|---|
| Web | `dsh web` 或 `dsh --profile web` | 交互式会话、设置、trajectory 和 Plugin UI；默认监听 `127.0.0.1:3080` |
| headless | `dsh --profile headless "<task>"` | 一次性任务；等待 Agent idle 后输出最后一条 assistant 文本，不启动 HTTP 服务 |

`dsh web` 和 `dsh --profile headless` 都把启动命令所在目录设为 Agent 的默认 workspace。先进入目标项目再启动 dsh，Agent 的相对文件路径和命令便以该项目目录为起点：

```sh
cd /path/to/project
dsh web
```

这里的 workspace 表示 Agent 操作的项目目录，与 Plugin 的安装位置相互独立。一个插件怎样从安装包进入指定运行配置、再形成最终启用的能力组合，见 Plugin 开发篇的[配置与安装包关系](dsh-dev.md#plugin-objects)。

Web 与 headless 是两个 Profile（启动时选用的具名运行配置）。Web 提供浏览器应用和 HTTP 服务；headless 负责一次性运行任务，并在 Agent idle 后输出结果。

> 来源：[npm 与源码启动命令](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/README.md#L13-L37)；[Profile boot、Web alias 与 headless 行为](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L7-L32)。

### <a id="systemd-user-service"></a>systemd 用户服务

dsh 的配置、凭据和 Session 都归启动它的普通用户。systemd user service（用户级服务）以同一身份托管 Web 进程；linger 让该用户的 manager 在无人登录时继续运行并参与开机启动。

服务入口可以指向 npm 全局安装的 `dsh`，也可以指向固定源码 checkout 构建出的 `apps/cli/lib/bin.js`。两条路径都在部署阶段完成依赖解析，并把 `WorkingDirectory` 留给 Agent 的项目 workspace。

#### 运行入口与工作目录

NVM 可以同时保存多个 Node 版本。部署时先解析实际使用的 Node 与 dsh 路径，再把绝对路径写入 unit：

```sh
nvm version default
command -v node
command -v dsh
readlink -f "$(command -v dsh)"
```

systemd user manager 直接执行 `ExecStart`，不会加载交互 shell 的 NVM 初始化。npm 全局安装的 `dsh` 使用 `#!/usr/bin/env node`，所以 unit 同时需要固定 `dsh` 的绝对路径，并在 `PATH` 中包含相应 Node 的 `bin` 目录。

源码入口由绝对 Node 路径执行 `<source-checkout>/apps/cli/lib/bin.js`。源码 checkout 按其 `packageManager` 字段选择 pnpm，并在每次切换 tag 后重新安装与构建。Agent 的默认 workspace 来自启动 cwd，因此 `WorkingDirectory` 应指向实际项目目录，与 dsh 的安装或源码目录分开。

> 来源：[Node 与 pnpm 版本约束](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/package.json#L1-L10)；[CLI 的 `bin` 入口](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/package.json#L11-L18)；[所有运行模式的默认 workspace](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L81-L85)。

#### 用户管理器与 linger

```sh
loginctl show-user "$USER" -p Linger
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" -p Linger    # 应为 Linger=yes
```

开启 linger 需要管理员权限。`Linger=yes` 时，user manager 可以在没有登录会话时运行；`Linger=no` 时，其生命周期跟随用户登录。systemd 用户服务的一般生命周期、网络顺序和凭据边界归 `software` skill 维护。

#### 服务配置

先创建 Agent workspace，再把 `<node-bin-dir>` 和 `<dsh-executable>` 换成前面解析出的绝对路径：

```sh
install -d -m 0755 "$HOME/dsh-workspace"
```

```ini
[Unit]
Description=DeepSeek Harness Web

[Service]
WorkingDirectory=%h/dsh-workspace
Environment=PATH=<node-bin-dir>:/usr/local/bin:/usr/bin:/bin
ExecStart=<dsh-executable> web --no-open --host 127.0.0.1 --port 3080
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

保存为：

```text
~/.config/systemd/user/dsh.service
```

这几项各有独立用途：

| 配置 | 作用 |
|---|---|
| `PATH` 与绝对 `ExecStart` | 固定 Node 和 dsh 入口，并提供 Plugin、MCP 与子进程继承的命令路径 |
| `WorkingDirectory` | 设置 Agent 默认 workspace |
| `--no-open --host 127.0.0.1` | 以无浏览器、仅回环地址的方式启动 Web |
| `Restart=always` | clean exit 或失败后重新启动；显式 stop 仍会停止服务 |
| `default.target` | 把 unit 挂到 user manager 的启用目标 |

若选用固定源码 tag，只替换 `ExecStart`，其余 service 语义不变：

```ini
ExecStart=<node-executable> <source-checkout>/apps/cli/lib/bin.js web --no-open --host 127.0.0.1 --port 3080
```

`pnpm dlx` 在 service 启动时仍可能下载和解析 package；固定入口把这些工作留在部署阶段。遥测模式及 `DSH_TELEMETRY_DISABLED` 的作用见[遥测数据](#telemetry-data)。

#### 启用与验收

先停止占用同一地址和端口的手工 dsh 进程，再加载并启动 unit：

```sh
install -d -m 0755 "$HOME/.config/systemd/user"
systemd-analyze --user verify "$HOME/.config/systemd/user/dsh.service"
systemctl --user daemon-reload
systemctl --user enable --now dsh.service
```

验收同时覆盖 unit 状态和 Web 响应：

```sh
systemctl --user show dsh.service \
  -p LoadState -p UnitFileState -p ActiveState -p SubState \
  -p MainPID -p ExecMainStatus -p NRestarts -p FragmentPath
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3080/
```

预期是 `enabled`、`active/running`、`NRestarts=0` 和 HTTP 200。失败时用 `systemctl --user status dsh.service` 与 `journalctl --user -u dsh.service` 查看 `EADDRINUSE`、入口路径或依赖加载错误。再执行一次 `systemctl --user restart dsh.service`，确认服务独立于当前交互 shell。

#### 升级、回滚与数据

升级前先停 unit并备份实际的 DSH home（默认 `~/.dsh`）。npm 全局路径显式安装目标版本：

```sh
systemctl --user stop dsh.service
npm install --global @deepseek-ai/dsh@<new-verified-version>
dsh --version
systemctl --user start dsh.service
```

源码路径切到明确 tag，重新执行 `pnpm install --frozen-lockfile && pnpm run build`，再启动并重复验收。显式版本让升级发生在部署操作中；developer preview 的 Session 数据在跨版本恢复前仍需核对兼容性。

卸载 executable 或 unit 会保留 `~/.dsh` 中的 Session、配置和凭据。运行时卸载与数据删除是两个独立操作；回滚同样安装明确的旧版本或切回旧 tag。

### <a id="systemd-system-service"></a>systemd 系统服务

与前文的用户服务相比，system service（系统级服务）由 PID 1 的 system manager 托管，不依赖用户 manager 或 linger，适合由主机管理员统一维护。这个托管层级的变化不应改变 DSH 的运行身份：系统 unit 必须用 `User=`、`Group=` 降权到普通用户，并显式提供该用户的 Home、DSH home、PATH 和 workspace。

| 维度 | 用户服务 | 系统服务 |
|---|---|---|
| unit 路径 | `~/.config/systemd/user/dsh.service` | `/etc/systemd/system/dsh.service` |
| manager / enable target | user manager / `default.target` | system manager（PID 1）/ `multi-user.target` |
| DSH 进程身份 | 隐式为当前用户 | 显式 `User=<user>`、`Group=<group>`；不要省略为 root |
| Home 与运行数据 | 通常自动继承用户环境 | 显式 `HOME=<home>`、`DSH_HOME=<dsh-home>` |
| 无人登录时启动 | 依赖 `Linger=yes` | 不依赖 linger |
| 管理与日志 | `systemctl --user …`、`journalctl --user -u …` | `sudo systemctl …`、`sudo journalctl -u …` |
| 适用场景 | 单用户自行维护 | 主机管理员统一托管、按系统启动顺序管理 |

下面是 `/etc/systemd/system/dsh.service` 的完整模板。把所有尖括号占位符换成绝对值；`<workspace>` 与 `<dsh-home>` 必须归 `<user>` 可读写。模板沿用前文解析出的 npm 全局入口；使用源码 checkout 时，把 `ExecStart` 换成绝对 Node 路径加 `<source-checkout>/apps/cli/lib/bin.js`。

```ini
[Unit]
Description=DeepSeek Harness Web
Wants=network-online.target
After=network-online.target
RequiresMountsFor=<workspace> <dsh-home>

[Service]
Type=simple
User=<user>
Group=<group>
WorkingDirectory=<workspace>
Environment=HOME=<home>
Environment=DSH_HOME=<dsh-home>
Environment=PATH=<node-bin-dir>:/usr/local/bin:/usr/bin:/bin
ExecStart=<dsh-executable> web --no-open --host 127.0.0.1 --port 3080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> 来源：[systemd 系统与用户 unit 的加载路径](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#Unit%20File%20Load%20Path)、[`User=`、`Group=` 与执行环境](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#User=)、[`WantedBy=` 的 enable 语义](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#%5BInstall%5D%20Section%20Options)、[linger 的生命周期语义](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html#enable-linger%20USER%E2%80%A6)。

### <a id="web-trusted-host"></a>Web 域名信任与反向代理

DSH Web 默认监听 `127.0.0.1:3080`。CLI 把 `--host 0.0.0.0` 视为安全相关的用法错误并退出，使默认服务入口保持在 loopback。

远程接入可以由不同层的方法独立完成或按需组合：

| 方法 | 建立的路径 | 主要职责 |
|---|---|---|
| SSH 本地隧道 | 浏览器本机 `127.0.0.1:3080` → 服务主机 `127.0.0.1:3080` | 为单个操作者提供临时的端到端 loopback 入口 |
| `socat`、Windows `portproxy` 或 SSH 端口转发 | 受控私网地址 → DSH loopback | 在主机、网络 namespace 或节点之间提供 TCP 接力；绑定地址与来源 ACL 定义可达范围 |
| Caddy 或同类反向代理 | 稳定域名 → 私有上游 | 提供 TLS、身份认证、域名路由，以及按部署模式设置上游 `Host` / `Origin` |

#### SSH 本地隧道

SSH 本地隧道让远端浏览器通过自己的 loopback authority 访问 DSH：

```sh
ssh -N -L 3080:127.0.0.1:3080 <host>
```

浏览器访问 `http://127.0.0.1:3080`。请求携带 loopback `Host` 与 `Origin`，普通 API、WebSocket 和配置平面都沿用本机访问语义。

当反向代理与 DSH 分处不同节点或网络 namespace 时，可以先用受控 TCP relay 提供私有上游。例如：

```sh
socat TCP-LISTEN:<relay-port>,bind=<private-address>,fork,reuseaddr TCP:127.0.0.1:3080
```

该 relay 的绑定地址、主机防火墙和来源 ACL 可以只覆盖反向代理节点；上层域名、TLS、认证和 HTTP header 处理继续由反向代理承担。

#### Caddy 公网入口的最低要求

走 Caddy 路线至少要同时完成四项：

1. **保持 DSH 上游私有。** DSH 继续监听 `127.0.0.1:3080`；Caddy 同机时直接访问该地址，跨节点时只通过受控 relay 到达，并用绑定地址、防火墙或来源 ACL 把 relay 限给网关。
2. **在 Caddy 终止 TLS 并执行真实认证。** DSH 的 Host / Origin fence 不是身份认证；认证必须发生在 `reverse_proxy` 之前，并覆盖整个 DSH 站点。
3. **代理完整的 HTTP 与 WebSocket 路径。** 不要只代理某一个 API；Caddy 的 `reverse_proxy` 会处理 WebSocket upgrade，不需要另建一条绕过认证的 WebSocket route。
4. **只选择一种 authority 策略并贯彻到底。** 要么保留公网 `Host` 与同源公网 `Origin`，同时给 DSH 配 `--trusted-host`；要么把上游 `Host` 与 `Origin` 成对改成同一个 loopback authority。只写 `X-Forwarded-Host` 或只改其中一个 header 都不满足 DSH 校验。

以下示例中的 `authorize with <policy>` 代表部署中已经安装并实际生效的认证模块与策略；若使用 `basic_auth`、`forward_auth` 或其他认证方式，应替换成对应的真实配置，不能省略。

##### 方案一：保留公网 authority，并使用 `--trusted-host`

用可重复的 `--trusted-host <host[:port]>` 声明普通 `/api` 和 WebSocket 接受的公网 authority：

```sh
dsh web --no-open --trusted-host <public-authority>
```

合法值是规范化的裸主机名或 `host:port`，不带 scheme、路径或用户信息。对普通 HTTP 上游，Caddy 默认透传浏览器的 `Host` 和其他请求 headers；不要再用其他规则把 `Host` 或 `Origin` 改成不同 authority：

```caddyfile
https://<public-host> {
	authorize with <policy>
	reverse_proxy <private-upstream>:3080
}
```

`--trusted-host` 负责 DNS rebinding（DNS 重绑定）与同源校验，不负责 TLS、网络入口或身份认证。公网 `Host` 与同源公网 `Origin` 可以通过普通 `/api` 和 WebSocket 栅栏；`settings.*`、`credentials.*`、预设编辑、宿主文件选择与打开、模型端点探测等配置平面仍只接受 loopback authority。

##### 方案二：强认证后成对改写为 loopback

反向代理完成强认证后，可以让 DSH 收到 loopback authority。此模式不需要把公网域名加入 `--trusted-host`，但 `Host` 与 `Origin` 必须成对改写为同一个 authority：

```caddyfile
https://<public-host> {
	authorize with <policy>
	reverse_proxy <private-upstream>:3080 {
		header_up Host 127.0.0.1:3080
		header_up Origin http://127.0.0.1:3080
	}
}
```

这里改的是 DSH 实际读取的 `Host` 和 `Origin`，不是 `X-Forwarded-Host`。同一个 `reverse_proxy` 处理普通请求和 WebSocket upgrade，因此两条 `header_up` 同时覆盖两者。

##### 同源校验结论

确认：在“代理改写为 loopback”模式下，`Host` 和 `Origin` 必须成对改写为相同 authority。DSH 的 `isTrustedApiRequest()` 按以下顺序执行：

1. 解析 `Host`；它必须是 loopback authority 或命中 `trustedHosts`。
2. 若 `Sec-Fetch-Site: cross-site`，立即拒绝。
3. 若存在 `Origin`，执行等价于 `new URL(origin).host === hostUrl.host` 的比较。

这里实际比较的是两边经 WHATWG URL 解析得到的 `.host`（hostname 加规范化后的端口）。代码不直接比较 scheme，但 scheme 会影响默认端口是否从 `.host` 中省略。以下组合假定 `Sec-Fetch-Site` 不为 `cross-site`；若它是 `cross-site`，无论其他 headers 如何都会在第 2 步拒绝。

| DSH 收到的 `Host` | DSH 收到的 `Origin` | 结果 |
|---|---|---|
| 公网 authority | loopback authority | 拒绝；公网 Host 未受信时在第 1 步失败，即使已配置 `--trusted-host` 也会因第 3 步不同源失败 |
| loopback authority | 公网 authority | 拒绝；第 3 步不同源 |
| loopback authority | 相同 loopback authority | 通过 |
| 公网 authority | 相同公网 authority | 配置匹配的 `--trusted-host` 后，通过 Host 端普通 API / WebSocket 栅栏；不因此开放 loopback-only 配置平面 |

缺少 `Origin` 的请求可以在 Host fence 通过后继续，但浏览器 fetch 和 WebSocket 通常会携带 `Origin`，代理不能依赖“恰好没有 Origin”。同样不要删除或伪造 `Sec-Fetch-Site` 来绕过第 2 步；正常从该公网页面发往同源公网 API 的请求本就不是 `cross-site`。

还要区分 Host 端信任与 Client 端页面身份：代理改写只改变 DSH 收到的 headers，浏览器地址栏仍是公网 hostname。DSH Client 通过 `location.hostname` 计算 `ctx.connection.isLoopback`；因此 Host 端放行不等于所有 Client 界面都会启用只在本机页面开放的能力。需要浏览器端也具备 loopback 语义时，应使用 SSH 本地隧道并从 `http://127.0.0.1:<port>` 打开页面，不能靠反向代理改写 headers 伪造浏览器自身的 hostname。

> 来源：[Web CLI 的默认监听、`--host 0.0.0.0` 限制与 `--trusted-host`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L67-L79)；[Host fence、cross-site fence 与 Origin/Host 精确相等检查](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/api-request-trust.ts#L90-L123)；[对应的 Host / Origin 行为测试](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/tests/api-request-trust.host.spec.ts#L19-L68)；[loopback 与 trusted-host RPC authority 的选择](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/rpc-host.ts#L74-L105)；[Client 从页面 hostname 派生 `isLoopback`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/client/index.ts#L80-L89)；[Web server 的 TLS 与认证边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/host/webserver/README.zh.md#L19-L22)；[Caddy `reverse_proxy` 的 header 默认值与 WebSocket 支持](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。

## <a id="runtime-composition"></a>Cordis 插件框架

DSH 把模型、工具、策略、存储和界面等能力做成可以组合的 Plugin。Profile（具名运行配置）保存一套部署实际安装并启用的插件集合；不同 Profile 可以面向 Web、一次性任务或其他入口采用不同组合。

### Plugin 的安装与卸载

| 目的 | 命令 | 生效方式 |
|---|---|---|
| 安装到指定 Profile | `dsh plugin --profile <profile> add <package-or-git-spec>` | 写入该 Profile；重启后使用新的插件集合 |
| 从指定 Profile 卸载 | `dsh plugin --profile <profile> remove <package>` | 从该 Profile 移除；重启后不再加载 |

安装和卸载改变的是指定 Profile，已经运行的进程继续使用本次启动时的插件集合，直到重启。一个插件怎样从安装包进入运行配置、怎样合并默认设置与部署覆盖，见开发篇的[加载方式、保存位置与生效时间](dsh-dev.md#plugin-loading-paths)；插件怎样共享能力、响应运行事件，并在更新或卸载时清理自身影响，见开发篇的[模块与生命周期](dsh-dev.md#plugin-runtime)。

> 来源：[Plugin package、Profile 与安装命令](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/user/develop/basic/publish.md#L9-L128)；[安装、移除与重启边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.md#L41-L64)；[插件框架的整体结构](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/architecture.zh.md#L15-L37)。

### <a id="agent-preset"></a>Agent preset

Agent preset（智能体预设）是创建 Agent 时选择的工作模式，决定该 Agent 可见的工具、角色说明、提示内容、压缩策略、workflow 和 Subagent 入口。Profile 决定整个 DSH 服务启用哪些共享能力，preset 决定单个 Agent 怎样使用这些能力。

官方随附四种 preset：

| ID | 显示名称 | 模型获得的工作方式 |
|---|---|---|
| [`standard`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/config/agent-presets/standard/preset.yml#L1-L3) | 标准模式 | 完整 coding agent，包括文件编辑、Shell、检索、Skills、计划、目标、Subagent 和 workflow |
| [`code`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/config/agent-presets/code/preset.yml#L1-L3) | PTC 模式 | 在标准能力上通过 Code Mode SDK 呈现工具，由 TypeScript 程序组合多步操作 |
| [`minimal`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/config/agent-presets/minimal/preset.yml#L1-L3) | 极简模式 | 固定 system prompt，只提供 persistent Bash 与 `str_replace_editor` |
| [`cordis`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/config/agent-presets/cordis/preset.yml#L1-L3) | 创造模式 | 在标准能力上增加运行时检查、动态 Plugin 实验和自定义 preset 创作能力 |

Session 创建时采用所选 preset。尚未产生内容的 Session 可以切换 preset；已经产生内容的 Session 保持原能力集合，使日志中的工具调用与恢复后的工具定义一致。preset 的后续修改由新建或新加入的 Session 使用。怎样组合和保存自定义工作模式，见开发篇的[运行配置与 Agent 工作模式](dsh-dev.md#plugin-loading-paths)。

#### <a id="creation-mode"></a>创造模式

`cordis` preset 是 standard coding agent 加上运行时自省、动态 Plugin 和 preset 创作能力。它除了辅助 Plugin 开发，还可以承担以下工作：

| 用途 | 能做什么 | 持久性 |
|---|---|---|
| 运行时检查与排障 | 查看当前加载的 Plugin、可用能力、工具、界面扩展位置和失败状态 | 只读取运行状态，不修改配置 |
| 临时调整 | 在运行中的 DSH 里增加小工具、提示内容、事件处理或局部界面，用于验证想法 | 当前进程内；版本、停用和清理方法见开发篇 |
| Agent 定制 | 复制已有 Agent preset，再调整工具、角色说明、提示内容、压缩策略或子智能体入口，并验证组合能否挂载 | 写入用户 preset，供之后创建的 Session 使用 |
| Plugin 开发 | 先观察 DSH 的实际扩展位置，再快速制作临时原型 | 何时使用、何时不用及如何落成正式 Plugin，见开发篇的[创造模式中的 Plugin 开发](dsh-dev.md#creation-mode-plugin-development) |

创造模式主要调整当前 Agent 和临时扩展。需要跨 Session 共用的持久能力、权限或模型路由，应整理成可以长期维护和测试的正式 Plugin；长期使用的 Agent 工作方式则保存为自定义 preset。动态 Plugin 会接触真实运行时，安全上按 shell 权限看待。

> 来源：[Agent preset 的组成、挂载与切换](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/preset/agent-presets/README.zh.md#L5-L85)；[创造模式的定位](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/config/agent-presets/cordis/preset.yml#L1-L3)；[动态 Plugin 的运行、内存生命周期与信任立场](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/extensions/cordis-host-runner/README.zh.md#L7-L32)。

## <a id="agent-execution"></a>Agent 执行与会话

### 轮次流程

一个轮次（turn）是 Agent 从领取输入到没有后续工作为止的一次响应过程；一个步骤（step）是其中的一次模型请求及其工具调用。工具结果可能要求再次请求模型，因此一个轮次可以包含多个步骤。

默认智能体循环（agent loop）推进这条流程，Plugin 则在 prompt 组装、模型请求、工具执行和轮次收尾等扩展点加入策略。审批、重试、超时、压缩和观测通过 service 或 event 与循环组合。

### Session 日志与持久化

Session 是只追加的事件日志。模型历史、Trajectory、恢复、分叉、回放和遥测都从同一条记录推导；**model-visible means logged** 表示进入模型请求的信息必须能够从日志重建。

默认 Profile 为每个 Session 保存一份 `.jsonl.zstd` 日志。可选的 SQLite `SessionPersistence` provider 可以把多个 Session 集中到一个数据库，随产品交付的组合当前不启用它。两种 backend 共享同一套逻辑事件语义；预发布存储格式不提供跨 schema 迁移。

开发需要持久保存的新事件、从日志计算状态或回放历史时，转到 [会话数据 Plugin](dsh-dev.md#session-data-plugins)。

> 来源：[官方轮次流程与会话日志](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/architecture.zh.md#L65-L100)；[默认 Profile 的 JSONL provider](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/bundle/base/cordis.patch.yml#L98-L101)；[JSONL 的每 Session 布局与默认压缩](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence-jsonl/README.zh.md#L5-L17)；[SQLite provider 的启用边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence-sqlite/README.zh.md#L5-L7)。

## <a id="builtin-extensions"></a>内置扩展

这些能力在实现上仍是 Plugin，但本节只讲部署者和使用者看到的行为。对应 package 的开发模式会在开发篇作为 Tool、Provider 或协议驱动案例出现。

### 模型配置

Web 的 **Settings → Models** 可以配置 DeepSeek、已安装 catalog provider 和自定义兼容端点。Settings 只保存 credential reference；密钥写入 `$DSH_HOME/.credentials.yaml`，页面读回的是脱敏描述而不是明文。

自定义 provider 需要 Provider ID、base URL、API 协议、凭据和模型列表。手工添加的模型默认按 text-only 处理；需要图片输入时，必须在模型或 route metadata 中显式声明，dsh 不会探测端点能力。模型和凭据变化在下一次请求生效，不要求重启服务。

> 来源：[模型、凭据、自定义 provider 与图片能力配置](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/user/guide/providers.zh.md#L5-L80)。

### Skills

`dsh-skill-filesystem` 按顺序扫描项目的 `.dsh/skills`、项目的 `.agents/skills`、显式自定义目录、`$DSH_HOME/skills`，以及 `$DSH_AGENTS_HOME/skills`（默认 `~/.agents/skills`）。较早的根在同名 Skill 冲突时优先。

Skill 支持 `<name>/SKILL.md` 目录 bundle 和 `<name>.md` 平铺文件；发现深度为一层。Provider 监听目录成员和 `SKILL.md` frontmatter 的变化。每次调用都会重新读取正文，因此正文与 `references/`、`scripts/`、`assets/` 的更新不需要重建目录；这些资源的变化本身也不会改变目录摘要。

> 来源：[Skill 根目录、优先级、格式与加载生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/skill/skill-filesystem/README.zh.md#L29-L67)。

### MCP

内置 MCP client 支持 `stdio` 和 `streamable-http`。每个 server 以独立 Plugin 连接并把远端工具注册进 `ctx.tools`，公开名称带 server namespace，避免不同 server 的同名工具冲突。

当前桥接面是 **Tools**；Resources 与 Prompts 尚无 Harness 消费接口。执行期规范值保留完整 JSON MCP blocks 和可选 `structuredContent`。进入模型历史时，文本与资源链接转成文本；挂载附件存储且调用模型明确声明图片输入能力时，PNG、JPEG、WebP 和 GIF 会成为持久图片块。音频、嵌入资源和不受支持的 block 会变成明确的诊断文本。

默认 Profile 不启动任何 MCP server。`stdio` server 是 Host 直接启动的可执行程序，不受 Agent 工具沙箱约束。

> 来源：[MCP transport、工具命名、结果映射与图片准入](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L5-L32)，以及[工具结果与已知边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L62-L117)。

### Subagent

`ctx.subagents` 允许多个命名 provider 并存。每个面向模型的 Subagent tool row 静态绑定一个 provider；部署可以注册多条具有不同 `toolName` 的工具，把不同进程和传输方式同时提供给 Agent。

| provider | child 形态 | 上下文关系 |
|---|---|---|
| spawn in-process | 当前 dsh 进程中的新 Agent | 继承 cwd、lineage、模型与 Host 服务，不继承父对话 |
| fork in-process | 当前进程中的新 Agent | 以父 Session 已完成的 turns 作为一次性 seed |
| [ACP](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/subagent/subagent-acp/README.zh.md#L5-L21) | 新 subprocess 中的 Agent | 独立 runtime、Session、模型和工具，通过 ACP 驱动 |
| [Codex](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/subagent/subagent-codex/README.zh.md#L5-L18) | 真实 Codex app-server child | 独立产品上下文，parent 主要获得最终结果 |
| [Claude Code](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/subagent/subagent-claude-code/README.zh.md#L5-L18) | 官方 Claude Agent SDK child | 独立产品上下文，认证与配置由 Claude Code 负责 |
| [dsh SDK](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/subagent/subagent-dsh-sdk/README.zh.md#L5-L23) | TypeScript SDK 启动的 dsh runtime | 独立完整 Plugin 树，通过 SDK 协议驱动 |

Provider 可以声明 structured output、persona、tool filter、depth limit 或 continuation 等能力；调用者要求 provider 不支持的能力时应显式失败，而不是静默忽略。

Codex 与 Claude Code provider 作为彼此独立的可选 Profile 组合包分发。安装组合包会让 Host 注册休眠 provider；复制 Agent preset 并启用对应 tool row，才会把工具提供给之后创建的 Session。

> 来源：[Subagent provider 家族与可选组合包](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/subagent/README.zh.md#L5-L21)；[in-process spawn 与 fork 的上下文差异](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/subagent/subagent-in-process-driver/README.zh.md#L5-L63)。

## <a id="programmatic-access"></a>程序化接入

这些入口驱动的是完整 Harness，而不是直接调用模型 API。外部程序创建或连接 Agent、发送输入、观察 Session event，并负责 runtime subprocess 的配置和生命周期。

### ACP

内置 ACP server 通过 JSON-RPC stdio 提供基础自动化：客户端可以创建 fresh Session，发送文本与受支持的光栅图片，接收已提交的 assistant 文本与图片，处理一次性 permission request，并取消工作。图片能力只在挂载持久附件存储、且确切模型 route 声明支持图片输入时公布。

ACP 面向自动化传输。历史 Session 的 list/resume/delete/fork、reasoning、tool activity、plans、titles 和 UI presentation 留在其他界面；一个连接拥有其创建的全部 Session，并在断开时负责清理。

> 来源：[ACP 的协议范围、图片准入、生命周期和已知限制](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/acp/acp/README.zh.md#L5-L83)。

### TypeScript 与 Python SDK

| SDK | 客户端接口 | runtime 来源 |
|---|---|---|
| TypeScript | 高层 `DeepSeekHarness.run()`；低层 `HarnessClient` 协议 API | 调用者显式提供 command 与 args |
| Python | 高层 turns API 与低层 JSON-RPC client | 可随 Python distribution 取得匹配的 runtime binary |

两者都通过 stdio JSON-RPC 驱动 subprocess。高层 API 可以把一次调用定义为“消息入队到下一次全 Agent idle”的活动区间，但结果不是严格归因于单个 prompt：steering、注入内容或其他排队输入也可能在该区间内贡献输出。低层 client 则暴露 enqueue receipt、event stream、notification 和显式 teardown。

TypeScript SDK 是纯 client library，不向 Cordis 注册 Plugin；它启动的 child 才是完整 Harness。Python 侧把 SDK 与可分发 runtime 拆成两个 package，方便应用不依赖源码 checkout。

> 来源：[TypeScript SDK 的高低层接口与进程生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/sdk/client/README.zh.md#L5-L49)；[Python SDK 与 runtime package 的分工](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/python/README.zh.md#L5-L16)。

## <a id="trust-boundaries"></a>信任边界

Host Plugin、Agent 工具、MCP server 和遥测处理的是不同权限主体。工具沙箱不是进程总沙箱，也不能撤销已经授予 Plugin 或安装脚本的 Host 权限。

### Plugin 与安装脚本

#### Host 进程权限

普通第三方 Plugin 在 `dsh` Host 进程中运行，拥有启动该进程的用户权限。它可以注册工具或监听器，也可以直接执行自身代码；tool approval 只约束 Agent 通过工具管线发起的调用。

创造模式通过 `cordis_define` 记录、再由 `cordis_run` 激活的动态 Plugin，其 Host 代码在 VM 中执行。VM 限制直接使用 Node 全局，并向代码提供 Cordis service façade（受控服务外观）；这些服务仍能触达存活运行时，因此 VM 不构成安全边界。动态 Plugin 按临时 Host Plugin 的权限评估。

#### Git 依赖的构建授权

从 Git 安装 TypeScript Plugin 时，包通常依赖 `prepare` 生成构建产物。pnpm 会要求用户在 Profile 的 `pnpm-workspace.yaml` 中加入 `allowBuilds`；这项授权意味着安装期直接执行 package 代码，发生在 Agent sandbox 之外。

不希望用户授权构建脚本时，应发布已经包含产物的 npm package 或 tarball。具体流程见开发篇的 [打包与安装](dsh-dev.md#packaging-and-installation)。

> 来源：[Git 安装的构建脚本与授权边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/user/develop/basic/publish.md#L153-L178)；[动态 Cordis VM 的信任立场](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/extensions/cordis-host-runner/README.zh.md#L26-L32)。

### Agent 工具执行

#### 工具沙箱与审批

新 Session 默认使用 `workspace-write`，限制 Bash 和 filesystem mutation 的文件写入范围。该文件策略允许读取与网络访问；进程可见性由 sandbox backend 决定：bwrap 使用私有 PID namespace 隐藏 Host 进程，Landlock 与 Seatbelt 保持 Host 进程可见。Sandbox backend 负责执行层隔离，approval service 负责一次工具调用的 allow / ask / deny 决策。

部分平台只能提供有限隔离。没有可用 backend 时，负责强制隔离的执行器应显式失败，而不是悄悄退回无约束执行。

#### MCP 进程权限

`stdio` MCP server 是 Host 启动的独立可执行程序。Agent 看到的是它桥接出的 tool，但 server 本身不在 Agent 工具沙箱里；HTTP MCP server 则把同等信任转移到远端服务和认证 header。默认 Profile 因此不启用任何 MCP server。

> 来源：[CLI 对默认权限、网络与进程可见性的说明](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L81-L91)；[sandbox policy 的文件操作边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/sandbox/sandbox-policy/README.zh.md#L59-L68)。

### <a id="telemetry-data"></a>遥测数据

Session telemetry 默认是 `DISABLED`，启动 Web 或运行 Agent 时数据留在本地。显式启用时：

- `FULL` 持续把投影后的 Session records 交给 OpenTelemetry backend；
- `FEEDBACK_ONLY` 只在记录反馈时回放并导出相关 Session log 后缀。

Telemetry seam 提供 `sessionTelemetry/record` waterfall，让部署挂载脱敏规则；官方默认组合没有挂载任何规则。因此上传模式会按捕获值转发 message、tool arguments/results、文件内容和 workspace path 中可能存在的敏感信息。`DSH_TELEMETRY_MODE` 选择模式，任意非空的 `DSH_TELEMETRY_DISABLED` 都会强制关闭，collector 由 `DSH_TELEMETRY_OTLP_URL` 选择。

> 来源：[默认遥测模式、环境变量与数据边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L89-L91)；[脱敏扩展点与默认无规则的边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-telemetry/README.zh.md#L37-L53)。
