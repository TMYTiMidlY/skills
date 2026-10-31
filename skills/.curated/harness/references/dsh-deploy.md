# DeepSeek Harness（dsh）安装、服务部署与维护

本文负责 DSH runtime 的取得、固定安装、服务托管、多实例、升级、验收和回滚。运行模式、Profile／模型／MCP 配置、Plugin、会话与权限机制见 [DSH 运行时](dsh.md)；Plugin 开发与打包见 [Plugin 开发](dsh-dev.md)。运行时篇只保留这些部署主题的导航，具体操作在本文维护。

本 skill 的 DSH 首次部署与升级把 **pi-ai 更新到当次 registry 的 `latest`** 作为固定步骤：当次查询版本号，再将明确版本写入依赖覆盖；下一次升级重新查询。DSH 本体使用明确的目标发布版本或源码 tag。这样能持续更新模型目录，并保留每次部署可复现、可回滚的版本组合。

统一的是识别安装、选择版本、覆盖依赖、切换运行实例和验收的流程；具体写入位置、包管理器、权限及进程管理方式由实际部署决定。下面的 Linux 系统 npm 命令是其中一种实现，其他安装方式按对应分支处理。

新建长期部署优先使用独立、固定路径的安装项目，把 DSH 精确版本、pi-ai override 和锁文件保存在外层 manifest；服务入口固定到该项目。这样覆盖能随本体升级保留，锁文件可复现整棵依赖树。既有全局安装沿用原安装方式即可，每次重建安装树后重新应用覆盖。具备候选目录或镜像的部署，可在停机前完成依赖安装、构建和隔离验收，再停服务、备份数据并切换入口，缩短停机时间。

只修复模型目录时，保留 DSH 本体版本，跳过本体升级，直接覆盖 pi-ai 并重新安装依赖。全局 DSH 升级会替换包目录，包内的 override 随之丢失，因此每次本体升级后都要在新安装树中重新设置。

## <a id="installation-scope"></a>安装位置与运行实例

先从服务 `ExecStart`、启动脚本或运行进程确认实际 DSH 入口，再核对安装方式、目录所有者、包管理器、运行 Node 的绝对路径、包管理器版本和 registry。服务、容器、Python SDK 与当前 shell 可能分别使用不同的 `dsh`。`command -v dsh` 只反映当前 shell；以实际运行者的入口为准。

Linux npm 发布包的入口目前为 `<dsh-root>/lib/bin.js`，可以使用 `readlink -f` 反推。跨平台定位优先读取已确认包管理器的安装位置：npm 全局包用该 npm 的 `root --global --prefix <原全局 prefix>`，本地包用所属项目的依赖解析结果；再核对该包 `bin.dsh` 与启动入口是否对应。Linux／macOS 的全局包通常位于 `<prefix>/lib/node_modules`，Windows 则位于 `<prefix>/node_modules`。macOS 系统 `readlink` 不提供 GNU 的 `-f`，可用已确认 Node 的 `fs.realpathSync()` 解析软链；Windows `.cmd`／`.ps1` shim 要读取转发目标，不能按目录层数反推。

下面仅是 Linux npm 入口布局的定位例子；先把 `DSH_BIN` 换成实际服务入口：

```sh
DSH_BIN='<服务实际使用的 dsh 绝对路径>'
DSH_ROOT="$(dirname "$(dirname "$(readlink -f "$DSH_BIN")")")"
```

随后读取 `$DSH_ROOT/package.json`，确认包名为 `@deepseek-ai/dsh`。源码、Windows shim、pnpm wrapper 或其他入口布局按真实项目结构定位。

| 安装方式 | 升级对象与 pi-ai 覆盖位置 | 权限与包管理器 |
|---|---|---|
| 系统 npm 全局安装 | 本体安装到原全局 prefix；升级后在 DSH 包根的 `package.json` 写 npm `overrides` 并重装包内依赖 | 以可写安装目录的身份操作；需要提权时用 `sudo`，固定 Node PATH、npm 绝对路径和 prefix |
| 用户 npm 全局安装，含 NVM / fnm / asdf | 原 Node 环境的全局 prefix；升级后在 DSH 包根写 npm `overrides` | 由安装目录所有者运行，通常无需 `sudo`；固定原 Node/npm，切换 Node 后重新核对服务入口 |
| npm 项目本地安装 | 管理 DSH 的项目根 `package.json` 写 `overrides`，更新 DSH 依赖及项目锁文件 | 使用该项目原有 npm；覆盖位置是外层项目根 |
| pnpm 项目安装 | 所属 workspace 根配置写 pnpm `overrides`，更新 DSH 依赖及锁文件 | 使用项目指定的 pnpm，保留 workspace 其他配置 |
| pnpm 全局安装 | 找到 DSH 所属全局项目或安装组；每次全局升级后重新定位并覆盖 | pnpm 10 的共享根与 11 的独立安装组分别处理；由原安装用户操作 |
| `npx` / `pnpm dlx` 临时运行 | 新包规格或 cache 重建会产生另一棵安装树 | 持续保留覆盖时，改为有 manifest 的固定 npm / pnpm 项目，再使用项目流程 |
| 源码 checkout | 明确 tag 对应的仓库根 `pnpm-workspace.yaml` 写 `overrides`，更新锁文件并构建 | 使用 `packageManager` 指定的 pnpm；保留开发依赖和上游构建脚本策略 |
| Python runtime wheel／单文件可执行程序 | 内置依赖在打包的虚拟文件系统中；在构建源覆盖、重新打包，或选择已覆盖的外部 DSH | 保持 SDK 与 runtime 的精确版本配对及完整伴随资源 |
| 容器／只读镜像 | 在镜像或部署产物的构建项目中覆盖，再构建并切换整份产物 | 保留数据卷、运行用户和所有共享实例；权限由构建环境决定 |
| Yarn／Bun 等其他包管理器 | 使用原管理器的根项目覆盖字段及锁文件；先确认该版本支持的语法 | 沿用项目约定及实际运行入口，完成同样的依赖与运行验收 |

npm 的 `overrides` 只从执行安装的项目根读取。全局发布包在 `$DSH_ROOT` 内重装时，包根本身成为项目根；本地项目安装则编辑外层 manifest。pnpm 从所属根项目重建由其管理的软链和 store。

