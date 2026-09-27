#!/usr/bin/env python3
"""デプロイの前に、この PC とアカウントで何ができるかを一括で確かめる。

    python scripts/preflight.py https://<組織>.crm7.dynamics.com
    （設定ファイルは環境変数 YAJ_CONFIG で指定する。docs/11 の 2-2）

管理者権限が無い前提で、つまずく箇所を先に見つけるためのもの。何も作らない・変えない。

  1. ツール      pac / az / Python のモジュール
  2. 設定        YAJ_CONFIG の siteUrl が実環境の値になっているか
  3. pac         有効なプロファイルが YAJ_PAC_PROFILE か、環境につながるか
  4. Azure CLI   サインイン先のテナントが siteUrl のテナントと同じか
  5. Dataverse   ソリューションのインポート・作成などの権限を持っているか
                 （ロール名は言語で変わるので、権限そのものを調べる）
  6. 既存の物    フロー用・アプリ用のソリューション、発行者
  7. 接続        SharePoint / OneDrive for Business / Office 365 Outlook の接続
  8. SharePoint  サイトがあるか、リストがそろっているか（Graph のトークンがあれば）
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yajcli

ROOT = Path(__file__).resolve().parent.parent
ENV = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else sys.exit(__doc__)
CFG_PATH = Path(os.environ.get("YAJ_CONFIG", ROOT / "solution/config.json"))
PROFILE = os.environ.get("YAJ_PAC_PROFILE", "yanmar-test")
CRED = Path(os.environ.get("YAJ_CRED_HOME", Path.home() / ".cliauth/yanmar"))

results = []   # (状態, 項目, 内容, 次にやること)


def ok(item, msg):
    results.append(("✓", item, msg, ""))


def warn(item, msg, todo=""):
    results.append(("!", item, msg, todo))


def ng(item, msg, todo=""):
    results.append(("✗", item, msg, todo))


def run(cmd):
    # Windows の az.cmd も見つけて呼ぶ。出力は UTF-8 / cp932 のどちらでも読む
    return yajcli.run(cmd, timeout=180)


def http(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"raw": body[:300].decode(errors="replace")}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


def az_token(resource):
    return yajcli.az_token(resource)


# ---- 1. ツール --------------------------------------------------------------
WIN = yajcli.IS_WINDOWS
for tool, hint in [("pac", "docs/11 の 2-1（Windows: Power Platform Tools の VS Code 拡張か MSI。Mac: dotnet tool install -g microsoft.powerapps.cli.tool）"),
                   ("az", "docs/11 の 2-1（Windows: Azure CLI の ZIP 版なら PC の管理者権限は不要。Mac: brew install azure-cli）")]:
    if shutil.which(tool):
        code, out = run([tool, "--version"] if tool == "az" else [tool, "help"])
        ver = next((l for l in out.splitlines() if "Version" in l or l.startswith("azure-cli")), "").strip()
        ok("ツール", f"{tool} {ver}")
    else:
        ng("ツール", f"{tool} が見つかりません", hint)
missing = []
for mod in ["yaml", "jsonschema", "openpyxl"]:
    try:
        __import__(mod)
    except ImportError:
        missing.append(mod)
if missing:
    ng("ツール", "Python のモジュールが足りません: " + ", ".join(missing),
       ("python -m pip install --user" if WIN else "pip3 install") + " pyyaml jsonschema openpyxl python-docx")
else:
    ok("ツール", "Python のモジュール（pyyaml / jsonschema / openpyxl）")

# ---- 2. 設定 ----------------------------------------------------------------
site_url = ""
if not CFG_PATH.exists():
    ng("設定", f"{CFG_PATH} がありません", "solution/config.json を config.local.yanmar.json としてコピーし、siteUrl を直す（docs/11 の 2-4）")
else:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    site_url = cfg["sharePoint"]["siteUrl"].rstrip("/")
    if "CONTOSO" in site_url:
        ng("設定", f"{CFG_PATH.name} の siteUrl が既定値のままです", "sharePoint.siteUrl を実際のサイトの URL にする")
    else:
        ok("設定", f"{CFG_PATH.name}  siteUrl = {site_url}  / メール差出人 = {cfg['mail'].get('senderMode', 'operator')}")
sp_host = urllib.parse.urlparse(site_url).netloc if site_url else ""

# ---- 3. pac -----------------------------------------------------------------
code, out = run(["pac", "auth", "list"])
active = next((l for l in out.splitlines() if " * " in f" {l} " and "UNIVERSAL" in l), "")
active_name = active.split()[3] if len(active.split()) > 3 else ""
if not active:
    ng("pac", "有効な認証プロファイルがありません", f"pac auth create --name {PROFILE}（ブラウザーが開く。開けない環境では --deviceCode）")
elif active_name != PROFILE:
    ng("pac", f"有効なプロファイルが {active_name} です（想定 {PROFILE}）", f"pac auth select --name {PROFILE}")
else:
    ok("pac", " ".join(active.split()[3:5]))
code, out = run(["pac", "org", "who", "--environment", ENV])
if code == 0 and "Error" not in out:
    name = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.strip().startswith("Friendly Name")), "")
    ok("pac", f"環境につながります（{name or ENV}）")
else:
    ng("pac", "環境につながりません: " + out.strip().splitlines()[-1][:160] if out.strip() else "環境につながりません",
       "環境 URL と、その環境へのアクセス権（セキュリティ ロール）を確認する")

# ---- 4. Azure CLI -----------------------------------------------------------
code, out = run(["az", "account", "show", "-o", "json"])
if code != 0:
    ng("Azure CLI", "サインインしていません",
       "az login --tenant <テナント>.onmicrosoft.com --allow-no-subscriptions（ブラウザーが開く）")
    acct = {}
else:
    acct = json.loads(out)
    ok("Azure CLI", f"{acct.get('user', {}).get('name')}  テナント {acct.get('tenantId')}")

dv = az_token(ENV) if acct else None
graph = az_token("https://graph.microsoft.com") if acct else None
if acct and not dv:
    ng("Azure CLI", "Dataverse のトークンを取れません", "az login をやり直す（フローをオンにする処理で使う）")

# ---- 5. Dataverse の権限 -----------------------------------------------------
NEED = {
    "prvImportCustomization": "ソリューションのインポート（フローを入れる）",
    "prvExportCustomization": "ソリューションのエクスポート（アプリの差し替えに使う）",
    "prvCreateSolution": "ソリューションの作成（アプリ用）",
    "prvCreatePublisher": "発行者の作成（初回のインポート）",
    "prvPublishCustomization": "カスタマイズの公開",
    "prvCreateWorkflow": "フローの作成",
    "prvWriteWorkflow": "フローの更新・オン",
    "prvCreatecanvasapp": "キャンバスアプリの作成",
    "prvCreateconnectionreference": "接続参照の作成",
}
if dv:
    st, who = http(f"{ENV}/api/data/v9.2/WhoAmI", dv)
    if st != 200:
        ng("Dataverse", f"WhoAmI に失敗（HTTP {st}）。この環境に Dataverse が無いか、アクセス権がありません",
           "Dataverse が有効な環境が必要。IT 部門に環境の用意か、開発者環境の作成可否を確認する")
    else:
        uid = who["UserId"]
        st, pv = http(f"{ENV}/api/data/v9.2/systemusers({uid})/Microsoft.Dynamics.CRM.RetrieveUserPrivileges()", dv)
        have = {p.get("PrivilegeName", "").lower() for p in pv.get("RolePrivileges", [])}
        lack = [f"{v}（{k}）" for k, v in NEED.items() if k.lower() not in have]
        st2, roles = http(f"{ENV}/api/data/v9.2/systemusers({uid})?$select=fullname&$expand=systemuserroles_association($select=name)", dv)
        role_names = ", ".join(r["name"] for r in roles.get("systemuserroles_association", [])) if st2 == 200 else "?"
        if lack:
            ng("Dataverse", "足りない権限: " + " / ".join(lack) + f"（ロール: {role_names}）",
               "IT 部門に、この環境の「System Customizer（システム カスタマイザー）」ロールを依頼する")
        else:
            ok("Dataverse", f"必要な権限はそろっています（ロール: {role_names}）")

        # ---- 6. 既存のソリューション・発行者 ----
        if CFG_PATH.exists():
            for uname, label in [(cfg["solution"]["uniqueName"], "フロー用"), ("YAJCancelFeeApp", "アプリ用")]:
                st, sol = http(f"{ENV}/api/data/v9.2/solutions?$select=version&$filter=uniquename eq '{uname}'".replace(" ", "%20"), dv)
                if sol.get("value"):
                    ok("既存の物", f"{label}ソリューション {uname}（版 {sol['value'][0]['version']}）")
                else:
                    warn("既存の物", f"{label}ソリューション {uname} はまだありません",
                         "deploy.sh で作られる" if label == "フロー用" else "deploy-app.sh が作る（アプリは初回だけ Studio で作る）")
            pub = cfg["solution"]["publisherUniqueName"]
            st, p = http(f"{ENV}/api/data/v9.2/publishers?$select=friendlyname,customizationprefix&$filter=uniquename eq '{pub}'".replace(" ", "%20"), dv)
            if p.get("value"):
                ok("既存の物", f"発行者 {p['value'][0]['friendlyname']}（接頭辞 {p['value'][0]['customizationprefix']}）")
            else:
                warn("既存の物", f"発行者 {pub} はまだありません", "最初の deploy.sh で作られる")

# ---- 7. 接続 ----------------------------------------------------------------
code, out = run(["pac", "connection", "list", "--environment", ENV])
if code == 0:
    for api, label in [("shared_sharepointonline", "SharePoint"),
                       ("shared_onedriveforbusiness", "OneDrive for Business"),
                       ("shared_office365", "Office 365 Outlook")]:
        rows = [l for l in out.splitlines() if l.split() and len(l.split()) >= 4 and l.split()[-2].endswith("/" + api)]
        good = [r for r in rows if r.split()[-1].lower() == "connected"]
        if len(good) == 1:
            ok("接続", f"{label}（{good[0].split()[0]}）")
        elif len(good) > 1:
            warn("接続", f"{label} の接続が {len(good)} 個あります", "deploy.sh が止まるので、使わないものを削除するか deploy-settings.json に ID を手で入れる")
        else:
            ng("接続", f"{label} の接続がありません（または切断中）",
               "make.powerapps.com → 接続 → 新しい接続 で作る（サインインして許可するだけ）")
else:
    warn("接続", "接続の一覧を取れませんでした: " + out.strip()[:120])

# ---- 8. SharePoint ----------------------------------------------------------
tok_file = CRED / "graph-sites-token.json"
sites_tok = None
if tok_file.exists():
    t = json.loads(tok_file.read_text(encoding="utf-8"))
    if t.get("expires_at", 0) > time.time() + 60:
        sites_tok = t["access_token"]
if sp_host:
    tok = sites_tok or graph
    st, site = http(f"https://graph.microsoft.com/v1.0/sites/{sp_host}:{urllib.parse.urlparse(site_url).path}?$select=id,webUrl,displayName", tok) if tok else (0, {})
    if st == 200:
        ok("SharePoint", f"サイトがあります（{site.get('displayName')}）")
        if sites_tok:
            st, lists = http(f"https://graph.microsoft.com/v1.0/sites/{site['id']}/lists?$select=name,displayName&$top=100", sites_tok)
            names = {l.get("name") for l in lists.get("value", [])} | {l.get("displayName") for l in lists.get("value", [])}
            want = ["SignatureCases", "OrgMaster", "ConsentMaster", "AppAdmins", "SendLog", "AuditLog",
                    "DocumentNumberCounter", "SignatureDocs", "SignatureImages", "WorkTemp", "DocTemplates"]
            lack = [w for w in want if w not in names]
            if lack:
                warn("SharePoint", "まだ無いリスト・ライブラリ: " + ", ".join(lack), "provision-sharepoint-graph.py で作る")
            else:
                ok("SharePoint", "リスト7つ・ライブラリ4つがそろっています")
        else:
            warn("SharePoint", "リストの有無は未確認（Sites.Manage.All のトークンが無い）",
                 "scripts/graph-device-login.py <テナント> を実行する（device code が禁止されていれば --browser）")
    elif st in (401, 403):
        warn("SharePoint", f"サイトを読めません（HTTP {st}）。サイトのメンバーでないか、トークンの権限が足りません",
             "サイトの所有者に追加してもらう。Graph のトークンを取り直す")
    elif st == 404:
        warn("SharePoint", "サイトがまだありません",
             "自分でチームサイトを作れるなら provision-sharepoint-graph.py が作る。作れなければ IT 部門に依頼し、所有者にしてもらう")
    else:
        warn("SharePoint", f"サイトを確認できませんでした（HTTP {st}）")

# ---- 結果 -------------------------------------------------------------------
import unicodedata


def dwidth(t):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in t)


width = max(dwidth(r[1]) for r in results)
for mark, item, msg, todo in results:
    print(f"{mark} {item}{' ' * (width - dwidth(item))}  {msg}")
    if todo:
        print(f"  {' ' * width}  → {todo}")
bad = [r for r in results if r[0] == "✗"]
print()
print(f"✗ {len(bad)} 件 / ! {sum(r[0] == '!' for r in results)} 件 / ✓ {sum(r[0] == '✓' for r in results)} 件")
sys.exit(1 if bad else 0)
