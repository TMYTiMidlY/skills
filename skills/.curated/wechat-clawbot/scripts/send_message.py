#!/usr/bin/env python3
"""Send a WeChat message via OpeniLink Hub Bot API (POST /bot/v1/message/send).
Handy for "搞定后通知我" completion pings. Pure stdlib (urllib), no deps.

Config via env (nothing hardcoded; app_token injected via portal secret, never argv):
  OIH_HUB_URL    hub base url, e.g. https://hub.example.com  (default https://127.0.0.1:9800)
  OIH_APP_TOKEN  installation app_token (app_<64hex>); inject via portal_exec secrets=[...]
  OIH_TO         recipient wxid; omit / empty = send to the Bot itself
  OIH_INSECURE   "1" to skip TLS verify (reverse proxies often use self-signed `tls internal`)

Message text: first CLI arg, else stdin.

  OIH_APP_TOKEN=$OIH_APP_TOKEN OIH_TO=wxid_abc python send_message.py "done: built X"
"""
import json
import os
import ssl
import sys
import urllib.request

HUB = os.environ.get("OIH_HUB_URL", "https://127.0.0.1:9800").rstrip("/")
TOKEN = os.environ["OIH_APP_TOKEN"]
TO = os.environ.get("OIH_TO", "").strip()

content = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
content = content.strip()
if not content:
    sys.exit("empty message")

body = {"type": "text", "content": content}
if TO:
    body["to"] = TO

ctx = None
if os.environ.get("OIH_INSECURE") == "1" or HUB.startswith("https://127.0.0.1") or HUB.startswith("https://localhost"):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    HUB + "/bot/v1/message/send",
    data=json.dumps(body).encode(),
    method="POST",
    headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
)
try:
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    print(resp.status, resp.read().decode()[:300])
except urllib.error.HTTPError as e:
    # 401 = token 无效/未认证；403 = token 有效但缺 message:write scope
    print("HTTP", e.code, e.read().decode()[:300])
    sys.exit(1)
