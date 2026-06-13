#!/usr/bin/env python3
"""Set/replace an OpeniLink Hub installation's scopes via the *management API*
(the recommended, db-safe way). Logs in with username+password to get a session
cookie, updates the app scopes, then reauthorizes the installation to inherit
them (Slack model: only installation scopes take effect).

Run with uv:  uv run --python 3.13 api_setscope.py

Config via env (nothing hardcoded; password injected via portal secret):
  OIH_HUB_URL   hub base url, default https://127.0.0.1:9800
  OIH_USER      hub username
  OIH_PASSWORD  hub password  (inject via portal_bash secrets=["..."], never argv)
  OIH_APP_ID    app id
  OIH_IID       installation id
  OIH_SCOPES    JSON array, default '["message:write","message:read","bot:read","contact:read"]'
"""
import os, json, ssl, urllib.request, http.cookiejar

HUB = os.environ.get("OIH_HUB_URL", "https://127.0.0.1:9800")
USER = os.environ["OIH_USER"]
PW = os.environ["OIH_PASSWORD"]
APP = os.environ["OIH_APP_ID"]
IID = os.environ["OIH_IID"]
SCOPES = json.loads(os.environ.get(
    "OIH_SCOPES", '["message:write","message:read","bot:read","contact:read"]'))

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE  # reverse proxies often use `tls internal` self-signed certs
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                 urllib.request.HTTPCookieProcessor(cj))


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(HUB + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        resp = op.open(r, timeout=12)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


st, _ = req("POST", "/api/auth/login", {"username": USER, "password": PW})
print("login            ->", st)
st, bd = req("PUT", "/api/apps/" + APP, {"scopes": SCOPES})
print("update-app scopes->", st, bd[:120])
st, bd = req("POST", "/api/apps/" + APP + "/installations/" + IID + "/reauthorize")
print("reauthorize      ->", st, bd[:120])
st, bd = req("GET", "/api/apps/" + APP + "/installations/" + IID)
print("get-installation ->", st, bd[:300])
