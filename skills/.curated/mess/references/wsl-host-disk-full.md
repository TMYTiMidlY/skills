# 宿主机 C 盘满：WSL Git 空文件与 Zellij 登录异常

> 2026-10-09 | Windows 宿主 + WSL2 | Git | Zellij Web | Caddy

## 发生了什么

当时 Windows 宿主机的 C 盘满了，WSL 里的开发和 Web 终端接连出问题。

Git 已经把任务认领提交推到远端，本地却出现零字节的分支引用和对象文件，读不到正常的 HEAD。具体涉及 `doing/task-fa-jordan-full-range-227` 的本地引用、远端跟踪引用和一个新提交对象，HEAD reflog 尾部也出现了零字节内容。

同一时期 Zellij 的数据库出了问题。Caddy 中已经配置了 Zellij 的 session token，访问 Web 终端仍然失败。Zellij 的登录依赖应用侧 token 数据库；排查需要沿着宿主机空间、数据库状态和代理持有的会话值逐层看。

## 排查时的线索

任务认领提交的时间是 **08:39:21**，上一轮系统日志停在 **08:39:19**。到 **09:34** 再启动时，系统日志出现：

```text
EXT4-fs (sdd): recovery complete
system.journal corrupted or uncleanly shut down, renaming and replacing.
```

这些时间点与最近写入的 Git 文件损坏吻合。远端提交仍完整，后续可以从远端或健康的 clone 补回本地对象和引用。

事后复查磁盘时，WSL 的 `/` 显示约 **895 GB** 可用，而 Windows C 盘使用率仍有 **98%**，剩余约 **39 GB**。这很容易让只看 Linux 空间的排查绕远。

WSL2 的 Linux 文件系统保存在宿主卷上的 `ext4.vhdx` 中，Linux 看到的是虚拟磁盘容量；还要检查 Windows C 盘以及 VHDX 实际所在的卷。Microsoft 的 [WSL 磁盘空间说明](https://learn.microsoft.com/en-us/windows/wsl/disk-space#how-to-check-your-available-disk-space)解释了这两层容量的关系。

```bash
df -h / /mnt/c
```

## 恢复顺序

先在 Windows 侧腾出空间，确认宿主卷和 WSL 的写入恢复正常，再处理留下的文件损坏。

Git 这次有两条恢复路径：solver 用健康仓库建了独立 clone，继续远端已经认领的任务；随后另一个 agent 修复原仓库的空对象和引用，把本地状态 stash 保存后切回 main。修复后 HEAD 可以正常读取，任务分支也与已交付的远端版本一致。stash 是恢复后的保存步骤，时间为 **10:35:52**。

遇到同类 Git 故障时，先保存工作区和损坏文件，再核对远端完整 SHA，从健康来源补回对象、恢复引用。最后检查 HEAD、分支和本地改动，保留还需要继续工作的 stash。

Zellij 按同样的顺序恢复：先检查和备份 `tokens.db`，让数据库正常读写，再确认对应实例的 session token。需要更新会话时，通过该实例的登录流程取得新的 session token，更新 Caddy 使用的凭据，并按实际环境变量加载方式使其生效。最后检查 `/ws/control` 的认证和 WebSocket 升级，再打开 Web 终端。

具体操作沿用已有主题：

- [Zellij login token 与 session token](../../software/references/zellij.md#web-session-tokens)
- [Caddy 服务凭据与环境变量](../../network/references/caddy.md#service-environment)

## 留下的经验

宿主机磁盘满时，Git、应用数据库和日志可能同时出现异常。看到多个服务一起出问题，先查 Windows 宿主卷，再查 WSL 文件和应用状态。Caddy 的 session token 配置还要配合 Zellij 数据库中的有效会话记录；恢复存储后，把整条登录链路走通。
