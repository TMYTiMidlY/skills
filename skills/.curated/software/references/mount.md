# 挂载与文件共享

## WSL 中 UNC/SMB 共享性能差

现象：WSL 中把 Windows/UNC 共享挂到 `/mnt/...` 后，读写大文件尚可，但创建、遍历、删除海量小文件极慢，`rm -rf`、`du`、`find` 长时间无输出。

先确认挂载类型：

```bash
findmnt -T /mnt/team -o TARGET,SOURCE,FSTYPE,OPTIONS
df -Th /mnt/team
stat -f -c 'type=%T block_size=%s' /mnt/team
```

如果看到 `FSTYPE=9p`、`aname=drvfs;path=UNC\...` 或 `path=T:`，这是 WSL 的 `drvfs/9p` 路径。它对小文件元数据操作通常很慢。把 `\\server\share` 先映射成 Windows 盘符再挂为 `T:` 可能略有改善，但底层仍是 `9p`，不会有质变。

更好的方案是在 WSL 内直接用 Linux CIFS 挂 SMB：

```bash
sudo apt-get update
sudo apt-get install -y cifs-utils smbclient
sudo mkdir -p /etc/samba/credentials
sudo chmod 700 /etc/samba/credentials
```

凭据文件示例，注意不要把真实密码写进聊天、日志或 repo：

```ini
username=tmy
password=...
domain=Quantum
```

权限：

```bash
sudo chmod 600 /etc/samba/credentials/quantum-team
```

先用 `smbclient` 验证认证和 share 名：

```bash
sudo smbclient -L //10.100.158.17 -A /etc/samba/credentials/quantum-team -m SMB3
```

能列出目标 share 后，再用 `mount.cifs`，不要只依赖裸 `mount -t cifs`：

```bash
sudo mkdir -p /mnt/team
sudo mount.cifs //10.100.158.17/Team /mnt/team \
  -o credentials=/etc/samba/credentials/quantum-team,uid=1000,gid=1000,iocharset=utf8,vers=3.1.1,noperm,sec=ntlmssp,domain=Quantum
```

持久化 `/etc/fstab` 示例：

```fstab
//10.100.158.17/Team /mnt/team cifs credentials=/etc/samba/credentials/quantum-team,uid=1000,gid=1000,iocharset=utf8,vers=3.1.1,noperm,sec=ntlmssp,domain=Quantum,noauto,x-systemd.automount 0 0
```

`noauto,x-systemd.automount` 可以避免开机时网络或凭据暂不可用导致启动卡住；访问 `/mnt/team` 时再自动挂载。

## 排障经验

- `No route to host` 或 `Unable to determine destination address`：WSL/Linux 侧解析不到 Windows 可访问的 NetBIOS/局域网名字。用 Windows 侧 `ping -4 server` 或 `Resolve-DnsName server` 拿 IP，然后在 Linux CIFS 中使用 IP。
- `Host is down`：IP 或路由不是 SMB 服务实际可用路径，或 445 端口不可达。可用 `timeout 3 bash -lc '</dev/tcp/IP/445'` 粗测端口。
- `SessSetup = -13`：SMB 认证阶段被拒。检查用户名、密码、`domain=`、`sec=`、SMB 版本；也可以用 `smbclient -L` 验证凭据。
- `smbclient` 能列出 share，但 `mount -t cifs` 失败：安装 `cifs-utils` 后使用 `mount.cifs` 再试；`mount.cifs` 会走更完整的 helper 逻辑。
- Windows 已经能访问 `\\server\share` 不等于 Linux CIFS 一定能复用 Windows 会话；Linux CIFS 需要自己的凭据文件。
- 切换正式挂载前先查占用者：`sudo fuser -vm /mnt/team`。如有残留 `rm`、`cp`、`du`、`find`，先停掉再 `umount`。

## 性能验证

小文件基准可以用固定数量文件做相对比较：

```bash
base=/mnt/team/QuantumAtlas
d="$base/.mount-bench-$$"
mkdir -p "$d"
start=$(date +%s%N)
i=1; while [ $i -le 200 ]; do touch "$d/f$i"; i=$((i+1)); done
mid=$(date +%s%N)
rm -rf "$d"
end=$(date +%s%N)
echo "create_ms=$(( (mid-start)/1000000 )) delete_ms=$(( (end-mid)/1000000 ))"
```

一次实际案例：同一 SMB share 在 WSL `drvfs/9p` 下创建 200 个空文件约 1912ms、删除约 624ms；改成 CIFS 后创建约 613ms、删除约 364ms。
