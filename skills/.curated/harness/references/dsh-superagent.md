# DeepSeek Harness Superagent

本文集中解答 DeepSeek 开源的 `dsh-superagent-prototype`（`0.1.0`）与 DSH 主程序的关系、进程与数据隔离边界、GitHub／飞书身份配置及最小接入步骤。DSH 本体运行机制见 [DSH 运行时](dsh.md)，服务托管与多实例运维见 [安装、服务部署与维护](dsh-deploy.md)；原型完整设计说明见上游仓库的 [编号文档目录](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/README.md#L19-L31)。

> 来源：[原型定位说明](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/README.md#L3-L7)。上游将其定位为供参考的公开研究原型（非正式 DeepSeek 产品，尚未发布官方 npm 包），升级时需重新核对源码行为。

## <a id="composition"></a>宿主关系与 Web 会话形态

`deepseek-harness` 提供标准宿主运行时，`dsh-superagent-prototype` 作为外装 Cordis bundle 装入目标 Web Profile——两者是“宿主＋插件包”组合，并非从 DSH 主线 fork 出的独立分支。

安装启动后界面仍是标准 DSH Web：用户照常可新建和使用独立的普通聊天会话；侧栏新增 **Superagent** 管理面板（负责配置消息源、准入策略与查看 Ticket），插件同时在后台自动创建并维护受管的 router 与 worker 会话。

> 来源：[bundle 与 Web 客户端声明](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/package.json#L30-L45)、[受管会话创建与识别](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/sessions.ts#L137-L153)、[普通 Agent 会话分支](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/sessions.ts#L228-L237)。

## <a id="isolation"></a>进程环境与多实例隔离

插件启动时执行 `applyEnvironment()`，将 `worker-bin` 插到宿主 Node 进程 `PATH` 的最前端，并把 `GIT_CONFIG_GLOBAL` 指向 `worker-gitconfig`。由于这些环境变量直接改在宿主 `process.env` 上，同一进程内新建的普通会话也会沿默认环境继承这套 CLI 与 Git 凭据，原样部署时应为 Superagent 单独运行一个 DSH 实例，与个人日常工作实例分开。

DSH 宿主（核对至 `0.2.2-rc.4` `3f321d3` 与 `master` `ca33fd6`）已在 `subprocess` 执行接口开放显式子进程 `env` 参数，并在工具层提供按 Agent 过滤的执行钩子（而 `shellEnv` 服务仍仅限注册 `DSH_*` 前缀变量，不能直接注册 `PATH` 或 `GIT_CONFIG_GLOBAL`）。当前 `dsh-superagent-prototype`（`8c32a9d`）尚未接入这组按会话传递环境的宿主接口，仍走启动期全局覆写 `process.env`，因此仅升级 DSH 本体而不改插件代码时仍需独立实例；后续上游迭代时，可据此复核插件是否已改为会话级环境注入。

在同一系统用户下并行运行多个 DSH 实例时，须同时隔离 **`DSH_HOME`**、插件 **`stateDir`** 与**监听端口**（同时保持真实 `HOME` 不变）。仅更换 Profile 名和端口仍会共用默认 `~/.dsh` 目录，导致多个进程共享会话列表并争抢会话锁与 `storages/schedule.json`。通用多实例与 systemd 模板写法见 [多用户与多实例](dsh-deploy.md#multiple-instances)。

> 来源：[启动调用 applyEnvironment](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/app/setup.ts#L91-L96)、[worker Git 与路径构造](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/infra/environment.ts#L45-L59)、[进程级覆写 process.env](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/infra/environment.ts#L118-L124)、[上游隔离说明](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L5-L19)；宿主接口见 [子进程环境参数定义](https://github.com/deepseek-ai/deepseek-harness/blob/3f321d32bfe382212a8ed8785c1d47a5a300aa23/packages/subprocess/subprocess/src/types.ts#L77-L106)、[子进程与终端执行入口](https://github.com/deepseek-ai/deepseek-harness/blob/3f321d32bfe382212a8ed8785c1d47a5a300aa23/packages/subprocess/subprocess/src/index.ts#L129-L169)、[按 Agent 过滤的工具钩子](https://github.com/deepseek-ai/deepseek-harness/blob/ca33fd6843b205e279c7ccb6cb73a472c78f5760/packages/core/tools/src/events.ts#L19-L29)、[shellEnv 键名前缀限制](https://github.com/deepseek-ai/deepseek-harness/blob/ca33fd6843b205e279c7ccb6cb73a472c78f5760/packages/shell/shell-env/src/index.ts#L131-L146)。上游部署示例仅新建 Profile；同用户多实例隔离 `DSH_HOME` 为避免共用 `~/.dsh` 存储锁的运行要求。独立 Profile 或 `DSH_HOME` 均非操作系统级权限边界，需强隔离凭据与文件时应使用专用系统用户。

## <a id="github-identity"></a>GitHub 账号、仓库边界与提交作者

- **专用 GitHub 用户账号**：原型依赖用户账号的 Notifications API 轮询接活，并在读取评论时跳过自身 `login` 的发言以防自激循环；不支持用 GitHub App 代替该用户账号。若与操作者共用个人账号，操作者的评论也会被当作自身输出一并跳过。
- **`gh-agent` 包装器**：`gh-agent` 是官方部署示例给出的可执行包装器名称（名称可自定，面板保存实际脚本绝对路径），通过环境变量 `GH_CONFIG_DIR` 指向独立配置目录保存专用账号登录态，与操作者默认的 `~/.config/gh` 互不干扰：

  ```sh
  #!/bin/sh
  GH_CONFIG_DIR="$HOME/.config/gh-agent" exec gh "$@"
  ```

- **实例单仓边界与包装器权限边界**：单个 Superagent 实例在 `Sources → GitHub` 中仅绑定一个 `owner/repository`，内置 API 封装与 Ticket 交付均围绕该仓库运转（经飞书入口发起的任务同样落向该目标仓）。专用账号与 `gh-agent` 包装器本身不受单仓限制，直接调用时可按账号获授的仓库权限跨仓操作。
- **Git 提交作者与推送凭据解耦**：代码推送与 GitHub API 鉴权走专用账号的 CLI 凭据，而 Git 提交的 `author` 独立配置。可在面板 **Prompts → Delivery requirements** 中指定人类开发者的姓名与邮箱，也可填写专用账号的自定义显示名配 `<id>+<login>@users.noreply.github.com`（未显式指定时默认使用专用账号 `login` 与该 noreply 邮箱），无需修改宿主机的个人全局 Git 配置。

> 来源：[专用账号与 gh-agent 包装器示例](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L31-L47)、[Notifications API 轮询](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/github.ts#L297-L319)、[跳过自身 login 评论](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/github.ts#L390-L400)、[GitHub Source 单仓字段](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/github.ts#L38-L47)、[内置 API 仓库前缀绑定](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/infra/commands.ts#L80-L97)、[提交作者身份可选项](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/SETUP.md#L49-L51)、[默认 noreply 作者拼装](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/github.ts#L92-L102)。

## <a id="feishu-bot"></a>飞书机器人接入

接入飞书（或国际版 Lark）前，先准备启用机器人能力的企业自建应用，开通接收消息事件、读写消息与读取群成员权限，发布应用版本并将机器人拉入目标群。

`lark-bot` 同样是官方示例包装器名称（名称可自定，面板填写实际可执行路径），通过独立的 `LARKSUITE_CLI_CONFIG_DIR` 隔离机器人配置并锁死 `bot` 身份，不影响个人日常使用的 `lark-cli`：

```sh
LARKSUITE_CLI_CONFIG_DIR="$HOME/.lark-cli-dsh-superagent" \
  lark-cli config init --app-id <app-id> --app-secret-stdin
LARKSUITE_CLI_CONFIG_DIR="$HOME/.lark-cli-dsh-superagent" \
  lark-cli config strict-mode bot --global

cat > ~/.local/bin/lark-bot <<'EOF'
#!/bin/sh
export LARKSUITE_CLI_CONFIG_DIR="$HOME/.lark-cli-dsh-superagent"
exec lark-cli "$@"
EOF
chmod +x ~/.local/bin/lark-bot
```

插件 setup 阶段会硬校验机器人就绪状态与 `strict-mode` 精确为 `bot`：仍允许 `user` 身份的 CLI 配置会被直接拒绝，机器人端也无需做个人用户登录。启用后由插件自行拉起事件消费进程监听消息。

> 来源：[飞书配置与包装器示例](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L49-L69)、[bot 身份硬校验](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/deployment.ts#L110-L130)、[事件消费拉起逻辑](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/src/sources/feishu-loops.ts#L70-L84)。同一 App ID 的多套配置目录可能共用系统 keychain 中的 App Secret，停用机器人配置时只移走其独立目录，勿执行 `lark-cli config remove`。

## <a id="setup"></a>源码安装与面板配置速览

先准备满足原型 `engines.dsh` 约束的 DSH 运行时（上游部署文档示例为 `@deepseek-ai/dsh@0.2.1-rc.3`），并为专用实例选定未占用的绝对路径 `DSH_HOME`、`stateDir` 与监听端口（保持真实 `HOME` 不变）。原型通过本地源码构建后以 `link:` 方式装入目标 Web Profile：

```sh
export DSH_HOME="<absolute-instance-home>"
git clone https://github.com/deepseek-ai/dsh-superagent-prototype.git
cd dsh-superagent-prototype
pnpm install && pnpm build
dsh superagent --from-default-profile web --dump-config > /dev/null
dsh plugin --profile superagent add "link:$PWD"
```

> `--from-default-profile` 会重建目标 Profile 并清空原有的 `cordis.patch.yml`，仅用于首次新建 Profile；升级已有实例时跳过该条命令以保留机器配置。

参照上游 [`examples/profile.cordis.patch.yml`](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/examples/profile.cordis.patch.yml#L1-L12) 写入 `$DSH_HOME/profiles/superagent/cordis.patch.yml`，配置 loopback 监听地址与端口、绝对路径 `stateDir`，使用飞书时一并将 `dsh-superagent-feishu` 设为 `disabled: false`（常驻服务托管见 [多用户与多实例](dsh-deploy.md#multiple-instances)）。启动实例后打开侧栏 **Superagent** 面板，依次完成以下 5 个配置块：

| 配置块 | 核心配置项 | 上游文档 |
| --- | --- | --- |
| Sources → GitHub | 单个目标仓库 `owner/repository`、`gh-agent` 绝对路径、通知与仓库事件观察范围 | [Deployment · Settings](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L147) |
| Sources → Feishu | `lark-bot` 绝对路径、目标群聊、各群 `mentions`／`all` 接收模式、私聊开关 | [Deployment · Settings](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L147) |
| Policy | 允许派活的 GitHub `login` 与飞书用户白名单（支持从指定群同步成员）、主动接受规则 | [002 Authorization](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/002-authorization.md#L1-L20) |
| Execution | 工作目录根路径、按 Ticket 创建 worktree 的 `prepare` 命令、禁用个人 CLI 列表、模型与并发 worker 数 | [003 Execution](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/003-execution.md#L49-L81) |
| Prompts | Git 提交作者（`Delivery requirements`）、GitHub 身份披露说明、评审机器人与人工／自动合并条件 | [004 Prompts](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/004-prompts.md#L5-L43) |

保存后可通过本地管理接口（[`GET /orchestrator/api/state`](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L159-L175)，带请求头 `x-orchestrator-request: 1`）核对 `setup.problem`、`setup.feishuProblem` 均为 `null` 且 `health` 各模块进入 `ready`，再由白名单成员从 GitHub 评论或飞书会话触发小任务验收闭环。

> 来源：[安装与机器配置](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L71-L98)、[面板配置顺序与示例](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/006-deployment.md#L143-L157)、[面板视图说明](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/005-panel.md#L34-L43)、[交互式配置向导](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/SETUP.md#L31-L79)。
