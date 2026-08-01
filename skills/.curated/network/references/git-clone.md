# 受限网络下的 Git clone 与 submodule

这里处理的不是 Git 身份认证，而是仓库原站不可达：GitHub 只能经 ghfast、GitLab 需要另一条入口，或目标机器完全没有外网。临时绕行应只改变本次传输路径，仓库保存的 `origin` 和 `.gitmodules` 仍保持官方地址。

下文把包含 submodule 的上层仓库称为 superproject；gitlink 是 superproject 记录的子仓库目标 SHA。bundle 是 Git 自带的离线传输文件，bare mirror 是没有工作区、保存仓库 refs（分支和标签等引用）的镜像。

| 网络条件 | 获取方式 |
| --- | --- |
| 能访问 ghfast，仓库均在 GitHub | 一次性 `url.*.insteadOf` 改写 |
| GitHub 与 GitLab 混合，两个站点都有可达入口 | 按主机分别配置一次性 URL 改写 |
| 只有个别 GitLab 仓库有非等价镜像 | 在本地 `.git/config` 覆盖对应 submodule URL |
| 镜像缺少 superproject 锁定的提交 | 从联网机器传 bundle；已有 gitdir（Git 元数据目录）时也可补对象 |
| 完全没有外网 | 本地 bare mirror 树；少量仓库可逐个使用 bundle |
| 私有仓库 | 可信代理、内网镜像或 bundle，不把凭据交给公共第三方代理 |

## ghfast 的能力边界

