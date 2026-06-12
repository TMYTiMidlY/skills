# docs-share：用 S3 presigned 直链分享私密文档

把 Markdown / HTML 放进**私有 Git 仓库** → forgejo runner 自动把仓库内容 sync 到 RustFS S3 桶 → 用 **S3 presigned URL** 分享。`.md` 浏览器贴地址栏自动 markdeep 渲染，`curl/wget` 拿原始文本。

> 服务端部署 / Caddy / `_viewer.html` 壳子 / 桶 + CI key 创建：见 `vps-maintenance` skill 的 [`references/caddy.md` §「文档私链分享站」](../../vps-maintenance/references/caddy.md)。
>
>
> 本节只覆盖**客户端使用**：凭据放哪、生成分享链接、撤销分享、markdeep 写作惯例。

## 客户端凭据：受限 `ci` access key

部署完成后，**唯一会持久存在的凭据**就是一把绑了 policy 的**受限 access key**，只能操作 `docs-share/*` 这一个桶（policy 在服务端配置时已固化）。

| 凭据 | 存哪 | 用途 |
|---|---|---|
| 受限 CI key（AK + SK） | 本机 `~/.mc/config.json` 一个 alias | 日常生成 presigned URL |
| 同上 | forgejo 仓库 secret `RUSTFS_CI_AK` / `RUSTFS_CI_SK` | runner 跑 `rclone sync` |
| **root key** | **不该出现在客户端**——部署时 mc admin 用一次就删掉本地 alias | 只用于建桶 / 发 CI key / 配 policy（一次性） |

本机 alias 命名建议两个：

```bash
# 走公网域名（生成外发链接用）
mc alias set <PUB_ALIAS> https://<S3_HOST>      <CI_AK> <CI_SK> --api s3v4
# 走 mesh 内网（自己机器测 / CI 用，省一跳）
mc alias set <MESH_ALIAS> http://<MESH_HOST>:9000 <CI_AK> <CI_SK> --api s3v4
```

> SigV4 把 host 也签进签名了——**生成对外链接必须用 alias 对应公网域名**；mesh alias 签出来的链接外部访问会签名失败。

## 生成分享链接

### 方式 A：地址栏直贴 .md → 自动渲染（推荐）

```bash
mc share download --expire 168h <PUB_ALIAS>/docs-share/<dir>/<file>.md
```

输出里 `Share:` 那行就是完整 presigned URL。**直接发给读者**——浏览器贴地址栏看到排版页（Caddy `Accept: text/html` 分流到 viewer rewrite），`curl/wget` 拿到原文。

### 方式 B：viewer.html?doc= 包装（向后兼容，跨 S3 后端通用）

```bash
RAW=$(mc share download --expire 168h <PUB_ALIAS>/docs-share/<dir>/<file>.md | sed -n 's/.*Share: *//p')
ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$RAW")
echo "https://<S3_HOST>/docs-share/viewer.html?doc=$ENC"
```

适用：后端是 MinIO / 其他 S3 但没装 viewer rewrite 的边缘 Caddy。

### 非 .md 资源（图片 / pdf / html / mp4）

直接用方式 A 的命令。S3 把这些对象的 Content-Type 设对就行，浏览器自然渲染。

```bash
mc share download --expire 168h <PUB_ALIAS>/docs-share/<dir>/<file>.png
mc share download --expire 168h <PUB_ALIAS>/docs-share/<dir>/<file>.pdf
```

## 更新内容（git push 即同步）

```bash
git clone <forgejo>/TiMidlY/docs-share
# 编辑（一次改多个文件都行）
git push
```

- **一次 push 推多个 commit 只触发一次同步**：`on: push` 按 push 事件触发不是按 commit；rclone sync 是「对齐到最终状态」的幂等操作，同步 push 后的最终 tree，不在乎中间几个 commit。
- **本地 git status 干净 = 桶状态干净？不一定**：如果你（或别人）做过 forgejo rerun 早 sha 的操作，桶可能被回滚（详见 `~/TiMidlY-projects/docs-share/.github/copilot-instructions.md`）。
- **想立刻让桶对齐 main HEAD**：`git commit --allow-empty -m "trigger sync" && git push`。

## 撤销分享

| 想做的 | 怎么做 |
|---|---|
| 单条链接到期 | 啥都不用做，`X-Amz-Expires` 自动失效 |
| **立刻作废所有在途链接** | 在持 root key 的机器上 `mc admin accesskey rm rootadmin/ <CI_AK>` + 重新建一把新 CI key + 替换 forgejo secret + 替换本机 `~/.mc/config.json`（**让所有已发链接同时失效**） |
| 撤回单个对象 | git 仓库 `git rm <path> && git push`，下次 sync 会把桶里对应对象删掉；已发出去的链接 GET 该对象会 404 |

## markdeep 写作惯例：依据引用 vs 说明脚注（可选）

下面这套只在**同时满足**两个条件时启用：① 用户明确要求"有依据 / 挂来源 / 每条都要出处"；且 ② 这份 md **只通过 markdeep 渲染查看**（不发到 GitHub / VS Code / CommonMark 环境）。

**如果目标是 GFM 兼容**（要发到 GitHub issue、wiki、VS Code 原生预览、或不确定读者用什么渲染器），**不要用 `[#key]`**——CommonMark 不识别，读者只会看到字面的 `[#key]`；给来源直接用普通内联链接 `[说明文字](url)`，也不要做 `**Bibliography**:` 段。

