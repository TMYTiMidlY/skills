# 自托管 Markdown 文件分享

**定位**：一套 **"capability URL 作凭据"的无额外认证私链分享**——读取方拿到一段长随机串 URL 就能访问，没有登录页、没有 OAuth；上传侧单独用 basic_auth 保护，和读取侧共享同一份存储目录。

本 reference 覆盖"服务端已经配好 WebDAV + Markdeep viewer"之后的客户端视角：怎么上传、怎么拿分享链接、怎么写给 viewer 看的 markdown。

## 前置条件

**服务端已配置**：按 `vps-maintenance` skill 的 `caddy` reference 里「无额外认证的文档分享私链（WebDAV + Markdeep viewer）」一节**装好 caddy-webdav 扩展**并完成 Caddy site block（`/dav/*` basic_auth 上传端 + capability URL `/<token>/*` 读取端 + viewer 挂载 + 凭据生成）。没这一步就没得上传也没得分享。

**本地 `~/.env` 提供四项**（上传走 basic_auth；分享的 capability URL 本身不需要凭据，**但也放进 `.env`**——skill 上传后才能拼出成品链接、做 200 验证、直接贴回给用户）：

```bash
WEBDAV_URL=https://<host>/dav              # 写入入口，完整到 /dav 前缀
WEBDAV_USER=<user>                         # basic_auth 用户名
WEBDAV_PASS=<pass>                         # basic_auth 明文密码；rclone 固化 remote 时要 `rclone obscure` 处理
WEBDAV_SHARE_URL=https://<host>/<token>    # 公开读取入口（capability URL），不带尾斜杠；skill 上传后拼 `$WEBDAV_SHARE_URL/<file>` 就是成品分享链接
```

## 上传与验证

标准流程四步：**source `.env` → 上传 → HEAD 验证公开链接 200 → 把成品 URL 贴给用户**。

**一次性 `curl`（最轻量，不需要装 rclone）**

```bash
set -a; . ~/.env; set +a
fn=local.md
curl -fT "$fn" -u "$WEBDAV_USER:$WEBDAV_PASS" "$WEBDAV_URL/$fn"   # 上传（-f：非 2xx 返回非零退出码）
curl -fsI "$WEBDAV_SHARE_URL/$fn" >/dev/null                       # 验证：公开链接 HEAD 200
echo "📎 $WEBDAV_SHARE_URL/$fn"
```

**rclone（含远端浏览 / diff / 批量同步）**

一次性用法：

```bash
rclone copyto local.md :webdav:local.md \
  --webdav-url="$WEBDAV_URL" \
  --webdav-user="$WEBDAV_USER" \
  --webdav-pass="$(rclone obscure "$WEBDAV_PASS")" \
  --webdav-vendor=other
curl -fsI "$WEBDAV_SHARE_URL/local.md" >/dev/null && echo "📎 $WEBDAV_SHARE_URL/local.md"
```

要固化远端：`rclone config` 建一个 `webdav` 类型 remote（vendor 选 `other`），之后 `rclone copy local.md mywebdav:` 即可。

**skill 对 AI 的期望行为**：用户说"把 foo.md 分享给我 / 帮我把这个发布一下"时，skill 应当按顺序：(1) source `~/.env`；(2) `curl -fT` 上传到 `$WEBDAV_URL/foo.md`；(3) `curl -fsI "$WEBDAV_SHARE_URL/foo.md"` 确认公开链接返回 200；(4) 把 `$WEBDAV_SHARE_URL/foo.md` 贴回给用户（如果是 `.md` 文件，顺带说明"浏览器打开自动走 Markdeep viewer，curl 拿到的是 raw"）。任一步失败先贴 HTTP 状态码 / 响应头 / rclone stderr 让用户看到真实报错，再决定是否重试。

## 分享链接形态

服务端把同一份存储目录挂到两条路径下：

- `$WEBDAV_URL`（即 `https://<host>/dav/`）— 需要 basic_auth 的**写入入口**（上传用）
- `$WEBDAV_SHARE_URL`（即 `https://<host>/<token>`）— 长随机串当前缀的**读取入口**。浏览器打开 `.md` 自动走 Markdeep viewer 渲染；CLI `curl` / `wget` 默认 Accept 不含 `text/html`，直出 raw 原文

