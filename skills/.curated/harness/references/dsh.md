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

### <a id="web-trusted-host"></a>直接远程访问 Web

DSH Web 的直接远程访问、`--trusted-host`、`--public-url`、浏览器认证、Caddy 门禁接入，以及远程设置与文件兼容处理，统一见 [dsh-public-web README](https://github.com/TMYTiMidlY/dsh-public-web#web-trusted-host)。该仓库记录相关官方版本历史、插件用途与安全边界。

<a id="browser-session-auth"></a><a id="browser-session-lifecycle"></a><a id="cookie-max-age-patch"></a><a id="launch-token-journal"></a><a id="remote-access-methods"></a><a id="ssh-tunnel"></a><a id="tcp-relay"></a><a id="caddy-public-entry"></a><a id="client-isloopback"></a><a id="loopback-privilege-history"></a>

旧章节锚点保留用于已有引用；具体操作请读取上述 README 对应同名章节。

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

### <a id="instruction-discovery"></a>AGENTS.md 指令发现与加载

本节以 `dsh-v0.2.1-rc.2` 的默认 `dsh-base` 为准。`dsh-agent-instructions` 为第一次模型请求加载适用的全局与项目指令，profile 可以禁用或调整其预算。排查“模型默认读了什么”时，应分别核对部署的系统提示词、自动注入的指令文件和本轮手动读取的文件。

系统提示词由部署与插件组装，包括 harness 身份、persona 和适用的工具指导；动态运行状态另以用户角色上下文提供。`AGENTS.md` 指令也以持久的用户角色消息进入会话，虽然外层写着 `<system-reminder>`，仍受 system、developer 和用户直接指令约束。Skills 的目录与按需加载正文属于另一条加载链。

> 来源：[系统提示词、工具与动态上下文的组装](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/core/system-prompt/README.zh.md#L98-L110)、[模型实际收到的系统提示词](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/core/system-prompt/README.zh.md#L133-L146)；[指令文件的用户角色消息与持久化](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L86-L107)。

#### <a id="instruction-baseline"></a>默认指令链

第一次请求按下表顺序加载已存在且可读取的文件；项目链从宽泛目录走向当前会话目录。

| 范围 | 默认入口 | 用途与加载顺序 |
|---|---|---|
| DSH 用户全局 | `$DSH_HOME/AGENTS.md`，默认 `~/.dsh/AGENTS.md` | DSH 专用的用户要求，先加载 |
| 共享用户全局 | `$DSH_AGENTS_HOME/AGENTS.md`，默认 `~/.agents/AGENTS.md` | 供支持该约定的 Agent 工具共享的要求，随后加载 |
| 项目与当前目录 | 项目根到 Session cwd 路径上各目录的候选文件 | 每个目录依次加载 `AGENTS.md`、`CLAUDE.md`、`AGENTS.local.md`、`CLAUDE.local.md` |

> 来源：[默认指令链、根目录解析与候选名称](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L28-L68)。

项目根默认是从 cwd 向上找到的最近一个含 `.git` 标记的目录；一路都没有标记时，以 cwd 自身为根。只收录根到 cwd 这条目录链，因此家目录的 `~/AGENTS.md` 只有恰好位于该项目链中时才会加载，并无独立的全局入口地位。探测项目根标记时遇到权限或 I/O 错误，会停止发现并返回原始错误，而不是跳到更上层项目。

同目录中不同内容的候选会一起加载，更具体目录的指令优先约束该目录内的工作。去除首尾空白后内容完全相同的同组候选只保留最早一份：两个全局入口是一组，每个项目目录各自一组。指向普通文件的软链接会跟随到目标内容；全局与项目的作用范围仍按加载入口表达。因此，同一项目目录用 `CLAUDE.md` 软链接到 `AGENTS.md`，既能提供兼容入口，又会在 DSH 中折叠为一份内容。

> 来源：[项目根与目录链算法](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/src/files.ts#L223-L282)、[候选发现顺序](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/src/files.ts#L323-L366)、[去重与软链接边界](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L219-L226)。

维护项目指令时，通常把团队共享约定放进受 Git 跟踪的基础文件，把本地规则放进已配置忽略的 `.local` 文件。DSH 也采用“基础文件＋本地补充”的叠加设计：Git 是否追踪与指令是否加载彼此独立，`.local` 命名本身不替用户配置 Git 忽略。

> 来源：[本地补充的设计与默认候选](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/.agents/notes/archived/feature/2026-07-21-local-instruction-overlay.md#L8-L18)。

候选名称按配置精确匹配；默认识别大写复数的 `AGENTS.md`，自定义名称通过 `instructionFileCandidates` 与 `localInstructionFileCandidates` 设置。全局根固定只取 `AGENTS.md`，项目候选配置不会给全局增加 `CLAUDE.md` 或 `.local` overlay。若要单独保存全局本地规则，可在主文件中明确要求 Agent 继续读取加载入口同目录的补充文件；这是主文件驱动的读取约定，DSH 自身不解析 `@path` import。

> 来源：[配置字段](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L38-L68)、[全局候选与本地 overlay 的边界](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L219-L225)。

#### <a id="instruction-nested-loading"></a>子目录发现与刷新

首次加载只建立适用的基线。成功的第一方 `read`、`write`、`edit` 调用触及 cwd 下更深的文件时，插件沿 cwd 到目标文件父目录的路径发现新增指令，并在后续模型请求前注入；工具返回的文件正文与自动追加的指令消息是两件事。

例如 cwd 是含 `.git` 的项目根，目录为：

```text
repo/
├── .git/
├── AGENTS.md
└── packages/
    ├── AGENTS.md
    └── api/
        ├── AGENTS.local.md
        └── client.ts
```

首次请求加载全局指令和根目录的 `AGENTS.md`。成功读取 `packages/api/client.ts` 后，后续请求再收到 `packages/AGENTS.md` 与 `packages/api/AGENTS.local.md`；消息注明来源及适用子目录。兄弟目录在触及前保持未发现状态。仅运行 Shell 的 `cd` 或读取命令，以及 `glob`、`grep` 搜索，不属于这条文件触及钩子。修改 Session 工作目录则会在下一次请求前重新计算适用的项目链。

> 来源：[嵌套目录路径计算](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/src/files.ts#L270-L282)、[参与发现的工具及路径参数](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/src/index.ts#L76-L84)、[请求前的加载与工作目录切换](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L28-L34)。

指令文件没有持续 watcher。文件系统触及或恢复会话对账后，新来源以 `Additional instructions from:` 注入，已改变的来源以 `Updated instructions from:` 替换，已移除的来源以 `Instructions removed:` 声明失效；未变内容通过来源与内容比较抑制重复。自动注入会记录来源和作用范围，模型手动读过任意路径的文件则只说明该会话看到了文件内容，不能据此断言新会话也会自动加载。

`dsh-base` 默认给整条渲染基线 65,536 字节，单个源文件读取上限默认为 1,048,576 字节。超预算时先省略较宽泛文件，再截断最具体文件，并给出预算通知；核对实际提示词时，应同时查看来源消息和省略／截断通知。

> 来源：[字节预算与省略策略](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L30-L74)、[新增、更新与移除消息](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L163-L210)、[刷新触发条件与预算省略边界](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/context/agent-instructions/README.zh.md#L219-L226)。

### Session 日志与持久化

Session 是只追加的事件日志。模型历史、Trajectory、恢复、分叉、回放和遥测都从同一条记录推导；**model-visible means logged** 表示进入模型请求的信息必须能够从日志重建。

默认 Profile 为每个 Session 保存一份 `.jsonl.zstd` 日志。可选的 SQLite `SessionPersistence` provider 可以把多个 Session 集中到一个数据库，随产品交付的组合当前不启用它。两种 backend 共享同一套逻辑事件语义；预发布存储格式不提供跨 schema 迁移。

开发需要持久保存的新事件、从日志计算状态或回放历史时，转到 [会话数据 Plugin](dsh-dev.md#session-data-plugins)。

> 来源：[官方轮次流程与会话日志](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/architecture.zh.md#L65-L100)；[默认 Profile 的 JSONL provider](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/bundle/base/cordis.patch.yml#L98-L101)；[JSONL 的每 Session 布局与默认压缩](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence-jsonl/README.zh.md#L5-L17)；[SQLite provider 的启用边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-persistence-sqlite/README.zh.md#L5-L7)。

### <a id="session-statistics"></a>会话统计条

Web 输入区旁的统计描述**当前 Session 的完整已记录历史**。主会话打开时看主会话，子代理会话打开时看那个子会话；它不会递归合并后代，也不按整台机器或模型登录账号汇总。因此这里用“当前会话”比“主线程”准确——是否运行在同一个系统线程，不决定统计归属。切换模型也不会清空之前的累计值。

> 本节逐字段对应 `dsh-v0.1.2-rc.1` 的文本统计条；另核对 `dsh-v0.1.5-rc.1` 的展示变化，见[界面版本](#session-statistics-ui)。源码：[当前会话的统计入口](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/ui-chat/src/client/chat/StatsLine.tsx#L163-L208)、[按 Session ID 分开的投影存储](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/api/session-controller/src/client/sessions/manager.ts#L334-L348)。投影是从日志计算出的累计读数；正常装配读取 `sessionStats` 和 `tokenUsage`，缺少 `sessionStats` 的自定义装配才回退到当前已加载消息窗口。

#### <a id="session-statistics-fields"></a>字段与计算方法

例如下面这行信息，所有字段都以当前会话为范围，但各自的计数单位和计时区间不同：

```text
11 轮 · 146 步 | LLM 41分32秒 · 工具调用 4分52秒 | 首 token 平均 14秒 · 150 tok/s | 缓存命中 98% | 输入 28.7M tok · 输出 69.7K tok
```

| 显示项 | 源码中的计算口径 | 怎样理解示例 |
|---|---|---|
| `11 轮` | `turns`：至少含一个已关闭步骤的不同 turn 数；在该轮第一次 `step/end` 时加一 | 11 个有实际步骤结束的响应过程，不一定等于 11 条用户消息；未进入步骤的空轮不计 |
| `146 步` | `steps`：`step/end` 数；成功、失败、取消、达到输出上限的步骤都计入 | 146 个已结束的 agent 步骤，不等于 146 次成功 HTTP 请求，也不等于工具调用次数；同一步可重试或调用多个工具 |
| `LLM 41分32秒` | `llmMs`：将匹配的 `step/start → assistant/message` 墙钟间隔逐步相加 | 是步骤开始至模型消息组装完成的累计耗时，包含首 token 前等待，不是纯解码时间；没有组装出消息的中断步骤不贡献这一项 |
| `工具调用 4分52秒` | `toolMs`：按 `callId` 匹配 `tool/call → tool/result`，逐项相加 | 是工具配对耗时总和，不是调用次数；并行工具的重叠时间仍各计一次，因此不等于任务的真实经过时间 |
| `首 token 平均 14秒` | `ttftMs / ttftSteps`：有首 token 且组装出消息的步骤，其 `step/start → 首个有效流式增量` 延迟的算术平均 | 首个有效增量可以是文本、推理或工具调用名称／参数，不限于用户看到的第一句正文；分母只取有计时样本的步骤，不能直接假定为 146 |
| `150 tok/s` | `decodeTokens / (decodeMs / 1000)`：对同时有首 token 和有效输出用量的步骤，输出 token 总和除以首 token 至消息完成的时间总和 | 是合并后的解码吞吐量，不是各步速度的简单平均，也不能用 `69.7K / 41分32秒` 复算 |
| `缓存命中 98%` | `cacheReadTokens / (uncachedInputTokens + cacheReadTokens + cacheWriteTokens)`，再格式化百分比 | 按输入 token 数加权的缓存读取占比，不是 98% 的请求命中、跳过了 98% 的步骤或节省了 98% 的费用 |
| `输入 28.7M tok` | `uncachedInputTokens + cacheReadTokens + cacheWriteTokens` | 当前会话累计约 2870 万输入 token，**已经包含缓存读取和缓存写入**；上下文在多次请求中出现时会多次计入，不是当前上下文长度或用户新输入字数 |
| `输出 69.7K tok` | 累计提供方上报并经适配器映射的 `outputTokens` | 当前会话累计约 6.97 万输出 token；不是可见正文字符数。pi-ai 路由把推理用量包含在输出中，不应再额外加一次推理 token |

> 源码：[轮／步与时间累计](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/session/session-stats/src/projection.ts#L146-L208)、[首 token 增量判定](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/session/session-stats/src/projection.ts#L32-L43)、[平均值和吞吐量展示](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/ui-chat/src/client/chat/StatsLine.tsx#L174-L204)、[输入与命中率公式](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/ui-chat/src/client/chat/StatsLine.tsx#L96-L115)、[pi-ai 用量映射](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/llm/llm-pi-ai/src/stream.ts#L18-L31)。`K`、`M` 分别按 1000、1000000 缩写并四舍五入；显示的 98% 和 28.7M 不能反推出精确缓存数，见[格式化实现](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/ui-chat/src/client/chat/token-format.ts#L3-L15)与[百分比舍入](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/client/ui-chat/src/client/chat/token-format.ts#L59-L98)。

#### <a id="session-statistics-scope"></a>子代理、重试与历史范围

主会话的输入、输出、命中率、轮／步数和模型计时都不自动加上子代理内部的对应统计。子代理返回的文本在主会话后续模型请求中成为输入时，会作为**那次主会话请求的输入**计量；这与把子代理内部所有请求并入父统计不同。父会话自身的委派工具仍按工具起止配对计时：同步等待子代理的时间可能落进父 `toolMs`，后台启动调用则不代表子代理运行全程。因此汇总耗时不能把父工具等待和子代理模型时间无条件相加。

用量按调用尝试去重，而不是每个流式片段都加一次：同一次尝试的早期 usage 样本被最终样本替换；`llm/retry-started` 结束这个替换范围，下一次尝试再增加用量。失败前已经上报的 usage 可以保留；没有上报 usage 的处理成本无法从该读数还原。这也是“步骤数”“成功响应数”“上游物理请求数”不能互换的原因。

> 源码：[usage 样本替换与重试累计](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/llm/token-meter/src/usage-projection.ts#L111-L158)。token 投影只消费指定的 usage 事件，不会自动遍历工具内部请求；标题生成、外部搜索、图片服务等辅助调用是否入账，要核对各自记录位置，不能将统计条当成账号的完整账单。

分页和 compact 改变可见历史或下次请求上下文，**不扣减已经累计的用量与步骤数**；压缩触发线是另一项上下文压力预算，见[上下文窗口配置](#pi-ai-catalog-version)。因此 200k 的单次上下文预算与几千万累计输入并不矛盾。

分叉（fork）还需单独处理：它可能把父会话已完成轮次的整个日志前缀作为 seed 带进新会话。所核版本的统计投影遍历该会话完整日志，不自行扣除继承前缀；所以跨父子／分叉会话对账时，应按 `inheritedEventCount`（JSONL header 的 `seedLength`）排除重复继承记录，不能简单相加各页面累计数。普通子代理的独立运行不会反向增加父会话统计。

> 源码：[fork 捕获已完成轮次前缀](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/subagent/subagent-fork-in-process/src/index.ts#L40-L89)、[完整日志的投影重放](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/session/session-projection/src/index.ts#L602-L624)、[JSONL 的继承前缀字段](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/session/session-persistence-jsonl/src/format.ts#L59-L112)。

#### <a id="session-statistics-ui"></a>界面版本

`dsh-v0.1.5-rc.1` 已把文本统计条改成时间／速度和 token 用量两个按钮，仍读取当前 Session 的 `sessionStats` 与 `tokenUsage`。用量按钮外侧显示的是**全部输入加输出的总数**；展开后把未缓存输入、缓存读取、非零缓存写入和输出分别列出。不能把新版明细中的未缓存输入，与旧版统计条含缓存的“输入”直接比较。新版流式事件也从独立 chunk 改为消息／尝试内嵌 stream；解析原始日志应对应版本，不要固定只找旧的 `assistant/chunk`。

> 源码：[新版 token 按钮及明细](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/client/ui-chat/src/client/chat/StatsPills.tsx#L236-L327)、[新版 usage 来源与尝试累计](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.5-rc.1/packages/llm/token-meter/src/usage-projection.ts#L81-L150)。

## <a id="builtin-extensions"></a>内置扩展

这些能力在实现上仍是 Plugin，但本节只讲部署者和使用者看到的行为。对应 package 的开发模式会在开发篇作为 Tool、Provider 或协议驱动案例出现。

### 模型配置

Web 的 **Settings → Models** 可以配置 DeepSeek、已安装 catalog provider 和自定义兼容端点。Settings 只保存 credential reference；密钥写入 `$DSH_HOME/.credentials.yaml`，页面读回的是脱敏描述而不是明文。

自定义 provider 需要 Provider ID、base URL、API 协议、凭据和模型列表。手工添加的模型默认按 text-only 处理；需要图片输入时，必须在模型或 route metadata 中显式声明，dsh 不会探测端点能力。模型和凭据变化在下一次请求生效，不要求重启服务。

> 来源：[模型、凭据、自定义 provider 与图片能力配置](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/docs/user/guide/providers.zh.md#L5-L80)。

#### <a id="pi-ai-catalog-version"></a>pi-ai 模型目录版本与上下文窗口配置

`dsh-llm-pi-ai` 从 `@earendil-works/pi-ai` 取得内置 provider 的模型目录、请求协议和推理档位等元数据。DSH `0.1.1-rc.2` 声明的是 `^0.82.1`；对 `0.x` 版本，caret 范围不会跨 minor，因此它只能解析 `<0.83.0`，不能自动跟到 `0.84.x`。已知 provider 的“发现模型”也直接返回已安装目录，不会请求厂商的 `/models` 刷新。由此产生的典型症状是：凭据已配置、厂商接口已经列出新模型，但 DSH 选择器没有该模型；强行点名则由适配器报 `UNKNOWN_MODEL`。

> 来源：[`dsh-llm-pi-ai` 的 pi-ai 依赖范围](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/package.json#L45-L47)、[已知 provider 只读取安装目录](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/discovery.ts#L1-L14)、[目录优先分支](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/discovery.ts#L195-L210)，以及 [npm caret range 规则](https://github.com/npm/node-semver/blob/v7.7.2/README.md#caret-ranges-123-025-004)。

**API 规格与 Codex 订阅目录。** 配置上下文前先区分 API 模型规格、Codex 产品目录与 DSH 客户端预算。下面是 2026-09-08 核验的快照：API 页面公布模型的总窗口和最大输入；Codex `0.153.4` 的目录则另列默认工作窗口与配置覆盖上限，四款模型的默认工作窗口均为 272,000 tokens。

| 模型与 API 文档 | API 总窗口 | API 最大输入 | Codex `max_context_window` |
|---|---:|---:|---:|
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra.md) | 1,050,000 | 922,000 | 872,000 |
| [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol.md) | 1,050,000 | 922,000 | 872,000 |
| [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra.md) | 1,050,000 | 922,000 | 872,000 |
| [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna.md) | 1,050,000 | 922,000 | 872,000 |

> 2026-09-08 官方模型页原文摘录（四款相同）：`1,050,000 context window`、`Maximum input tokens: 922,000`、`128,000 max output tokens`。本节就近保存当日关键原文，表中在线链接保留为阅读入口，不以网页后续变更回填当日记录。
>
> Codex 数值是发布目录中直接写出的字段，不是由 API 规格推算：[Astra](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/models.json#L4-L33)、[Sol](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/models.json#L173-L200)、[Terra](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/models.json#L304-L331)、[Luna](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/models.json#L430-L457)。字段定义明确为[允许配置覆盖到的最大窗口](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/protocol/src/openai_models.rs#L431-L446)。

四款 API 模型页同时列出最大输出 128,000，数值上 `1,050,000 − 128,000 = 922,000`；总窗口包含输入、输出与推理 token，不能把 1.05M 总窗口当成允许输入 1.05M。`922,000 − 872,000 = 50,000` 只是两个已公布数值的差，本次未找到这 50,000 的官方用途说明，不能自行解释成系统提示、工具或压缩预留。Codex 的目录上限也不等于已经验证的服务端硬上限。

> [OpenAI 上下文管理文档](https://developers.openai.com/api/docs/guides/conversation-state.md)的 2026-09-08 原文摘录：“The **context window** is the maximum number of tokens that can be used in a single request. This max tokens number includes input, output, and reasoning tokens.” API Key 接入与 ChatGPT 订阅接入的可用模型、窗口和额度分别受各自服务约束；API 规格不能直接作为订阅账号的容量承诺。

Codex CLI 的顶层 `model_context_window` 和 `model_auto_compact_token_limit` 对当前活动模型生效，不绑定同文件中 `model = ...` 指定的单个模型。以配置 1,000,000 / 800,000 为例，上述版本先把窗口截断为 `min(1,000,000, 872,000) = 872,000`，再按目录的 95% 计算可用窗口 828,400；压缩阈值也截断为 `min(800,000, 872,000 × 90%) = 784,800`。因此配置能解析、界面显示大窗口和服务端成功处理超长输入，是不同的验证结果。

> 来源：[Codex 配置覆盖与窗口截断](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/src/model_info.rs#L25-L37)、[可用窗口及自动压缩阈值的计算](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/protocol/src/openai_models.rs#L487-L511)；CLI 配置入口见 [Codex 运行时笔记](codex.md)。

> 🔬 2026-09-08 本机核验：从 `codex-cli 0.153.4` 的 Linux musl 二进制内嵌 JSON 提取到四款模型的 `max_context_window: 872000`，与发布目录一致；ChatGPT 订阅登录的同版本 `models_cache.json` 当日快照也给出相同值。已有 Astra 会话的 `token_count.info.model_context_window` 为 828400，与 95% 计算一致。这验证了目录及客户端实际使用的预算，没有验证接近 872K 或 922K 的服务端请求。

复核其他账号或版本时，读取 `${CODEX_HOME:-$HOME/.codex}/models_cache.json` 的 `fetched_at`、`client_version` 和目标模型的 `context_window`、`max_context_window`、`effective_context_window_percent`，再与对应版本及会话记录对照；缓存中的数值不应跨账号、跨版本当成永久规则。其他模型也不能一律改成 1M：Spark 的目录窗口为 128,000；GPT-5.4 mini 的 API 总窗口为 400,000、最大输入 272,000；GPT-5.5 即使 API 总窗口为 1,050,000，Codex `0.153.4` 的配置覆盖上限仍为 272,000。

> 2026-09-08 API 原文摘录：[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini.md)为 `400,000 context window`、`Maximum input tokens: 272,000`；[GPT-5.5](https://developers.openai.com/api/docs/models/gpt-5.5.md)为 `1,050,000 context window`、`128,000 max output tokens`，该页没有单列最大输入。Codex 目录见 [mini](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/models.json#L1019-L1046) 与 [5.5](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/models-manager/models.json#L786-L813)；Spark 数值来自同次本机订阅目录核验。
>
> [Codex 官方模型文档](https://learn.chatgpt.com/docs/models.md)的 2026-09-08 原文摘录：“GPT-5.4 and GPT-5.4 mini retire from Codex on August 31, 2026.” 同段明确 “If you sign in with ChatGPT” 的用户需要更换模型，并说明 “The OpenAI API and Codex authenticated with your own API key aren't affected.” 因此该次退役针对 ChatGPT 登录的 Codex；本地目录残留条目不能证明账号仍可调用。

**DSH 上下文覆盖。** DSH 官方 `openai-codex` provider 由 `dsh-llm-pi-ai` 驱动，不读取 Codex CLI 的 `config.toml` 或模型缓存，也不执行上述截断规则。上下文容量在官方插件的 `config.providers` 中配置；当前入口是 Cordis patch，而不是旧版 `$DSH_HOME/settings.yaml` 的命名空间片段。

在 `$DSH_HOME/cordis.patch.yml` 的既有 `llm-pi-ai` 条目中，合并下面的 `openai-codex` 配置。该位置的结构为 `- id: llm-pi-ai` → `config` → `providers` → `openai-codex`；只调整对应 provider，保留同一 config 中其他 provider 和凭据引用。此例使用 `models` 明确选择可用模型，并对目标条目覆盖上下文预算：

```yaml
openai-codex:
  models:
    - id: gpt-5.3-codex-spark
    - id: gpt-5.5
    - id: gpt-5.6-luna
      contextWindow: 872000
    - id: gpt-5.6-sol
      contextWindow: 872000
    - id: gpt-5.6-terra
      contextWindow: 872000
    - id: gpt-6-astra
      contextWindow: 872000
    - id: gpt-6-luna
      contextWindow: 872000
    - id: gpt-6-sol
      contextWindow: 872000
    - id: gpt-6.1-sol
      contextWindow: 872000
```

`models` 替换该 provider 的可选模型列表，但每个已收录 ID 的未指定字段仍继承 pi-ai 目录，包括正式展示名、`maxTokens`、输入模态和 reasoning/effort 映射。只写 ID 的 Spark 和 GPT-5.5 保留目录默认窗口；不需要使用时可从列表移除。其余条目仅覆盖上下文预算为 872000，不必重抄能力字段。执行前确认安装的 pi-ai 已收录所有列出的 ID；872000 是部署选择，不是 DSH 强制要求或对所有列出模型的服务端上限证明。

若希望保留 provider 的整个已安装目录、仅调整个别模型，则在同一个 `config.providers.openai-codex` 位置使用 `modelOverrides` 字典：键为模型 ID，值为包含 `contextWindow` 等覆盖字段的对象。它也是官方配置能力，与使用何种界面无关；同一 provider 的 `models` 与 `modelOverrides` 互斥。已有 `models` 列表时直接修改对应条目，无需再建立第二份窗口配置。

> 来源：[`contextWindow` 与 `modelOverrides` 配置字段](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/config.ts#L283-L335)、[模型覆盖的约束与解析优先级](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/llm/llm-pi-ai/src/catalog.ts#L790-L880)。

DSH 的 `compaction-basic` 按解析后的 `contextWindow` 计算压力预算，默认在窗口的 80% 触发压缩，最近原文的保留预算为 16%。窗口为 872,000 时，对应 697,600 tokens 触发、139,520 tokens 原文保留预算；不再套用 Codex 的 95% 或 90% 系数。自定义比例、绝对保留量或摘要模型由 Agent preset 的 compaction 配置决定，Codex CLI 的压缩参数不控制 DSH。

> 来源：[compaction 默认比例与按模型策略](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/compaction/compaction-basic/src/types.ts#L9-L43)；这里给的是默认策略的预算计算，不能代替对部署实际 preset 的检查。

**热加载与验收。** 修改前备份目标 patch 并保留所有者及私有权限，只合并目标字段。`live` 型 Profile 会重读 patch，后续请求使用更新后的插件配置；`startup` 型 Profile 在下次启动生效，具体机制见 [Patch 热更新的生效机制](#mcp-patch-hot-reload)。刷新官方 Models 页面，核对目标模型的 `contextWindow` 与未修改的名称、输出上限和 effort 元数据。若仍是旧值，检查最终合成配置、加载错误和页面刷新状态。

上下文配置覆盖与 pi-ai 依赖升级是两项操作：前者按 Profile 的配置重载规则生效，后者替换进程加载的代码，必须重启 DSH。

### <a id="pi-ai-dependency-override"></a>pi-ai 依赖覆盖

pi-ai 的模型目录和协议适配通常比 DSH 的依赖范围更新得更快。厂商已经开放新模型，而 DSH 仍显示原始模型 ID、缺少 reasoning/effort 控件，或目录中没有该模型时，核对 DSH 依赖树中的 pi-ai 版本与目标发布包的 provider 数据。模型进入目录只表示客户端认识该 ID，不代表当前账号已有服务端调用权限。

DSH 使用自身依赖树中的 pi-ai；更新另一份全局安装不会改变 Host 的解析结果。直接添加一个 `--no-save` 依赖也可能留下更近的旧副本。应在动态发现的 DSH 安装根设置 npm `overrides`，把依赖树统一到一个经过核对的明确版本。

先查询目标版本、Node 要求和 changelog，确认所需模型的协议、`reasoning` 与 `thinkingLevelMap`：

```sh
npm view @earendil-works/pi-ai version engines --json
node --version
```

停止 DSH 后，把 `<version>` 换成目标版本执行；系统级安装需要 `sudo`，用户自有安装去掉 `sudo`：

```sh
DSH_ROOT="$(dirname "$(dirname "$(readlink -f "$(command -v dsh)")")")"
sudo npm pkg set 'overrides.@earendil-works/pi-ai=<version>' --prefix "$DSH_ROOT"
sudo npm install --prefix "$DSH_ROOT" --package-lock=false --ignore-scripts --omit=dev --no-audit --no-fund --dry-run
sudo npm install --prefix "$DSH_ROOT" --package-lock=false --ignore-scripts --omit=dev --no-audit --no-fund
```

用独立命令检查整棵依赖树；结果应只包含目标版本并标记 `overridden`，不能残留更近的旧副本：

```sh
npm ls --prefix "$(dirname "$(dirname "$(readlink -f "$(command -v dsh)")")")" @earendil-works/pi-ai --all
```

依赖代码只在进程启动时装载，因此升级后必须重启 DSH，不能用 settings/Profile HMR 代替。刷新 Models 页面后，目标模型应使用目录中的正式名称，reasoning/effort 档位应与发布包一致；再用新 Session 验证文本请求、工具调用和 reasoning replay。

回滚时停止 DSH，删除 override 并按原依赖范围重装；系统级安装需要 `sudo`：

```sh
DSH_ROOT="$(dirname "$(dirname "$(readlink -f "$(command -v dsh)")")")"
sudo npm pkg delete 'overrides.@earendil-works/pi-ai' --prefix "$DSH_ROOT"
sudo npm install --prefix "$DSH_ROOT" --package-lock=false --ignore-scripts --omit=dev --no-audit --no-fund
```

这项 override 修改安装产物，不是 DSH 源码；重新安装或升级 DSH 会覆盖它，也会影响同一 Host 中共享 pi-ai 的适配器和 Plugin。目标版本超出适配器声明范围时，本地 override 只是可撤销的过渡方案，正式升级仍应由 DSH 更新依赖并完成回归。

> 来源：[pi-ai 0.84.3 changelog](https://github.com/earendil-works/pi/blob/v0.84.3/packages/ai/CHANGELOG.md#L3-L28)记录了新模型目录与推理档位的更新；依赖覆盖后的兼容性仍需针对实际 DSH 与 pi-ai 版本组合验证。

### Skills

`dsh-skill-filesystem` 按顺序扫描项目的 `.dsh/skills`、项目的 `.agents/skills`、显式自定义目录、`$DSH_HOME/skills`，以及 `$DSH_AGENTS_HOME/skills`（默认 `~/.agents/skills`）。较早的根在同名 Skill 冲突时优先。

Skill 支持 `<name>/SKILL.md` 目录 bundle 和 `<name>.md` 平铺文件；发现深度为一层。Provider 监听目录成员和 `SKILL.md` frontmatter 的变化。每次调用都会重新读取正文，因此正文与 `references/`、`scripts/`、`assets/` 的更新不需要重建目录；这些资源的变化本身也不会改变目录摘要。

> 来源：[Skill 根目录、优先级、格式与加载生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/skill/skill-filesystem/README.zh.md#L29-L67)。

### <a id="mcp"></a>MCP

DSH 通过内置 MCP client Plugin 接入外部工具。插件运行在 DSH Host 进程中，每个配置实例连接一个 MCP server，并将它的工具注册到 `ctx.tools`；工具公开名称中的 server namespace（服务器命名空间）用于区分不同 server 提供的同名工具。

MCP client 支持 `stdio` 和 `streamable-http` 两种连接方式。`stdio` 模式下，DSH 按 `command` 和 `args` 启动独立的 MCP server 子进程：DSH 是父进程，server 是子进程，各自拥有进程 ID 和环境变量，通过标准输入、标准输出管道通信。`streamable-http` 模式下，client 通过网络连接 `url` 指向的现有服务，本地只运行 DSH 中的 client 插件。

> 来源：[MCP client 的工具注册职责](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L1-L14)；[stdio 子进程与 HTTP 连接的创建](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/transport.ts#L25-L49)。

本节将 MCP client 写在 web profile 的 `$DSH_HOME/profiles/web/cordis.patch.yml` 中，通过顶层 `insert` 列表为每台 server 添加一个实例，由 DSH 统一加载和管理。同一 DSH 进程中可使用相应工具的多个会话共享这些连接；使用 `stdio` 时，也共享对应的 MCP server 子进程。不同配置与加载方式的共享范围如下：

| MCP client 的配置与加载方式 | 实例与连接的共享范围 |
|---|---|
| 写入 Profile/Home patch，由 DSH 统一加载（本节采用） | 同一 DSH 进程中可使用该工具的会话共用实例、连接及对应的 stdio 子进程 |
| 写入 Agent preset | 同一 preset 配置版本只加载一次，使用该版本的多个 Agent 共用实例与连接 |
| 通过自定义代码在每个 `agent.ctx` 单独加载 | 每个 Agent 各有实例与连接；stdio 各自启动 server 子进程 |

> 来源：[MCP 实例的注册作用域](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L137-L190)；[多个 Agent 共用 preset 插件实例](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/preset/agent-presets/src/index.ts#L1-L22)。

按本节方式配置的 MCP client，其连接由 DSH 中的插件实例管理：新会话接入已有连接，会话结束后连接继续供其他会话使用；插件停用、配置重载、Host 关闭或断线重连时，连接相应销毁或重建。每个独立 DSH Host 进程都持有自己的 client 连接和 stdio 子进程，包括使用同一 Profile 启动的多个 Host。多个 HTTP client 可以连接同一远端服务，服务端状态的共享方式由该服务实现决定。

DSH 按 Session 分别保留会话历史。共用 MCP 的会话可能共同使用 server 的内存状态、认证身份和外部资源；这些状态与资源的会话级隔离需要 server 或部署方案显式提供。

> 来源：[MCP 连接的插件级生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L137-L190)。

配置由 `transport` 字段的值决定取哪个分支，两个分支构成判别联合（discriminated union，由一个共用字段决定取哪个分支的联合类型），字段不共用：

| | `stdio` | `streamable-http` |
|---|---|---|
| 连接方式 | spawn 本机子进程，管道通信 | 连接远程 HTTP MCP 端点 |
| 必填字段 | `command` | `url` |
| 认证位置 | `env`（并入子进程环境） | `headers`（附加到每条请求） |
| 分支其余字段 | `args`、`cwd` | — |

`serverName`、`toolCallTimeoutMs`、`failOnStartupError` 与 `reconnect.*` 为两种 transport 共有。Streamable HTTP 内部使用 SSE，但配置枚举只有这两个值，没有单独的 `sse` 或 WebSocket 选项。认证位置的差异源于形态本身：stdio server 是本地进程，自己读环境变量；HTTP 端点没有子进程，凭据只能放进请求 header。

当前 Harness 消费面覆盖 **Tools**；Resources 与 Prompts 等待相应的消费接口。执行期规范值保留完整 JSON MCP blocks 和可选 `structuredContent`。进入模型历史时，文本与资源链接转成文本；挂载附件存储且调用模型明确声明图片输入能力时，PNG、JPEG、WebP 和 GIF 会成为持久图片块。音频、嵌入资源和 Harness 当前范围之外的 block 会变成明确的诊断文本。

MCP server 采用显式启用方式：部署在 patch 中加入 server 对应的 MCP client Plugin 实例。`stdio` server 由 Host 直接启动并持有 Host 用户权限；Agent 工具沙箱与 server 进程构成两个独立的权限范围。

> 来源：[MCP transport、工具命名、结果映射与图片准入](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L5-L32)，以及[工具结果与已知边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/mcp/mcp-client/README.zh.md#L62-L117)；[transport 判别联合 schema 与两种 Config 的字段清单](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L49-L134)。

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

`id` 是 Cordis 配置行的稳定标识，只需在组合中保持唯一，不要求以 `mcp` 开头。为了让 MCP 行在 patch、日志和排障输出中容易识别，推荐使用 `mcp-<serverName>` 形式；`mcp-` 是配置可读性约定，模型工具名仍由 `serverName` 决定。`serverName` 对应模型所见的 `mcp__<serverName>__<rawName>` namespace；它匹配 `[A-Za-z0-9_-]{1,32}`；在同一注册作用域内，存活的 MCP client 实例不能使用相同的 `serverName`。

上例中的环境变量读取与 MCP 凭据配置分属不同位置，需结合 `transport` 一起看：

| 写法 | 含义 | 上例中的用途 |
|---|---|---|
| `process.env` | Node.js 提供的当前进程环境变量对象，不是文件 | YAML 的 `!!js` 在 DSH Host 中求值，因此从 Host 环境取 token |
| `config.env` | 这条 stdio MCP client 配置中的 `env` 字典 | 明确补充或覆盖交给 `local-tools` 子进程的变量 |
| `config.headers` | 这条 HTTP MCP client 配置中的请求头字典 | 把 Host 取出的 token 构造成发给 `remote-tools` 的认证头，不创建子进程 |

在 stdio 配置 `LOCAL_MCP_TOKEN: !!js process.env.LOCAL_MCP_TOKEN` 中，左侧是交给 MCP 子进程的变量名；右侧的 `!!js` 是 Cordis 的 YAML 标签，让 Host 在挂载配置时把后面的内容当作 JS 表达式求值。这里直接取出 Host 环境中的 token，而不是把 `process.env.LOCAL_MCP_TOKEN` 当字面字符串传给 MCP。两侧可以使用不同变量名，但左侧必须符合该 MCP server 的要求。

`config.env` 不会自动读取某个 `.env` 文件：由 shell 或 systemd 把环境文件加载进 Host 的方式见下文。若 MCP server 本身也用 Node.js，它启动后代码里的 `process.env` 指它自己的子进程环境，已不是 Host 的那个对象。

stdio MCP 的 `config.env` 在 DSH 完成[子进程环境过滤](#child-process-environment)后合并，因此上例必须显式转发 `LOCAL_MCP_TOKEN`；它不会仅因存在于 Host 中就被默认继承。普通变量仍可能从 Host 继承，`config.env` 不是完整环境白名单；具体筛选、覆盖顺序及安全限制统一见该节。

HTTP 配置中的 `Authorization: !!js >-` 则用 Host 取出的 token 构造请求头。`!!js` 同样要求把内容当 JS 表达式求值；`>-` 是 YAML 的折行标量写法，其中 `>` 把普通折行合为空格，`-` 去掉末尾换行，只负责长表达式的排版，不提供认证或过滤。表达式中的 `a && b` 是 JS 短路求值：上例仅在 `process.env.REMOTE_MCP_TOKEN` 为真值时拼接 `Bearer …`；变量未设置时直接得到 `undefined`。

表达式的结果随后接受 MCP 配置校验。`env` 和 `headers` 都要求字符串字典，因此上例的 stdio 直接引用与 HTTP 短路表达式在变量未设置时都会因 `undefined` 而加载失败。若 HTTP 照官方 README 的直写形式 `` !!js '`Bearer ${process.env.MCP_TOKEN}`' ``，模板字符串会把缺失值拼成 `Bearer undefined`，字符串校验反而放行。显式空字符串也能通过字符串校验，`a && b` 在 token 为空时同样返回空字符串；这些写法都不验证凭据是否有效。允许匿名访问的 HTTP server 可以省略认证头；设字符串默认值只能避免缺值的类型错误，不能代替有效凭据。

> 来源：[官方 README 的 HTTP header 直写示例](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/README.zh.md#L45-L60)、[`env` 与 `headers` 的字符串字典校验](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L113-L134)。

接入新 server 时，可以先把 overlay 保存为独立文件，例如 `./mcp-test.cordis.yml`，并在测试 shell 中导出 overlay 引用的环境变量。第一条命令验证配置层能否组合，第二条命令在备用端口启动一次真实 Web 进程，完成连接和工具发现测试：

```sh
dsh --profile web --patch ./mcp-test.cordis.yml --dump-config >/dev/null
dsh --profile web --patch ./mcp-test.cordis.yml --no-open --port 3081
```

`--patch <path>` 的作用域是当前进程，测试进程结束时该 overlay 的运行生命周期随之结束。测试通过后，把同一 `insert` 合并进持久 patch：单个 Profile 使用 `$DSH_HOME/profiles/<profile>/cordis.patch.yml`，所有 Profile 共用则使用 `$DSH_HOME/cordis.patch.yml`。配置层按 bundle、Profile patch、home patch、各个 `--patch` 的顺序叠加，后面的同 id 修改优先。

Web 部署通常把 server 定义写进 `$DSH_HOME/profiles/web/cordis.patch.yml`，并把该 Profile 使用的启动环境集中在相邻的 `$DSH_HOME/profiles/web/<env-file>`。编辑 patch 时保留现有顶层数组内容，把新的 `insert` 与已有条目合并。Profile 环境文件使用一行一个 `KEY=value` 的格式，YAML 通过 `process.env` 引用对应值：

```dotenv
LOCAL_MCP_TOKEN=<token>
REMOTE_MCP_TOKEN=<token>
```

```sh
chmod 600 "$DSH_HOME/profiles/web/<env-file>"
```

`<env-file>` 表示部署自行选定的环境文件名；下文的 shell 命令与 systemd `EnvironmentFile=` 都应替换成实际路径。这个文件由启动方式加载，DSH 不会因为它与 patch 相邻便自动读取；上例的 MCP 表达式引用的是 Host 中已经存在的变量。直接从 shell 启动 dsh 时，先把变量导入当前 shell，再启动目标 Profile：

```sh
set -a
. "$DSH_HOME/profiles/web/<env-file>"
set +a
dsh --profile web
```

**systemd service 托管。** 下面的内容适用于由 systemd 启动 dsh 的部署。system service 的 drop-in 记录环境文件路径：

```ini
[Service]
EnvironmentFile=<absolute-dsh-home>/profiles/web/<env-file>
```

system service 把 drop-in 保存到 `/etc/systemd/system/dsh.service.d/20-mcp-environment.conf`；user service 把它保存到 `~/.config/systemd/user/dsh.service.d/20-mcp-environment.conf`，并使用对应的 `systemctl --user` 命令。drop-in 变更通过 `daemon-reload` 和 restart 生效；环境文件中的值变更通过 restart 进入新进程：

```sh
sudo systemctl daemon-reload
sudo systemctl restart dsh.service
systemctl show dsh.service -p EnvironmentFiles -p ActiveState -p SubState
```

systemd 的 PATH 通常比交互 shell 短，systemd 部署中的 stdio `command` 使用绝对路径可获得一致的命令解析结果。

config 的 schema 校验发生在插件 apply 之前；`failOnStartupError` 只覆盖初始连接与工具同步这类运行期失败，管不到校验层。校验失败的表现按进程状态分两种：冷启动 `dsh --profile web` 时一行配置校验抛错，整棵 plugin tree 加载失败、进程非零退出，错误从 `failed to apply loader entry <id>` 汇总为 `plugin tree failed to load`，不是只跳过这一行；已在运行的进程改 patch 触发 HMR（机制见 [Patch 热更新的生效机制](#mcp-patch-hot-reload)）时，校验失败的候选被整体丢弃，上一棵可用树继续服务，进程不退出。

> 来源：[`failOnStartupError` 的作用域](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L67-L72)、[冷启动时 `plugin tree failed to load` 的汇总与退出](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/boot/app-boot/src/index.ts#L770-L788)、[HMR 候选失败后保留旧树的测试](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/boot/app-boot/tests/config-reload.spec.ts#L190-L210)。

#### <a id="mcp-patch-hot-reload"></a>Patch 热更新的生效机制

持久 patch 改动不重启进程即生效，运行中的会话也会在下一个模型请求上看到工具集变化。这个机制在 Cordis 里叫 HMR（Hot Module Replacement，热模块替换）：监视文件改动、不重启进程就地重载改动部分。本节沿文件监视到模型请求的顺序展开这条链路。

是否安装监视器由 Profile 清单的 `patchReload` 字段决定：出厂模板里 web 是 `live`，acp / headless / sdk / sdk-minimal 是 `startup`（改动等下一次启动生效），自建 Profile 默认 `live`。被监视的是两个文件——`$DSH_HOME/profiles/<profile>/cordis.patch.yml` 和 home 层 `$DSH_HOME/cordis.patch.yml`；`--patch` overlay 只活在当前进程，不在监视范围。Profile 若没有显式启用模块 HMR，启动器会补挂一个 `root: []` 的 watch-only HMR 实例：只做配置文件热更、不替换源码模块——dsh-base 默认关闭模块 reload，patch 编辑走的是配置专线。

**包重装的热生效按 DSH 版本分叉（🔬 2026-10-18 对 `@deepseek-ai/dsh-hmr` 发布 tarball 逐行 diff 实测）**：`<0.2.1-alpha.3` 里，profile `package.json` 虽也被 `registerConfig` 监视，但刷新回调先比较 bundle 列表 JSON，列表不变（典型：`dsh plugin add` 只升版本号）就 early-return；模块文件监视又忽略 node_modules——所以旧版"已运行进程保持原 Bundle 集合，重启后切换"。`≥0.2.1-alpha.3` 新增 `ModuleFiles`：按 `inode:size:mtime` 记录已加载 `file:` 模块的磁盘身份（特意兼容 pnpm 从 store 硬链接导入的场景），依赖遍历增加 `includeNodeModules`；重装/换版后这些模块被判为陈旧并热重载受影响 entry——`dsh plugin add` 装完即热生效，无需重启进程，运行中会话同样在下一个模型请求看到新工具集。

监视由 HMR 的 `registerConfig` 完成：它用 chokidar（Node 生态常用的文件变动监视库）监听确切路径（文件还不存在时向上找最近的现存父目录当 watch root），add / change / unlink 都触发刷新；每次刷新串行执行且用 dirty 标记合并连发事件，编辑器一次保存触发多个事件也不会并发重放。刷新回调重新读 patch 文件（文件被删除等价于用户层清空）、按启动时的层次重新组合（bundle 层在下、`--patch` overlay 在上），然后对根 Include 条目调用 `entry.update()`；Include 收到 `internal/update` 后，把新 patch 列表应用到缓存的基准解析上，产出新的 entry 列表交给 Loader。

Loader 对新列表做事务式对账：`EntryGroup.update` 逐行 `create`，消失的行 dispose，任何一行失败则整体回滚、上一棵可用树继续服务。单行处理按 diff 分三种：全新行——导入插件、启动 fiber（Cordis 中一个插件实例的运行与生命周期单元），`apply()` 连接 server 并把工具注册进 `ctx.tools`；只改 `config`——`Fiber.update` 先触发 `internal/update` 事件链（监听者可否决或替换默认动作），默认动作是 `restart()`：dispose 当前实例、带新配置重新 apply；`name` / `inject` 变化——dispose 后重新导入再启动。MCP client 没有挂自己的 update 钩子，所以「编辑某台 server 的配置行」在 loader 层就是换实例。README 说「编辑配置项会在原地重载服务器连接，未变的名称保持不变」——「原地」指 loader 的 entry id 稳定，「名称不变」来自公开名是 `(serverName, rawName)` 的纯函数：实例换了名字不换，会话历史与权限规则继续有效。

运行中的会话无需任何通知就能看到变化：agent loop 在每个 step（每次模型请求）前都重新执行 `systemPrompt.assemble()`；ToolRuntime 在构造时把自己注册为 tools provider，`wireSchemas` 每次都从 live 层注册表现算该 scope 的可见工具——注册表与请求之间不存在缓存快照，会话本身也不持久化工具清单。因此 patch 落地后，正在执行的 turn 的下一个 step、空闲会话的下一个 turn，模型请求自然带上新的工具集。两个边界要精确：同一 step 的重试沿用已构建的请求（含旧工具表），变化从下一个 step 边界生效；被编辑行对应的 server 上正在执行的 `tools/call` 会在 dispose 中被中止（supervisor 等在途调用停稳才完成卸载），以取消收场。server 侧的工具清单变化（`tools/list_changed` 通知）重同步进的是同一条注册表，与 patch 走同一条可见性路径。

> 来源：[watchUserPatches 与 patch 文件重读](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/boot/app-boot/src/index.ts#L235-L267)、[Profile 模板的 patchReload 取值与自建默认](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/boot/app-boot/src/profile.ts#L137-L169)、[live 判定与 watch-only HMR 实例](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/apps/cli/src/profile-boot.ts#L270-L296)、[registerConfig 的确切路径监视与串行刷新](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/vendor/hmr/src/index.ts#L134-L187)、[Include 对 internal/update 的重应用](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/vendor/include/src/index.ts#L206-L213)、[EntryGroup 的事务对账与回滚](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/vendor/loader/src/config/group.ts#L59-L106)、[Entry.update 的三种分叉](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/vendor/loader/src/config/entry.ts#L142-L246)、[Fiber.update 默认 restart](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/vendor/cordis/src/fiber.ts#L736-L753)、[MCP 插件「HMR 换实例、名称不变」的约定](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/index.ts#L7-L11)、[agent loop 每 step 重新 assemble](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/core/agent-loop/src/agent.ts#L234-L296)、[ToolRuntime 注册为 tools provider](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/core/tools/src/index.ts#L825)与[view 的 live 层遍历](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/core/tools/src/index.ts#L1143-L1184)。

无论采用 shell 还是 systemd 启动，上述热更新对 live 型 Profile 同样成立（startup 型 Profile 的 patch 改动在下次启动时生效）。Patch 热更新只重读配置，不重读启动环境文件；systemd 的 `EnvironmentFile=` 值变更须通过重启服务进入 Host，shell 部署则重新导入环境后再启动。随后按[持久配置 MCP Server](#mcp-persistent-configuration)中的 `config.env` 或 `config.headers` 转发给对应 server。

完成持久配置后，通过服务状态和新 Session 的工具清单验收；新 Session 中应能看到 `mcp__<serverName>__...` 工具。

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

#### <a id="subagent-concurrency"></a>并发派发与上游速率预算

单条消息里的多条 subagent 调用按 agent-loop 的滚动池调度：同时 in-flight 的并行安全调用至多 `maxParallelToolCalls` 条（默认 10），其余排队等空位依次执行。排队属于调度行为，调用条数超出池宽时依然全部获得执行机会。

每个子代理是独立的 LLM 消费者：一次 N 路 burst 的峰值 token 吞吐约等于"池宽 × 单路上下文体积"，全部计入同一个上游账户的速率预算。走订阅类 key（Token Plan 一类）时账户按 RPM/TPM 维度限流，超额请求返回 429，官方并发指引按套餐分级（数个持续运行的 agent 量级）并在高峰时段动态收紧。提高并行路数的两条正路：把 burst 规模控制在账户吞吐内，或给子代理任务做 prompt 瘦身——契约内联进任务描述，替代每个子代理各自读入同一份大文件。

子代理运行以 stopReason `completed` 收尾；`aborted` / `error` / `max-tokens` / `refusal` 等其他停止原因都会以 failed 信号上报父会话。`dsh-llm-retry` 对 `RATE_LIMIT` / `SERVER` / `TIMEOUT` / `EMPTY_RESPONSE` / `TRANSPORT` 类失败按指数退避重试（默认 5 次、约 500ms 起逐次翻倍、单次上限 10s，整链约 15s）；上游限流窗口以分钟计时，把退避上限调到与之间量级（60s+）即可让 burst 场景下的瞬时 429 自愈。

每个子代理有独立会话日志（`~/.dsh/sessions/<workspace>--/<child-id>/session.v3.jsonl.zstd`，zstd JSONL）；`llm/retry`、`turn/end`、`tool/call` 事件给出终态与最后动作，是诊断批量结果的第一通道。评估批量结果时以子代理实际产物为准，终态信号与产物落地时刻各自独立。用量按尝试去重的口径见[子代理、重试与历史范围](#session-statistics-scope)。

> 来源：`@deepseek-ai/dsh-agent-loop` 的 `DEFAULT_MAX_PARALLEL_TOOL_CALLS` 常量与 `dsh-tool-subagent` 的 stopReason 映射（本地安装 0.1.5-rc.3 源码读取）；重试策略形状取自会话日志 `policyKey`（`["normal",5,["EMPTY_RESPONSE","RATE_LIMIT","SERVER","TIMEOUT","TRANSPORT"],500,10000,0.1]`）实测记录。

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

### <a id="child-process-environment"></a>子进程环境与凭据过滤

子进程是 DSH Host 另行启动的程序进程，例如 Shell 命令或 stdio MCP server；Host 是父进程，两者的环境变量分别属于各自的进程。DSH 的环境过滤发生在为子进程准备继承环境时，控制的是从 Host 默认复制哪些变量，不是清理 DSH 自己的环境。它由 `dsh-subprocess` 的 `scrubbedParentEnv()` 定义，本地子进程服务使用它构造执行环境；stdio MCP transport 虽由 Host 中的 MCP SDK 启动进程，也复用同一个过滤函数。HTTP MCP 没有这条子进程路径，认证配置见[MCP](#mcp-persistent-configuration)。

`process.env` 是当前 Node.js 进程的环境变量对象。过滤函数每次遍历 Host 当前的 `process.env`，建立一个新对象；它既不修改 Host 的原环境，也不把任何值替换成脱敏字符串。名称筛选等价于下面的代码：

```js
const sensitiveName = /KEY|PASSWORD|SECRET|TOKEN/i
const inheritedEnv = {}
for (const [name, value] of Object.entries(process.env)) {
  if (value === undefined || sensitiveName.test(name) || name.toUpperCase().startsWith('DSH_')) continue
  inheritedEnv[name] = value
}
```

这段筛选依次排除没有值的项、名称包含 `KEY` / `PASSWORD` / `SECRET` / `TOKEN` 任一片段的项，以及名称以 `DSH_` 开头的项。两类名称匹配都不区分大小写；匹配的是任意子串，不要求词边界，所以名称中偶然含有 `KEY` 的普通变量也会被移除。其余变量保留原值，包括空字符串。

| Host 中的变量名示例 | 默认继承结果 | 原因 |
|---|---|---|
| `DEEPSEEK_API_KEY`、`LOCAL_MCP_TOKEN` | 移除 | 名称含 `KEY` 或 `TOKEN` |
| `db_password`、`APP_SECRET` | 移除 | 名称含 `PASSWORD` 或 `SECRET`，大小写不影响匹配 |
| `DSH_HOME`、`dsh_session_id` | 移除 | 名称以 `DSH_` 开头，避免继承旧的 Harness 身份与运行事实 |
| `PATH`、`HOME`、`LANG`、`HTTPS_PROXY` | 原值保留 | 名称未匹配过滤规则 |
| `CODEX_HOME`、`PORTAL_ALLOW_LOCAL_EXEC`、`SSH_AUTH_SOCK` | 原值保留 | 同样未匹配；不是仅传给名字所指的某个工具 |

筛选后的对象只是子进程环境的基底。调用方显式提供的 `env` 随后补充或覆盖它：本地子进程服务取 `spec.env`，stdio MCP 取已经求值的 `config.env`。因此，显式指定的 token 或当前 `DSH_*` 运行事实可以重新加入，不会再被这次继承过滤删除。本地子进程服务合并时，POSIX 按区分大小写的键覆盖，Windows 按不区分大小写的键覆盖；该服务还允许显式 `undefined` 删除一个变量，而 MCP 的 `config.env` 只接受字符串值。

> 来源：[继承环境过滤函数与名称规则](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/subprocess/subprocess/src/index.ts#L37-L66)；[本地子进程的显式环境合并](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/subprocess/subprocess-local/src/spawn.ts#L29-L47)；[MCP 复用过滤函数并合并配置](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-rc.1/packages/mcp/mcp-client/src/transport.ts#L15-L49)。上述规则已与 `0.1.2-rc.1` 安装产物核对。

这是一种按名称避免凭据被默认继承的启发式过滤，不是环境变量白名单，也不检查变量值。秘密若存放在不匹配的名称下，仍可能被继承；例如代理 URL 内的认证信息不会仅因其值包含密码就被删除。普通 Host Plugin 仍可读取共享环境，in-process subagent 也不因创建新 Session 获得独立进程环境。第三方程序自行启动后代进程或读取其他凭据来源，不受这次环境构造约束。

环境过滤与文件访问、模型输入脱敏也是不同机制。文件权限 `0600` 不能阻止同一用户身份下有相应访问权限的程序读取凭据文件；工具若把读出的原文作为结果返回，内容仍可能进入模型上下文和 Session 日志。清理子进程的继承环境既不禁止这条文件读取路径，也不脱敏工具输出。

### Agent 工具执行

#### 工具沙箱与审批

新 Session 默认使用 `workspace-write`，限制 Bash 和 filesystem mutation 的文件写入范围。该文件策略允许读取与网络访问；进程可见性由 sandbox backend 决定：bwrap 使用私有 PID namespace 隐藏 Host 进程，Landlock 与 Seatbelt 保持 Host 进程可见。Sandbox backend 负责执行层隔离，approval service 负责一次工具调用的 allow / ask / deny 决策。

部分平台只能提供有限隔离。没有可用 backend 时，负责强制隔离的执行器应显式失败，而不是悄悄退回无约束执行。

##### <a id="sandbox-tmp-ssh"></a>DSH 内 SSH 控制目录的可见性

本节处理 **SSH 在宿主终端正常，在 DSH 工具或内置终端中行为却不同**的情况，例如：一个工具调用刚创建控制目录，下一次调用又找不到；或者宿主已创建目录，DSH 终端仍报 `unix_listener ... No such file or directory`。SSH 的临时目录配置、安全初始化、认证后监听失败的源码解释与复用验收统一在 `software` skill（SSH 客户端与服务端）中维护；这里只说明 DSH 带来的执行环境差异。

按 `0.2.1-alpha.1` 源码，Linux 默认优先探测 bwrap，再尝试 Landlock。同为 `workspace-write`，`/tmp` 的含义仍取决于 runner：

- **bwrap**：`--ro-bind / /` 提供只读宿主根，`--unshare-pid --proc /proc` 提供私有进程视图，`workspace-write` 额外加 `--tmpfs /tmp` 和可写工作区 bind。这个 `/tmp` 是该执行器新建的挂载，不是宿主目录的可写映射。
- **Landlock**：授权列表给宿主 `/tmp` 和工作区读写权限，没有把 `/tmp` 换成新挂载。目录及仍存活的 SSH master 可以被下一次、同样有访问权限的客户端使用。
- **Seatbelt（macOS）**：把真实 `/tmp` 和 `os.tmpdir()` 列入可写根，内容跨命令持久。
- **Windows ACL**：为每个 session 分配随机私有临时目录，会话结束回收。
- **danger-full-access**：Bash executor 直接交给本地执行器，不调用 confinement；它看到的是宿主 `/tmp`。这是文件策略，不是 sudo 或 root 提权，也与审批是否需要用户回答分属不同机制。

进程内文件工具（read/edit/write）按 fs fence 的同一套可写根判定，落的是宿主机真实 `/tmp`，与 Bash 沙箱内那份相互独立。经 `/tmp` 中转文件前先确认所在 backend；需要跨命令或交给用户的产物写入 workspace。

> 来源：[bwrap 与 Landlock 的 profile 构造](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/sandbox/sandbox-local/src/profiles.ts#L16-L35)、[Linux runner 优先链](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/sandbox/sandbox-local/src/index.ts#L151-L166)、[Bash 按模式选择直接执行或 confinement](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/shell/bash-sandbox/src/index.ts#L89-L103)、[Seatbelt 与进程内 fs fence 共享的可写根含 `/tmp` 与 `os.tmpdir()`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/sandbox/sandbox/src/roots.ts#L43-L55)、[Windows ACL 为每个 session 分配随机私有临时目录](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/sandbox/sandbox-local/src/index.ts#L8-L13)。以上与该版本安装产物核对。

执行器生命周期进一步决定能复用多久。普通 Bash 调用每次走 `confine(['bash', '-c', command], …)`：若选 bwrap，每条命令便有独立 `/tmp`。持久终端则在 `spawn()` 时 confinement 一次，后续输入送进同一 PTY；在这个 PTY 内创建 `/tmp/ssh-cm-<uid>/` 后，可以在终端存活期间复用。另一个 PTY 或普通 Bash 工具调用不会自动共享它。

> 来源：[普通命令的 confinement 入口](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/shell/bash-sandbox/src/index.ts#L183-L190)、[终端按策略包装 shell argv](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/terminal/terminal-bash/src/index.ts#L100-L109)、[每个持久终端仅在创建时 spawn shell](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/terminal/terminal-bash/src/index.ts#L201-L226)。

处理这种目录不可见问题时，在**实际使用的 PTY 内**执行 SSH 指南中的目录准备步骤，并在同一 PTY 建立 master。DSH `terminal-bash` 默认以 `--noprofile --norc -i` 启动，不自动读取 `.bashrc`；要么在该 PTY 显式初始化，要么配置经授权的终端启动初始化。若需求是跨普通 Bash 工具调用复用，则还需提供共享的可访问目录，并确认 master 能跨执行器存活，不能仅把 `ControlPath` 改成另一个路径就认为已经解决。

> 来源：[终端的默认 shell 参数及覆盖规则](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/packages/terminal/terminal-bash/src/config.ts#L62-L88)。2026-10-22，Linux/OpenSSH 8.0p1 对照实测：宿主私有 `/tmp` 下建立的 master 可被第二次独立命令复用，第二客户端禁用认证方法仍成功执行只读命令，并返回同一 master PID；分别按上述 profile 启动的两个 bwrap 执行器则不共享第一份目录。不能把后一个结果扩大为“SSH 无法靠 `/tmp` 复用”。

##### <a id="sandbox-uid-ssh"></a>用户命名空间中的文件属主检查

这是另一种独立症状：**同一 SSH 配置在宿主可以读取，在 DSH 的 bwrap 工具中却报 `Bad owner or permissions`**，且文件属主在两边显示不同。沙箱内的数字 UID 属于当前用户命名空间的视图，应先在获准的宿主视图与执行器内分别核对 `id`、`/proc/self/uid_map`、文件数字属主和 mode；不能只看到 `nobody:nobody` 就建议在宿主执行 `chown`。

OpenSSH 8.0p1 在读取带权限检查标记的配置时，要求文件属主是 `0` 或 `getuid()`，并且不允许 group/other 写入；每个递归 `Include` 都会加这个检查。在一次 bwrap 环境中，宿主本来为 `0:0 0644` 的系统 Include 文件，在沙箱内显示为未映射 UID `65534`，且不等于进程 UID，于是被拒绝；宿主相同配置正常。这是用户命名空间与应用安全检查的交互，不是宿主配置真的被改了属主，`chmod` 也不能修正 UID 视图。临时文件目录不存在导致的 `unix_listener ... ENOENT` 是另一条路径，应分别诊断。

> 来源：[OpenSSH 配置的数字 UID/mode 检查](https://github.com/openssh/openssh-portable/blob/V_8_0_P1/readconf.c#L1788-L1799)、[Include 递归强制权限检查](https://github.com/openssh/openssh-portable/blob/V_8_0_P1/readconf.c#L1551-L1565)；2026-10-22 现场配对观察到宿主 UID `0`、bwrap 内 UID `65534`，并用相同 bwrap profile 复现该报错。UID 是否映射取决于实际 user namespace，不能概括成所有 bwrap 环境都显示相同属主。

需要隔离诊断时，可在权限允许且配置已审核的条件下显式 `-F <用户配置>`，区分用户配置与系统 Include 的影响；它会跳过默认系统配置，不是通用修复，若该文件又 Include 了同样的系统文件，仍会触发递归权限检查。准备控制目录、检查主机密钥与修复 SSH 配置权限是不同操作，不能为了通过沙箱内的一次检查降低宿主的权限或主机密钥校验。

#### MCP 进程权限

`stdio` MCP server 是 Host 启动的独立可执行程序。Agent 看到的是它桥接出的 tool，但 server 本身不在 Agent 工具沙箱里；HTTP MCP server 则把同等信任转移到远端服务和认证 header。默认 Profile 因此不启用任何 MCP server。

> 来源：[CLI 对默认权限、网络与进程可见性的说明](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L81-L91)；[sandbox policy 的文件操作边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/sandbox/sandbox-policy/README.zh.md#L59-L68)。

### <a id="telemetry-data"></a>遥测数据

Session telemetry 默认是 `DISABLED`，启动 Web 或运行 Agent 时数据留在本地。显式启用时：

- `FULL` 持续把投影后的 Session records 交给 OpenTelemetry backend；
- `FEEDBACK_ONLY` 只在记录反馈时回放并导出相关 Session log 后缀。

Telemetry seam 提供 `sessionTelemetry/record` waterfall，让部署挂载脱敏规则；官方默认组合没有挂载任何规则。因此上传模式会按捕获值转发 message、tool arguments/results、文件内容和 workspace path 中可能存在的敏感信息。`DSH_TELEMETRY_MODE` 选择模式，任意非空的 `DSH_TELEMETRY_DISABLED` 都会强制关闭，collector 由 `DSH_TELEMETRY_OTLP_URL` 选择。

> 来源：[默认遥测模式、环境变量与数据边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L89-L91)；[脱敏扩展点与默认无规则的边界](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/packages/session/session-telemetry/README.zh.md#L37-L53)。