启用 markdeep 引用体系时，两套标识刻意区分用途：

- **外部依据（URL 可核的断言 / 数字 / 官方原话）** → `[#key]`，文末 `**Bibliography**:` 统一列条目。断言后直接跟 `[#key]`，多源并列用逗号 `[#a, #b]`。条目格式：`[#key]: 作者/机构, "标题", 年. URL`。
- **补充说明（展开解释 / 计算口径 / 风险提示，非引用）** → 脚注 `[^1]` / `[^name]`，正文插标识、文末或段末写 `[^name]: 说明`。**脚注在 GFM 2021-09 后也支持，GFM 模式可保留脚注**，只需丢掉 `[#key]`。

语义区别：`[#key]` 回答"这条我从哪看到的"（markdeep 自动汇总到 Bibliography）；`[^name]` 回答"这条要额外解释一下"（**定义行放哪、就在哪渲染**）。

### markdeep 引用 vs GitHub/CommonMark 不兼容点

| 语法点 | Markdeep | CommonMark / GFM |
| --- | --- | --- |
| `[#Key]` 引用 | 识别为学术引用 | 仅当存在 `[#Key]: url` 定义才解析为 shortcut link，否则字面显示 |
| `[#A, #B]`（单括号内逗号） | ✅ 支持 | ❌ 逗号不是合法 label 分隔 |
| `[#Key]: 作者, 年, 标题, URL` 自由混排 | ✅ markdeep 自抽 URL | ❌ CommonMark 要求冒号后紧跟 URL |
| `**Bibliography**:` 段 | ✅ 生成编号 + 反链 | ❌ 仅一段加粗文字 |
| 脚注 `[^name]` | ✅ | ✅（GFM 2021-09 起） |

依据：[CommonMark 0.31.2 spec](https://spec.commonmark.org/0.31.2/)、[GitHub Footnotes 2021-09-30](https://github.blog/changelog/2021-09-30-footnotes-now-supported-in-markdown-fields/)、[Markdeep features](https://casual-effects.com/markdeep/features.md.html)。

### 研报长文模板（作者固化风格，可选）

研报类长文骨架（用户写作惯例，非 markdeep 要求）：

- **文件头 metadata 行**（三项 `·` 分隔一行）：`**最后更新日期**：YYYY-MM-DD　·　**作者**：<name>　·　**话题**：<简述>`，接一行 `---`。
- 首节固定「零、TL;DR」：每条结论一整句（粗体关键词前置、带数字），启用引用体系时末尾必挂 `[#key]`。
- 子节 `### 1.1`；段间 `---` 分隔；表格最后一列统一叫"来源"。
- 行内：原文直引用 `> 原文：**"..."**[#key]`；小结段用粗体标签开头（`**推论**：`/`**策略**：`）；来源分级标记 `【官方】`/`【第三方】`/`【推算】`。
- 结尾：`---` + `**Bibliography**:`（条目一行一条、条间空行）+ 再一个 `---` + `**变更说明**`。

### markdeep 不能用什么（viewer 渲染下）

- **`<script>`** —— viewer 客户端只加载 `markdeep.min.js`；md 内嵌脚本不执行（也不该执行，否则 docs-share 的"md 原样存储"约定被破坏）
- **mermaid** —— viewer 没加载 mermaid runtime；要画流程图用 markdeep 原生 [ASCII diagram](https://casual-effects.com/markdeep/features.md.html#diagrams)
- **GFM 表格里的复杂内联 HTML** —— markdeep 表格语法跟 GFM 兼容但严格度更高

需要这些功能就转为方式 B（`viewer.html?doc=`）的 viewer 是 stock markdeep 渲染，或者考虑直接传 HTML 文件（桶照样存，按 mc Content-Type 设 `text/html`）。

## 排障速查

| 现象 | 原因 / 修法 |
|---|---|
| 改了内容 push 后桶没更新 | 看 forgejo Actions run 是否成功；最常见是 DinD 短暂连不上 `data.forgejo.org` 拉 `actions/checkout` 超时（21s 那种）。**下次 push 会带上当前 main tree 整体 sync**，不用回头 rerun |
| 浏览器贴 .md URL 看到的不是排版页是 md 原文 | 边缘 Caddy 没装 Accept rewrite，只支持方式 B；改用 `viewer.html?doc=` |
| `viewer.html?doc=` 打开空白 / 报错 | `?doc=` 必须是**可 fetch** 的 URL（私有桶用 presigned）；presigned 与 viewer **同源**才无 CORS；浏览器需能访问 markdeep CDN |
| presigned 链接 403 / 过期 | `X-Amz-Expires` 到期重新生成；或受限 key 被删 / 改 policy |
| 同一个对象 mc cp 上传后下次 sync 又消失 | `rclone sync --remove` 是"以 git 仓库为权威 mirror"，桶里多余对象会被删；**永远以 git push 为唯一写入路径**，除非在做 hot-fix 对齐 |
| 桶里看到很多 `0B` 目录条目 | `mc ls` 不带 `--recursive` 把 S3 prefix 列为 0B（视觉占位）；用 `mc ls --recursive` 看真实内容 |

> 把 Markdown 导出为 PDF 见 `pdf-export.md`；源文件格式转换见 `format-conversion.md`。S3 兼容存储底层行为见 `rustfs.md`。