`$WEBDAV_URL/foo.md` 上传成功的瞬间，`$WEBDAV_SHARE_URL/foo.md` 即可公开访问——skill 就是以此拼装出成品链接交给用户的。

**撤销**：换服务端 token + `systemctl reload caddy` 一把梭撤销整个池（换完**记得同步更新 `~/.env` 里的 `WEBDAV_SHARE_URL`**，否则后续上传返回的链接是旧 token、无法访问）；单文件撤销靠从 WebDAV 删该文件（`curl -X DELETE -u "$WEBDAV_USER:$WEBDAV_PASS" "$WEBDAV_URL/foo.md"` 或 rclone `deletefile`）。

## Markdeep 写作惯例：依据引用 vs 说明脚注（可选）

**默认不强制加 `[#key]` 引用**。只有在**同时满足两个条件**时才启用本节约定：

1. 用户明确要求"有依据"/"挂来源"/"每条都要出处"；且
2. 这份 md **只走 Markdeep viewer 渲染**（即只分享 capability URL、不发到 GitHub / VS Code / CommonMark 环境）。

**如果目标是 GFM 兼容**（文件要发到 GitHub issue、wiki、VS Code 原生预览、或不确定读者用什么渲染器），**不要用 `[#key]`**——CommonMark 不识别，读者只会看到字面的 `[#key]`。GFM 模式下给来源直接用普通内联链接 `[说明文字](url)` 就好，也不要做 `**Bibliography**:` 段（同理会退化成一段加粗文字）。

启用 Markdeep 引用体系时，两套互相独立的标识用途刻意区分：

- **需要外部依据（URL 可核的断言 / 数字 / 官方原话）** → 用 `[#key]` 引用，文末 `**Bibliography**:` 统一列条目。断言后直接跟 `[#key]`，多源并列用逗号 `[#a, #b]`。Bibliography 条目格式：`[#key]: 作者/机构, "标题", 年. URL`（Markdeep 自由文本，但统一风格便于阅读）。
- **需要补充说明（展开解释、计算口径、参数差异、风险提示等，非引用）** → 用脚注 `[^1]` / `[^2]` / `[^name]`，数字或命名皆可。正文插标识，文末对应 `[^name]: 说明文字`。**脚注本身在 GFM 2021-09 后也支持，所以 GFM 模式保留脚注没问题**，只是 `[#key]` 引用要丢掉。

两者语义不同：

- `[#key]` 回答"这条数字我从哪看到的"——Markdeep 自动收集所有引用，统一渲染在 `**Bibliography**:` 段
- `[^name]` 回答"这条数字需要额外解释一下"——**定义行（`[^name]: ...`）在源文件里放哪，渲染就在哪**：放章节末尾→在章节末尾显示，全部堆到文末前→在文末显示。决定权在作者。建议把"紧跟当前段思路的注解"放段内尾部，把"横跨全文的长解释"堆文末。

**原则（仅在 Markdeep 引用体系启用时适用）**：

- 每个关键数字 / 断言至少挂一个来源；一手（官方文档 / 发布稿）优先，第三方（评测 / 报道）次之，推算（本文折算）要在脚注里标明口径。
- 表格类内容最后一列统一命名"来源"，每行一个或多个 `[#key]`。
- TL;DR 段里每条结论末尾也要挂引用，不要只挂到正文详述里。
- 区分"引用原文"和"引用数据"：引原文用 `> **原文**："..."[#key]` 的 block quote；引数字直接行内 `[#key]`。

## Markdeep 引用 vs GitHub/CommonMark 的不兼容点

**viewer 里渲染正常不代表 GitHub/VS Code 也行**。给人分享 md 原文要心里有数。关键差异（已核对官方规范）：

