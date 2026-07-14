# Dokploy

[Dokploy](https://dokploy.com) 是开源自托管 PaaS。与 Coolify 的选型、端口所有权、控制面/工作负载边界及清理原则先见 [coolify-dokploy.md](coolify-dokploy.md)；本文只记录 Dokploy 专有架构，以及多服务宿主上可能出现的非标准运行态。

运行镜像与仓库证据对齐 **v0.29.8**（tag commit `1f4f9404`）。源码链接均锁定该 tag。安装行为来自 2026-07-05 抓取的滚动来源 [`https://dokploy.com/install.sh`](https://dokploy.com/install.sh)：它不随仓库 tag 固定，也未找到与 v0.29.8 对应的不可变归档，因此升级或复核时必须重新抓取比较，不能把下面的脚本片段冒充为版本锁定证据。

## Swarm 编排与安装前置

2026-07-05 抓取的官方滚动安装脚本在 `install_dokploy()` 开头检查 80、443、3000；任何一个端口已被监听都会直接 `exit 1`，不是警告后继续：

```bash
if ss -tulnp | grep ':80 ' >/dev/null; then
    echo "Error: something is already running on port 80" >&2
    exit 1
fi
if ss -tulnp | grep ':443 ' >/dev/null; then
    echo "Error: something is already running on port 443" >&2
    exit 1
fi
if ss -tulnp | grep ':3000 ' >/dev/null; then
    echo "Error: something is already running on port 3000" >&2
    echo "Dokploy requires port 3000 to be available. Please stop any service using this port." >&2
    exit 1
fi
```

该脚本随后会退出可能存在的旧 Swarm，执行 `docker swarm init --advertise-addr <检测到的私网IP>`，再创建 `--driver overlay --attachable` 的 `dokploy-network`。这意味着在已有 Swarm 工作负载的宿主上直接运行脚本，安装前置动作本身就可能影响其他系统。

仓库 v0.29.8 的目标服务器设置逻辑也直接执行 [`docker swarm init`](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/server-setup.ts#L433-L441)，随后创建 [`attachable` overlay 网络](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/server-setup.ts#L442-L449)。因此 Swarm 不是一次实测中的偶然选择；即使只有一个节点，Dokploy 仍以 Swarm manager 为编排基础。

## 控制面与入口代理

2026-07-05 抓取的滚动安装脚本把 Dokploy 本体创建为 Swarm service，并用 `--publish published=3000,target=3000,mode=host` 发布控制面。`mode=host` 绕开 Swarm routing mesh，直接在运行 task 的节点监听 3000。诊断时不要只看 `docker service ls` 的 `PORTS` 列，应检查 service 规格：

```bash
docker service inspect dokploy --format '{{json .Spec.EndpointSpec}}'
```

官方默认入口还包括独立的 `dokploy-traefik`。v0.29.8 源码中的 [`initializeStandaloneTraefik()`](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/traefik-setup.ts#L27-L91) 把它作为普通容器创建，绑定 80/443 并接入 `dokploy-network`；同文件也保留了 [Swarm service 形式](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/traefik-setup.ts#L93-L166)。端口常量 [`TRAEFIK_PORT`、`TRAEFIK_SSL_PORT`](https://github.com/Dokploy/dokploy/blob/v0.29.8/packages/server/src/setup/traefik-setup.ts#L14-L21) 默认分别为 80、443，可由同名环境变量覆盖。

官方完整入口因此包含两部分：

- 3000：Dokploy 控制面自身的 host-mode 发布。
- 80/443：`dokploy-traefik` 接收平台面板域名和已部署应用域名，再转发到 overlay 网络内的目标。

## 非标准运行态的识别

一次实测环境中，80/443/3000 已由其他服务占用，最终运行态出现了两个关键偏差：

1. `docker service inspect dokploy --format '{{json .Spec.EndpointSpec}}'` 只有 `{"Mode":"vip"}`，没有任何 `Ports` 配置；本体的官方 host-mode 3000 发布被摘掉。
2. `dokploy-traefik` 容器不存在，因此平台部署出的应用没有官方 80/443 入口。

这不是滚动安装脚本按默认路径能够自然产生的状态，而是端口冲突后的人为改造。没有操作历史时，不臆测修改者和具体步骤；只依据 service 规格、容器清单、overlay 网络连接和实际监听状态判断。

控制面可访问也不能证明发布链路完整。该实例的 `/etc/dokploy/applications/` 为空，说明只形成了面板运行态，没有形成可验证的应用发布链路；这个观察只描述当次实测，不能推广为 Dokploy 默认行为。

## socat 桥接

该环境通过一个独立 `alpine/socat` 容器把非标准宿主端口桥接到 overlay 网络里的 `dokploy:3000`：

```text
TCP4-LISTEN:<非标准宿主端口>,fork,reuseaddr TCP:dokploy:3000
```

`dokploy` 是 overlay 网络里的 DNS 服务名，解析到 Swarm VIP。Dokploy v0.29.8 仓库与 2026-07-05 抓取的安装脚本中都没有 socat 方案；这是为绕过端口冲突手工添加的 workaround，不是官方推荐路径。

它的能力边界很明确：

- dashboard 可以经非标准端口打开；
- TLS 可以由更上游的反向代理终结；
- 已部署应用的入口不会因此恢复，应用域名仍依赖平台入口代理的路由和 80/443；
- 独立 socat 容器不是 Swarm service，删除 Dokploy services 不会自动带走它。

## 多服务宿主的部署选择

如果 80/443/3000 已被占用，有三种现实选择：

1. **给 Dokploy 独占宿主**：最贴近官方安装假设，端口和 Swarm 生命周期最清晰。
2. **重新规划端口所有权后完整安装**：保留控制面的 host-mode 发布和平台入口代理，再把 TLS 或公网入口交给上游反代；同时验证升级后自定义端口仍保留。
3. **只做临时 dashboard 桥接**：可用于调查已有数据，但应明确标记为不完整实例，不把它当成能部署对外应用的生产方案。

单纯删掉 publish、跳过 `dokploy-traefik`、再加 socat，只解决 dashboard 可达性；它没有替代 Dokploy 的应用入口控制面。

## <a id="product-cleanup"></a>产品专有清理

通用清理边界见 [coolify-dokploy.md](coolify-dokploy.md)。Dokploy 还需额外确认：

- 独立 `dokploy-traefik`、socat 或其他端口桥接容器不是 Swarm service，`docker service rm` 不会自动删除它们。
- 删除 service 后，task containers 可能短暂显示为 `Exited`，随后才由 Swarm 自动回收；等待收敛后再判断是否存在真正残留。
- overlay 网络、产品卷、配置目录和镜像属于不同资源层，需要分别核对；删除 service 或配置目录都不是完整卸载。
- `/etc/dokploy/applications/` 为空只能说明当次实例没有形成应用发布链路，不能省略对 service、卷、网络、镜像和独立容器的核查。
- 退出 Swarm 前先检查全部 service、node 和 overlay network。只有确认没有其他 Swarm 工作负载时，才执行 `docker swarm leave --force`。
