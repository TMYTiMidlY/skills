# 测速

## 带宽测试

```bash
iperf3 -c <目标IP> # 目标IP上需开启 iperf3 -s
```

## 延迟测试

```bash
sudo mtr -r -c 10 <目标IP> # 测试10次延迟
```
