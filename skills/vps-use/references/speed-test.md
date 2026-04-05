# 测速

## 带宽测试 (iperf3)

目标机器上先启动服务端：

```bash
iperf3 -s
```

客户端测试：

```bash
iperf3 -c <目标IP>       # 测试上传
iperf3 -c <目标IP> -R    # 测试下载
iperf3 -c <目标IP> -P 4  # 并行流
```

## 延迟测试

```bash
sudo mtr -r -c 10 <目标IP> # 测试 10 次延迟
```
