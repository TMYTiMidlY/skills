#!/usr/bin/env python3
"""Regenerate an OpeniLink Hub installation's app_token via the management API.
The new token is written to a 0600 file and NOT printed (so it never lands in
an agent transcript); the old token is verified revoked.

Run with uv:  uv run --python 3.13 api_regen.py

Config via env (password injected via portal secret, never argv):
  OIH_HUB_URL    hub base url, default https://127.0.0.1:9800
  OIH_USER       hub username
  OIH_PASSWORD   hub password
  OIH_APP_ID     app id
  OIH_IID        installation id
  OIH_OLD_TOKEN  (optional) previous app_token, to confirm it gets revoked
  OIH_OUT        output file for the new token, default /tmp/oih_new_token.txt
"""
import os, json, ssl, urllib.request, http.cookiejar

HUB = os.environ.get("OIH_HUB_URL", "https://127.0.0.1:9800")
USER = os.environ["OIH_USER"]
PW = os.environ["OIH_PASSWORD"]
APP = os.environ["OIH_APP_ID"]
IID = os.environ["OIH_IID"]
OLD = os.environ.get("OIH_OLD_TOKEN", "")
OUT = os.environ.get("OIH_OUT", "/tmp/oih_new_token.txt")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.HTTPCookieProcessor(cj))


def sess(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(HUB + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        resp = op.open(r, timeout=12)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check_token(token):
    o = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    r = urllib.request.Request(HUB + "/bot/v1/info", headers={"Authorization": "Bearer " + token})
    try:
        return o.open(r, timeout=10).status
    except urllib.error.HTTPError as e:
        return e.code


st, _ = sess("POST", "/api/auth/login", {"username": USER, "password": PW})
print("login           ->", st)
st, bd = sess("POST", "/api/apps/" + APP + "/installations/" + IID + "/regenerate-token")
print("regenerate-token->", st)
new = json.loads(bd)["app_token"]

with open(OUT, "w") as f:
    f.write(new + "\n")
os.chmod(OUT, 0o600)

print("new token GET /bot/v1/info ->", check_token(new), "(expect 200 = works)")
if OLD:
    print("OLD token GET /bot/v1/info ->", check_token(OLD), "(expect 401 = revoked)")
print("new token written to", OUT, "(0600) -- full value intentionally NOT printed")
print("new token sanity: prefix=%s len=%d" % (new[:8], len(new)))