[ghfast 首页](https://ghfast.top/)在 2026-07-27 展示的命令行能力是为 `github.com`、GitHub Raw 和 Gist 的 HTTPS 下载加前缀，并明确写明不支持 SSH Key clone。它是会变化的在线服务，使用前以首页当日说明为准。

公共 GitHub 仓库可以直接写代理 URL：

```bash
git clone https://ghfast.top/https://github.com/<owner>/<repo>.git
git -C <repo> remote set-url origin https://github.com/<owner>/<repo>.git
```

更适合自动化和 submodule 的方式是仅给本次 Git 命令增加 [`url.<base>.insteadOf`](https://git-scm.com/docs/git-config/2.43.0#Documentation/git-config.txt-urlbaseinsteadOf)。Git 在传输前改写匹配的 URL，配置文件仍记录调用者给出的官方 URL：

```bash
git \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=git@github.com:' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=ssh://git@github.com/' \
  clone --recurse-submodules https://github.com/<owner>/<repo>.git
```

三条规则分别接住 HTTPS、scp 风格 SSH 和完整 SSH URL。`-c` 只在当前命令及其 Git 子进程中生效，不会留下全局代理规则。Git 2.43.0 本地实测：主仓库与递归 submodule 都经改写源完成 clone，最终各自的 `origin` 仍是原始 GitHub URL。

ghfast 的公开页面虽然给出了把 token 放进 URL 的私有仓库示例，但 TLS 连接终止在 `ghfast.top`，代理端会收到该凭据。除非明确接受这个信任边界并使用短期、最小权限 token，否则私有仓库走可信代理、内网镜像或离线 bundle。

ghfast 没有声明代理 `gitlab.com`；不要把 `https://gitlab.com/...` 机械拼到 ghfast 前缀后。GitLab 仓库按下文单独分流。

## GitHub submodule

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

父模块初始化后，才能看到它携带的下一层 `.gitmodules`。下面的命令只遍历已经初始化的层级：

```bash
git submodule foreach --recursive '
  if test -f .gitmodules; then
    git config -f .gitmodules --get-regexp "^submodule\\..*\\.url$" || :
  fi
'
```

如果主仓库 clone 成功而 submodule 失败，常见原因是 `.gitmodules` 使用了 SSH URL、存在 GitLab 仓库，或更深一层还没有初始化；它们都是独立仓库，不会自动继承主仓库的 `origin`。

## GitHub 与 GitLab 混合仓库

如果 GitLab 有一个保持 `group/repo.git` 路径结构的可信入口，可以同时改写两个站点。`<reachable-gitlab-prefix>` 必须是该服务文档给出的完整 HTTPS 前缀，并以 `/` 结尾：

```bash
git \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=https://github.com/' \
  -c 'url.https://ghfast.top/https://github.com/.insteadOf=git@github.com:' \
  -c 'url.<reachable-gitlab-prefix>.insteadOf=https://gitlab.com/' \
  -c 'url.<reachable-gitlab-prefix>.insteadOf=git@gitlab.com:' \
  submodule update --init --recursive
```

有些“镜像”只是另一个项目仓库，owner、仓库名或历史同步范围不同，不能作为整个 GitLab 前缀的等价替换。此时只覆盖一个 submodule：

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

镜像可访问不代表它含有目标提交。superproject 要求的 SHA 可以这样取得并核验：

```bash
required_sha=$(git rev-parse HEAD:<submodule-path>)
git -C <submodule-path> cat-file -e "${required_sha}^{commit}"
git -C <submodule-path> checkout --detach "$required_sha"
```

`cat-file` 失败或更新时报 `not our ref` / `reference is not a tree`，说明镜像没有 superproject 锁定的对象。不要改成镜像的最新版本；应补入精确提交或换用完整来源。

## 本地 bare mirror 树

需要反复为多台离线机器准备主仓库和多层 submodule 时，按原站路径保存 bare mirror：

```text
<mirror-root>/
├── github.com/<owner>/<repo>.git
├── github.com/<owner>/<submodule>.git
└── gitlab.com/<group>/<submodule>.git
```

在联网机器上为每个独立仓库建立镜像：

```bash
git clone --mirror \
  https://github.com/<owner>/<repo>.git \
  <mirror-root>/github.com/<owner>/<repo>.git

git clone --mirror \
  https://gitlab.com/<group>/<repo>.git \
  <mirror-root>/gitlab.com/<group>/<repo>.git
```

submodule 对象不会存进 superproject 的对象库；每个 submodule，包括嵌套层级，都需要自己的 bare mirror。传输前核对 mirror 含有 superproject 锁定的提交：

```bash
required_sha=$(git -C <super-checkout> rev-parse HEAD:<submodule-path>)
git --git-dir=<submodule-mirror>.git cat-file -e "${required_sha}^{commit}"
```

把整个 `<mirror-root>` 带到离线机器后，使用一次性前缀改写。将 `<mirror-root>` 替换成绝对路径；例如绝对路径以 `/mnt/...` 开头时，生成的 URI 是 `file:///mnt/...`：

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

Git 对递归命令触发的本地 `file` 传输默认更谨慎，因此这里按当前命令设置 [`protocol.file.allow=always`](https://git-scm.com/docs/git-config/2.43.0#Documentation/git-config.txt-protocolallow)，不写成全局配置。一次性改写使 clone 实际读取本地 mirror，但仓库配置仍保存官方 URL。

如果主仓库先由 bundle 克隆，先把它的 `origin` 改回官方 URL，再初始化带相对 URL 的 submodule；否则相对 URL 会依据 bundle 文件路径解析：

```bash
git -C <repo> remote set-url origin https://github.com/<owner>/<repo>.git
```

## Git bundle

[`git bundle`](https://git-scm.com/docs/git-bundle/2.43.0) 是 Git 官方提供的离线对象与 ref 传输格式，可以被 `clone`、`fetch` 和 `verify` 直接读取。少量仓库优先用 bundle，而不是手工搬 `.pack`。

下面的 `<transfer-dir>` 使用绝对路径。在联网机器上创建并校验：

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

给现有 superproject 初始化单个离线 submodule：

```bash
git submodule init <submodule-path>
git config 'submodule.<name>.url' \
  '<transfer-dir>/<submodule>.bundle'
git -c protocol.file.allow=always \
  submodule update <submodule-path>

git submodule sync --recursive
```

这里也要为每个 submodule 单独制作 bundle；superproject 的 bundle 只有 gitlink SHA，没有子仓库对象。嵌套 submodule 在父模块检出后才出现，少量仓库可以逐层重复上述操作；数量多时把 bundle 在离线端转换成 bare mirror 树更省事：

```bash
git clone --mirror \
  <transfer-dir>/<submodule>.bundle \
  <mirror-root>/<host>/<group>/<submodule>.git
```

## 已有 gitdir 时补目标提交

可达镜像没有目标 SHA、但已经留下 `.git/modules/<name>` 时，优先把包含精确提交的 bundle 作为本地 remote 获取：

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

`.pack` 不携带 bundle 的 ref 清单和 prerequisite（接收端必须已有的先决对象）校验。如果它来自浅克隆，且目标对象库没有边界外的父提交，还必须把来源仓库的 shallow 边界写到 `git -C <submodule-path> rev-parse --git-path shallow` 返回的位置；thin pack（省略接收端已有基础对象的包）也要求目标对象库已经有它引用的基础对象。导入后至少运行 `cat-file -e`、`fsck --connectivity-only` 并检出 superproject 锁定的 SHA。能重新制作传输物时，bundle 比裸 pack 更容易验证和复现。

## 状态核验

```bash
git remote -v
git submodule status --recursive
git submodule status --recursive | sed -n '/^[-+U]/p'
git submodule foreach --recursive 'git fsck --connectivity-only'
git config --show-origin --get-regexp '^url\..*\.insteadof$' || :
```

`submodule status` 的正常行以空格开头；`-` 表示未初始化，`+` 表示当前提交与 superproject 不一致，`U` 表示冲突。第二条筛选命令没有输出才表示所有已列出的层级都对齐。最后一条用于发现是否曾把临时 URL 改写持久化到配置；本页的 `git -c` 写法不会留下记录。

| 现象 | 含义与处理 |
| --- | --- |
| 主仓库成功，submodule 仍访问 GitHub SSH | 补上 `git@github.com:` 与 `ssh://git@github.com/` 两种改写 |
| ghfast 前缀访问 GitLab 失败 | ghfast 不承担 GitLab 前缀代理；改用 GitLab 的可信入口或离线传输 |
| `transport 'file' not allowed` | 在本次递归命令加 `-c protocol.file.allow=always` |
| `not our ref` / `reference is not a tree` | 镜像不含目标 SHA；用 bundle 或含精确对象的来源补齐 |
| 深层目录为空 | 父模块尚未检出，或缺少 `--init --recursive` |
| bundle clone 后相对 submodule URL 指错位置 | 初始化前把 superproject 的 `origin` 恢复为官方 URL |
| `origin` 留成代理或 bundle | 主仓库用 `remote set-url`；submodule 用 `submodule sync --recursive` |
