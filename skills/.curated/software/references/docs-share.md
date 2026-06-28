# docs-share：Git 仓库 → S3 presigned 直链分享

私有 Git 仓库 → forgejo runner `rclone sync --checksum --remove` → RustFS S3 桶（桶结构 = 仓库树）。`public/*` 匿名可读，其他路径**默认**走 presigned URL。`.md` 浏览器直贴自动 markdeep 渲染。

> **本文件 = 简明索引 + 安装/部署。** 每节是 1-3 句的速查;每个日常操作话题都在仓库 `README.md` 有**更详细的版本**:
> <https://github.com/TMYTiMidlY/docs-share/blob/main/README.md>
>
> 服务端基础设施（建桶、CI key 创建、bucket policy、Caddy 边缘 + Accept-rewrite、viewer / `_viewer.html` 部署）→ **vps-maintenance** skill 的 `references/caddy.md` §「文档私链分享站」（含完整端到端部署步骤）。RustFS 桶日常操作的客户端坑（mc / boto3 行为差异、versioning、跨桶 copy、删桶）→ **software** skill 的 `references/rustfs.md`（同目录 `rustfs-bulk-ops.md` 写批量 ops 注意点）。仓库目录结构与本机 alias 细节 → 仓库 `README.md`。

---

## 部署前的密钥体系

| 角色 | 能力 | 生命周期 |
|---|---|---|
| **root key** | 建桶 / 发 CI key / 设 bucket policy | 部署时临时用，用完删 alias，不留客户端 |
| **受限 CI key** | 只能操作 `<BUCKET>/*` | 长期存在，日常唯一凭据 |

CI key 部署后存两处：
- 本机 `~/.mc/config.json`（按需配多个 alias 对应不同入口 URL；**SigV4 签名含 host**，内网 alias 签出的链接外部不可用，外发链接必须用公网入口 alias）。
- forgejo 仓库 secret（AK + SK，由 `.forgejo/workflows/sync.yml` 注入 rclone env：`RCLONE_S3_ACCESS_KEY_ID` / `RCLONE_S3_SECRET_ACCESS_KEY`）。

## 桶初始化（一次性，需 root key）

### 1. 建桶 + 发受限 CI key

完整步骤（建桶 + 发 CI key + Caddy 反代 + viewer 部署）都在 **vps-maintenance** skill 的 `references/caddy.md` §「文档私链分享站」。建好 CI key 后存进仓库 secret 与本机 `~/.mc/config.json`。（**software** skill 的 `references/rustfs.md` 只讲 mc / boto3 客户端操作坑，**不**讲 RustFS 服务部署。）

### 2. 设 `public/*` 匿名可读的 bucket policy

桶默认全私有。`public/*` 前缀通过 bucket policy 开匿名 `s3:GetObject`：

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": ["*"]},
    "Action": ["s3:GetObject"],
    "Resource": ["arn:aws:s3:::<BUCKET>/public/*"]
  }]
}
```

应用（root key，用完即弃）：

```bash
mc alias set rfsadmin http://<MESH>:9000 <ROOT_AK> <ROOT_SK> --api s3v4
mc anonymous set-json policy.json rfsadmin/<BUCKET>
mc alias rm rfsadmin
```

其他路径不受影响，仍然 403 → 全靠 presigned。

> ⚠️ **默认走 presigned 私链，不要默认丢进 `public/`。** `public/` 是**永久、匿名、全网可读**——只在内容**明确**可公开且需要不过期直链时才用。日常分享统统走 presigned，详见仓库 README §分享方式。

---

## 生成分享链接

**私有文件（默认）**：`mc share download --expire <TTL> <PUB_ALIAS>/<BUCKET>/<path>`，输出 `Share:` 行即完整 presigned URL（带签名 + 有效期，到期自动失效）。`<PUB_ALIAS>` 必须是公网入口 alias。presigned **按 HTTP method 签名**，`mc share download` 签的是 GET——本地验证别用 `curl -I`(HEAD)，会 403，要用 `curl` GET。

**公开文件（仅 `public/` 下，需明确选择）**：直拼 `https://<S3_HOST>/<BUCKET>/public/<path>`。

**带图片的私有 md / html**：相对图在 presigned 下会 403（`_viewer.html` 故意剥签名）。md 在第一行加 `<!-- docs-share:bundle -->` 标记，CI 生成自包含 `<名>.bundle.md`（图 base64 内联），分享 `.bundle.md` 即可；html 惯例是单文件自包含手写 `data:` URI。**详细工作流（bundler 边界、`<a download>` 强制下载、JS Blob 下载原文）见仓库 README §分享方式 B/C**。

## 更新内容

`git push` 即触发同步（rclone 幂等对齐最终 tree）。**forgejo rerun 早 sha 的 run 会回滚桶**——想对齐当前 HEAD 推空 commit 或 rerun HEAD 对应的 run（详见仓库 README §更新内容 §rerun 早 sha 会回滚桶）。

## 撤销分享

| 想做的 | 怎么做 |
|---|---|
| 单条链接到期 | `X-Amz-Expires` 自动失效 |
| 作废所有在途链接 | 用 root key 删当前 CI key + 重建 + 替换 forgejo secret + 本机 alias |
| 撤回单个对象 | `git rm <path> && git push`，sync 后桶里对象消失 |

