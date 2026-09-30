# miwifi-root

Root command execution on Xiaomi routers.

> **Scope**
>
> Tested on **BE5000 / RD18 / stable 1.0.91**.
>
> Login relies on behaviour of the MiWiFi Lua framework; other models and firmware
> versions are **unverified**. Where it does not apply, you get no command output or
> a validation error.

> **Disclaimer**
>
> For use only on devices **you own**. This runs arbitrary commands as root and can
> rewrite persistent configuration, so **using it may leave the device in an
> unexpected state** -- assess that yourself and accept full responsibility.
>
> The author gives no warranty of any kind and takes no liability for any damage.
>
> By using it you confirm lawful ownership of the device.


## Requirements

* A machine on the same LAN as the router.
* The router's web admin password.

## Usage

```bash
export MIWIFI_HOST=192.168.1.1
export MIWIFI_PASS='your web admin password'

./miwifi_root.py --verify                # confirm uid 0
./miwifi_root.py --cmd 'cat /proc/mounts'
./miwifi_root.py --shell                 # interactive loop
```

> `--cmd` / `--shell`: the result comes back as one outbound HTTP request from the
> router to your `--port` (default 8000). No listening port on the router, no
> resident service.
>
> `--push`: the other way round -- the router `GET /f/<filename>` from your machine,
> renames it into place, then prints the target's `ls -l`. File mode preserved as-is.
>
> `--verify` / `--cleanup`: no port needed; pure timing or plain API calls.

## Persistent SSH

The stock image has no SSHD at all. Prebuilt dropbear is published by this repo's
Actions.

> The prebuilt dropbear is `armv7 + soft-float + musl`; confirm the target
> architecture on other models.

```bash
./miwifi_root.py --push dropbear    /data/dropbear
./miwifi_root.py --push dropbearkey /data/dropbearkey
./miwifi_root.py --cmd 'chmod +x /data/dropbear /data/dropbearkey;
  mkdir -p /data/etc/dropbear;
  [ -f /data/etc/dropbear/hk ] || /data/dropbearkey -t ed25519 -f /data/etc/dropbear/hk'
./miwifi_root.py --cmd 'grep -q "/data/dropbear" /etc/crontabs/root ||
  cp /etc/crontabs/root /data/crontab.root.bak;
  sed -i "/data/dropbear/d" /etc/crontabs/root;
  printf "\n* * * * * pidof dropbear || /data/dropbear -r /data/etc/dropbear/hk\n" >> /etc/crontabs/root'
./miwifi_root.py --cmd '/etc/init.d/cron restart; sleep 60; pidof dropbear'
```

The root password:

```bash
./miwifi_root.py --root-pass              # reads hardware.sn from the device
./miwifi_root.py --root-pass '<SN>'       # or pass the SN directly
```

To undo all of it:

```bash
./miwifi_root.py --cmd 'kill $(pidof dropbear) 2>/dev/null;
  test -f /data/crontab.root.bak && cp /data/crontab.root.bak /etc/crontabs/root;
  sed -i "/data/dropbear/d" /etc/crontabs/root; /etc/init.d/cron restart;
  rm -f /data/dropbear /data/dropbearkey /data/crontab.root.bak;
  rm -rf /data/etc/dropbear'
```

## Options

| flag | meaning |
|---|---|
| `--host` | router IP, or `MIWIFI_HOST` |
| `--password` | web admin password, or `MIWIFI_PASS` |
| `--proxy` | HTTP proxy to egress through, see Troubleshooting |
| `--port` | the callback port on your machine, default 8000 |
| `--timeout` | seconds to wait for a command result, default 120 |
| `--verify` / `--cmd` / `--shell` | prove execution / one command / interactive loop |
| `--push LOCAL REMOTE` | copy a local file to a path on the device |
| `--root-pass [SN]` | print the derived root password |
| `--cleanup` | sweep the inert rules this tool leaves behind |

## Troubleshooting

**`--push` times out, or `--cmd` never returns or returns no output.** Both need the
router to reach your `--port`. Check that the firewall allows inbound there, and that
the address in use is one the router can route to.

## Housekeeping

Every operation temporarily adds one rule to the router's MAC blacklist, using a
locally-administered `02:f0:..` address no real client can occupy, so the rule is
inert; it is deleted again when the operation finishes. If a run is interrupted:

```bash
./miwifi_root.py --cleanup
```

Check the current state any time through the router's own `get_macfilter_info`
endpoint.

## License

MIT, see `LICENSE`. The dropbear and musl binaries published by CI are third-party
derived works under their own permissive licenses; see `THIRD_PARTY_NOTICES.md`.
No Xiaomi firmware is redistributed here.
