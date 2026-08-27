# 受限网络下的 Git clone 与 submodule

失败发生在传输层，不在认证层：地址和权限都没问题，只是原站这台机器够不着——GitHub 要经代理才通、GitLab 另有一套入口，或者目标机器压根没有外网。绕行只应改变本次传输走哪条路；仓库里存下来的 `origin` 和 `.gitmodules` 始终保持官方地址，否则日后每次拉取都被临时方案绑架。

包含 submodule 的上层仓库称为 superproject，这是 Git 术语表里的正式词条：

> A repository that references repositories of other projects in its working tree as submodules. The superproject knows about the names of (but does not hold copies of) commit objects of the contained submodules.
>
> —— [gitglossary 2.43.0](https://git-scm.com/docs/gitglossary/2.43.0#def_superproject)

superproject 只记下每个 submodule 该停在哪个提交，这个被记下的 SHA 称为 gitlink；子仓库的对象一份也不在 superproject 里。下面所有麻烦都由这一条派生：每个 submodule，包括嵌套层级，都得自己把对象弄到手。

| 网络条件 | 获取方式 |
| --- | --- |
| 能访问 ghfast，仓库均在 GitHub | [一次性 URL 改写](#ghfast) |
| GitHub 与 GitLab 混合，两个站点都有可达入口 | [按主机分别配置一次性改写](#mixed) |
| 只有个别 GitLab 仓库有非等价镜像 | [在本地 `.git/config` 覆盖这一个 submodule](#mixed) |
| 完全没有外网 | [从联网机器传 bundle](#bundle)；仓库多时在离线端转成 [bare mirror 树](#mirror) |
| 来源缺少 superproject 锁定的提交 | [向已有 gitdir 补对象](#fill-objects) |
| 私有仓库 | 可信代理、内网镜像或 bundle，不把凭据交给公共第三方代理 |

## <a id="verify-sha"></a>核对目标提交

镜像能连上，不等于它有你要的那个提交。superproject 锁定的是一个具体 SHA，而所谓"镜像"常常只是同步频率不同、甚至 owner 和历史范围都不同的另一个仓库。因此不管走下面哪条路径，对象到手后都用同一组命令确认：

```bash
required_sha=$(git rev-parse HEAD:<submodule-path>)
git -C <submodule-path> cat-file -e "${required_sha}^{commit}"
git -C <submodule-path> checkout --detach "$required_sha"
```

`rev-parse HEAD:<submodule-path>` 读出的就是 superproject 记的 gitlink。`cat-file -e` 失败，或更新时报 `not our ref` / `reference is not a tree`，都说明这个来源没有该对象。此时别改成镜像的最新版本凑合——版本对不上等于换了个项目；要么补入精确提交，要么换一个完整来源。

对象还没落地、想先判断某个 bare mirror 或 bundle 值不值得传过去时，把校验目标换成来源本身：

```bash
required_sha=$(git -C <super-checkout> rev-parse HEAD:<submodule-path>)
git --git-dir=<submodule-mirror>.git cat-file -e "${required_sha}^{commit}"
```

## <a id="ghfast"></a>ghfast 代理 GitHub

[ghfast](https://ghfast.top/) 的做法是在原始地址前面拼一段代理前缀，请求打到 `ghfast.top`，由它回源取内容。首页 meta 描述声明的覆盖面是 GitHub 文件、Releases、archive、gist 和 `raw.githubusercontent.com`（2026-08-01 抓取）；`git clone` 走同一套 HTTPS 前缀拼接，实测可用。

它只能代理 HTTPS。SSH 地址 `git@github.com:<owner>/<repo>.git` 根本不是 URL，没有可供前缀嵌套的 scheme 与 host 结构，拼不出等价形式——所以下面的改写规则都把 SSH 写法一并折向 HTTPS。

ghfast 是第三方在线服务，覆盖范围和可用性随时可能变，上面的抓取结论有时效；用之前先看首页当天的说明。

公共 GitHub 仓库可以直接写代理 URL：

```bash
git clone https://ghfast.top/https://github.com/<owner>/<repo>.git
git -C <repo> remote set-url origin https://github.com/<owner>/<repo>.git
```

要用在自动化和 submodule 上，更合适的做法是只给这一条 Git 命令挂上 [`url.<base>.insteadOf`](https://git-scm.com/docs/git-config/2.43.0#Documentation/git-config.txt-urlbaseinsteadOf)。Git 在发起传输前把匹配的 URL 换成代理形式，而写进配置文件的仍是调用者给出的官方 URL：

```bash
git \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=git@github.com:' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=ssh://git@github.com/' \
  clone --recurse-submodules https://github.com/<owner>/<repo>.git
```

三条规则分别匹配 HTTPS、scp 风格 SSH（`git@github.com:<owner>/<repo>`）和完整 SSH URL（`ssh://git@github.com/<owner>/<repo>`），覆盖 `.gitmodules` 里可能出现的全部写法。`-c` 只在当前命令及其 Git 子进程中生效，不会留下全局代理规则。Git 2.43.0 本地实测：主仓库与递归 submodule 都经改写源完成 clone，最终各自的 `origin` 仍是原始 GitHub URL。

拉私有仓库时，有人会把 token 拼进代理 URL。技术上走得通，但 TLS 连接终止在 `ghfast.top`，凭据是明文交到代理端手里的。除非明确接受这个信任边界并使用短期、最小权限 token，否则私有仓库走可信代理、内网镜像或离线 bundle。

ghfast 没有声明代理 `gitlab.com`，把 GitLab 地址套进同一个前缀不会生效。GitLab 仓库按下一节单独分流。

## <a id="recursive"></a>递归初始化 submodule

已有主仓库时，用同一组一次性改写初始化所有层级：

```bash
git \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=git@github.com:' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=ssh://git@github.com/' \
  submodule update --init --recursive --jobs 4
```

[`git submodule init`](https://git-scm.com/docs/git-submodule/2.43.0) 把 `.gitmodules` 的建议 URL 注册到当前仓库的 `.git/config`；`update` 获取 gitlink 指定的精确提交；`--recursive` 对随后发现的嵌套 submodule 重复这个过程。相对 URL 会先依据 superproject 的默认 remote 解析，再进入正常的 URL 传输逻辑。

先看顶层清单：

```bash
git config -f .gitmodules --get-regexp '^submodule\..*\.url$'
```

父模块的工作区没检出，它带的下一层 `.gitmodules` 就不存在，也就无从列起。因此下面这条只能遍历当前已初始化的层级，每往下初始化一层就得重跑一次：

```bash
git submodule foreach --recursive '
  if test -f .gitmodules; then
    git config -f .gitmodules --get-regexp "^submodule\\..*\\.url$" || :
  fi
'
```

submodule 是独立仓库，既不继承主仓库的 `origin`，也不共用它这次的传输设置。所以"主仓库 clone 成功、submodule 却全军覆没"是常态，多半是 `.gitmodules` 写的 SSH URL、里面混了 GitLab 仓库，或者更深一层压根还没初始化。

## <a id="mixed"></a>GitHub 与 GitLab 混合来源

如果 GitLab 有一个保持 `group/repo.git` 路径结构的可信入口，可以同时改写两个站点。`<reachable-gitlab-prefix>` 必须是该服务文档给出的完整 HTTPS 前缀，并以 `/` 结尾：

```bash
git \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=git@github.com:' \
  -c 'url.<reachable-gitlab-prefix>.insteadOf=https://gitlab.com/' \
  -c 'url.<reachable-gitlab-prefix>.insteadOf=git@gitlab.com:' \
  submodule update --init --recursive
```

但很多所谓"镜像"并不是整站镜像，只是别人另开的一个项目仓库——owner 不同、仓库名不同、同步的历史范围也不同。这种镜像当不了整个 GitLab 前缀的等价替换，只能定点覆盖到真正用得上它的那一个 submodule：

```bash
git config -f .gitmodules --get-regexp '^submodule\..*\.path$'

git submodule init <submodule-path>
git config 'submodule.<name>.url' 'https://<reachable-mirror>/<group>/<repo>.git'
git submodule update <submodule-path>
```

`<name>` 取自上面输出的 `submodule.<name>.path`，不一定等于目录路径。这个设置只写入本仓库的 `.git/config`，不要为临时网络问题修改并提交 `.gitmodules`。

完成后恢复 `.gitmodules` 记录的官方 URL：

```bash
git submodule sync --recursive
git submodule foreach --recursive 'git remote get-url origin'
```

镜像换完之后务必按[核对目标提交](#verify-sha)确认它真的含有 superproject 锁定的 SHA——这一步在混合来源下最容易出问题，因为非等价镜像同步落后是常态。

## <a id="bundle"></a>Git bundle 离线传输

[`git bundle`](https://git-scm.com/docs/git-bundle/2.43.0) 把一批对象和 ref 打成单个文件，`clone`、`fetch`、`verify` 都能直接把它当远端读。它是 Git 官方的离线传输格式，自带 ref 清单和完整性校验，因此仓库不多时优先用它，别手工搬 `.pack`。

下面的 `<transfer-dir>` 用绝对路径。在联网机器上创建并校验：

```bash
git -C <source-repo> \
  bundle create <transfer-dir>/<repo>.bundle --branches --tags
git -C <source-repo> \
  bundle verify <transfer-dir>/<repo>.bundle
```

若 submodule 当前是 detached HEAD（直接停在某提交而不挂分支），而且该提交不再被分支或 tag 引用，先给它一个临时 ref，避免 bundle 漏掉 superproject 需要的提交：

```bash
git -C <source-submodule> \
  update-ref refs/offline-transfer/pinned HEAD
git -C <source-submodule> \
  bundle create <transfer-dir>/<submodule>.bundle \
  refs/offline-transfer/pinned
git -C <source-submodule> \
  bundle verify <transfer-dir>/<submodule>.bundle
git -C <source-submodule> \
  update-ref -d refs/offline-transfer/pinned
```

新建主仓库可以直接从 bundle clone，随后恢复官方 remote：

```bash
git clone <transfer-dir>/<repo>.bundle <repo>
git -C <repo> remote set-url origin <official-url>
```

第二条命令不能省。`.gitmodules` 里的相对 URL 是拿 superproject 的 `origin` 当基准解析的；`origin` 还指着 bundle 文件时，相对 URL 会算到那个文件路径上去，随后的 submodule 初始化必然找错地方。

给现有 superproject 初始化单个离线 submodule：

```bash
git submodule init <submodule-path>
git config 'submodule.<name>.url' \
  '<transfer-dir>/<submodule>.bundle'
git -c protocol.file.allow=always \
  submodule update <submodule-path>

git submodule sync --recursive
```

每个 submodule 都要单独做 bundle：superproject 的 bundle 里只有 gitlink 记下的 SHA，没有子仓库对象。嵌套层要等父模块检出后才露面，仓库少时逐层重复上面的操作就行；层数或数量一多，就在离线端把 bundle 转成 bare mirror 树，省得每层手工配一遍：

```bash
git clone --mirror \
  <transfer-dir>/<submodule>.bundle \
  <mirror-root>/<host>/<group>/<submodule>.git
```

## <a id="mirror"></a>本地 bare mirror 树

bare mirror 是没有工作区、只存对象和全部 refs（分支、标签等引用）的仓库副本。要反复给多台离线机器供货时，与其逐个搬 bundle，不如按原站路径摆一棵镜像树：

```text
<mirror-root>/
├── github.com/<owner>/<repo>.git
├── github.com/<owner>/<submodule>.git
└── gitlab.com/<group>/<submodule>.git
```

路径照抄原站，是为了让下面的前缀改写能整段替换主机名，而不必逐个仓库配规则。在联网机器上为每个独立仓库建镜像：

```bash
git clone --mirror \
  https://github.com/<owner>/<repo>.git \
  <mirror-root>/github.com/<owner>/<repo>.git

git clone --mirror \
  https://gitlab.com/<group>/<repo>.git \
  <mirror-root>/gitlab.com/<group>/<repo>.git
```

每个 submodule、包括嵌套层级，都要有自己的镜像，因为它们的对象从不进 superproject 的对象库。搬运之前先按[核对目标提交](#verify-sha)逐个确认镜像含有锁定的 SHA，免得东西运到离线端才发现缺。

把整棵 `<mirror-root>` 搬到离线机器后，同样用一次性前缀改写，只是这次改写目标是本地文件。`<mirror-root>` 要写成绝对路径，拼进 `file://` 之后是三个斜杠的形式——挂载点 `/mnt/usb/mirrors` 对应 `file:///mnt/usb/mirrors`：

```bash
git \
  -c protocol.file.allow=always \
  -c 'url.file://<mirror-root>/github.com/.insteadOf=https://github.com/' \
  -c 'url.file://<mirror-root>/github.com/.insteadOf=git@github.com:' \
  -c 'url.file://<mirror-root>/github.com/.insteadOf=ssh://git@github.com/' \
  -c 'url.file://<mirror-root>/gitlab.com/.insteadOf=https://gitlab.com/' \
  -c 'url.file://<mirror-root>/gitlab.com/.insteadOf=git@gitlab.com:' \
  -c 'url.file://<mirror-root>/gitlab.com/.insteadOf=ssh://git@gitlab.com/' \
  clone --recurse-submodules \
  https://github.com/<owner>/<repo>.git \
  <repo>
```

`protocol.file.allow=always` 不是可选项。[`protocol.allow`](https://git-scm.com/docs/git-config/2.43.0#Documentation/git-config.txt-protocolallow) 给 `file` 的默认策略是 `user`，而 `user` 的含义是"只有用户直接发起时才允许"——git-config 文档举的正是递归 submodule 初始化这个例子：那些由 Git 自己派生、没有用户逐条过目的 clone/fetch 不适用。递归 clone 恰好落在被挡的一侧，所以要按本次命令显式放开，不写成全局配置。

改写只影响这一次传输：clone 实际读的是本地镜像，落盘的仓库配置仍是官方 URL。

## <a id="fill-objects"></a>向已有 gitdir 补目标提交

镜像连得上、gitdir（子模块的 Git 元数据目录 `.git/modules/<name>`）也已经建好，只差那个提交——这时不必推倒重来，把对象补进现有对象库即可。首选仍是 bundle，直接当本地 remote 取：

```bash
required_sha=$(git rev-parse HEAD:<submodule-path>)
git -C <submodule-path> fetch \
  <transfer-dir>/<submodule>.bundle \
  refs/offline-transfer/pinned
git -C <submodule-path> cat-file -e "${required_sha}^{commit}"
git -C <submodule-path> checkout --detach "$required_sha"
git submodule sync --recursive
```

只有原始 `.pack` 时，`index-pack` 可以把对象导入现有对象库：

```bash
pack_file='<transfer-dir>/<objects.pack>'
git -C <submodule-path> \
  index-pack --stdin --fix-thin < "$pack_file"
```

裸 `.pack` 比 bundle 少三样东西，所以只在拿不到 bundle 时才走这条路：

- **没有 ref 清单**：pack 只有对象，不告诉你里面哪个 SHA 是你要的，也没有 prerequisite（接收端必须先有的先决对象）声明可校验。
- **没有 shallow 边界**：pack 若来自浅克隆，它引用的父提交在边界之外。目标对象库若也没有这些父提交，还得把来源仓库的 shallow 边界文件复制到 `git -C <submodule-path> rev-parse --git-path shallow` 指出的位置。
- **thin pack 依赖外部基础对象**：thin pack 会省略它认为接收端已有的基础对象（`--fix-thin` 就是补这一段）；这些基础对象必须真的已经在目标对象库里，否则补不上。

导入后至少跑一遍 `cat-file -e`、`fsck --connectivity-only`，并检出 superproject 锁定的 SHA。传输物还能重做时，就重做成 bundle——它可验证、可复现，裸 pack 两样都差。

## <a id="status"></a>状态核验与常见错误

```bash
git remote -v
git submodule status --recursive
git submodule status --recursive | sed -n '/^[-+U]/p'
git submodule foreach --recursive 'git fsck --connectivity-only'
git config --show-origin --get-regexp '^url\..*\.insteadof$' || :
```

`submodule status` 的正常行以空格开头：`-` 表示未初始化，`+` 表示当前提交与 superproject 不一致，`U` 表示冲突。带 `sed` 那条把所有非正常行筛出来，它没有输出，才说明已列出的层级全部对齐。最后一条查有没有把临时 URL 改写写进配置——本页一律用 `git -c`，正常情况下它应当没有输出。

| 现象 | 含义与处理 |
| --- | --- |
| 主仓库成功，submodule 仍访问 GitHub SSH | 补上 `git@github.com:` 与 `ssh://git@github.com/` 两种改写 |
| ghfast 前缀访问 GitLab 失败 | ghfast 不承担 GitLab 前缀代理；改用 GitLab 的可信入口或离线传输 |
| `transport 'file' not allowed` | 在本次递归命令加 `-c protocol.file.allow=always` |
| `not our ref` / `reference is not a tree` | 镜像不含目标 SHA；用 bundle 或含精确对象的来源补齐 |
| 深层目录为空 | 父模块尚未检出，或缺少 `--init --recursive` |
| bundle clone 后相对 submodule URL 指错位置 | 初始化前把 superproject 的 `origin` 恢复为官方 URL |
| `origin` 留成代理或 bundle | 主仓库用 `remote set-url`；submodule 用 `submodule sync --recursive` |
