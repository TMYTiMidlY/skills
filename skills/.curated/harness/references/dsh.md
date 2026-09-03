# DeepSeek Harness（dsh）运行时

本文从使用者和集成者视角说明 DeepSeek Harness 的产品定位、安装与运行、Cordis 插件框架、Agent 执行、内置扩展、程序化入口和权限边界。本文只给出安装、卸载和选择工作模式所需的插件概念；插件怎样组成运行环境、叠加配置、协作和清理，以及怎样开发和分发，见 [DeepSeek Harness Plugin 开发](dsh-dev.md)。现成扩展与社区项目见 [DeepSeek Harness Plugin 调研记录](dsh-research.md)。

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

### <a id="web-trusted-host"></a>Web 域名信任、会话认证与反向代理

DSH Web 默认监听 `127.0.0.1:3080`。CLI 把 `--host 0.0.0.0` 视为安全相关的用法错误并退出，使默认服务入口保持在 loopback。浏览器请求先过 Host/Origin 信任校验，再过浏览器会话认证；自 `0.1.2-alpha.1` 起 **localhost 不再是特权**——没有有效会话时，带 loopback `Host` 的请求同样收到 401。`0.1.1-rc.2` 及更早仍是 loopback 即特权，见本节末的[历史模型](#loopback-privilege-history)。

> 版本边界：`browser-auth.ts` 在 [`dsh-v0.1.2-alpha.1`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.1/packages/client/connection/src/browser-auth.ts) 已存在，在 [`dsh-v0.1.1-rc.2`](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.1.1-rc.2/packages/client/connection/src) 尚无；npm 上 `0.1.2` 系列自 `0.1.2-alpha.2` 起发布，`alpha.1` 仅有 Git tag。

#### authority 在本文中的含义

本文中的 authority 专指 URL 解析后的 `host[:port]`，也就是**域名或 IP，加上非默认端口**；不包含 `http://`、`https://` 等 scheme，也不包含路径。请求的 `Host` header 直接携带 authority；`Origin` 则形如 `scheme://authority`，DSH 用 `new URL(origin).host` 取出其中的 authority。

| 本文用语 | 示例 | 指什么 |
|---|---|---|
| 公网域名及端口（公网 authority） | `dsh.example.com`、`dsh.example.com:8443` | 浏览器地址栏所访问的域名及可选非默认端口 |
| Caddy 上游连接地址 | `127.0.0.1:3080`、`10.144.18.10:13080` | Caddy 在网络层实际连接的 DSH 或 relay 地址 |
| DSH 收到的 authority | `Host` 与 `Origin` 中最终送到 DSH 的 `host[:port]` | DSH 执行 Host / Origin 校验时真正读取的值 |

后两者不是一回事。例如 Caddy 可以实际连接 `10.144.18.10:13080`，同时把 DSH 收到的 `Host` 与 `Origin` 改成 `127.0.0.1:3080`。下文凡讨论放行或拒绝，均以 **DSH 实际收到的 authority** 为准，而不是以 Caddy 连接了哪个 IP 和端口为准。

远程接入可以由不同层的方法独立完成或按需组合：

| 方法 | 建立的路径 | 主要职责 |
|---|---|---|
| SSH 本地隧道 | 浏览器本机 `127.0.0.1:3080` → 服务主机 `127.0.0.1:3080` | 为单个操作者提供临时的端到端 loopback 入口 |
| `socat`、Windows `portproxy` 或 SSH 端口转发 | 受控私网地址 → DSH loopback | 在主机、网络 namespace 或节点之间提供 TCP 接力；绑定地址与来源 ACL 定义可达范围 |
| Caddy 或同类反向代理 | 稳定域名 → 私有上游 | 提供 TLS、身份认证、域名路由，以及按部署模式设置上游 `Host` / `Origin` |

#### <a id="browser-session-auth"></a>Host 信任校验与浏览器会话认证

浏览器无论经哪条路径到达 DSH，请求都按顺序经过两道校验：先信任，后身份。每个 Host RPC 方法与 WebSocket stream 都要求同一个浏览器会话，不存在按方法区分的 loopback 层。

| 阶段 | 通过条件 | 失败结果 | 防御对象 |
|---|---|---|---|
| 信任 | `Host` 是 loopback，或匹配 `trustedHosts` 条目；`Sec-Fetch-Site` 是 `same-origin`、`same-site`、`none` 或缺省；`Origin` 缺省，或与 `Host` 为同一 authority | 403 | DNS rebinding 与跨站请求；不证明请求者身份 |
| 身份 | 信任通过后，请求携带未过期、签名正确、绑定当前 authority 的会话 cookie | 401 | 未认证访问；伪造 `Host: localhost` 也绕不过这一层 |

第一次（或没有 cookie）时，必须完成一次 token 交换：

1. 每个进程在启动时生成一个随机 token，`dsh web` 打印（且除非 `--no-open` 或 SSH 抑制，自动打开）`http://127.0.0.1:<port>/?token=...`；
2. 这个 query token 只在 `GET /` 一个入口被接受；命中后 DSH 写入绑定 authority 的签名 cookie，并 303 重定向到不带 token 的干净 `/`；
3. 之后 RPC、WebSocket 和 index 页面都靠这枚 cookie，URL 里不再带 token。根路径交换之外，HTTP 载体不接受 query token，也不接受 Authorization header token。

已经认证过则：

- cookie 未过期（默认 30 天，`cookieMaxAgeDays`）且签发时的 hostname:port 与签名密钥未变时，重启 dsh 后仍可用，不必再贴 token——签名密钥是 `$DSH_HOME/.credentials.yaml` 中 `client-connection/browser-session` 拥有的持久凭据记录，不随进程重新生成，启动 token 才是逐进程新生成；
- URL 里带了旧 token 但 cookie 仍有效时，DSH 直接 303 清掉 query 进入页面；
- 非 index 的静态资源保持公开；能真正操作 Host 的接口都要会话。

cookie 本身是 host-only、`Path=/`、`HttpOnly`、`SameSite=Strict`，确定性名称与签名 payload 都绑定规范化的 hostname 和 port；随附服务器使用 loopback HTTP，因此刻意不设置 `Secure`。没有 logout 操作：清除浏览器站点数据只结束这一个浏览器；删除上述凭据记录并重启 dsh 撤销全部会话。

`cookieMaxAgeDays` 的最小取值是 1，没有永不过期；签发时刻与寿命按安全整数校验，上千天的取值远在界内。`expiresAt` 在签发时写入签名 payload，验证只读票内值，并额外要求票内「签发→过期」跨度不超过**当前配置**的 maxAge。由此方向不对称：调大配置不延长已发的 cookie；调小配置让所有跨度更长的旧票立即作废。无论哪个方向，要按新期限取票都须重新兑换。

调整该值通过 patch 层修改 `connection` 行（`@deepseek-ai/dsh-client-connection`）的 `config`。patch 按 id 定位行并**整段替换**其 `config`，原有的 `trustedHosts` 注入必须一并复述（patch 文件位置与叠加顺序见[持久配置 MCP Server](#mcp-persistent-configuration)）：

```yaml
- id: connection
  config:
    cookieMaxAgeDays: 3650
    trustedHosts: !!js ctx.webRuntime.trustedHosts
```

> 把一枚已认证的 cookie 手工放进另一个浏览器，只在浏览器以同一 authority 直接访问 DSH 时有效；经反向代理域名访问时，浏览器不会把 loopback 域名的 cookie 发给公网域名。反代部署换浏览器时，要么用当前进程的启动 token 重新兑换，要么由代理层统一附带会话，见 [Caddy 代持会话 cookie](#caddy-cookie-delegation)。

`dsh web` 一般会自己打印并打开带 token 的 URL，本机用户通常感觉不到这次交换；但设计上连本机浏览器也必须完成它。远程部署时，token 由部署者从启动输出转交给远端浏览器。

systemd 托管时，这条 URL 随标准输出进入 journal（系统服务把 `--user` 去掉）：

```sh
journalctl --user -u dsh.service -o cat | grep -oE 'token=[A-Za-z0-9_-]+' | tail -n 1
```

token 只随进程重启更换：它以进程的 root context 为键存于内存，修改 patch 等触发的 Connection 热重载沿用同一 token，journal 里已打印的旧 token 仍可兑换。

> 来源：[浏览器认证与请求信任](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/README.zh.md#L32-L39)；[requestRejection](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/src/rpc-host.ts#L96-L98)；[authorizeIndex](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/src/browser-auth.ts#L240-L276)；[cookie 名称与属性](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/src/browser-auth.ts#L107-L122)；[签名密钥的凭据记录](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/src/browser-auth.ts#L12-L16)；[无 logout 的边界](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/README.zh.md#L59-L63)；[web-app 的启动输出](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/bundle/web-app/README.zh.md#L37)；[maxAge 的下限与默认值](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/index.ts#L88)、[寿命的安全整数校验](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L189-L200)与[跨度不超过当前 maxAge 的验证](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L297-L302)、[启动 token 以 root context 为键、跨 Connection 重载保留](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L202-L209)、[token URL 的 stdout 打印](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/bundle/web-app/src/index.ts#L271-L284)、[patch 按 id 整段替换 config](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/docs/architecture.md#L27)与[web bundle 的 `connection` 行](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/bundle/web-app/cordis.patch.yml#L162-L169)。决策记录：[浏览器令牌认证](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/.agents/notes/implemented/architecture/2026-08-24-browser-token-authentication.zh.md)、[浏览器请求信任](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/.agents/notes/implemented/architecture/2026-07-28-api-browser-trust-boundary.zh.md)。

#### SSH 本地隧道

SSH 本地隧道让远端浏览器通过自己的 loopback authority 访问 DSH：

```sh
ssh -N -L 3080:127.0.0.1:3080 <host>
```

浏览器访问 `http://127.0.0.1:3080`。请求携带 loopback `Host` 与 `Origin`，直接通过信任校验；会话校验仍要完成——通过隧道打开启动打印的 `http://127.0.0.1:<port>/?token=...` 一次，之后凭 cookie 继续使用。

当反向代理与 DSH 分处不同节点或网络 namespace 时，可以先用受控 TCP relay 提供私有上游。例如：

```sh
socat TCP-LISTEN:<relay-port>,bind=<private-address>,fork,reuseaddr TCP:127.0.0.1:3080
```

该 relay 的绑定地址、主机防火墙和来源 ACL 可以只覆盖反向代理节点；上层域名、TLS、认证和 HTTP header 处理继续由反向代理承担。

#### Caddy 公网入口配置

Caddy 公网入口包含四个组成部分：

1. **私有 DSH 上游。** DSH 继续监听 `127.0.0.1:3080`；Caddy 同机时直接访问该地址，跨节点时通过受控 relay 到达，并用绑定地址、防火墙或来源 ACL 把 relay 限给网关。
2. **TLS 与用户认证。** Caddy 负责 TLS 终止和面向互联网的用户认证；DSH 的 Host / Origin fence 负责 DNS rebinding 与同源校验，浏览器会话认证独立于 Caddy 生效——远端浏览器仍要持有效会话：由使用者完成一次 token 交换，或由代理统一兑换并代持（见 [Caddy 代持会话 cookie](#caddy-cookie-delegation)）。
3. **完整的 HTTP 与 WebSocket 代理。** 同一条 `reverse_proxy` route 覆盖整个 DSH 站点，并由 Caddy 处理 WebSocket upgrade。
4. **自洽的 Host / Origin。** DSH 读取实际收到的 `Host` 与 `Origin`。部署可以保留公网域名及端口并配置匹配的 `--trusted-host`，也可以把两者成对改成同一个 loopback 域名/IP及端口；`X-Forwarded-Host` 继续承担转发元数据记录。

以下示例用 `authorize with <policy>` 表示已经安装并生效的认证模块与策略。部署时将它替换为实际使用的 `authorize`、`basic_auth`、`forward_auth` 或其他认证配置。

##### 保留公网 Host / Origin

假设浏览器访问 `https://dsh.example.com`，其公网 authority 是 `dsh.example.com`。DSH 启动时声明同一个裸 `host[:port]`；标准 HTTPS 端口 443 由 URL 规范化省略，非默认端口显式写入：

```sh
dsh web --no-open --trusted-host dsh.example.com
# 公网地址为 https://dsh.example.com:8443 时：
# dsh web --no-open --trusted-host dsh.example.com:8443
```

`--trusted-host` 使用裸 `host[:port]` 格式。对普通 HTTP 上游，Caddy 默认透传浏览器的 `Host` 和其他请求 headers；这一路径保持公网 `Host` 与同源公网 `Origin` 原值：

```caddyfile
https://dsh.example.com {
	authorize with <policy>
	reverse_proxy <private-upstream>:3080
}
```

这里的 `<private-upstream>:3080` 是 Caddy 的连接地址。DSH 的信任判断使用实际收到的 `Host: dsh.example.com` 和 `Origin: https://dsh.example.com`；匹配的 `--trusted-host dsh.example.com` 让信任校验放行，会话、事件流、其他普通 API 与 WebSocket 能否使用仍取决于浏览器会话。

配置 `--trusted-host dsh.example.com` 后，公网 `Host` 通过信任校验；能否调用 Host API 此后只取决于浏览器会话（见[Host 信任校验与浏览器会话认证](#browser-session-auth)）。Settings 读写、Credentials、Agent preset 管理、宿主文件操作（`host.pickDirectory`、`host.openPath`）、端点探测（`llm.discoverModels`）这组本机管理方法在 `0.1.1-rc.2` 及更早版本被单独圈出，在通用校验之后追加只接受 loopback Host / Origin 的第二层，公网路径上返回 403；统一会话认证（`0.1.2-alpha.1` 起）取消了这层名单，它们与其余 Host RPC 一样只要求同一枚会话 cookie，没有会话时统一返回 401。旧模型的完整描述见[历史模型](#loopback-privilege-history)。

`--trusted-host` 提供 DNS rebinding 与跨站请求防护，Caddy 提供 TLS 与面向互联网的用户认证，浏览器会话认证决定谁能操作 Host；三层各守自己的边界。

##### 改写为 loopback Host / Origin

Caddy 完成强认证后，可以把 DSH 实际收到的 `Host` 与 `Origin` 成对改为相同的 loopback 域名/IP及端口。DSH 在这一路径中直接使用 loopback 校验，无需把公网域名加入 `--trusted-host`：

```caddyfile
https://dsh.example.com {
	authorize with <policy>
	reverse_proxy <private-upstream>:3080 {
		header_up Host 127.0.0.1:3080
		header_up Origin http://127.0.0.1:3080
	}
}
```

Caddy 仍可实际连接任意受控的 `<private-upstream>:3080`；DSH 收到的是 `Host: 127.0.0.1:3080` 与 `Origin: http://127.0.0.1:3080`。这两条 `header_up` 作用于普通请求和由同一 `reverse_proxy` 处理的 WebSocket upgrade。

DSH 的 `isTrustedApiRequest()` 按以下顺序校验改写后的请求：

1. 解析 `Host`，接受 loopback 域名/IP及端口或 `trustedHosts` 中的值。
2. 检查 `Sec-Fetch-Site`，值为 `cross-site` 时拒绝请求。
3. 读取可选的 `Origin`，并比较 `new URL(origin).host === hostUrl.host`。

比较对象是两边经 WHATWG URL 解析得到的 `.host`（hostname 加规范化后的端口）。scheme 不直接参与比较，但会决定默认端口是否从 `.host` 中省略。下表假定 `Sec-Fetch-Site` 的值为 `same-origin`、`same-site`、`none` 或缺省：

| DSH 收到的 `Host` | DSH 收到的 `Origin` | 信任校验结果 |
|---|---|---|
| `dsh.example.com` | `http://127.0.0.1:3080` | 公网域名未受信时在 Host 校验拒绝；配置 `--trusted-host dsh.example.com` 后仍因两边 `.host` 不同而拒绝 |
| `127.0.0.1:3080` | `https://dsh.example.com` | Host 校验通过，Origin 的 `.host` 不同，拒绝 |
| `127.0.0.1:3080` | `http://127.0.0.1:3080` | 通过；随后的会话校验决定 401 还是放行 |
| `dsh.example.com` | `https://dsh.example.com` | 配置 `--trusted-host dsh.example.com` 后通过；同样还要会话 |

缺少 `Origin` 的请求由 Host fence 决定结果。浏览器 fetch 和 WebSocket 通常携带 `Origin`；代理保留浏览器产生的 `Sec-Fetch-Site`，同一公网页面发往同源 API 时该值符合非 cross-site 条件。

成对改写为 loopback 只影响信任校验。会话 cookie 的名称与签名 payload 绑定 DSH 实际收到的 authority；代理一致地改写 authority 时，token 交换与 cookie 回传也按改写后的 authority 进行——这条组合路径未在本库做过端到端实测，部署前应先验证。此路径的安全边界由 Caddy 强认证、覆盖完整站点的 route 和私有上游共同构成。

##### <a id="caddy-cookie-delegation"></a>Caddy 代持会话 cookie

前两种组合最终都要远端浏览器各自完成一次 token 交换；这一种把交换收进运维侧：Caddy 强认证通过后，代替浏览器携带一枚已兑换的会话 cookie 访问 DSH，公网用户只过 Caddy 的认证层，不接触 DSH 的启动 token。DSH 侧与「保留公网 Host / Origin」的组合相同——声明匹配的 `--trusted-host`，不改写 `Host` / `Origin`，页面的 `isLoopback` 判定也不受影响。

兑换按「浏览器经代理到达 DSH 时呈现的 authority」进行，即公网 `host[:port]`（HTTPS 默认端口不写）；用 `127.0.0.1:<port>` 兑换出的票与公网 Host 对不上。启动 token 从服务日志取得（systemd 部署的抓取命令见 [Host 信任校验与浏览器会话认证](#browser-session-auth)），在本机以公网 Host 兑换（前提是 DSH 已带匹配的 `--trusted-host`，否则兑换请求先被信任校验拒绝）：

```sh
curl -sS -D - -o /dev/null \
  -H 'Host: dsh.example.com' \
  'http://127.0.0.1:3080/?token=<launch-token>'
```

期望 `303`、`location: /` 和 `set-cookie: dsh-auth-<hash>=v1.…`，cookie 名按前文规则由该 authority 决定。兑换只认启动 token，把 `.credentials.yaml` 里的签名密钥贴进 `?token=` 只会得到 401。把值（`v1.` 起的整段）放进 Caddy 的进程环境——例如 systemd unit 经 `EnvironmentFile=` 加载的 `0600` 文件——站点片段：

```caddyfile
https://dsh.example.com {
	authorize with <policy>
	reverse_proxy 127.0.0.1:3080 {
		header_up Cookie "dsh-auth-<hash>={$DSH_BROWSER_COOKIE}"
		header_down -Set-Cookie
	}
}
```

- `header_up Cookie` 整段覆盖浏览器的 Cookie 头，普通请求与 WebSocket upgrade 都只带这一张会话票，GitHub 等认证 cookie 留在 Caddy 层。DSH 视角由此只剩代理持有的一个会话，能否进入 DSH 实际由 `authorize` 决定。
- `header_down -Set-Cookie` 剥掉 DSH 的全部 `Set-Cookie`，会话票不落入公网域名的浏览器——即使有人拿到启动 token 打开 `/?token=…`，兑换响应里的票也会被剥掉。当前版本全服务只有 token 兑换这一个 `Set-Cookie` 来源，剥离不破坏其他功能；升级 DSH 后应复核该前提。
- `{$VAR}` 在 Caddyfile 解析期展开，要求变量已在 Caddy 进程环境中；误写成 `{env.VAR}` 时占位符原样发给上游，只会得到 401。环境文件属于 systemd 在启动时固定的进程环境，改值后须 `restart` Caddy，`reload` 不会重读。

片段与命令中的 `3080` 是默认端口；`--port` 改变监听端口时，兑换命令、上游地址和公网使用非默认端口时的 authority 都要换成实际值。把用户重定向到 `/?token=…` 的自动兑换做法会让 token 进入浏览器历史与访问日志，也与 DSH 兑换后清空 query 的行为相抵触。

代持后，会话票的运维事件集中为：

| 事件 | 影响 | 处置 |
|---|---|---|
| 重启 dsh 进程 | 票仍有效（签名密钥持久），启动 token 换新 | 无须重兑 |
| 热重载（改 patch 等，未重启进程） | 启动 token 不变 | journal 里的旧 token 仍可兑换 |
| 票面到期，或调小 `cookieMaxAgeDays` 使票面跨度超限 | 票失效 | 重兑，更新环境后 `restart` Caddy |
| 调大 `cookieMaxAgeDays` | 旧票按票面期限继续有效 | 需要更长寿命时重兑 |
| 更换域名、端口或改用 Host 改写 | authority 变化，cookie 名与票都失配 | 重兑 |
| 删除 `browser-session` 凭据记录 | 全部会话作废 | 重兑 |

> 🔬 2026-09-03 本机实测：systemd 托管 dsh、Caddy 公网入口的部署按此模式运行（GitHub 认证 + `header_up Cookie` 注入 + `header_down -Set-Cookie` 剥离，保留公网 Host）；公网过认证后直接进入 DSH，本机无票直连返回 401、带注入票返回 200，浏览器不产生 DSH cookie。

> 来源：[token 兑换入口与 303/Set-Cookie](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L240-L266)、[authority 取自请求 Host](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L69-L78)、[cookie 名由 authority 哈希得出](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L106-L108)、[`?token=` 只与启动 token 做常数时间比较](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L100-L104)、[401 响应](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/connection/src/browser-auth.ts#L304-L312)；[`{$VAR}` 与 `{env.VAR}` 的展开时机](https://caddyserver.com/docs/caddyfile/concepts#environment-variables)见 Caddy 文档。

##### 远程页面下浏览器 Client 的 `isLoopback`

浏览器 Client 仍从页面 hostname 派生 `isLoopback`，且只用于页面自身状态展示；Host 端方法可用性由会话认证统一决定，不再随接入方式区分：

| 接入方式 | 浏览器 Client 的 `isLoopback` | 说明 |
|---|---|---|
| SSH 本地隧道，从 `http://127.0.0.1:3080` 打开 | `true` | Host 与页面都具备 loopback 语义 |
| Caddy 保留公网 Host / Origin | `false` | 页面按公网域名判定 |
| Caddy 强认证后改写为 loopback Host / Origin | `false` | 改写只影响 Host 收到的请求；页面仍按地址栏的公网域名判定 |

##### <a id="loopback-privilege-history"></a>历史模型：本机管理方法的 loopback 特权

DSH `0.1.1-rc.2` 及更早版本没有会话认证：通用校验之后，上述本机管理方法再以空 `trustedHosts` 调用 `isTrustedApiRequest()`，构成只接受 loopback Host / Origin 的第二层。于是 `--trusted-host` 公网路径上这些方法返回 403；Caddy 强认证后把 `Host` / `Origin` 成对改写为 loopback 就能让它们通过——loopback 本身即特权，无需任何会话。统一浏览器会话认证在 `0.1.2-alpha.1` 取代了这一层（npm 首个发布为 `0.1.2-alpha.2`）：伪造 loopback `Host` 不再带来任何特权，上述改写路径与按接入方式区分的差异表随之失效。

> 来源：[旧版本机管理方法清单与空 trust list 二层校验](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/src/index.ts#L69-L154)、[对应的 Host / Origin 行为测试](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/client/connection/tests/api-request-trust.host.spec.ts#L19-L68)；现行统一会话模型的来源见 [Host 信任校验与浏览器会话认证](#browser-session-auth)。

> 来源：[Web CLI 的 `--host`、`--port`、`--trusted-host` 与 `--no-open`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/bundle/web-app/README.zh.md#L41-L54)、[`--host 0.0.0.0` 的启动拒绝](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/bundle/web-app/src/startup.ts#L74-L75)；[Host fence、cross-site fence 与 Origin/Host 精确相等检查](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/src/api-request-trust.ts#L91-L118)；[webserver 的 host 只接受回环与全接口](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/host/webserver/README.zh.md#L39)；[Client 的 loopback 判定只用于页面自身状态](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.5/packages/client/connection/README.zh.md#L28)；[Caddy `reverse_proxy` 的 header 默认值与 WebSocket 支持](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。

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

#### <a id="pi-ai-catalog-version"></a>pi-ai 模型目录版本与上下文窗口配置

`dsh-llm-pi-ai` 从 `@earendil-works/pi-ai` 取得内置 provider 的模型目录、请求协议和推理档位等元数据。DSH `0.1.1-rc.2` 声明的是 `^0.82.1`；对 `0.x` 版本，caret 范围不会跨 minor，因此它只能解析 `<0.83.0`，不能自动跟到 `0.84.x`。已知 provider 的“发现模型”也直接返回已安装目录，不会请求厂商的 `/models` 刷新。由此产生的典型症状是：凭据已配置、厂商接口已经列出新模型，但 DSH 选择器没有该模型；强行点名则由适配器报 `UNKNOWN_MODEL`。

> 来源：[`dsh-llm-pi-ai` 的 pi-ai 依赖范围](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/package.json#L45-L47)、[已知 provider 只读取安装目录](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/discovery.ts#L1-L14)、[目录优先分支](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/discovery.ts#L195-L210)，以及 [npm caret range 规则](https://github.com/npm/node-semver/blob/v7.7.2/README.md#caret-ranges-123-025-004)。

DSH 的 `openai-codex` provider 由 `dsh-llm-pi-ai` 直接驱动，不读取 Codex CLI 的 `~/.codex/config.toml`。当已安装的 pi-ai 目录仍把 `gpt-5.6-sol` 的 `contextWindow` 记为 272000，而部署希望 DSH 按 1,000,000 tokens 预算时，应在 `$DSH_HOME/settings.yaml` 覆盖该模型的目录元数据：

```yaml
llm-pi-ai:
  providers:
    openai-codex:
      modelOverrides:
        gpt-5.6-sol:
          contextWindow: 1000000
```

`modelOverrides` 只改指定模型的容量，保留同一 provider 的其余目录字段；settings provider 会热重载文件，`dsh-llm-pi-ai` 在后续操作重新读取 profile，因此不需要重启服务或新建 Session。目标是 1M 时应写 `1000000`；Codex CLI 的 `max_context_window` 等元数据属于另一套运行时，换成较小数值会直接缩小 DSH 的预算，并非等价配置。使用 dsh-model-hub 的部署还需确认选择的是官方 `openai-codex`，而不是插件自带的 `codex`；两条路由的归属区别见[调研记录](dsh-research.md#2026-08-27-installed-source-followup)。

自动压缩由 DSH 的 `compaction-basic` 负责，并按解析后的 `contextWindow` 计算预算。默认在窗口的 80% 触发压缩，逐字保留最近 16%；窗口设为 1,000,000 后，对应 800,000 tokens 触发、保留 160,000 tokens。若要改变比例、绝对保留量或摘要模型，应修改 Agent preset 中的 compaction 配置，而不是 Codex CLI 的 `model_auto_compact_token_limit`。

> 🔬 2026-08-27 本机实测：把正在使用的 `openai-codex/gpt-5.6-sol` profile 从空配置改为上述 override 后，Web 页面即时显示 1M，当前 Session 的后续请求也继续成功；这验证了热重载和路由可用，不是向服务端发送接近 1M 输入的压力测试。`contextWindow` 是客户端容量声明，不能扩大服务端实际能力。

> 来源：[`contextWindow` 与 `modelOverrides` 配置字段](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/config.ts#L283-L335)、[模型覆盖的解析优先级](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/catalog.ts#L790-L880)、[settings 动态配置的生效时机](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/README.zh.md#L115-L119)，以及 [compaction 默认比例与按模型策略](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/compaction/compaction-basic/src/types.ts#L9-L43)。

> 🔬 2026-08-27 本机实测：Z.AI 和 xAI 的真实 `/models` 请求都返回 200，并分别列出 `glm-5.3` 和 `grok-4.6`；同机 DSH 实际解析的 pi-ai `0.82.1` 却只列到 `glm-5.2` 和 `grok-4.5`。pi-ai `0.84.3` 同时补齐两项：xAI 内置模型改走 Responses API，并把 Grok 4.6 设为默认；Z.AI Coding Plan 的 GLM-5.3 推理档位补全为 low、high 和 max。

> 来源：[pi-ai 0.84.3 的 xAI 协议与 GLM-5.3 元数据变更](https://github.com/earendil-works/pi/blob/v0.84.3/packages/ai/CHANGELOG.md#L3-L28)。

仅在 DSH 安装根执行 `npm install --no-save @earendil-works/pi-ai@0.84.3` 不足以完成升级。同一安装树的 npm dry-run 显示，npm 可以把 0.84.3 放在上层，同时在 `dsh-llm-pi-ai/node_modules` 下重新安装满足 `^0.82.1` 的 0.82.1；Node 按最近依赖优先解析，适配器仍会使用旧目录。正确路径是在 DSH 安装根设置 `overrides`，统一 Host 进程实际解析的整棵依赖树。先按前文对应的 systemd manager 停止 dsh，再执行：

```sh
DSH_PACKAGE_ROOT="$(dirname "$(dirname "$(readlink -f "$(command -v dsh)")")")"
test -f "$DSH_PACKAGE_ROOT/package.json"

npm pkg set 'overrides.@earendil-works/pi-ai=0.84.3' \
  --prefix "$DSH_PACKAGE_ROOT"
npm install --prefix "$DSH_PACKAGE_ROOT" \
  --package-lock=false --ignore-scripts --omit=dev \
  --no-audit --no-fund --dry-run
npm install --prefix "$DSH_PACKAGE_ROOT" \
  --package-lock=false --ignore-scripts --omit=dev \
  --no-audit --no-fund
npm ls --prefix "$DSH_PACKAGE_ROOT" @earendil-works/pi-ai --all
```

最后一条命令应只看到 `@earendil-works/pi-ai@0.84.3 overridden`，不能在适配器下面残留 0.82.1。随后启动 dsh，依次验收 service 为 `active/running`、Web 返回 HTTP 200、两个模型出现在目录，并各建一个新 Session 完成真实模型请求。该次实测中，包含 `dsh-model-hub` 的 Web Profile 正常加载并展示两项模型，GLM-5.3 与 Grok 4.6 的最小端到端请求也都成功；这只证明该 DSH、Plugin 与 pi-ai 版本组合，不代替其余 provider、工具调用、reasoning replay 和 OAuth 刷新的回归测试。

这项 override 修改的是全局安装产物，不是 DSH 源码；重新全局安装或升级 DSH 会覆盖它。回滚时删除 override、让 npm 按 DSH 自己的依赖范围恢复，再重启并重复 service 与 HTTP 验收：

```sh
npm pkg delete 'overrides.@earendil-works/pi-ai' \
  --prefix "$DSH_PACKAGE_ROOT"
npm install --prefix "$DSH_PACKAGE_ROOT" \
  --package-lock=false --ignore-scripts --omit=dev \
  --no-audit --no-fund
```

override 会影响 Host 中所有共享 pi-ai 的适配器和 Plugin。正式升级仍应由 DSH 发布新的依赖范围，并对 catalog、事件流、工具调用、reasoning 和 replay 做完整回归；本地 override 是一条可明确撤销的过渡路径。

### Skills

`dsh-skill-filesystem` 按顺序扫描项目的 `.dsh/skills`、项目的 `.agents/skills`、显式自定义目录、`$DSH_HOME/skills`，以及 `$DSH_AGENTS_HOME/skills`（默认 `~/.agents/skills`）。较早的根在同名 Skill 冲突时优先。

Skill 支持 `<name>/SKILL.md` 目录 bundle 和 `<name>.md` 平铺文件；发现深度为一层。Provider 监听目录成员和 `SKILL.md` frontmatter 的变化。每次调用都会重新读取正文，因此正文与 `references/`、`scripts/`、`assets/` 的更新不需要重建目录；这些资源的变化本身也不会改变目录摘要。

> 来源：[Skill 根目录、优先级、格式与加载生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/skill/skill-filesystem/README.zh.md#L29-L67)。

### MCP

内置 MCP client 支持 `stdio` 和 `streamable-http`。每个 server 以独立 Plugin 连接并把远端工具注册进 `ctx.tools`，公开名称中的 server namespace 区分不同 server 的同名工具。

当前 Harness 消费面覆盖 **Tools**；Resources 与 Prompts 等待相应的消费接口。执行期规范值保留完整 JSON MCP blocks 和可选 `structuredContent`。进入模型历史时，文本与资源链接转成文本；挂载附件存储且调用模型明确声明图片输入能力时，PNG、JPEG、WebP 和 GIF 会成为持久图片块。音频、嵌入资源和 Harness 当前范围之外的 block 会变成明确的诊断文本。

MCP server 采用显式启用方式：部署在 patch 中加入 server 对应的 MCP client Plugin 实例。`stdio` server 由 Host 直接启动并持有 Host 用户权限；Agent 工具沙箱与 server 进程构成两个独立的权限范围。

> 来源：[MCP transport、工具命名、结果映射与图片准入](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L5-L32)，以及[工具结果与已知边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L62-L117)。

#### <a id="mcp-persistent-configuration"></a>持久配置 MCP Server

安装 dsh 时，npm 会同时安装 `@deepseek-ai/dsh-mcp-client`。这个 package 提供 MCP transport、工具发现和 `ctx.tools` 注册能力。部署者通过 Cordis patch 为每个 MCP server 创建一个 Plugin 实例；实例激活后建立连接、读取工具 schema，并把工具提供给 Agent。

下面的 overlay 同时连接一个本地 stdio server 和一个远端 Streamable HTTP server，既可用于一次性测试，也可合并进持久 patch：

```yaml
- insert:
    - id: mcp-local-tools
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: local-tools
        transport: stdio
        command: /absolute/path/to/local-mcp-server
        args: []
        cwd: !!js process.cwd()
        env:
          LOCAL_MCP_TOKEN: !!js process.env.LOCAL_MCP_TOKEN

    - id: mcp-remote-tools
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: remote-tools
        transport: streamable-http
        url: 'https://mcp.example.com/mcp'
        headers:
          Authorization: !!js >-
            process.env.REMOTE_MCP_TOKEN && `Bearer ${process.env.REMOTE_MCP_TOKEN}`
```

`id` 是 Cordis 配置行的稳定标识，只需在组合中保持唯一，不要求以 `mcp` 开头。为了让 MCP 行在 patch、日志和排障输出中容易识别，推荐使用 `mcp-<serverName>` 形式；`mcp-` 是配置可读性约定，模型工具名仍由 `serverName` 决定。`serverName` 对应模型所见的 `mcp__<serverName>__<rawName>` namespace；它匹配 `[A-Za-z0-9_-]{1,32}`，并在存活的 MCP client 实例中唯一。

接入新 server 时，可以先把 overlay 保存为独立文件，例如 `./mcp-test.cordis.yml`，并在测试 shell 中导出 overlay 引用的环境变量。第一条命令验证配置层能否组合，第二条命令在备用端口启动一次真实 Web 进程，完成连接和工具发现测试：

```sh
dsh --profile web --patch ./mcp-test.cordis.yml --dump-config >/dev/null
dsh --profile web --patch ./mcp-test.cordis.yml --no-open --port 3081
```

`--patch <path>` 的作用域是当前进程，测试进程结束时该 overlay 的运行生命周期随之结束。测试通过后，把同一 `insert` 合并进持久 patch：单个 Profile 使用 `$DSH_HOME/profiles/<profile>/cordis.patch.yml`，所有 Profile 共用则使用 `$DSH_HOME/cordis.patch.yml`。配置层按 bundle、Profile patch、home patch、各个 `--patch` 的顺序叠加，后面的同 id 修改优先。

Web 部署通常把 server 定义写进 `$DSH_HOME/profiles/web/cordis.patch.yml`，并把该 Profile 使用的启动环境集中在相邻的 `$DSH_HOME/profiles/web/mcp.env`。编辑 patch 时保留现有顶层数组内容，把新的 `insert` 与已有条目合并。Profile 环境文件使用一行一个 `KEY=value` 的格式，YAML 通过 `process.env` 引用对应值：

```dotenv
LOCAL_MCP_TOKEN=<token>
REMOTE_MCP_TOKEN=<token>
```

```sh
chmod 600 "$DSH_HOME/profiles/web/mcp.env"
```

`mcp.env` 是部署约定的启动环境文件，加载责任属于启动方式。直接从 shell 启动 dsh 时，先把变量导入当前 shell，再启动目标 Profile：

```sh
set -a
. "$DSH_HOME/profiles/web/mcp.env"
set +a
dsh --profile web
```

**systemd service 托管。** 下面的内容适用于由 systemd 启动 dsh 的部署。system service 的 drop-in 记录环境文件路径：

```ini
[Service]
EnvironmentFile=<absolute-dsh-home>/profiles/web/mcp.env
```

system service 把 drop-in 保存到 `/etc/systemd/system/dsh.service.d/20-mcp-environment.conf`；user service 把它保存到 `~/.config/systemd/user/dsh.service.d/20-mcp-environment.conf`，并使用对应的 `systemctl --user` 命令。drop-in 变更通过 `daemon-reload` 和 restart 生效；`mcp.env` 值变更通过 restart 进入新进程：

```sh
sudo systemctl daemon-reload
sudo systemctl restart dsh.service
systemctl show dsh.service -p EnvironmentFiles -p ActiveState -p SubState
```

systemd 的 PATH 通常比交互 shell 短，systemd 部署中的 stdio `command` 使用绝对路径可获得一致的命令解析结果。

无论采用 shell 还是 systemd 启动，运行中的 Host 都会监视 Profile patch，并通过 HMR 应用 patch 变更。进程环境在启动时形成快照，因此环境文件更新通过重新启动进入 Host。stdio transport 以清理后的父环境为基底，再合并 `config.env`；部署在 `config.env` 中显式转发各 server 所需的变量。HTTP header 由配置表达式从 Host 环境构造。

环境变量是整个 Host 进程的共享状态，每个 Host Plugin 都具备读取能力。`0600` 把环境文件的磁盘读写权限授予文件所有者；Host Plugin 信任范围同时构成这些凭据的读取范围。完成持久配置后，通过服务状态和新 Session 的工具清单验收；新 Session 中应能看到 `mcp__<serverName>__...` 工具。

> 来源：[Profile 配置层顺序、`--patch` 与 `--dump-config`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L7-L39)、[Profile 与 home patch 的监视和 MCP 启用方式](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L81-L93)、[MCP Plugin 配置、命名和环境字段](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L7-L60)，以及[stdio 环境构造和持久 patch 位置](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/examples/mcp-memory/README.zh.md#L9-L33)。systemd 的 `EnvironmentFile=` 解析与生效时机见 [`systemd.exec`](https://www.freedesktop.org/software/systemd/man/255/systemd.exec.html#EnvironmentFile=)。

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
