# DeepSeek Harness（dsh）升级与回滚

本 skill 的 DSH 升级流程把 **pi-ai 更新到当次 registry 的 `latest`** 作为固定步骤：当次查询版本号，再将明确版本写入依赖覆盖；下一次升级重新查询。DSH 本体使用明确的目标发布版本或源码 tag。这样能持续更新模型目录，并保留每次部署可复现、可回滚的版本组合。

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

## <a id="sequence"></a>执行顺序

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

`--package-lock=false` 使包内重装忽略且不生成 `package-lock.json`，适用于这种全局发布包修补；项目安装保留项目锁文件。`--ignore-scripts --omit=dev` 用于已有构建产物的依赖重装：若本次新增依赖确实需要原生构建或安装脚本，则按该依赖的实际要求执行并验收。DSH 本体首次安装与源码构建沿用[安装脚本策略](dsh.md#install-script-authorization)，源码保留开发依赖。依赖树的检查也核对 pi-ai 之外的变化，保留实际版本记录或整份安装备份。

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

其他托管方式按[执行顺序](#sequence)恢复。核对全部实例使用的新入口、进程启动时间、服务状态、Web／SDK 响应和日志；Linux systemd 服务可重复[服务验收](dsh.md#systemd-user-service)。刷新 Models 页面，核对正式模型名及 reasoning/effort 档位、当前 Profile 的模型白名单和默认模型，再验证新 Session 的文本、工具闭环和多轮 reasoning replay。目录有模型只说明客户端认识该 ID，服务端账号权限以实际请求为准；每次部署分别记录目录、启动和真实调用的验收结果。

> 2026-10-03 本机只读核验：DSH `0.2.1-alpha.1` 的适配器实际解析到 pi-ai `0.99.1`，`openai-codex` 目录有 `gpt-6.1-sol` / `GPT-6.1 Sol`；共享安装树的服务均处于 `active/running`，启动时间晚于依赖文件更新时间。该核验覆盖依赖、目录和服务状态，服务端模型调用需另作验收。

## <a id="rollback"></a>回滚

回滚也先停止共享实例。只回滚 pi-ai 时，把覆盖恢复为之前已验收的明确版本并重装；恢复 DSH 自带范围时删除这一条 override，再重新安装。系统 npm 安装继续使用固定 PATH、`/usr/bin/npm` 和 DSH 包根 prefix，用户安装和 pnpm 项目沿用各自管理器及权限。

回滚 DSH 本体则安装原精确版本或切回原 tag，随后恢复该组合的 pi-ai 覆盖、项目锁文件和构建产物，再验收和启动。Session 跨版本恢复前核对格式兼容性，必要时使用停机时备份的 DSH home。卸载运行时与删除用户数据分别处理。
