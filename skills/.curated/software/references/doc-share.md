# 自托管 Markdown 文件分享

**定位**：一套 **"capability URL 作凭据"的无额外认证私链分享**——读取方拿到一段长随机串 URL 就能访问，没有登录页、没有 OAuth；上传侧单独用 basic_auth 保护，和读取侧共享同一份存储目录。

本 reference 覆盖"服务端已经配好 WebDAV + Markdeep viewer"之后的客户端视角：怎么上传、怎么拿分享链接、怎么写给 viewer 看的 markdown。

## 前置条件

**服务端已配置**：在 `vps-maintenance` skill 里完成「无额外认证的文档分享私链（WebDAV + Markdeep viewer）」相关章节——**装好 caddy-webdav 扩展**并配置 Caddy site block（`/dav/*` basic_auth 上传端 + capability URL `/<token>/*` 读取端 + viewer 挂载 + 凭据生成）。没这一步就没得上传也没得分享。

**本地 `~/.env` 提供四项**（上传走 basic_auth；分享的 capability URL 本身不需要凭据，**但也放进 `.env`**——skill 上传后才能拼出成品链接、做 200 验证、直接贴回给用户）：

```bash
WEBDAV_URL=https://<host>/dav              # 写入入口，完整到 /dav 前缀
WEBDAV_USER=<user>                         # basic_auth 用户名
WEBDAV_PASS=<pass>                         # basic_auth 明文密码；rclone 固化 remote 时要 `rclone obscure` 处理
WEBDAV_SHARE_URL=https://<host>/<token>    # 公开读取入口（capability URL），不带尾斜杠；skill 上传后拼 `$WEBDAV_SHARE_URL/<file>` 就是成品分享链接
```

**direnv 环境（如本机 `~/TiMidlY-projects/.envrc`）**：四项可以直接 `export` 到 `.envrc` 里，cwd 进树就自动注入；下文的 `set -a; . ~/.env; set +a` 那行省掉即可。判定方法：`echo "$WEBDAV_SHARE_URL"` 非空即说明 direnv 已加载。注意 cwd 跑出 direnv 树（如 `cd /tmp` 后跑 skill）就没了——这种场景仍需手动 source 一份 `~/.env` 或临时 `eval "$(direnv export bash)"`。

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

---

把 Markdown 导出为 PDF（自打印 / 研报 / 论文等）见 [pdf-export.md](pdf-export.md)：Prince XML / Vivliostyle / Paged.js / WeasyPrint / Typst 选型对比、pixi 无 sudo 安装、CJK 字体大坑、引用标签预处理流水线。

---

## copyparty（带 UI + share API 的全功能替代）

