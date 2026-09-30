# miwifi-root

取得小米路由器的 root 命令执行。

> **适用范围**
>
> 实测 **BE5000 / RD18 / 稳定版 1.0.91**
>
> 登录方式依赖于 MiWiFi Lua 框架行为，其他型号与固件版本**未经验证**。
> 在不适用的版本上，表现为命令拿不到输出或接口返回校验错误。

> **免责声明**
>
> 本工具仅用于对**你自己拥有**的设备进行研究。这会在设备上
> 以 root 执行任意命令、并可改写持久化配置，
> **使用即可能使设备处于不可预期的状态**，请自行评估并承担全部后果。
>
> 作者不提供任何形式的担保，也不对使用本工具造成的任何损害负责。
>
> 你在使用前即视为已确认对所操作设备拥有合法所有权。


## 前置条件

* 与路由器同局域网。
* 路由器的 Web 管理密码。

## 用法

```bash
export MIWIFI_HOST=192.168.1.1
export MIWIFI_PASS='你的Web管理密码'

./miwifi_root.py --verify                # 确认 uid 0
./miwifi_root.py --cmd 'cat /proc/mounts'
./miwifi_root.py --shell                 # 交互循环
```

> `--cmd` / `--shell`：结果由路由器主动发出一个 HTTP 请求回传到你机器的 `--port`（默认 8000）。路由器上不开放任何监听端口，也没有常驻服务。
>
> `--push`：方向相反，路由器 `GET /f/<文件名>` 从你机器下载文件后改名到位，并打印目标的 `ls -l`。权限按本地文件原样保留。
>
> `--verify` / `--cleanup`：不需要端口，纯时延或纯 API 调用。

## 持久 SSH

原厂镜像内无任何 SSHD 服务。本仓库 Actions 中提供预编译 dropbear 下载

> 预编译 dropbear 是按 `armv7 + soft-float + musl` 编译的，其他型号需先确认目标架构。

```bash
./miwifi_root.py --push bins/dropbear    /data/dropbear
./miwifi_root.py --push bins/dropbearkey /data/dropbearkey
./miwifi_root.py --cmd 'chmod +x /data/dropbear /data/dropbearkey;
  mkdir -p /data/etc/dropbear;
  [ -f /data/etc/dropbear/hk ] || /data/dropbearkey -t ed25519 -f /data/etc/dropbear/hk'
./miwifi_root.py --cmd 'grep -q "/data/dropbear" /etc/crontabs/root ||
  cp /etc/crontabs/root /data/crontab.root.bak;
  sed -i "/data/dropbear/d" /etc/crontabs/root;
  printf "\n* * * * * pidof dropbear || /data/dropbear -r /data/etc/dropbear/hk\n" >> /etc/crontabs/root'
./miwifi_root.py --cmd '/etc/init.d/cron restart; sleep 60; pidof dropbear'
```

root 密码计算

```bash
./miwifi_root.py --root-pass              # 从设备读 hardware.sn
./miwifi_root.py --root-pass '<SN>'       # 或直接给 SN
```

全部撤销：

```bash
./miwifi_root.py --cmd 'kill $(pidof dropbear) 2>/dev/null;
  test -f /data/crontab.root.bak && cp /data/crontab.root.bak /etc/crontabs/root;
  sed -i "/data/dropbear/d" /etc/crontabs/root; /etc/init.d/cron restart;
  rm -f /data/dropbear /data/dropbearkey /data/crontab.root.bak;
  rm -rf /data/etc/dropbear'
```


## 参数

| 参数 | 含义 |
|---|---|
| `--host` | 路由器 IP，也可用环境变量 `MIWIFI_HOST` |
| `--password` | Web 管理密码，也可用环境变量 `MIWIFI_PASS` |
| `--proxy` | 指定出口的 HTTP 代理，见下方排障 |
| `--port` | 本机的回传端口，默认 8000 |
| `--timeout` | 等待命令结果的秒数，默认 120 |
| `--verify` / `--cmd` / `--shell` | 验证执行 / 单条命令 / 交互循环 |
| `--push LOCAL REMOTE` | 把本地文件复制到设备上的指定路径 |
| `--root-pass [SN]` | 打印按序列号派生的 root 密码 |
| `--cleanup` | 清扫本工具遗留的规则 |

## 排障

**`--push` 超时，或 `--cmd` 一直不返回或拿不到任何输出。** 两者都要路由器能连到你机器的 `--port`。
检查防火墙是否放通该端口入站，以及实际使用的地址是不是路由器真能路由到的那个。

## 收尾

每个操作都会往路由器的 MAC 黑名单里临时加一条规则，用的是本地管理地址
`02:f0:..`，真实客户端不可能占用，所以规则是惰性的；操作结束后会自己删掉。
如果中途被打断，用这个清理：

```bash
./miwifi_root.py --cleanup
```

随时可以通过路由器自带的 `get_macfilter_info` 接口核对当前状态。

## 许可

MIT，见 `LICENSE`。CI 发布出去的 dropbear 与 musl 二进制属于第三方衍生作品，
适用各自的宽许可，见 `THIRD_PARTY_NOTICES.md`。本仓库不再分发任何小米固件。