## markdeep 写作惯例：依据引用 vs 说明脚注（可选）

下面这套只在**同时满足**两个条件时启用：① 用户明确要求“有依据 / 挂来源 / 每条都要出处”；且 ② 这份 md **只通过 markdeep 渲染查看**（不发到 GitHub / VS Code / CommonMark 环境）。

**如果目标是 GFM 兼容**（要发到 GitHub issue、wiki、VS Code 原生预览、或不确定读者用什么渲染器），**不要用 `[#key]`**——CommonMark 不识别，读者只会看到字面的 `[#key]`；给来源直接用普通内联链接 `[说明文字](url)`，也不要做 `**Bibliography**:` 段。

启用 markdeep 引用体系时，两套标识刻意区分用途：

- **外部依据（URL 可核的断言 / 数字 / 官方原话）** → `[#key]`，文末 `**Bibliography**:` 统一列条目。断言后直接跟 `[#key]`，多源并列用逗号 `[#a, #b]`。条目格式：`[#key]: 作者/机构, "标题", 年. URL`。
- **补充说明（展开解释 / 计算口径 / 风险提示，非引用）** → 脚注 `[^1]` / `[^name]`，正文插标识、文末或段末写 `[^name]: 说明`。**脚注在 GFM 2021-09 后也支持，GFM 模式可保留脚注**，只需丢掉 `[#key]`。

语义区别：`[#key]` 回答“这条我从哪看到的”（markdeep 自动汇总到 Bibliography）；`[^name]` 回答“这条要额外解释一下”（**定义行放哪、就在哪渲染**）。

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
- 子节 `### 1.1`；段间 `---` 分隔；表格最后一列统一叫“来源”。
- 行内：原文直引用 `> 原文：**"..."**[#key]`；小结段用粗体标签开头（`**推论**：`/`**策略**：`）；来源分级标记 `【官方】`/`【第三方】`/`【推算】`。
- 结尾：`---` + `**Bibliography**:`（条目一行一条、条间空行）+ 再一个 `---` + `**变更说明**`。

### markdeep 不能用什么（viewer 渲染下）

- **`<script>`** —— viewer 客户端只加载 `markdeep.min.js`；md 内嵌脚本不执行（也不该执行，否则 docs-share 的“md 原样存储”约定被破坏）。
- **mermaid** —— viewer 没加载 mermaid runtime；要画流程图用 markdeep 原生 [ASCII diagram](https://casual-effects.com/markdeep/features.md.html#diagrams)。
- **GFM 表格里的复杂内联 HTML** —— markdeep 表格语法跟 GFM 兼容但严格度更高。

需要这些功能就走“直接传 HTML 文件”（桶照样存，mc 自动按扩展名设 `Content-Type: text/html`），或者用旧的 `viewer.html?doc=` 模式（是 stock markdeep 渲染）。

## 排障速查

| 现象 | 原因 / 修法 |
|---|---|
| 改了内容 push 后桶没更新 | 看 forgejo Actions run 是否成功；最常见是 DinD 短暂连不上 `data.forgejo.org` 拉 `actions/checkout` 超时（21s 那种）。**下次 push 会带上当前 main tree 整体 sync**，不用回头 rerun |
| 浏览器贴 `.md` URL 看到的不是排版页是 md 原文 | 边缘 Caddy 没装 Accept rewrite（如 `47.102.36.175:9000` Alibaba 直暴 RustFS 入口），只支持方式 B；换装了 rewrite 的 `s3.tmytimidly.com` 入口，或改用 `viewer.html?doc=<URL>` |
| md 渲染了但**图片全裂**（403） | 用了相对图但没走 bundle；给文档第一行加 `<!-- docs-share:bundle -->`，push 后分享 `<名>.bundle.md` |
| `viewer.html?doc=` 打开空白 / 报错 | `?doc=` 必须是**可 fetch** 的 URL（私有桶用 presigned）；presigned 与 viewer **同源**才无 CORS；浏览器需能访问 markdeep CDN |
| presigned 链接 403 / 过期 | `X-Amz-Expires` 到期重新生成；或 host 不匹配（SigV4 签名含 host，跨入口 alias 签出的链接互不能用）；或受限 key 被删 / 改 policy |
| 同一个对象 mc cp 上传后下次 sync 又消失 | `rclone sync --remove` 是“以 git 仓库为权威 mirror”，桶里多余对象会被删；**永远以 git push 为唯一写入路径**，除非在做 hot-fix 对齐 |
| 桶里看到很多 `0B` 目录条目 | `mc ls` 不带 `--recursive` 把 S3 prefix 列为 0B（视觉占位）；用 `mc ls --recursive` 看真实内容 |

> 把 Markdown 导出为 PDF 见 **software** skill 的 `references/pdf-export.md`；源文件格式转换见 **software** skill 的 `references/format-conversion.md`；操作 RustFS 桶的客户端坑（mc / boto3 / versioning / 删桶）见 **software** skill 的 `references/rustfs.md`（同目录 `rustfs-bulk-ops.md` 写批量 ops）。

## 部署后

仓库 `README.md` 是日常操作的**更详细版本**——本文件是速查索引，遇到边界情况、bundler 细节、html 下载按钮 JS Blob 模板、入口差异、Accept-rewrite 完整 curl 矩阵等，去 README 看完整版。
