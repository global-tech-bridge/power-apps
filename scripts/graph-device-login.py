#!/usr/bin/env python3
"""SharePoint のリスト作成に必要な Graph トークンを取得する。

    python3 scripts/graph-device-login.py <テナント>             # device code（既定）
    python3 scripts/graph-device-login.py <テナント> --browser   # ブラウザーでサインイン
    （--no-open を付けるとブラウザーを自動で開かず、URL だけ表示する）

Azure CLI のトークンには Sites.* の権限が無く、SharePoint のリストを作れない
（読むことはできる）。そこで Microsoft 公式の「Microsoft Graph Command Line Tools」
（Microsoft Graph PowerShell が使うアプリ）でサインインし、
Sites.Manage.All だけを要求する。アプリ登録は不要。

--browser は、条件付きアクセスで device code のサインインが禁止されている
テナント向け。既定のブラウザーが開き、サインイン後に http://localhost へ戻る
（PKCE 付きの認可コードフロー。Microsoft Graph PowerShell と同じ方式）。

初回は同意画面が出る。テナントでユーザーによる同意が禁止されていると
「管理者の承認が必要」と表示される。その場合は IT 部門に同意を依頼するか、
リストを Excel から作る手順（docs/08 の Part 1）に切り替える。
同意はテナントに残り、Entra 管理センター → エンタープライズ アプリケーション →
Microsoft Graph Command Line Tools から取り消せる。

取得するのはアクセストークンだけ（有効期限 約1時間）。リフレッシュトークンは
要求しない。保存先は YAJ_CRED_HOME（既定 ~/.cliauth/yanmar）の graph-sites-token.json（600）。
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"   # Microsoft Graph Command Line Tools
SCOPES = "https://graph.microsoft.com/Sites.Manage.All https://graph.microsoft.com/User.Read"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
TENANT = args[0] if args else sys.exit("テナントを指定してください（例: contoso.onmicrosoft.com）")
BROWSER = "--browser" in sys.argv
OUT = Path(os.environ.get("YAJ_CRED_HOME", Path.home() / ".cliauth/yanmar")) / "graph-sites-token.json"
BASE = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"


def post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def save(tok):
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


def device_code():
    dc = post(f"{BASE}/devicecode", {"client_id": CLIENT_ID, "scope": SCOPES})
    if "user_code" not in dc:
        sys.exit(f"device code の取得に失敗: {dc.get('error_description', dc)}")
    print(f"サインインしてください: {dc['verification_uri']}  コード: {dc['user_code']}", flush=True)
    deadline = time.time() + int(dc.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(int(dc.get("interval", 5)))
        tok = post(f"{BASE}/token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": CLIENT_ID,
            "device_code": dc["device_code"],
        })
        if "access_token" in tok:
            save(tok)
        if tok.get("error") not in ("authorization_pending", "slow_down"):
            hint = ""
            if "AADSTS50097" in str(tok) or "AADSTS53003" in str(tok):
                hint = "\n  条件付きアクセスで device code が禁止されている可能性があります。--browser を試してください。"
            sys.exit(f"サインインに失敗: {tok.get('error_description', tok)}{hint}")
    sys.exit("有効期限内にサインインが完了しませんでした")


def browser():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:
                result.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("サインインが終わりました。このタブは閉じてかまいません。".encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("localhost", 0), Handler)
    redirect = f"http://localhost:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"{BASE}/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": redirect,
        "scope": SCOPES, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account",
    })
    print("ブラウザーでサインインしてください（開かない場合は次の URL を開く）:", flush=True)
    print(url, flush=True)
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    deadline = time.time() + 600
    while not result and time.time() < deadline:
        time.sleep(0.5)
    server.shutdown()
    if not result:
        sys.exit("10分以内にサインインが完了しませんでした")
    if result.get("state") != state:
        sys.exit("state が一致しません。やり直してください")
    if "error" in result:
        sys.exit(f"サインインに失敗: {result.get('error_description', result['error'])}")
    tok = post(f"{BASE}/token", {
        "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": result["code"],
        "redirect_uri": redirect, "code_verifier": verifier, "scope": SCOPES,
    })
    if "access_token" not in tok:
        sys.exit(f"トークンの取得に失敗: {tok.get('error_description', tok)}")
    save(tok)


browser() if BROWSER else device_code()
