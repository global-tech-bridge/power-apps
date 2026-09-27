#!/usr/bin/env python3
"""preview.doc を Office の変換サービスで PDF にする（メールを出さずにレイアウトを確かめる）。

    YAJ_CONFIG=solution/config.local.json python3 scripts/preview-document.py /tmp/p
    YAJ_CONFIG=solution/config.local.json python3 scripts/convert-preview-pdf.py /tmp/p/preview.doc

フローは OneDrive の「ファイルの変換」で .doc を PDF にする。同じ Office の変換サービスを
Graph の `/content?format=pdf` で呼べるので、フローを動かさなくても（＝メールを送らずに）
実際に近い PDF が得られる。WorkTemp ライブラリに一時ファイルを置き、変換後に消す。

トークンは scripts/graph-device-login.py で取得したもの（Sites.Manage.All）を使う。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads(Path(os.environ.get("YAJ_CONFIG", ROOT / "solution/config.json")).read_text(encoding="utf-8"))
SITE_URL = CFG["sharePoint"]["siteUrl"]
if "CONTOSO" in SITE_URL:
    sys.exit("siteUrl が既定値のままです。YAJ_CONFIG でテナントの設定を指定してください。")
if len(sys.argv) < 2:
    sys.exit(__doc__)
src = Path(sys.argv[1])
dst = src.with_suffix(".pdf")

tok_file = Path(os.environ.get("YAJ_CRED_HOME", Path.home() / ".cliauth/yanmar")) / "graph-sites-token.json"
tok = json.loads(tok_file.read_text())
if tok["expires_at"] < time.time() + 60:
    sys.exit("Graph のトークンが期限切れです: python3 scripts/graph-device-login.py <テナント>")
G = "https://graph.microsoft.com/v1.0"


def call(method, path, body=None, raw=False, ctype="application/json"):
    req = urllib.request.Request(
        G + urllib.parse.quote(path, safe="/?&=$,():'!"), method=method, data=body,
        headers={"Authorization": "Bearer " + tok["access_token"], "Content-Type": ctype},
    )
    with urllib.request.urlopen(req) as r:
        data = r.read()
    return data if raw else (json.loads(data) if data else None)


host, _, path = SITE_URL.removeprefix("https://").partition("/")
site = call("GET", f"/sites/{host}:/{path}")["id"]
drive = next(d for d in call("GET", f"/sites/{site}/drives")["value"] if d["webUrl"].endswith("/WorkTemp"))
name = f"preview-{int(time.time())}.doc"
item = call("PUT", f"/drives/{drive['id']}/root:/{name}:/content", src.read_bytes(), ctype="application/msword")
try:
    pdf = call("GET", f"/drives/{drive['id']}/items/{item['id']}/content?format=pdf", raw=True)
    dst.write_bytes(pdf)
    print(f"{dst}  ({len(pdf):,} bytes)")
finally:
    call("DELETE", f"/drives/{drive['id']}/items/{item['id']}")
