#!/usr/bin/env python3
"""SharePoint のリスト作成に必要な Graph トークンを device code で取得する。

    python3 scripts/graph-device-login.py <テナント>

Azure CLI のトークンには Sites.* の権限が無く、SharePoint のリストを作れない
（読むことはできる）。そこで Microsoft 公式の「Microsoft Graph Command Line Tools」
（Microsoft Graph PowerShell が使うアプリ）で device code サインインし、
Sites.Manage.All だけを要求する。アプリ登録は不要。

初回は同意画面が出る。同意はテナントに残り、Entra 管理センター →
エンタープライズ アプリケーション → Microsoft Graph Command Line Tools から取り消せる。

取得するのはアクセストークンだけ（有効期限 約1時間）。リフレッシュトークンは
要求しない。保存先はリポジトリ外の ~/.cliauth/yanmar/graph-sites-token.json（600）。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"   # Microsoft Graph Command Line Tools
SCOPES = "https://graph.microsoft.com/Sites.Manage.All https://graph.microsoft.com/User.Read"
TENANT = sys.argv[1] if len(sys.argv) > 1 else sys.exit("テナントを指定してください")
OUT = Path(os.environ.get("YAJ_CRED_HOME", Path.home() / ".cliauth/yanmar")) / "graph-sites-token.json"


def post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


base = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"
dc = post(f"{base}/devicecode", {"client_id": CLIENT_ID, "scope": SCOPES})
if "user_code" not in dc:
    sys.exit(f"device code の取得に失敗: {dc.get('error_description', dc)}")
print(f"サインインしてください: {dc['verification_uri']}  コード: {dc['user_code']}", flush=True)

deadline = time.time() + int(dc.get("expires_in", 900))
while time.time() < deadline:
    time.sleep(int(dc.get("interval", 5)))
    tok = post(f"{base}/token", {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": CLIENT_ID,
        "device_code": dc["device_code"],
    })
    if "access_token" in tok:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "access_token": tok["access_token"],
            "expires_at": int(time.time()) + int(tok.get("expires_in", 3600)),
            "scope": tok.get("scope", ""),
        }))
        os.chmod(OUT, 0o600)
        print(f"取得しました（権限: {tok.get('scope', '')}）", flush=True)
        print(f"保存先: {OUT}", flush=True)
        sys.exit(0)
    if tok.get("error") not in ("authorization_pending", "slow_down"):
        sys.exit(f"サインインに失敗: {tok.get('error_description', tok)}")
sys.exit("有効期限内にサインインが完了しませんでした")