> 来源：[npm overrides 的根项目规则](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#overrides)、[npm 全局目录布局](https://docs.npmjs.com/cli/v11/configuring-npm/folders/)、[pnpm 10 的根项目 overrides](https://pnpm.io/10.x/settings#overrides)。

## <a id="first-install"></a>首次安装

DSH `0.2.1-alpha.1` 的 Node.js 要求是 `^22.19.0 || >=24.0.0`，其他目标版本读取其 `engines`；pi-ai 的要求也独立核对。npm 包提供已经构建的 CLI；源码 checkout 需要先生成 Host、Client 和前端产物。没有版本号的包规格会跟随 registry 的 dist-tag，显式的 `<version>` 则固定这次安装或运行所用的发布版本。

### <a id="first-install-methods"></a>发布包与源码

| 安装方式 | 命令 | 依赖解析时机 | 使用场景 |
|---|---|---|---|
| npm 临时运行 | `npx @deepseek-ai/dsh@<version> web` | 尚无可复用的 `_npx` 安装树时 | 官方快速启动入口 |
| pnpm 临时运行 | `pnpm dlx @deepseek-ai/dsh@<version> web` | 尚无对应的 dlx 临时项目时 | 临时验证；历史版本的 Linux Web 与 PTY smoke test 见下文 |
| npm 全局安装 | `npm install --global @deepseek-ai/dsh@<version>`，随后运行 `dsh web` | 安装或升级阶段 | 需要固定可执行路径的服务 |
| 源码构建 | 应用覆盖后执行 `pnpm install --no-frozen-lockfile && pnpm run build`，随后运行 `pnpm dsh web` | checkout 的安装与构建阶段 | 源码开发、锁文件复现或源码审计 |

源码模式以仓库根 `package.json` 的 `packageManager` 字段确定 pnpm 版本。`pnpm run build` 生成 CLI 所需的 Host、Client 和前端产物；`pnpm dsh web` 使用已有产物。

首次安装也按本文策略选择明确 DSH 版本，并在首次正式启动前绑定当次最新 pi-ai；临时运行适合快速验证，长期保留覆盖使用下文的固定项目。已有部署按[升级顺序](#sequence)维护。

> 来源：[官方 npm 与源码运行方式](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/README.md#L13-L37)；[Node 与 pnpm 版本约束](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/package.json#L1-L10)；[CLI 的可执行入口](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/package.json#L11-L18)。

### <a id="first-install-project"></a>独立安装项目

新建长期运行实例时，在安装用户有写权限的固定目录准备独立项目，例如用户自己的应用目录；系统集中维护可使用管理员管理的目录。安装目录与 Agent workspace、DSH home 分开。先选定明确 DSH 发布版本，查询当次 pi-ai latest，核对两者的 Node 要求；用以下最小 manifest 表达这个版本组合，替换全部占位符后保存为项目根的 `package.json`：

```json
{
  "name": "dsh-deployment",
  "private": true,
  "dependencies": {
    "@deepseek-ai/dsh": "<dsh-version>"
  },
  "overrides": {
    "@earendil-works/pi-ai": "<pi-ai-version>"
  }
}
```

使用与服务相同 Node 环境的 npm，固定 PATH 与项目 prefix：

```sh
DSH_PROJECT='<独立安装项目的绝对路径>'
DSH_NPM='<npm 的绝对路径>'
DSH_PATH='<Node 的 bin 目录及所需系统工具路径>'
env PATH="$DSH_PATH" "$DSH_NPM" install --prefix "$DSH_PROJECT" --no-audit --no-fund
env PATH="$DSH_PATH" "$DSH_NPM" ls --prefix "$DSH_PROJECT" @earendil-works/pi-ai --all
```

服务使用 `<project>/node_modules/.bin/dsh`，或明确 Node 与包内 `lib/bin.js`。保存 manifest 和 `package-lock.json`；后续复现已验收的同一组合可执行 `npm ci`，升级时按[项目安装](#user-and-project)更新 manifest 与锁文件。用户项目由该用户安装；root 管理的项目仅在安装阶段按需提权，运行身份仍按[服务托管](#service-management)选择。

pnpm 项目先在所属根配置[pi-ai 覆盖](#pnpm-and-source)，再用 `pnpm add --save-exact @deepseek-ai/dsh@<version>` 安装；Yarn／Bun 使用各自的[根项目字段与锁文件](#other-managers)。首次全局安装用[安装方式表](#first-install-methods)中的命令和实际 Node/npm/global prefix，随后在实际包根完成对应的 pi-ai 覆盖；系统 npm 布局可沿用[系统 npm 操作](#system-npm)的固定 PATH、npm、global prefix、cache 与包内重装步骤。首次安装先查询版本、核对 Node，再安装本体并解析包根；读取旧 DSH 版本、备份旧安装和停止旧实例的步骤仅在旧安装存在时执行。

源码首次部署 clone 官方仓库并 checkout 明确 tag，读取其 `packageManager`，在根配置覆盖后安装、构建。构建和旧 pi-ai 补丁适配见[源码安装](#pnpm-and-source)。Python SDK／单文件 runtime 和容器的首次部署见[打包运行时与容器](#bundled-and-container)，其内置依赖随构建产物交付。

> 来源：[npm overrides](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/#overrides)、[npm install](https://docs.npmjs.com/cli/v11/commands/npm-install/) 与 [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/)。

> 来源：上述 Node 要求与 npm CLI 入口另见 [DSH engines](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/package.json#L7-L10) 和 [CLI bin](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/apps/cli/package.json#L13-L16)。

### <a id="install-script-authorization"></a>安装脚本授权

普通 npm 安装使用官方命令即可；`@deepseek-ai/dsh` 本身不要求用户把一批依赖手工加入 `--allow-scripts`。npm 的该选项是 lifecycle script（安装期脚本）白名单，授权对象应是实际拥有脚本、且部署确实需要执行脚本的依赖。

源码构建使用仓库自己的 pnpm 策略。固定 tag 中的 `pnpm-workspace.yaml` 记录已经审核的 `allowBuilds` 条目，也显式拒绝随依赖带入但不需要执行的脚本；部署直接沿用该文件，避免把 npm warning 翻译成另一套全量授权。

> 来源：[官方源码的 `allowBuilds`](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/pnpm-workspace.yaml#L35-L55)。

### <a id="npm-first-install-diagnostics"></a>npm 首次安装异常

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

## <a id="service-management"></a>服务托管

先以前台方式用正式运行用户、明确入口、目标 Profile、DSH home 和 workspace 验收，再配置常驻托管。Web／headless／SDK 的行为见[运行模式](dsh.md#install-and-run)；常驻 Web 由 supervisor 保持，headless 一次性任务由调度者收集退出结果，SDK subprocess 由应用管理其创建、关闭与重启。

安装身份取决于安装目录所有权，运行身份取决于实例的数据和工作区归属。root 安装的共享 DSH 可以由多个普通用户分别运行。每个实例记录 executable／Node、用户与 Home、DSH home、Profile、workspace、监听地址和端口，并把这些值固定在启动器里。安装和依赖解析在部署阶段完成，服务启动直接使用已验收入口。

`Type=exec` 让 systemd 在入口程序成功执行后才认为启动命令成功，随后仍要检查 DSH 初始化与 Web 响应；较旧 systemd 不支持时用 `Type=simple` 并保留独立健康验收。`Restart=always` 用于常驻 Web，显式 stop 会停止它；一次性任务按自己的完成与重试策略管理。

> 来源：[systemd Type 与启动状态](https://github.com/systemd/systemd/blob/v255/man/systemd.service.xml#L147-L172)、[Restart 策略](https://github.com/systemd/systemd/blob/v255/man/systemd.service.xml#L689-L751)。

### <a id="systemd-user-service"></a>systemd 用户服务

dsh 的配置、凭据和 Session 都归启动它的普通用户。systemd user service（用户级服务）以同一身份托管 Web 进程；linger 让该用户的 manager 在无人登录时继续运行并参与开机启动。

服务入口可以指向 npm 全局安装的 `dsh`，也可以指向固定源码 checkout 构建出的 `apps/cli/lib/bin.js`。两条路径都在部署阶段完成依赖解析，并把 `WorkingDirectory` 留给 Agent 的项目 workspace。

#### 运行入口与工作目录

NVM 可以同时保存多个 Node 版本。部署时先解析实际使用的 Node 与 dsh 路径，再把绝对路径写入 unit：

```sh
nvm version default
command -v node
command -v dsh
node -p 'require("node:fs").realpathSync(process.argv[1])' "$(command -v dsh)"
```

systemd user manager 直接执行 `ExecStart`，不会加载交互 shell 的 NVM 初始化。npm 全局安装的 `dsh` 使用 `#!/usr/bin/env node`，所以 unit 的入口有两种写法：写死部署时解析出的绝对路径（升级 Node 需要改 unit），或让入口在每次启动时解析 NVM default（写法见[服务配置](#service-config)）。

两种写法都只在进程启动时解析一次 Node。systemd 不监听 `~/.nvm/alias/default` 的变化：切换 default 或安装新版本后，仍需 `systemctl --user restart dsh` 才会用新版本启动。

> 🔬 2026-10-28 实测：Linux 生产机上三个用户级 unit 由写死绝对路径改为 `bash -c '. %h/.nvm/nvm.sh && nvm use --silent default && exec dsh …'`，各重启后均按 default 别名解析到对应 Node 下的 `dsh`。`nvm alias default <未安装版本>` 会被 nvm 拒绝设置、原别名保持不变；删除 default 正指向的已安装版本会让下一次重启失败，是该写法的边界。

源码入口由绝对 Node 路径执行 `<source-checkout>/apps/cli/lib/bin.js`。源码 checkout 按其 `packageManager` 字段选择 pnpm，并在每次切换 tag 后重新安装与构建。Agent 的默认 workspace 来自启动 cwd，因此 `WorkingDirectory` 应指向实际项目目录，与 dsh 的安装或源码目录分开。

> 来源：[Node 与 pnpm 版本约束](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/package.json#L1-L10)；[CLI 的 `bin` 入口](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/package.json#L11-L18)；[所有运行模式的默认 workspace](https://github.com/deepseek-ai/deepseek-harness/blob/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e/apps/cli/reference/README.zh.md#L81-L85)。

#### 用户管理器与 linger

```sh
loginctl show-user "$USER" -p Linger
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" -p Linger    # 应为 Linger=yes
```

开启 linger 需要管理员权限。`Linger=yes` 时，user manager 可以在没有登录会话时运行；`Linger=no` 时，其生命周期跟随用户登录。systemd 用户服务的一般生命周期、网络顺序和凭据边界归 `software` skill 维护。

#### <a id="service-config"></a>服务配置

先创建 Agent workspace，再把 `<node-bin-dir>` 和 `<dsh-executable>` 换成前面解析出的绝对路径：

```sh
install -d -m 0755 "$HOME/dsh-workspace"
install -d -m 0755 "$HOME/.config/systemd/user"
```

```ini
[Unit]
Description=DeepSeek Harness Web

[Service]
Type=exec
WorkingDirectory=%h/dsh-workspace
Environment=DSH_HOME=%h/.dsh
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

跟随 NVM default 的入口把 Node 版本解析留给每次启动，unit 只写命令本身：

```ini
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/bin/bash -c '. %h/.nvm/nvm.sh && nvm use --silent default && exec dsh web --no-open --host 127.0.0.1 --port 3080'
```

`nvm use default` 先把对应版本的 `bin` 目录前置到本次进程的 `PATH`，`exec dsh` 随之解析到该版本的全局安装，因此 `Environment=PATH` 里无需再写版本化路径。换版本流程：`nvm install <新版本>`、`nvm alias default <新版本>`、`systemctl --user restart dsh`。

> 来源：[`nvm use` 在当前 shell 中切换版本并修改 `PATH`](https://github.com/nvm-sh/nvm/blob/v0.40.6/README.md#usage)。

`pnpm dlx` 在 service 启动时仍可能下载和解析 package；固定入口把这些工作留在部署阶段。遥测模式及 `DSH_TELEMETRY_DISABLED` 的作用见[遥测数据](dsh.md#telemetry-data)。

#### 启用与验收

先停止占用同一地址和端口的手工 dsh 进程，再加载并启动 unit：

```sh
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

预期是 `enabled`、`active/running`、HTTP 响应符合部署的认证策略，且 `NRestarts` 不再持续增长；首次正常启动通常为 0。未启用认证的入口可返回 200，启用认证时匿名 401 只证明受保护入口可达，还需另验登录后的交互。失败时用 `systemctl --user status dsh.service` 与 `journalctl --user -u dsh.service` 查看 `EADDRINUSE`、入口路径或依赖加载错误。新部署验收可重启一次，确认服务独立于当前交互 shell；已有实例先协调任务并取得停启授权。

#### 运行数据

升级、pi-ai 覆盖与回滚统一见[升级与回滚](#sequence)。备份对象是 unit 实际使用的 DSH home（默认 `~/.dsh`），包括 Session、配置、凭据和 Profile；多个实例分别核对 `DSH_HOME`。

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

下面是 `/etc/systemd/system/dsh.service` 的模板。把所有尖括号占位符换成实际值，路径使用绝对路径；`<workspace>` 与 `<dsh-home>` 必须归 `<user>` 可读写。模板沿用前文解析出的 npm 全局入口；使用源码 checkout 时，把 `ExecStart` 换成绝对 Node 路径加 `<source-checkout>/apps/cli/lib/bin.js`。

```ini
[Unit]
Description=DeepSeek Harness Web
Wants=network-online.target
After=network-online.target
RequiresMountsFor=<workspace> <dsh-home>

[Service]
Type=exec
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

> 来源：[systemd 系统与用户 unit 的加载路径](https://github.com/systemd/systemd/blob/v255/man/systemd.unit.xml#L306-L460)、[`User=`、`Group=` 与执行环境](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml#L521-L552)、[`WantedBy=` 的 enable 语义](https://github.com/systemd/systemd/blob/v255/man/systemd.unit.xml#L1964-L1990)、[linger 的生命周期语义](https://github.com/systemd/systemd/blob/v255/man/loginctl.xml#L166-L178)。

加载系统 unit 前，确认账户存在、数据与 workspace 可写、入口及 Node 可执行；按实例实际路径创建所需目录。需要依赖的挂载由 `RequiresMountsFor=` 声明，网络就绪由系统配置的 wait-online 服务定义。新 unit 使用以下顺序：

```sh
sudo systemd-analyze verify /etc/systemd/system/dsh.service
sudo systemctl daemon-reload
sudo systemctl enable --now dsh.service
sudo systemctl show dsh.service \
  -p LoadState -p UnitFileState -p ActiveState -p SubState \
  -p MainPID -p ExecMainStatus -p NRestarts -p FragmentPath
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3080/
```

需要排查时读取 `sudo journalctl -u dsh.service`，按[依赖与服务验收](#verification)检查加载、模型和实际功能。`enable --now` 用于首次部署；更新已有 unit 时执行对应 manager 的 `daemon-reload` 和已授权的停启。外部用户访问 Web 的认证、反代和客户端兼容见 [dsh-public-web README](https://github.com/TMYTiMidlY/dsh-public-web)。

### <a id="multiple-instances"></a>多用户与多实例

共享安装树的维护范围按实际 executable 和依赖路径确定。用 `systemctl cat`、`systemctl show -p ExecStart -p MainPID` 与进程路径核对所有实例；unit 的名称相似不代表共享二进制，当前 shell 的 `dsh` 也可能是另一份。升级共享树时一起停止所有使用者，完成依赖验收后全部启动。

系统模板 `dsh@.service` 可复用公共配置，通过实例 drop-in 固定各自身份、Home、DSH home、workspace、端口和启动参数。只有实例名本身就是有效登录用户时，才可用 `User=%i`；任意 Profile／实例名使用明确的 `User=` 与 `Group=`。例如两个同用户实例分别使用 `dsh@web.service`、`dsh@lean.service`，而运行身份仍是同一个普通用户。

独立实例使用不同 DSH home、端口及需要独立的 workspace。多个 Profile 共享同一 DSH home 时，凭据、Session 和 home patch 也共享；按实例是否需要共享数据作出明确选择。独立实例的数据隔离还要逐项检查 Plugin 自己的状态文件配置，确认实际使用各实例声明的目录。

覆盖公共 `ExecStart` 时，drop-in 先清空原值，再写完整新命令；其余环境按实际实例设置：

```ini
[Service]
User=<user>
Group=<group>
WorkingDirectory=<workspace>
Environment=HOME=<home>
Environment=DSH_HOME=<instance-dsh-home>
ExecStart=
ExecStart=<dsh-executable> web --no-open --host 127.0.0.1 --port <instance-port>
```

系统实例 drop-in 位于 `/etc/systemd/system/dsh@<instance>.service.d/`；用户实例对应 `~/.config/systemd/user/`，其身份已由 user manager 决定。实例参数和配置只变更目标 unit，依赖更新则覆盖共享安装树的全部实例。

> 来源：[systemd service template](https://github.com/systemd/systemd/blob/v255/man/systemd.service.xml#L58-L68)、[drop-in 的 ExecStart 清空与覆盖](https://github.com/systemd/systemd/blob/v255/man/systemd.service.xml#L333-L354)。

### <a id="startup-environment"></a>启动环境与凭据

DSH `0.2.1-rc.2` 的原生环境入口按同名变量依次取：进程继承的环境 → 启动工作目录的 `.env` → `$DSH_HOME/.env`（默认 `~/.dsh/.env`）。启动器先确定 DSH home，再读取文件并将接受的值补入运行时 `process.env`；`.env` 不能设置 `DSH_HOME`。代理变量允许放在 DSH home 的文件中，配置方法见[出站 HTTP 代理](#outbound-proxy)。

> 来源：[环境文件的校验、加载顺序与运行时赋值](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/boot/app-boot/src/index.ts#L162-L258)。

自定义文件（例如 `$DSH_HOME/profiles/<profile>/<env-file>`）由 shell 或 service manager 显式加载；仅把它放在 patch 旁不会自动生效。文件权限设为运行身份可读的 `0600`。MCP 的 `config.env`／`config.headers` 表达式与子进程转发规则见[持久 MCP 配置](dsh.md#mcp-persistent-configuration)及[子进程环境](dsh.md#child-process-environment)。

需要显式 HTTP 代理时，把所需变量放进真正创建 Host 的启动链，而不是只在后来打开的终端里设置。systemd 直接启动 DSH、由脚本先加载环境再 `exec dsh`，是两种有效入口；仅看到 unit 的 `Environment` 没有代理键，不能排除脚本加载了环境。clashctl 的 shell 集成、代理变量与服务就绪检查由 `network` skill 的 clashctl 与代理启动环境主题维护；通用 service／linger 语义由 `software` skill 维护。

Host 环境会参与本地子进程及 stdio MCP 的环境构造，但 `0.2.1-rc.2` 还会做名称筛选、代理补充和调用方显式覆盖，见[子进程环境](dsh.md#child-process-environment)。因此应分别核 Host 和实际 child，不能把“父进程有变量”写成“所有程序一定采用同样代理”。

直接 shell 启动时，先导入自己信任、且采用 shell 赋值语法的文件；source 会执行文件内容，凭据文件只放受信任的赋值：

```sh
set -a
. "$DSH_HOME/profiles/<profile>/<env-file>"
set +a
/path/to/dsh --profile '<profile>'
```

systemd 通过以下 drop-in 加载；文件使用该 manager 的 `EnvironmentFile` 格式，shell 的变量展开与命令替换不适用于这里：

```ini
[Service]
EnvironmentFile=<absolute-dsh-home>/profiles/<profile>/<env-file>
```

系统 unit 的 drop-in 保存到 `/etc/systemd/system/<unit>.d/20-environment.conf`，user unit 保存到 `~/.config/systemd/user/<unit>.d/20-environment.conf`。修改 unit／drop-in 后 `daemon-reload` 再停启原实例；只修改环境文件值时重启原实例。核对 `systemctl show <unit> -p EnvironmentFiles -p ActiveState -p SubState`，用户服务使用 `systemctl --user`。PATH 同时包含 Plugin 管理需要的 pnpm，以及实际会调用的 MCP／子进程程序；stdio MCP 使用绝对 command 路径。

> 来源：[systemd EnvironmentFile 的格式和读取时机](https://github.com/systemd/systemd/blob/v255/man/systemd.exec.xml#L2704-L2800)。

验收时先确认监听进程属于哪个 unit，再核 `FragmentPath`、drop-in 和实际启动脚本，仅提取代理变量等必要白名单并遮蔽 URI 凭据。Linux 的 `/proc/<pid>/environ` 反映 exec 时的环境区，不能当成 Node 后续修改过的全部 `process.env`；DSH 的 HTTP policy 也可能规范化运行时变量。Host 的启动环境、当前环境文件及实际 child 的启动环境分别记录，避免从一个位置推断另一个位置。

> 🔬 2026-10-28，Linux／WSL、DSH `0.2.1-rc.2`：已运行的用户服务通过启动脚本导入环境文件，Host 与三个 stdio MCP child 均观测到代理。当前 clashctl 导出文件与 Host 的 `ALL_PROXY` 不同，child 的 `NO_PROXY` 还含补入的 loopback 条目。该核查没有重启 Host／代理或系统，没有发送模型请求；服务 `enabled`、`active` 和入口可达不代替冷启动顺序与出站验证。

### <a id="outbound-proxy"></a>出站 HTTP 代理

以下方法已核对 DSH `0.2.1-rc.2`。先确认目标实例实际的 `DSH_HOME` 和代理的 HTTP／mixed 监听入口，再把需要的键合入该 home 下已有的 `.env`，保留其中的 API key 等其他配置；使用 dotenv 赋值语法，无需 `export` 或手动 source：

```dotenv
http_proxy=http://<proxy-host>:<http-port>
https_proxy=http://<proxy-host>:<http-port>
no_proxy=localhost,127.0.0.1,::1,.internal.example
```

同一 DSH home 下的各 Profile 共用这份默认值；实例需要不同出口时使用各自的 DSH home，或由启动器提供覆盖值。同名变量优先采用启动进程继承的值。代理解析另有大小写优先级：非空小写优先、大写兜底，因此同时检查两种拼写，避免文件中的小写值与启动器导出的大写值相互遮蔽。需要兼容只认大写的子工具时，同步配置相同值的 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY`。`all_proxy`／`ALL_PROXY` 可为两种协议兜底；HTTPS 在未指定时还会回退到 HTTP 代理。

> 项目工作目录的 `.env` 设置代理变量会被启动器拒绝；用户自己的 `$DSH_HOME/.env` 才有此权限。代理 URL 使用 `http://` 或 `https://`，SOCKS／PAC 值会被报告并跳过。`no_proxy` 支持主机、域名后缀与可选端口，CIDR 网段不参与匹配；loopback 始终直连。来源：[代理取值与绕过规则](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/util/http-proxy/README.zh.md#L48-L79)。

修改文件后，在已授权的窗口重启**原 DSH 实例**；这是启动时解析的进程级策略，设置页刷新或 Profile 热重载不能替代重启。含凭据的代理 URL 同样会进入部分工具子进程的环境，文件设为 `0600`，诊断只展示必要变量并遮蔽 URI 凭据。

`dsh` 在加载第一个插件前，由内置库 `@deepseek-ai/dsh-http-proxy` 解析策略、构造 Undici `ProxyAgent` 并调用 `setGlobalDispatcher()`。使用全局 `fetch` 的 LLM／Web／HTTP MCP 请求由此路由；这层位于 Cordis 插件配置树之外，`dump-config` 和模型凭据设置都不是它的完整观察入口。主进程的这条路径也不依赖 Node 26 自动读取代理变量；子进程的筛选与 `NODE_USE_ENV_PROXY` 补充另见[子进程环境](dsh.md#child-process-environment)。

> 来源：[启动期安装与 fetch 调用范围](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/util/http-proxy/README.zh.md#L25-L44)、[ProxyAgent 工厂与全局 dispatcher 安装](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/util/http-proxy/src/install.ts#L131-L223)。OTLP 遥测、workflow／Node PTC 等独立执行环境有不同边界，见[传输限制](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.2/packages/util/http-proxy/README.zh.md#L105-L112)。WebUI 内 iframe 的请求由用户浏览器发出，浏览器代理单独核对。

验收按[启动环境核查](#startup-environment)确认实例、文件与变量来源，再结合一次获准的真实请求、代理日志和对应 PID 的连接归属核实出口。Linux 的 `/proc/<pid>/environ` 只反映 exec 时的环境区；即使其中没有 proxy，也应继续检查 DSH home 的 `.env` 与运行时代理初始化。另起 shell 的 `env`、单独执行一次 curl，分别只能说明那份子进程环境和 curl 的行为。

> 🔬 2026-10-31，Linux、DSH `0.2.1-rc.2`／Node `26.5.0`：隔离探针清除继承的代理变量后，调用原启动库与代理库，变量来源仍解析为 home `.env` 的 `user-env`，外部 HTTPS URL 判定走所配 HTTP 代理，本机 Web URL 判定直连；探针未发送网络请求。同一 Node 进程中新增变量后，`process.env` 与新子进程可读到，而 proc 环境区仍无该变量。这验证了配置解析及 proc 观察盲区，真实流量仍按上一段验收。

### <a id="other-supervisors"></a>macOS、Windows、容器与应用启动器

其他平台沿用同一份实例参数与验收标准，由实际 supervisor 管理生命周期。macOS 使用已有 launchd job，明确 `ProgramArguments`、工作目录和环境；选择登录用户 agent 或系统 daemon 时同时明确运行身份与无人登录时的生命周期。Windows 使用应用支持的 service wrapper 或计划任务，明确账户、可执行路径、工作目录、环境和开机／登录触发器；确认启动器能监督前台进程、停止整棵子进程树并收集日志。

> 来源：[Apple launchd agent／daemon 的启动生命周期](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)；[Windows Service Programs](https://learn.microsoft.com/en-us/windows/win32/services/service-programs) 为原生服务接口的阅读入口，普通 CLI 由实现这些接口的 wrapper 托管。

容器使用镜像中已安装的固定入口、明确运行 UID/GID、持久 DSH home 与 workspace、端口映射和原编排器的重启策略。Python／TypeScript SDK 的父应用负责 child 生命周期，升级同时处理会重建 child 的 worker、任务队列或进程管理器。WSL 先判断实例由发行版 systemd 还是 Windows 启动器托管，按实际边界停启；通用平台服务配置使用 `software` skill，不在此复制各平台的完整运维手册。

## <a id="sequence"></a>升级顺序

1. 记录实际入口、DSH／pi-ai／Node／包管理器版本、旧 override 和目标模型。DSH 沿既有发布频道查询 dist-tag 或源码 tag，解析成明确版本；pi-ai 固定查询当次 `latest`，保存具体版本为 `PI_AI_VERSION`。查询与安装使用一致的 registry 和 scope 配置，镜像目录滞后时先核对上游发布。停机前确认 Node 满足两者 `engines`，需要更新 Node 时一并安排服务入口与 PATH。
2. 停止共享该安装树的全部实例及会重新拉起它们的启动者。系统 unit 用 `sudo systemctl stop …`，用户 unit 用对应用户的 `systemctl --user stop …`；launchd、Windows 服务／计划任务、容器编排器和 SDK 父进程按原托管方式停启。停完后备份各实例实际的 DSH home，以及安装 manifest、覆盖配置、锁文件、服务入口和可直接恢复的旧安装产物。
3. 按原安装方式升级 DSH 本体；只更新 pi-ai 时跳过。升级后重新解析服务入口，确认新安装树的包名、版本和所有者。
4. 在所属项目根重新写入 `PI_AI_VERSION` 的覆盖，重新安装依赖；源码部署还要构建。这一步是每次升级的必做项，即使之前设置过覆盖也重新应用。
5. 核对依赖树与适配器实际解析到的 pi-ai 版本、路径和模型目录。通过后启动先前停止的全部实例，核对服务状态、Web 响应、模型选择器及新 Session 的文本、工具调用和 reasoning replay。

任一步失败就停止后续步骤；候选未通过时继续使用旧安装，原地更新失败时恢复已备份的旧组合并验收后启动，避免服务长期停在半安装状态。依赖更新影响共享安装树中的所有实例，settings / Profile 热重载无法替代进程停启。多个实例分别核对 `DSH_HOME`。候选运行使用独立 DSH home、端口与 workspace，正式数据在停机时备份。

## <a id="system-npm"></a>系统 npm 全局安装

以下 Bash 示例对应 Linux 上 `/usr/local/bin/dsh` → `/usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js`、root 所有安装树、`/usr/bin/npm` 和系统 Node。把版本和服务名替换为实际值；服务列表包含共享这一份二进制的全部实例。已处于 root 身份的执行环境去掉 `sudo`，其他布局按[安装位置](#installation-scope)选择路径和权限。

准备版本与安装位置，确认查询结果非空、Node 满足 DSH 与 pi-ai 的 `engines`，并记录旧版本组合。下列 `/usr/local`、`/usr/bin/npm` 和 PATH 来自这种部署布局；执行前核对实际环境：

```bash
DSH_VERSION='<本次 DSH 目标版本>'
DSH_UNITS=('dsh@<user-a>.service' 'dsh@<user-b>.service' 'dsh@<profile-user>.service')
DSH_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
DSH_PREFIX=/usr/local
DSH_BIN=/usr/local/bin/dsh
DSH_ROOT="$(dirname "$(dirname "$(readlink -f "$DSH_BIN")")")"
PI_AI_VERSION="$(env PATH="$DSH_PATH" /usr/bin/npm view @earendil-works/pi-ai@latest version)"
test -n "$PI_AI_VERSION"
env PATH="$DSH_PATH" /usr/bin/npm view "@deepseek-ai/dsh@$DSH_VERSION" engines --json
env PATH="$DSH_PATH" /usr/bin/npm view "@earendil-works/pi-ai@$PI_AI_VERSION" engines --json
env PATH="$DSH_PATH" node --version
env PATH="$DSH_PATH" "$DSH_BIN" --version
env PATH="$DSH_PATH" /usr/bin/npm ls --prefix "$DSH_ROOT" @earendil-works/pi-ai --all
```

停止全部实例，然后备份各实例实际的 DSH home 及旧 manifest / override：

```bash
sudo systemctl stop "${DSH_UNITS[@]}"
```

升级本体使用**原全局 prefix**。只修复 pi-ai 时跳过下面这条，保留当前 DSH 版本；修复到明确版本时将 `PI_AI_VERSION` 设为该版本，例如 `0.99.1`：

```bash
sudo env PATH="$DSH_PATH" npm_config_cache=/var/tmp/npm-cache-dsh \
  /usr/bin/npm install --global --prefix "$DSH_PREFIX" \
  "@deepseek-ai/dsh@$DSH_VERSION" --no-audit --no-fund
```

本体升级成功后，重新解析安装根、校验包名、覆盖 pi-ai 并重装**包内依赖**。此块在错误时退出；失败后保持服务停止并处理错误：

```bash
(
  set -eu
  test -n "$PI_AI_VERSION"
  DSH_ROOT="$(dirname "$(dirname "$(readlink -f "$DSH_BIN")")")"
  env PATH="$DSH_PATH" node -e \
    'if (require(process.argv[1]).name !== "@deepseek-ai/dsh") process.exit(1)' "$DSH_ROOT/package.json"
  sudo env PATH="$DSH_PATH" /usr/bin/npm pkg set \
    "overrides.@earendil-works/pi-ai=$PI_AI_VERSION" --prefix "$DSH_ROOT"
  sudo env PATH="$DSH_PATH" npm_config_cache=/var/tmp/npm-cache-dsh \
    /usr/bin/npm install --prefix "$DSH_ROOT" \
    --package-lock=false --ignore-scripts --omit=dev --no-audit --no-fund
  env PATH="$DSH_PATH" /usr/bin/npm ls --prefix "$DSH_ROOT" @earendil-works/pi-ai --all
)
```

`DSH_PREFIX=/usr/local` 是全局升级 prefix；`DSH_ROOT=/usr/local/lib/node_modules/@deepseek-ai/dsh` 是包内依赖安装 prefix。裸 `sudo npm` 受当前 PATH 影响，`sudo /usr/bin/npm install --global` 又可能使用不同的默认 prefix，两者都通过显式路径和 prefix 消除歧义。`npm_config_cache` 仅指定 root 安装操作的 cache，可替换为管理员维护的其他绝对路径。

`--package-lock=false` 使包内重装忽略且不生成 `package-lock.json`，适用于这种全局发布包修补；项目安装保留项目锁文件。`--ignore-scripts --omit=dev` 用于已有构建产物的依赖重装：若本次新增依赖确实需要原生构建或安装脚本，则按该依赖的实际要求执行并验收。DSH 本体首次安装与源码构建沿用[安装脚本策略](#install-script-authorization)，源码保留开发依赖。依赖树的检查也核对 pi-ai 之外的变化，保留实际版本记录或整份安装备份。

> 来源：[npm install 的全局安装与 package-lock、omit、ignore-scripts 选项](https://docs.npmjs.com/cli/v11/commands/npm-install/)。

## <a id="user-and-project"></a>用户 npm 与项目安装

用户 npm 全局安装沿用同一执行顺序，安装命令去掉 `sudo`，改用原 Node 环境的 npm 绝对路径和全局 prefix；PATH 首项是该 Node 的 `bin`。对系统 unit 的停启仍可能需要 `sudo`，安装权限和服务托管层级分别判断。原 prefix 为 `/usr` 时，继续显式用 `/usr`；NVM 等用户安装沿用其原版本目录。

Linux／macOS 同时固定安装命令与服务使用的 Node。npm 的 shebang 和安装脚本都会使用 PATH，因此只固定 npm 文件路径还不够；Node 版本管理器、Homebrew、系统包及编辑器附带工具分别识别。root 所有目录使用所需提权；用户目录由其所有者安装。权限不足时处理目标目录的授权，保留既有所有权与运行身份。

npm 本地项目在管理 DSH 的项目根设置覆盖，再更新本体；`DSH_NPM` 是确认过的 npm 绝对路径，`DSH_PROJECT` 是外层项目根，版本和停启按[执行顺序](#sequence)准备：

```sh
env PATH="$DSH_PATH" "$DSH_NPM" pkg set "overrides.@earendil-works/pi-ai=$PI_AI_VERSION" --prefix "$DSH_PROJECT"
env PATH="$DSH_PATH" "$DSH_NPM" install --prefix "$DSH_PROJECT" --save-exact "@deepseek-ai/dsh@$DSH_VERSION" --no-audit --no-fund
env PATH="$DSH_PATH" "$DSH_NPM" ls --prefix "$DSH_PROJECT" @earendil-works/pi-ai --all
```

只更新项目的 pi-ai 时，第二条改为无 package spec 的 `env PATH="$DSH_PATH" "$DSH_NPM" install --prefix "$DSH_PROJECT"`，保留 DSH 依赖规格并更新项目锁文件，验收本体实际版本未变。固定项目入口为 `<project>/node_modules/.bin/dsh`；服务继续固定此入口和相应 Node PATH。项目若直接依赖 pi-ai，该直接依赖与 override 的规格保持一致，避免 npm `EOVERRIDE`。

### <a id="windows-npm"></a>Windows npm 安装

从实际服务／启动器确认 Node、npm 和全局 prefix；`.cmd`／`.ps1` 只是入口 shim。下面 PowerShell 示例通过明确的 Node 与 `npm-cli.js` 执行同一套 npm 操作，每条原生命令检查退出码。系统位置需要管理员权限，用户安装沿用原账号；先按[执行顺序](#sequence)停实例并备份：

```powershell
$DshNode = '<实际 node.exe 的绝对路径>'
$DshNpmCli = '<对应 npm/bin/npm-cli.js 的绝对路径>'
$env:PATH = "$(Split-Path $DshNode);$env:PATH"
$DshPrefix = '<原全局 prefix>'
$DshVersion = '<本次 DSH 目标版本>'
$PiAiVersion = (& $DshNode $DshNpmCli view '@earendil-works/pi-ai@latest' version).Trim()
if ($LASTEXITCODE -ne 0 -or !$PiAiVersion) { throw 'pi-ai 版本查询失败' }
& $DshNode $DshNpmCli install --global --prefix $DshPrefix "@deepseek-ai/dsh@$DshVersion"
if ($LASTEXITCODE -ne 0) { throw 'DSH 安装失败' }
$ModulesRoot = & $DshNode $DshNpmCli root --global --prefix $DshPrefix
if ($LASTEXITCODE -ne 0) { throw '全局目录查询失败' }
$DshRoot = Join-Path ($ModulesRoot.Trim()) '@deepseek-ai/dsh'
if ((Get-Content (Join-Path $DshRoot 'package.json') -Raw | ConvertFrom-Json).name -ne '@deepseek-ai/dsh') { throw 'DSH 包名不符' }
& $DshNode $DshNpmCli pkg set "overrides.@earendil-works/pi-ai=$PiAiVersion" --prefix $DshRoot
if ($LASTEXITCODE -ne 0) { throw 'override 写入失败' }
& $DshNode $DshNpmCli install --prefix $DshRoot --package-lock=false --ignore-scripts --omit=dev --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
& $DshNode $DshNpmCli ls --prefix $DshRoot '@earendil-works/pi-ai' --all
if ($LASTEXITCODE -ne 0) { throw '依赖树检查失败' }
```

安装脚本需要的 Node `bin` 也加入这次进程的 PATH。只更新 pi-ai 时跳过本体安装；本地项目则把覆盖写在外层项目根并保留锁文件。验收后按原 Windows 托管方式启动，PowerShell 中的服务操作和 Bash 示例分别执行。

## <a id="pnpm-and-source"></a>pnpm 与源码安装

在管理 DSH 的 pnpm 项目根，将下面条目合并到既有 `pnpm-workspace.yaml` 的 `overrides`；将占位符换成当次查询所得的明确版本，保留其他覆盖与 workspace 配置：

```yaml
overrides:
  '@earendil-works/pi-ai': '<pi-ai-version>'
```

项目安装在所属项目执行 `pnpm add --save-exact @deepseek-ai/dsh@<dsh-version>`；workspace 根作为依赖持有者时加 `--workspace-root`，依赖在子项目时选择该子项目。只更新 pi-ai 时执行 `pnpm install --no-frozen-lockfile`，检查 DSH 版本未变及锁文件更新。用 `pnpm why @earendil-works/pi-ai` 查看依赖；registry 与版本查询沿用该项目对应的 pnpm 配置。

pnpm 全局安装先读 `pnpm --version`、`pnpm list --global --json`、bin shim 和所属 manifest。pnpm 10 沿用原共享全局项目；pnpm 11 的每个安装组拥有自己的 manifest／锁文件，升级会重建安装组，不能把旧组的覆盖视为已保留。统一采用“全局升级目标 DSH → 重新定位实际安装组根 → 写该根的 override → 从该根重新安装 → 检查 bin shim 和依赖”的顺序。只更新 pi-ai 时直接从现有根重装，保留 DSH 的精确版本：

```sh
env PATH="$DSH_PATH" "$DSH_PNPM" add --global "@deepseek-ai/dsh@$DSH_VERSION"
# 根据升级后的 bin shim／manifest 重新设置 DSH_PROJECT，并合并 override。
env PATH="$DSH_PATH" "$DSH_PNPM" --dir "$DSH_PROJECT" install --no-frozen-lockfile
env PATH="$DSH_PATH" "$DSH_PNPM" --dir "$DSH_PROJECT" why @earendil-works/pi-ai
```

这三个阶段分别核验后执行，安装根是 owning project，不是 store 中的包目录。pnpm 11 的全局写入按安装用户执行，官方当前全局管理入口拒绝 `sudo`；系统 unit 的停启权限仍独立判断。多个全局安装组的依赖检查从 DSH 所属组执行，避免跨组深层查询的限制。旧 pnpm 的配置字段按其版本核对，保留已有覆盖和脚本构建策略。

> 来源：[pnpm 11.7.0 changelog 中的全局安装组与更新行为](https://github.com/pnpm/pnpm/blob/v11.7.0/pnpm/CHANGELOG.md#L504-L514)；[pnpm Global Packages](https://pnpm.io/global-packages) 为后续版本的查阅入口，sudo 与组目录处理按执行时的具体版本核对。

源码安装先切换明确 tag，重新应用根项目覆盖，再执行 `pnpm install --no-frozen-lockfile && pnpm run build`。覆盖改变依赖求解结果，需同步更新锁文件；后续复现相同 manifest 和锁文件时再用 `--frozen-lockfile`。

切 tag 后核对上游针对旧 pi-ai 的 `patchedDependencies`：新版已包含修复时只移除对应映射，仍需补丁则按新版重新生成，保留其他补丁。DSH `0.2.1-alpha.1` 的源码 workspace 含针对 pi-ai `0.87.1` 的补丁，改变覆盖版本可能触发未使用补丁检查。源码与 pnpm 项目沿用原 `allowBuilds`，而非套用 npm 包内重装的 `--ignore-scripts --omit=dev`。

> 来源：[pnpm 根项目 overrides](https://pnpm.io/10.x/settings#overrides)；[DSH 源码覆盖配置](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/pnpm-workspace.yaml#L17-L20)与[pi-ai 补丁映射](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/pnpm-workspace.yaml#L100-L101)。

## <a id="other-managers"></a>Yarn 与 Bun 项目

已有项目沿用自己的管理器和锁文件。Yarn 在项目根 `package.json` 的 `resolutions` 中设置 `'@earendil-works/pi-ai': '<明确版本>'`，更新精确 DSH 依赖后运行该版本的 `yarn install`，用 `yarn why @earendil-works/pi-ai` 验收。Yarn PnP 项目的模型检查使用其实际 loader／`yarn node`，保留该项目入口的解析环境；无法通过真实 DSH 启动验收时，按该项目兼容方式使用 `node_modules` 布局。

Bun 项目在根 `package.json` 的 `overrides` 中设置同一条精确覆盖，更新 DSH 精确依赖后运行 `bun install`，保留 `bun.lock` 或该版本已有的锁文件；用该项目的依赖检查与实际 DSH 启动验收结果确认生效。包管理器和运行时分开核对：由 Bun 安装依赖不意味着 DSH 的 Node 运行入口也已变更。

Yarn／Bun 的全局安装先定位其真实全局 manifest，再按该版本的全局升级方式处理；确认升级后的覆盖与入口仍有效。共享全局项目若还有其他 CLI，覆盖可能影响这些 CLI 的 pi-ai；需要独立维护时采用固定 DSH 项目，使升级范围和锁文件归属明确。

> 来源：2026-10-04 核对的 [Yarn manifest resolutions](https://yarnpkg.com/configuration/manifest#resolutions)、[Bun overrides 的根项目规则](https://bun.com/docs/pm/overrides)；这些在线页面为当前语法入口，实际执行按项目安装的管理器版本核对。

## <a id="bundled-and-container"></a>打包运行时与容器

Python 的 `deepseek-harness-runtime-bin` 将内置 Node 依赖打进原生可执行程序，旁边放一份 npm override 不会改写其虚拟文件系统。需要最新 pi-ai 时，选择已按上述流程覆盖的外部 DSH 并让 SDK 的 `dsh_bin` 指向它，或在明确源码 tag 上覆盖 pi-ai 后重新执行该版本的运行时／wheel 构建流程。单纯升级官方 runtime wheel 是否达成目标，以新产物实际目录验收为准。

使用 wheel 时保持 `deepseek-harness-sdk` 与 runtime 的精确版本配对；在原隔离 Python 环境通过 Pixi 或 uv 更新，保留可执行程序、平台 helper、Office 和 primary-runtime 等该版本要求的完整伴随资源。重打包是本地构建，不包含向包仓库发布；其他单文件或桌面封装也在其构建源覆盖依赖，再整体替换产物。

Python SDK 首次安装在应用的 Pixi／uv 隔离环境中添加明确版本的 `deepseek-harness-sdk`，它会带入同版本的平台 runtime wheel。核对该产物支持的 OS／架构并显式提供 `dsh_home`；本仓最新 pi-ai 的部署策略仍通过已覆盖的外部 DSH 或重新构建的 runtime 达成。SDK 调用、Profile 与协议行为归运行时篇的[程序化接入](dsh.md#programmatic-access)。

> 来源：[runtime 的打包布局与虚拟文件系统](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/python/sdk-runtime/README.zh.md#L5-L15)、[runtime 构建入口](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/python/sdk-runtime/README.zh.md#L49-L55)、[SDK／runtime 版本配对](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/python/sdk/README.zh.md#L5-L8)与[外部 dsh_bin](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-alpha.1/python/sdk/README.zh.md#L58)。

容器或只读镜像把 DSH 版本与 pi-ai 覆盖写进构建项目／镜像配方，并在构建阶段安装依赖。先用隔离数据和端口验收候选镜像，停共享实例并备份正式数据卷后切换镜像；保存旧镜像及原配置供回滚。镜像若直接装单文件 runtime，按上一段从构建源处理其依赖。已有可写容器也应同步维护构建配方，使容器重建后保留相同覆盖。

## <a id="verification"></a>依赖与服务验收

依赖树应只包含目标 pi-ai 版本；npm 覆盖应显示 `overridden`。还要从 `@deepseek-ai/dsh-llm-pi-ai` 的实际入口解析 pi-ai，校验版本和模型目录，并导入适配器以发现静态 API 不兼容。下面的只读 Node 检查适用于 pi-ai `0.99.1` 的导出接口；换版本时核对其 API。`PI_AI_VERSION` 是本次已选定的版本，provider 与模型 ID 按部署目标设置：

```bash
DSH_PROVIDER=openai-codex
DSH_MODEL=gpt-6.1-sol
DSH_ADAPTER="$(env PATH="$DSH_PATH" node -e \
  'console.log(require("node:module").createRequire(process.argv[1]).resolve("@deepseek-ai/dsh-llm-pi-ai"))' "$DSH_ROOT/package.json")"
env PATH="$DSH_PATH" node --experimental-import-meta-resolve --input-type=module - \
  "$DSH_ADAPTER" "$PI_AI_VERSION" "$DSH_PROVIDER" "$DSH_MODEL" <<'JS'
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';
const [adapter, expectedVersion, provider, modelId] = process.argv.slice(2);
const pi = import.meta.resolve('@earendil-works/pi-ai', pathToFileURL(adapter).href);
const catalog = await import(import.meta.resolve('@earendil-works/pi-ai/providers/all', pathToFileURL(adapter).href));
const version = JSON.parse(readFileSync(new URL('../package.json', pi))).version;
if (version !== expectedVersion) throw new Error(`pi-ai 实际版本 ${version} 与目标 ${expectedVersion} 不符`);
const model = catalog.getBuiltinModel(provider, modelId);
if (!model) throw new Error('目标模型尚未进入实际加载的 pi-ai 目录');
await import(pathToFileURL(adapter).href);
console.log({ pi, version, id: model.id, name: model.name });
JS
```

上述定位命令适用于 npm 全局发布包。本地项目将查询锚点改为外层项目 manifest，源码直接设置实际 adapter 入口，pnpm 从所属项目解析，Yarn PnP 使用该项目 loader；Windows 通过选定的 Node 执行同样的 JavaScript 检查。打包 runtime 在候选可执行程序中做等效启动与目录验收。

确认 pi-ai 版本是当次覆盖值、目标模型存在、DSH 本体版本是选定值；只更新 pi-ai 时本体版本应与操作前相同。通过后才启动先前停止的全部实例。下面仍是 Linux 系统 unit 的启动例子：

```bash
env PATH="$DSH_PATH" "$DSH_BIN" --version
sudo systemctl start "${DSH_UNITS[@]}"
systemctl is-active "${DSH_UNITS[@]}"
```

其他托管方式按[执行顺序](#sequence)恢复。核对全部实例使用的新入口、进程启动时间、服务状态、Web／SDK 响应和日志；Linux systemd 服务可重复[服务验收](#systemd-user-service)。刷新 Models 页面，核对正式模型名及 reasoning/effort 档位、当前 Profile 的模型白名单和默认模型，再验证新 Session 的文本、工具闭环和多轮 reasoning replay。目录有模型只说明客户端认识该 ID，服务端账号权限以实际请求为准；每次部署分别记录目录、启动和真实调用的验收结果。

> 2026-10-03 本机只读核验：DSH `0.2.1-alpha.1` 的适配器实际解析到 pi-ai `0.99.1`，`openai-codex` 目录有 `gpt-6.1-sol` / `GPT-6.1 Sol`；共享安装树的服务均处于 `active/running`，启动时间晚于依赖文件更新时间。该核验覆盖依赖、目录和服务状态，服务端模型调用需另作验收。

## <a id="rollback"></a>回滚

回滚也先停止共享实例。只回滚 pi-ai 时，把覆盖恢复为之前已验收的明确版本并重装；恢复 DSH 自带范围时删除这一条 override，再重新安装。系统 npm 安装继续使用固定 PATH、`/usr/bin/npm` 和 DSH 包根 prefix，用户安装和 pnpm 项目沿用各自管理器及权限。

回滚 DSH 本体则安装原精确版本或切回原 tag，随后恢复该组合的 pi-ai 覆盖、项目锁文件和构建产物，再验收和启动。Session 跨版本恢复前核对格式兼容性，必要时使用停机时备份的 DSH home。卸载运行时与删除用户数据分别处理。