| 语法点 | Markdeep | CommonMark / GFM |
| --- | --- | --- |
| `#` 前缀的引用 `[#Key]` | 识别为学术引用 | 仅当存在 `[#Key]: url` 定义时才解析为普通 shortcut link，没有就字面显示 |
| 多引用 `[#A, #B]`（单括号内逗号） | ✅ 官方明确支持 | ❌ 不支持，逗号不是合法 label 分隔 |
| Bibliography 条目 `[#Key]: 作者, 年, 标题, URL 自由混排` | ✅ 自由文本，Markdeep 自己抽 URL | ❌ CommonMark 要求冒号后**必须紧跟 URL**，URL 前有其他字符就不算合法 link definition |
| `**Bibliography**:` 作为段落起始 | Markdeep 专门识别、生成编号 + 反链 | 仅渲染为一段加粗文字，无语义 |
| 脚注 `[^name]` + `[^name]: text` | ✅ | ✅（GFM 2021-09 起支持，CommonMark 核心规范不含但主流解析器都支持） |

依据来源：[CommonMark 0.31.2 spec](https://spec.commonmark.org/0.31.2/)、[GitHub Changelog 2021-09-30 Footnotes](https://github.blog/changelog/2021-09-30-footnotes-now-supported-in-markdown-fields/)、[Markdeep features.md](https://casual-effects.com/markdeep/features.md.html)。

**策略**：若文档主要通过 Markdeep viewer 分享，放心用 `[#Key]`；若同份 md 还要直接丢进 GitHub issue / wiki 或在 VS Code 原生预览里看，要么改成 CommonMark shortcut link（`[key]` + `[key]: url "题注"`），要么就接受非 Markdeep 环境下会看到字面量。

## 研报长文模板（作者固化风格）

研报类长文的固定骨架（下述描述是用户自己的写作惯例、不是 Markdeep 本身要求；用户写研报时按此模板产出）：

**文件头 metadata 行（固定三项，用 `·` 分隔放一行）**

```
**最后更新日期**：YYYY-MM-DD　·　**作者**：<name>　·　**话题**：<主题简述>
```

接一行 `---`。

（可选）要启用 Markdeep 引用体系时，在 metadata 下另起一段 `**原则**：...` 声明来源分级口径（作者惯用 `【官方】=第一手（厂商一手文档 / 发布稿）`、`【第三方】=评测媒体 / 社区实测`、`【推算】=本文基于官方口径折算`）；如果有前置报告，再加一行 `**前置报告**：[标题](链接)`。

**章节骨架**

- 首节固定是「零、TL;DR」：每条结论一整句（粗体关键词前置、带数字）、**末尾必挂 `[#key]`**，不要只挂到正文详述里
- 子节 `### 1.1`、`### 1.2`；段间 `---` 分隔
- 表格头部粗体圈当前主角行；**最后一列统一叫"来源"**，填 `[#key]` 或 `[#a, #b]`

**行内惯例**

- 原文直引用 block quote：`> 原文：**"..."**[#key]`（或 `> <出处> 原话：**"..."**[#key]`）
- 小结类段落用粗体标签开头：`**推论**：...`、`**策略**：...`、`**兜底路径**：...`
- 来源分级标记穿插论断里：【官方】、【第三方】、【推算】

**说明型脚注的典型用途**

- 参数换算口径（比如"HF 模型卡 754B vs GitHub README 744B 的差异来源"）
- 基准差异（比如"SWE-bench Pro vs Verified 不能直接比"）
- 官方未公布的推算过程（"Opus 4.6 × 94.6% → 76.4%"）
- 名词展开（"MTP = Multi-Token Prediction"）

**结尾**

- `---`
- `**Bibliography**:`（冒号在粗体外） + `[#key]: 作者/机构, "标题", 年. URL` 条目，一条一行、条间空行
- 再一个 `---` + `**变更说明**`（或 `**v2 vs v1**`、`**v2 → v2.1 修订**`）平铺列增删改点

**"行动清单"收尾（如果是偏采购 / 项目决策类的研报）**

末尾通常还有一节 `## 七、下一步行动清单`：按「技术（我）/ 商务（负责人）/ 决策点」分组；决策点用条件 → 结论形式列，例如「长期生产 → A 方案」「预算控死 → B 方案」「POC → C 方案」。