**定位**：相比 caddy-webdav 这种"capability URL = 凭据"的极简方案，[copyparty](https://github.com/9001/copyparty) 是 Python 单文件 sfx zipapp，自带浏览器 UI、账号系统、`POST /?share` 动态生成分享链接的 API。需要"登录后创建临时分享链接"场景用它，纯私链分发仍用 caddy-webdav。

### 完整部署方案（按官方推荐）

骨架直接抄 [`contrib/systemd/copyparty.service`](https://github.com/9001/copyparty/blob/hovudstraum/contrib/systemd/copyparty.service) 和 [`contrib/systemd/copyparty.conf`](https://github.com/9001/copyparty/blob/hovudstraum/contrib/systemd/copyparty.conf)，其余按下文调整。

**Step 0 决策点**（一次性确认，避免来回返工）：

| 决策 | 推荐 | 备注 |
|---|---|---|
| 监听端口 | `3923` | 不改默认；走 Caddy 反代到 443 |
| 服务用户 | `copyparty:copyparty` | 跟官方 contrib 一致 |
| 数据卷根目录 | `/data/share`（或 `/srv/copyparty/`） | 大盘挂载点；user 必须有 rw |
| 域名 | `<sub>.<your>.tld` | 走 DNS + Let's Encrypt（Caddy 自动） |
| 密码哈希 | `argon2`（tier 2） | 比明文/bcrypt 优；要装 `python3-argon2` |
| share API | 启用 (`shr: /share`) | 这是 copyparty 选它的核心理由 |
| TLS | 反代终端在 Caddy | copyparty 自己不挂 LE；避免 cfssl 自签警告 |

**Step 1 系统用户 + 数据目录**（需 sudo）：

```bash
useradd -r -s /sbin/nologin -m -d /var/lib/copyparty copyparty
install -d -o copyparty -g copyparty -m 750 /data/share
```

`-r` = system account，`-m -d /var/lib/copyparty` = 创建 home（用作 XDG_CONFIG_HOME 存 salt / sqlite）。

**Step 2 装运行时依赖**：

```bash
apt install python3 python3-argon2          # argon2-cffi 后端，ah-alg: argon2 必装
# 可选: ffmpeg pillow-heif  # 缩略图；不装不影响 share API
```

**用系统 Python 即可**（`/usr/bin/python3`，3.10+）。**不要用 uv 隔离 Python** —— `python3-argon2` 是 apt 包，装在系统 site-packages，uv venv 看不到。如果一定要 uv，改用 `uv pip install argon2-cffi` 装到 uv env 里，然后 ExecStart 指向 uv 的 python。

**Step 3 下载 sfx zipapp**：

```bash
curl -fsSL -o /usr/local/bin/copyparty-sfx.py \
  https://github.com/9001/copyparty/releases/latest/download/copyparty-sfx.py
chmod 755 /usr/local/bin/copyparty-sfx.py
```

升级就是覆盖这个文件 + `systemctl restart copyparty`。conf / salt / 数据全不动。

**Step 4 装 systemd unit**：

抄官方 contrib 那份 `copyparty.service` 整段到 `/etc/systemd/system/copyparty.service`。**两处可选改动**：

```ini
[Unit]
Description=copyparty file server
After=network-online.target      # 加这两行（官方没有，确保启动晚于网络）
Wants=network-online.target

[Service]
TimeoutStartSec=180              # 加：首次启 daemon 会创建 sqlite + salt，慢机器要时间
Restart=on-failure               # 加：临时网络抖动后自恢复
RestartSec=5

# 其余 (Type=notify / User=copyparty / XDG_CONFIG_HOME / 硬化项 / ExecStart) 保持官方原样
```

**不要** uncomment `AmbientCapabilities=CAP_NET_BIND_SERVICE`——只有 copyparty 直接监听 80/443 时才需要，反代场景不需要。

完成后：

```bash
systemctl daemon-reload
systemctl enable copyparty       # 先不 start，下一步写完 conf 再启
```

**Step 5 写最小 conf** 到 `/etc/copyparty.conf`（**官方 `contrib/copyparty.conf` 默认有 `r: *` 允许 anon read，那是 demo 不是生产**，替换成下面）：

```ini
[global]
  i: 127.0.0.1                  # 只听本地；Caddy 反代过来
  shr: /share                   # share API 挂在 url /share
  shr-adm: <user>               # 谁能 POST /?share 创建分享
  no-robots                     # 加 X-Robots-Tag: noindex
  ah-alg: argon2                # 启用 argon2 哈希；不写就当明文存

[accounts]
  <user>: PLAINTEXT_FILLED_LATER  # Step 6 让 daemon 自己哈希；先写明文

[/]                             # url 挂载点 /
  /data/share                   # 对应 fs 路径
  accs:
    A: <user>                   # A = rwmda. 全权限简写
```

`chmod 0640 /etc/copyparty.conf && chown root:copyparty /etc/copyparty.conf`（含密码，限读）。

**Step 6 哈希密码**（详见下文「官方推荐的密码哈希流程」节）：跑一次 daemon 让它把明文换成 `+<argon2-hash>`。

**Step 7 Caddy 反代**：

```caddy
<sub>.<your>.tld {
    reverse_proxy 127.0.0.1:3923
    import error_pages           # 可选
}
```

不需要 `header_up`、`encode`、特殊 cookie 处理——copyparty 自己处理 `X-Forwarded-For`、cookie path、HEAD/Range，按 default Caddyfile semantics 就够了。reload Caddy 之前先 `caddy validate`（见 `vps-maintenance` skill 的 caddy reference）。

**Step 8 启动 + 验证**：

```bash
systemctl start copyparty
systemctl is-active copyparty                                     # 期望: active
journalctl -u copyparty -n 30 --no-pager                          # 看 "listening @ 127.0.0.1:3923" 和 sd_notify
curl -sI https://<sub>.<your>.tld/?ls -o /dev/null -w "%{http_code}\n"  # 期望: 200
```

权限边界自检（anon 应该被拒）见下文「权限边界自检」表。完工后该输出一份部署报告（备份位置、回滚命令、凭据指针）给用户。

### 官方推荐的密码哈希流程（tier 2 argon2）

不要手动算 hash，**让 daemon 自己印**（避免 salt 协调）。`--ah-salt` 默认 24 字符自动生成存在 `$XDG_CONFIG_HOME/copyparty/`，daemon 和任何 `--ah-cli` 必须共享同一份 salt。

步骤：
1. 确认 `python3-argon2` 已装 —— `python3 -c "from argon2.low_level import Type"` 不报错
2. conf 里 `[accounts]` 段写明文密码（无 `+` 前缀），全局 declarer `ah-alg: argon2`
3. `systemctl start copyparty` → daemon 读 conf 发现明文 → 用 salt 哈希 → 印 `<user>: +<hash>` 到 journal → 退出
4. 等 5-10 秒，`systemctl stop copyparty` 截断 restart loop（daemon 退出会被 `Restart=on-failure` 拉起再哈希再退一遍，循环至你 stop）
5. 抓 hash：
   ```bash
   journalctl -u copyparty --since "5 min ago" | grep -oE "<user>:[[:space:]]*\+[A-Za-z0-9._\$+/=,-]+" | head -1
   ```
6. **替换 conf 里那行**——用 `awk`/portal_patch/编辑器手改，**绝不能 `diff <old> <new>` 打印**（明文会进 log，详见坑 #5）
7. `systemctl restart copyparty` → `is-active` 应为 `active` 且持续 ≥30 秒不退（不再因明文触发 hash-cycle）

### 权限边界自检（设计行为，别误判）

| 探测 | 期望 | 说明 |
|---|---|---|
| anon `GET /?ls` | **200** `acct:"*", perms:[], dirs/files 0/0` | 不是漏，是设计——拿空列表 |
| anon `GET /<known-file>` | 403 | 真实拒绝 |
| anon `PUT /x` | 401 | |
| anon `POST /?delete` / `?move` | 401/403 | |
| anon `POST /?share` | **500** `<pre>'k'` | copyparty 内部 `KeyError`，**没创建 share**，等价于 deny |
| anon `GET /?shares` | 200 `"you're not logged in"` | 不漏其他用户的 share |

测 authd 一侧（不要把密码写进 URL `?pw=` 进 access log，用 header）：

```bash
read -s -p "pw: " PW; echo
F="ctest-$(date +%s).txt"; echo test > /tmp/$F
curl -sS -H "pw: $PW" -T /tmp/$F http://127.0.0.1:3923/$F          # 期望: 201/200
curl -sS -H "pw: $PW" -X POST http://127.0.0.1:3923/$F?delete      # 期望: 200
curl -sS -H "pw: $PW" -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3923/$F  # 期望: 404
trash-put /tmp/$F; unset PW
```

### 踩过的坑

**1. `python3-argon2` 没装 → systemd 无限 restart loop**

- **现象**：`systemctl status copyparty` 显示 `activating (auto-restart)` 永不 `active`；`https://...` 502；`journalctl -u copyparty` 每 5s 重复打印 ImportError 块
- **根因**：conf 写了 `ah-alg: argon2`，daemon 启动加载 conf 时 `import argon2` 触发 `ModuleNotFoundError: No module named 'argon2'`，进程立即非 0 退出。`Restart=on-failure` 5s 后再起 → 再 import 失败 → 再退，systemd 上层只看到"反复 activating"，看不出依赖问题
- **排查**：`journalctl -u copyparty --no-pager -n 200 | grep -i "ModuleNotFoundError\|import"` 一抓一个准
- **解决**：`systemctl stop copyparty` 截断循环 → `apt install python3-argon2` → `systemctl start copyparty` → 验证 `is-active` 持续 ≥30s
- **避免**：Step 2 把 `python3-argon2` 跟 `python3` 一起装；不要等到 Step 6 才发现

**2. `systemd Type=notify` 在 uv 隔离 Python 下也能用，不需要 `python3-systemd` C 扩展**

- **背景**：很多 Python 项目用 `Type=notify` 必须装 `apt install python3-systemd`（libsystemd 的 C binding），而 uv venv / pyenv 之类隔离 Python 装不上系统 C 扩展，常被迫降级 `Type=simple`
- **现象**：以为要降级 `Type=simple`（systemd 立即认 ready，看不到真就绪信号；启 fail 不能正确 propagate）
- **真相**：copyparty 在 `src/copyparty/sd_notify.py` 自己实现了 sd_notify 协议——直接打开 `$NOTIFY_SOCKET`（AF_UNIX）发字节流 `READY=1`，**完全绕开 libsystemd**。任何能开 UnixSocket 的 Python 都行，uv / pyenv / sfx zipapp 全部兼容
- **结论**：放心用 `Type=notify`；journalctl 里看到 `sd_notify LOG: /run/systemd/notify` 就是成功握手

**3. `/etc/copyparty.conf` 不是 copyparty 自动读的路径**

- **现象**：把 conf 丢到 `/etc/copyparty.conf` 后直接 `copyparty-sfx.py` 跑，发现根本没读
- **根因**：copyparty 源代码里**没有默认 conf 搜索路径**（不像 nginx 找 `/etc/nginx/nginx.conf`）。`/etc/copyparty.conf` 是**约定**——官方 `contrib/systemd/copyparty.service` 的 `ExecStart` 行明写 `-c /etc/copyparty.conf` 才让它生效
- **避免**：检查 `ExecStart` 是否含 `-c <path>`；自己手跑也要 `copyparty-sfx.py -c /etc/copyparty.conf`

**4. conf 100% 手写，copyparty 永不回写**

- **现象**：以为类似 nginx，删几行 daemon 会"补默认值回去"
- **真相**：daemon 只读，**从不**写 conf。少写一行 = 走 default（如 `p: 3923`、`hist:` 默认 `<vol>/.hist/`、`xff-src:` 默认含 `127.0.0.0/8`），不会"自动补全"出现在文件里。所有 runtime state（salt / `up2k.db` / `shr.db` / 缩略图）放在 `$XDG_CONFIG_HOME/copyparty/` 和 `<vol>/.hist/`，跟 conf 完全分离
- **结论**：conf 想"恢复 default" → 把那行**删掉**，不要写"等号默认值"

**5. 改 conf 严禁用 `diff` 打印——会把明文密码进 log**

- **现象**：自动化脚本里写 `diff <(echo "$OLD_LINE") <(echo "$NEW_LINE")` 或 `echo "REPLACE: $OLD → $NEW"` 展示改动，结果脚本的 stdout 进 systemd journal / 文件 log，明文密码永久留痕
- **根因**：Step 6 那次"写明文 → 让 daemon 哈希 → 替换回 hash"的窗口里，conf 文件本身含明文。任何打印 `diff` / 旧值的命令都把它复制到第二处
- **正确做法**：
  - 用 `awk -v u="$USER" -v h="$HASH" '/^  *"$USER":/ {print "  " u ": " h; next} {print}' conf > conf.new && mv conf.new conf`
  - 或 portal_patch（带 hash 校验，不打印 old line）
  - 或本机编辑器原地改
- **如果泄露已发生**：`shred -uvz <log-file> <bak-file>`（不可 trash，trash 文件还在盘上可恢复）；不需要改密码，因为 hash 已生效，明文只是临时痕迹

**6. `[/]` 段下的 `accs:` 权限简写**

- **现象**：不知道 `A` `G` `g` 到底啥意思，README 又分散在多节
- **完整定义**（`copyparty-sfx.py --help-accounts`）：
  - `r` = read（下载 + 列目录）
  - `w` = write（上传 + 创建目录）
  - `m` = move（重命名）
  - `d` = delete
  - `g` = get（下载，**不能**列目录）—— 用于 capability URL 场景
  - `G` = upget（上传 + get，不能列）
  - `h` = html（允许在 dir listing 注入 HTML）
  - `.` = dots（看见 dotfile）
  - `a` = admin（看 server stats）
  - **`A` = `rwmda.` 全权限简写**（不含 `g`/`G`/`h`，那些是"反向"权限）
- 用法：`A: alice` 给 alice 全权；`r: *` 给 anon 只读；`g: bob` 给 bob 链接下载但不能浏览目录

**7. "hash 完即退" 触发 `Restart=on-failure` → 看似无限警告**

- **现象**：Step 6 启 daemon 后，journal 里"`hashed password for account <user>: +<hash>`"和"`please use the following hashed passwords`"每 5 秒重复一次
- **根因**：daemon 设计是"看到明文 → 哈希 → 印 → 退出（非 0）让用户去更新 conf"。systemd `Restart=on-failure` 看 exit code 非 0 就拉起，新进程读到**还是明文**的 conf，再哈希再印再退，无限循环。每次 hash 都不一样吗？**不会**，因为 salt 固定，hash 相同
- **避免**：捕获第一个 hash 后立刻 `systemctl stop copyparty`（截断 loop），再改 conf，再 `systemctl restart`

**8. anon `GET /?ls` 返回 200 + 空 body，不是权限漏洞**

- **现象**：写了 `[/] accs: A: <user>`，预期 anon 任何请求都该 401/403，结果 `curl http://127.0.0.1:3923/?ls` 返回 200
- **真相**：copyparty 设计上 anon 能 hit `/?ls`，但返回的 JSON 是 `{"acct":"*","perms":[],"dirs":[],"files":[],...}`——**有响应但 perms 空、列表空**。这是 SPA 加载页面拿 unauth 元数据的需要。**真正的资源**（`GET /<file>`、`PUT`、`POST /?delete`）才会 401/403
- **判定方法**：测 anon GET 一个具体已知文件（应 403）和 anon PUT（应 401），不要只看 `/?ls`

**9. anon `POST /?share` → HTTP 500 而不是 401**

- **现象**：以为 share API 漏权限
- **真相**：copyparty 内部错误模板 `KeyError: 'k'`——anon 没 session token，模板 lookup 时缺 key，抛 500。**但代码路径在权限检查之前就崩了，根本走不到"创建 share"**。功能上等价于 deny，没安全问题，只是不够漂亮。upstream bug，认证后带正确 body 调用正常。

**10. Caddy 反代不需特殊 header；`xff-src:` 别瞎覆盖**

- **现象**：见过有人在 conf 加 `xff-src: 127.0.0.1`（觉得"反代来自本地"），结果 daemon 反而拿不到真实客户端 IP
- **根因**：`xff-src:` 是**信任 X-Forwarded-For 的源 IP 列表**，默认已经包含 `127.0.0.0/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16`，写 `xff-src: 127.0.0.1` 反而**缩小**了范围，把内网反代都排除了
- **结论**：单点反代直接不配 `xff-src:`；多层反代或非典型内网段才需要覆盖默认值
