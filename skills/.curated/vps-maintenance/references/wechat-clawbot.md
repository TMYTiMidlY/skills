# OpeniLink Hub（微信 ClawBot）自托管部署

> [OpeniLink Hub](https://github.com/openilink/openilink-hub)（开源 MIT）是微信 **ClawBot / iLink 协议** 的自托管消息平台：单一 `oih` 二进制（或官方 docker 镜像）+ 默认 SQLite，监听 `:9800`。本文只覆盖**部署 / 反代 / env**；收发消息、Bot/管理 API、scope 的**使用**见 `wechat-clawbot` skill。

## 最小起步（单机、SQLite、零配置）

```bash
# 二进制（Linux / macOS）
curl -fsSL https://raw.githubusercontent.com/openilink/openilink-hub/main/install.sh | sh
oih                      # 前台跑；oih install 装成 systemd/launchd 服务常驻

# 或 docker（Windows 也走这条 / 或 WSL2）
docker run -d -p 9800:9800 -v oih-data:/var/lib/openilink-hub openilink/openilink-hub:latest
```

打开 `http://<host>:9800` 注册账号——**第一个注册的自动是管理员**，扫码绑微信号即用。数据默认落 SQLite：

| 运行身份 | SQLite 路径 |
|---|---|
| 普通用户 | `~/.local/share/openilink-hub/openilink.db`（macOS 在 `~/Library/Application Support/...`） |
| root / 系统服务 | `/var/lib/openilink-hub/openilink.db` |

要换 PostgreSQL：设 `DATABASE_URL=postgres://user:pass@host:5432/db?sslmode=disable`。媒体（图片/语音/文件）默认本地，接 S3/MinIO 走 `STORAGE_*`。

## 关键 env（决定能不能登录、媒体可不可达）

| env | 作用 | 注意 |
|---|---|---|
| `DATABASE_URL` | 不设 = SQLite；设了走 PostgreSQL | — |
| `LISTEN` | 监听地址/端口（默认 `:9800`） | 反代统一连这个 |
| `RP_ORIGIN` / `RP_ID` / `RP_NAME` | **Passkey (WebAuthn) 的 origin / RP ID** | **必须 = 对外访问的 origin**，否则注册/登录 Passkey 直接失败（见下「反代」） |
| `SECRET` | 会话/签名密钥 | 生产填随机串（`openssl rand -hex 32`） |
| `STORAGE_ENDPOINT` / `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` / `STORAGE_BUCKET` / `STORAGE_PUBLIC_URL` | 媒体走 S3/MinIO | `STORAGE_PUBLIC_URL` 是客户端能拉到媒体的公网地址 |
| `GITHUB_CLIENT_ID` / `_SECRET`、`LINUXDO_CLIENT_ID` / `_SECRET` | 第三方 OAuth 登录（可选） | — |

## 生产 docker-compose（PostgreSQL + MinIO + Hub）

```yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: openilink
      POSTGRES_PASSWORD: <强密码>
      POSTGRES_DB: openilink
    volumes: [ "pgdata:/var/lib/postgresql/data" ]

  hub:
    image: openilink/openilink-hub:latest   # 或 ghcr.io/openilink/openilink-hub:latest
    ports: [ "9800:9800" ]
    environment:
      DATABASE_URL: postgres://openilink:<强密码>@postgres:5432/openilink?sslmode=disable
      RP_ORIGIN: https://<hub.example.com>
      RP_ID: <hub.example.com>
      SECRET: <随机串>
    depends_on: [ postgres ]

volumes:
  pgdata:
```

需要媒体走对象存储时按 compose 注释补一组 MinIO + `STORAGE_*`。

## 反代（Caddy）+ 那个必踩的 Passkey 坑

Hub 自己不做 TLS，前面挂 Caddy 反代到 `:9800`。Caddy 安装 / 域名 vs IP 模式 / `tls internal` 见 [caddy.md](caddy.md)。

```caddyfile
# 域名 VPS（真证书）
<hub.example.com> {
    reverse_proxy 127.0.0.1:9800
}
```

```caddyfile
# 未备案 IP VPS（自签）——见 icp-filing.md，client 要 -k
https://<IP>:9800 {
    tls internal
    reverse_proxy 127.0.0.1:9800
}
```

**核心坑：`RP_ORIGIN` / `RP_ID` 必须和浏览器实际访问的 origin 完全一致**。Passkey/WebAuthn 把凭据**绑死在 origin** 上：

- 域名访问 → `RP_ORIGIN=https://<hub.example.com>`、`RP_ID=<hub.example.com>`。
- 纯 IP 访问（未备案 VPS）→ `RP_ORIGIN=https://<IP>:<port>`、`RP_ID=<IP>`。
- 不一致就表现为"注册 Passkey 失败 / 登录通不过"——查这里，别去翻反代日志。

媒体跨域：用 `STORAGE_PUBLIC_URL` 指向能公网拉到媒体的地址（同样经反代或独立 S3 域名）。

## CLI

| 命令 | 说明 |
|---|---|
| `oih` | 前台运行 |
| `oih install` / `oih uninstall` | 装 / 卸系统服务（systemd / launchd） |
| `oih version` | 版本 |

> Windows 原生不支持，用 docker 或 WSL2（官方 README 明确）。完整部署文档以 [openilink-hub README](https://github.com/openilink/openilink-hub#部署指南) 为准。
