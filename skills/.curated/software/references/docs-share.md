# docs-share：Git 仓库 → S3 presigned 直链分享

私有 Git 仓库 → forgejo runner `rclone sync --checksum --remove` → RustFS S3 桶（桶结构 = 仓库树）。`public/*` 匿名可读，其他路径**默认**走 presigned URL。`.md` 浏览器直贴自动 markdeep 渲染。

> **本文件只讲安装/部署。**日常操作（分享、bundle 带图私有文档、html 下载按钮、撤销、写作惯例、排障速查）全在仓库 `README.md`：
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

## 部署后

仓库 `README.md` 是日常操作的**唯一**入口（分享 / bundle / 写作惯例 / 排障速查全在那），本文件不再重复。
