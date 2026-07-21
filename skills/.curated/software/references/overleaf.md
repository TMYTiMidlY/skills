# USTC Overleaf：`olcli`、内部接口与 OT 审阅

本文记录的是中国科学技术大学自建实例
[`https://latex.ustc.edu.cn`](https://latex.ustc.edu.cn)，不是
[`overleaf.com`](https://www.overleaf.com) 官方托管服务。实测时间为
**2026-07-21**，使用 USTC 提供的 `olcli-ustc 0.7.0`。

还要区分两层“官方”：

- [`@aloth/olcli`](https://github.com/aloth/olcli) 是本文所说的**上游版**，
  作者是 Alexander Loth，不是 Overleaf 公司维护的官方 CLI。
- `olcli-ustc` 是 USTC 站点基于该上游版制作的定制构建。

USTC 的下载 URL 是滚动的 `latest`，版本号仍写 `0.7.0`，仅看版本号不足以
识别包内容。本次实测包指纹：

| 文件 | SHA-256 |
| --- | --- |
| `agent/bundle.tar.gz` | `482453e3e664a0ee5edc31576f34ea240a81a37815374dc1352ffa1433061704` |
| `agent/olcli-ustc-latest.tgz` | `be9323fb8718a9a55981a58ec40c93292d17ffc1c5a1a8d42cdabe9ee154c02e` |

> 来源：USTC 的 [Agent 安装页](https://latex.ustc.edu.cn/agent) 与两个滚动
> 下载端点；上面的哈希固定的是 2026-07-21 实测快照，不代表 URL 以后仍返回
> 同一内容。

## <a id="upstream-comparison"></a>USTC 构建与上游版

上游 `v0.7.0` 对应 commit
[`6efd99e9c94df600546d3b69f2f119b6638cd00c`](https://github.com/aloth/olcli/tree/6efd99e9c94df600546d3b69f2f119b6638cd00c)。
USTC tarball 与该版本逐文件比较后，核心同步、编译、上传和评论功能相同，
主要差异集中在实例默认值与无头认证：

| 维度 | 上游 `@aloth/olcli 0.7.0` | USTC `olcli-ustc 0.7.0` |
| --- | --- | --- |
| npm 包名 | `@aloth/olcli` | `olcli-ustc` |
| 默认实例 | `https://www.overleaf.com` | `https://latex.ustc.edu.cn` |
| 默认 session cookie | `overleaf_session2` | `overleaf.sid` |
| 浏览器无头认证 | 手工提供 session cookie | 新增 `/agent/setup` 一次性 token 与 `/agent/exchange` |
| 集群会话 | 普通 session cookie | 额外保存并续用 `lb_srv_id` |
| Cookie 更新 | 基础 `Set-Cookie` 处理 | 增加回调持久化、重试与会话 Cookie 刷新 |
| 安装来源 | npm / Homebrew | USTC 站点托管的 tarball |

上游默认 URL 与 cookie 名可在
[`src/config.ts`](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/src/config.ts#L40-L75)
中直接看到；USTC tarball 的对应默认值改成了学校实例，同时新增 token 与
`lb_srv_id` 逻辑。

### 上游版能否操作 Overleaf 官方站

**可以。** 上游版默认就是 `https://www.overleaf.com`，认证帮助明确让用户
读取 `overleaf_session2` cookie；README 也把 session cookie 标为同时适用于
`overleaf.com` 与 self-hosted 实例
（[安装与认证](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/README.md#L44-L85)）。

上游版也能通过 `config set-url` 和 `config set-cookie-name` 指向自建实例
（[配置示例](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/README.md#L217-L232)），
但它没有 USTC 的一次性 token 交换和 `lb_srv_id` 会话保持。反过来，
USTC 构建理论上仍可改 URL 和 cookie 名去连其他实例，但 USTC token 流程
不可移植，也没有在 Overleaf 官方站实测；操作官方站优先用上游版。

## <a id="installation"></a>Skill 与 CLI 安装

USTC 的 bundle 本身就是一个 skill 目录，包含：

- `SKILL.md`
- `install.sh`
- `install.ps1`

下载：

```bash
curl -sSL https://latex.ustc.edu.cn/agent/bundle.tar.gz \
  -o olcli-ustc-bundle.tar.gz
tar xzf olcli-ustc-bundle.tar.gz
```

全局使用时，可把这三个文件放到：

```text
~/.agents/skills/olcli-ustc/
```

本次安装后的 `SKILL.md` 与 USTC bundle 原文相比，只有手动 npm 安装命令
增加了命令级 `--prefix`：

```diff
-npm install -g https://latex.ustc.edu.cn/agent/olcli-ustc-latest.tgz
+npm install -g --prefix "$HOME/.local/olcli-ustc" https://latex.ustc.edu.cn/agent/olcli-ustc-latest.tgz
```

### nvm 与 npm prefix

USTC 原始 `install.sh` 会执行：

```bash
npm config set prefix "$HOME/.local/olcli-ustc"
npm install -g "$TARBALL"
```

第一条会把 `prefix=...` 持久写进用户级 `~/.npmrc`。nvm 要按当前 Node
版本管理自己的全局 prefix，因此每次加载 nvm 都会报告：

```text
Your user's .npmrc file has a globalconfig and/or a prefix setting,
which are incompatible with nvm.
```

隔离安装本身没有问题，问题是把隔离目录写成了 npm 的**永久默认值**。
改为只影响本次命令：

```bash
INSTALL_DIR="$HOME/.local/olcli-ustc"
mkdir -p "$INSTALL_DIR"
npm install -g --prefix "$INSTALL_DIR" \
  https://latex.ustc.edu.cn/agent/olcli-ustc-latest.tgz
```

安装脚本的等价补丁：

```diff
-npm config set prefix "$INSTALL_DIR"
-npm install -g "$TARBALL"
+npm install -g --prefix "$INSTALL_DIR" "$TARBALL"
```

`-g` 仍表示“安装为该 prefix 下的全局包”：模块落在
`$INSTALL_DIR/lib/node_modules/`，命令落在 `$INSTALL_DIR/bin/`；它并不表示
系统级安装，也不需要 sudo。

把命令目录加入 shell PATH：

```bash
export PATH="$HOME/.local/olcli-ustc/bin:$PATH"
```

长期使用可把同一行写入 `~/.bashrc` / `~/.zshrc`。验证：

```bash
olcli --version
olcli whoami
olcli list
```

## <a id="authentication"></a>无头认证与凭据

USTC 的认证流程是：

1. 用户先登录 USTC Overleaf，再在同域访问 `/agent/setup`。
2. 页面生成一次性 token。
3. `olcli auth --token <TOKEN>` 把 token 交给 `/agent/exchange`。
4. 服务返回 `overleaf.sid`，以及集群需要时的 `lb_srv_id`。
5. `olcli` 保存 cookie，随后用 `whoami` / `list` 验证。

token 和 session cookie 都是凭据，不应出现在命令历史、共享日志或对话正文；
用当前运行环境提供的带外 secret 注入能力传入。

凭据读取顺序沿用上游：

1. `OVERLEAF_SESSION`
2. 当前目录 `.olauth`
3. `~/.config/olcli-nodejs/config.json`

上游 README 对这三个来源有明确说明
（[Configuration](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/README.md#L217-L224)）。

全局配置内含可直接登录的 session cookie。至少保护父目录和文件：

```bash
chmod 700 ~/.config/olcli-nodejs
chmod 600 ~/.config/olcli-nodejs/config.json
```

`conf` 库在更新配置时可能原子重建文件并恢复较宽的文件 mode；父目录保持
`700` 才是更稳定的边界。

USTC 2026-07-21 快照的 `--verbose` 会打印 Cookie header。带凭据运行时不要
把 verbose 输出送进共享 CI 日志或 issue。

## <a id="cli-surface"></a>现有 CLI 能力

上游 `v0.7.0` 的完整命令表见
[README](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/README.md#L123-L151)。
USTC 构建保留了这些能力：

| 类别 | 命令 |
| --- | --- |
| 项目发现 | `list`、`info` |
| 本地同步 | `pull`、`push`、`sync` |
| 单文件 | `upload`、`download`、`rename`、`delete` |
| 构建 | `compile`、`pdf`、`output`、`zip` |
| 评论 | `comments list/add/reply/resolve/reopen/delete` |
| 配置 | `config`、`check`、`whoami`、`logout` |

当前公开 CLI **没有**：

- 创建项目命令
- 文本级 `edit` / patch 命令
- 创建 Track Changes 修订的命令
- Accept / Reject 修订的命令

`upload <file>` 一次只接收一个文件；批量修改走 `push` / `sync`。传入相对路径
如 `figures/plot.png` 时，客户端会解析或创建对应远端目录
（[上传实现](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/src/client.ts#L1565-L1626)）。

`output <type>` 不是只支持 `bbl`：它先编译，再从该项目实际返回的输出中按
type 或扩展名匹配。没有 bibliography 的项目本来就不会出现 `.bbl`。

`upload`、`push`、`sync` 最终走整文件上传，不会把本地 diff 转成文本 OT。
上游自己的 Git remote 文档也提醒：远端并发编辑可能冲突，push 会上传本地
版本（[Limitations](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/docs/GIT-REMOTE.md#L70-L74)）。

## <a id="project-creation"></a>内部 HTTP 项目创建

Overleaf Web 应用本身有登录后可用的内部 endpoint：

```http
POST /project/new
Content-Type: application/json

{"projectName":"<name>","template":"blank"}
```

路由要求登录并套创建项目 rate limit
（[`router.mjs`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/web/app/src/router.mjs#L537-L542)）；
controller 创建 basic/example project 后返回 `project_id`
（[`ProjectController.mjs`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/web/app/src/Features/Project/ProjectController.mjs#L316-L351)）。

本次实测复用了 `olcli-ustc` 保存的 cookie 与 CSRF，再调用编译后的
`OverleafClient.httpRequest()` / `getHeaders()` 创建项目。它们是 TypeScript
源码中的 private 方法
（[`client.ts`](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/src/client.ts#L389-L440)），
只是编译后 JavaScript 仍可访问；这不属于稳定的 `olcli` 公共 API。

核心调用形状：

```js
const response = await client.httpRequest(`${baseUrl}/project/new`, {
  method: 'POST',
  headers: client.getHeaders(true),
  body: JSON.stringify({
    projectName: '<name>',
    template: 'blank',
  }),
  expect: 'json',
})

const projectId = response.body.project_id
```

这是 Overleaf Web 前端所用的**内部 HTTP 接口**，不是官方承诺兼容性的公开
REST API。升级 USTC Overleaf 后要重新核对 route、CSRF 和响应格式。

## <a id="ot-editing"></a>普通 OT 编辑

Overleaf 文本协作不走 `/upload`，而走 real-time service 的 Socket.IO
`applyOtUpdate`。实时入口会校验项目、文档和权限，再补入真实 session 用户身份
（[`WebsocketController.js`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/real-time/app/js/WebsocketController.js#L558-L603)）。

`olcli` 已经有建立 project socket、`joinDoc` 和解析两类 OT snapshot 的内部
实现
（[`client.ts`](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/src/client.ts#L1134-L1178)），
但没有公开 `edit` 命令。

### `sharejs-text-ot`

USTC 本次演示项目的 `joinDoc` 返回 `sharejs-text-ot`。一次普通插入的 wire
形状是：

```js
await client.socketRpc(session, 'applyOtUpdate', [
  docId,
  {
    doc: docId,
    v: joined.version,
    op: [{ p: position, i: insertedText }],
  },
])
```

删除使用 `{ p, d: deletedText }`。`v` 必须是 `joinDoc` 得到的当前版本。

### `history-ot`

新协议用覆盖整个输入 snapshot 的 scan operation：

```js
{
  doc: docId,
  v: joined.version,
  op: [{
    textOperation: [
      retainBefore,
      insertedText,
      retainAfter,
    ],
  }],
}
```

删除是负数，tracked ranges 与 comments 也在同一 snapshot 中变换。

### 实测结果

在一个演示项目中：

- 两次普通 OT 插入让版本 `3 → 4 → 5`。
- 第二次在两条评论之前插入 144 个字符。
- 评论字符位置分别从 `494 → 638`、`1283 → 1427`，刚好都平移 144；
  评论文字、回复和 resolved 状态不变。
- 修改后的项目仍可正常编译 PDF。

这证明单文件细粒度 OT 编辑可行，也证明评论 range 会随操作变换。但这类
普通 OT 是**直接编辑**：正文立即改变，Review 面板不会出现 Accept/Reject。

只拿一次最新版本后裸发 `{p,i}` 适合单次受控实验，不是完整多人协作客户端。
可靠实现还要维护 pending/inflight op、处理 ack、版本冲突并做 transform/rebase；
否则在别人同时编辑时仍可能提交失败或错位。

## <a id="comments"></a>评论

现成 CLI 已支持：

```bash
olcli comments add main.tex "Please clarify this paragraph" \
  --text "selected source text"
olcli comments list --status open --context 2
olcli comments reply <thread-id> "Reply body"
olcli comments resolve <thread-id>
olcli comments reopen <thread-id>
olcli comments delete <thread-id>
```

`add` 会先取得文档内容和版本，再把评论锚点作为 OT operation 提交
（[`addComment`](https://github.com/aloth/olcli/blob/6efd99e9c94df600546d3b69f2f119b6638cd00c/src/client.ts#L2095-L2127)）。

Open 与 Resolved 不是两类评论：

1. 新评论创建时是 Open。
2. `comments resolve` 只把同一 thread 改为 Resolved。
3. `reopen` 可把它恢复为 Open。

Resolve 只表示讨论结束，不会修改正文，也不等于接受 Track Changes。

## <a id="tracked-changes"></a>Track Changes 与 Accept / Reject

Review 面板里有三种容易混淆的对象：

| 对象 | 正文是否变化 | 面板动作 |
| --- | --- | --- |
| 评论 | 不因评论本身变化 | Reply / Resolve / Reopen |
| 普通 OT 编辑 | 直接变化 | 没有 Accept / Reject |
| Track Changes 修订 | 以待审阅修改显示 | Accept / Reject |

### 旧协议中的 tracked change

`sharejs-text-ot` 仍发送普通 `{p,i}` / `{p,d}`，区别是 update 带
`meta.tc`：

```js
{
  doc: docId,
  v: joined.version,
  op: [{ p: position, i: insertedText }],
  meta: {
    tc: '<18-hex-id-seed>',
  },
}
```

Overleaf 前端正是这样给 update 增加 `meta.tc`
（[`share-js-doc.ts`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/web/frontend/js/features/ide-react/editor/share-js-doc.ts#L89-L107)）。
服务端看到 `meta.tc` 后启用 ranges tracker，并用该 seed 生成 change ID
（[`RangesManager.js`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/document-updater/app/js/RangesManager.js#L45-L69)）。
seed 是 Mongo ObjectId 风格的前 18 个十六进制字符，最后 6 位留给递增计数
（[`ranges-tracker`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/libraries/ranges-tracker/index.cjs#L73-L98)）。

本次实测提交一条带 `meta.tc` 的插入，文档版本 `5 → 6`，随后
`joinDoc` 的 `ranges.changes` 出现一条 change，页面显示 Accept/Reject；
这才是真正的“待审阅修改”。

### 接受与拒绝

旧 `sharejs-text-ot` 前端接受修订时调用：

```http
POST /project/<project-id>/doc/<doc-id>/changes/accept
Content-Type: application/json

{"change_ids":["<change-id>"]}
```

对应实现见
[`ranges-context.tsx`](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/web/frontend/js/features/review-panel/context/ranges-context.tsx#L341-L367)。
拒绝则在编辑器内生成逆向 OT。

`history-ot` 不走该旧 endpoint：Accept/Reject 都构造 `TextOperation`，
接受 insertion 会清掉 tracking，接受 deletion 会真正删除；拒绝 insertion
会删除候选文字，拒绝 deletion 会清掉 deletion tracking
（[history-ot 分支](https://github.com/overleaf/overleaf/blob/28ad3b03b71cb4311decdcb55c36b33ec10d72db/services/web/frontend/js/features/review-panel/context/ranges-context.tsx#L219-L339)）。

接受修订后 Review item 消失、插入文字保留为普通正文；拒绝插入修订后
Review item 与候选文字都消失。它们都不同于 `comments resolve`。

## <a id="figures"></a>文件上传与 `includegraphics`

上传相对路径会保留目录结构：

```bash
olcli upload figures/diagram.png <project>
```

再在 LaTeX 中引用：

```latex
\usepackage{graphicx}

\begin{figure}[htbp]
  \centering
  \includegraphics[width=0.85\linewidth]{figures/diagram.png}
  \caption{Uploaded through olcli.}
\end{figure}
```

本次实测用 `olcli upload figures/...png` 创建远端 `figures/` 并上传 PNG，
随后用普通 OT 添加 `graphicx` 与 figure 环境；现有评论和一条 tracked
change 都保留，PDF 编译成功。

## <a id="maintenance"></a>维护边界

- USTC `/agent/*`、Overleaf `/project/new`、Socket.IO event 与 Accept endpoint
  都是内部接口，不要当成版本稳定的公开 REST API。
- USTC tarball 使用滚动 `latest`；升级前后比较 SHA-256 与上游 diff，不能只看
  `0.7.0` 版本号。
- `upload` / `push` 是整文件覆盖路径。文档存在评论或 tracked changes 时，
  优先用 OT 修改正文，避免绕过 range transform。
- OT 操作提交前重新 `joinDoc` 取得最新 `v`；收到版本或权限错误后重新同步，
  不要静默重试旧位置。
- token、session cookie、`.olauth` 和全局 config 都按登录凭据处理。
