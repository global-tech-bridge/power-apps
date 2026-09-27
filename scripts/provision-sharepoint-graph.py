#!/usr/bin/env python3
"""SharePoint のサイト・リスト・ライブラリ・初期データを Microsoft Graph で作る。

    export AZURE_CONFIG_DIR=~/.cliauth/yanmar/azure
    az login --use-device-code --tenant <テナント> --allow-no-subscriptions
    YAJ_CONFIG=solution/config.local.json python3 scripts/provision-sharepoint-graph.py

PnP.PowerShell 版（Provision-SharePoint.ps1）の代替。PowerShell も
Entra ID へのアプリ登録も要らず、Azure CLI のサインインだけで動く。
定義元は data/list-schema.json（画面手順・PnP 版と同じ）。

何度実行しても安全（既にあるものはスキップし、足りない列だけ足す）。

作るもの
  1. Microsoft 365 グループ → チームサイト（config の siteUrl の末尾がエイリアス）
  2. リスト7つと全列（種類・必須・既定値・インデックス込み）
  3. ドキュメント ライブラリ4つ
  4. 初期データ: 組織マスタ105件 / 確認文面 v1.0 / 管理者（実行者）
  5. Word テンプレートのアップロード

作らないもの（Graph で設定できないため画面で行う。docs/04-permissions.md）
  - ライブラリ単位の権限（継承の中止）と項目レベルのアクセス許可
"""
import csv
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yajcli  # noqa: E402,F401  Windows でも出力を UTF-8 にする（✓ などは cp932 に無い）

ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = Path(os.environ.get("YAJ_CONFIG", ROOT / "solution/config.json"))
CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "data/list-schema.json").read_text(encoding="utf-8"))
DRY = "--dry-run" in sys.argv
GRAPH = "https://graph.microsoft.com/v1.0"

SITE_URL = CFG["sharePoint"]["siteUrl"].rstrip("/")
if "CONTOSO" in SITE_URL:
    sys.exit(f"{CFG_PATH} の siteUrl が既定値のままです。YAJ_CONFIG で実環境の設定を指定してください。")
HOST = urllib.parse.urlparse(SITE_URL).hostname
SITE_PATH = urllib.parse.urlparse(SITE_URL).path          # /sites/yaj-cancelfee
ALIAS = SITE_PATH.rstrip("/").split("/")[-1]              # yaj-cancelfee


def info(msg):
    print(f"\033[36m==>\033[0m {msg}", flush=True)


def az_token():
    import yajcli  # Windows の az.cmd も見つけて呼ぶ
    return yajcli.az_token("https://graph.microsoft.com") or sys.exit(
        "Azure CLI で Graph のトークンを取れません。az login --tenant <テナント> --allow-no-subscriptions")


def sites_token():
    """scripts/graph-device-login.py で取得した Sites.Manage.All 付きのトークン。

    Azure CLI のトークンには Sites.* の権限が無く、リストを作ると 403 になる
    （実環境で確認）。グループ作成は Azure CLI の Group.ReadWrite.All で足りる。
    """
    f = Path(os.environ.get("YAJ_CRED_HOME", Path.home() / ".cliauth/yanmar")) / "graph-sites-token.json"
    if not f.exists():
        return None
    t = json.loads(f.read_text(encoding="utf-8"))
    if t.get("expires_at", 0) < time.time() + 120:
        print("  ⚠ Sites 用トークンの期限が切れています。graph-device-login.py で取り直してください。")
        return None
    return t["access_token"]


AZ_TOKEN = az_token()
TOKEN = sites_token() or AZ_TOKEN
if TOKEN is AZ_TOKEN:
    print("  ⚠ Sites 用トークンが無いため Azure CLI のトークンで実行します（リスト作成は 403 になります）")


def call(method, path, body=None, raw=None, content_type="application/json",
         ok=(200, 201, 204), tok=None):
    url = path if path.startswith("http") else GRAPH + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {tok or TOKEN}")
    if data is not None:
        req.add_header("Content-Type", content_type)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as res:
                txt = res.read().decode() or "{}"
                return res.status, json.loads(txt) if txt.strip().startswith("{") else {}
        except urllib.error.HTTPError as e:
            txt = e.read().decode()
            if e.code in (429, 503, 504) and attempt < 4:
                time.sleep(int(e.headers.get("Retry-After", "5")))
                continue
            if e.code in ok:
                return e.code, {}
            return e.code, json.loads(txt) if txt.strip().startswith("{") else {"raw": txt}


def must(status, body, what):
    if status >= 300:
        msg = body.get("error", {}).get("message", body)
        sys.exit(f"✗ {what} に失敗しました（HTTP {status}）: {msg}")
    return body


# ---------------------------------------------------------------------------
# 1. サイト（Microsoft 365 グループのチームサイト）
# ---------------------------------------------------------------------------
def ensure_site():
    status, site = call("GET", f"/sites/{HOST}:{SITE_PATH}?$select=id,webUrl")
    if status == 200:
        info(f"サイトは既にあります: {site['webUrl']}")
        return site["id"]

    me = must(*call("GET", "/me?$select=id,userPrincipalName"), "サインイン中のユーザーの取得")
    info(f"Microsoft 365 グループ '{ALIAS}' を作成します（チームサイトが自動で作られます）")
    if DRY:
        return "DRY-RUN"
    group = must(*call("POST", "/groups", tok=AZ_TOKEN, body={
        "displayName": CFG["solution"]["displayName"],
        "mailNickname": ALIAS,
        "description": "YAJ 整備キャンセル料 確認書アプリのデータ保管用サイト",
        "groupTypes": ["Unified"],
        "mailEnabled": True,
        "securityEnabled": False,
        # 顧客の個人情報を扱うためプライベート（要件定義 15.3）
        "visibility": "Private",
        "owners@odata.bind": [f"{GRAPH}/users/{me['id']}"],
        "members@odata.bind": [f"{GRAPH}/users/{me['id']}"],
    }), "グループの作成")

    info("チームサイトの作成を待っています（通常1〜3分）")
    for i in range(40):
        status, site = call("GET", f"/groups/{group['id']}/sites/root?$select=id,webUrl",
                            tok=AZ_TOKEN)
        if status == 200 and site.get("id"):
            info(f"サイトができました: {site['webUrl']}")
            if site["webUrl"].rstrip("/").lower() != SITE_URL.lower():
                print(f"  ⚠ 想定のURL（{SITE_URL}）と違います。config の siteUrl を合わせてください。")
            return site["id"]
        time.sleep(10)
    sys.exit("✗ サイトの作成を待ちきれませんでした。少し時間をおいて再実行してください。")


# ---------------------------------------------------------------------------
# 2. 列定義: list-schema.json → Graph の columnDefinition
# ---------------------------------------------------------------------------
def column_def(c):
    d = {"name": c["Name"], "displayName": c["Name"]}
    t = c["Type"]
    if t == "Text":
        d["text"] = {"allowMultipleLines": False, "maxLength": 255}
    elif t == "Note":
        # プレーンテキスト。リッチテキストだと確認文面に HTML タグが混ざる
        d["text"] = {"allowMultipleLines": True, "textType": "plain",
                     "appendChangesToExistingText": False, "linesForEditing": 6}
    elif t == "Number":
        d["number"] = {"decimalPlaces": "none"}
    elif t == "Boolean":
        d["boolean"] = {}
    elif t == "DateTime":
        d["dateTime"] = {"format": "dateTime", "displayAs": "standard"}
    elif t == "Choice":
        d["choice"] = {"choices": c["Choices"], "allowTextEntry": False,
                       "displayAs": "dropDownMenu"}
    elif t == "User":
        d["personOrGroup"] = {"allowMultipleSelection": False, "chooseFromType": "peopleOnly"}
    else:
        raise ValueError(f"未対応の列型: {t}")
    if c.get("Required"):
        d["required"] = True
    if c.get("Indexed"):
        d["indexed"] = True
    if "Default" in c:
        d["defaultValue"] = {"value": str(c["Default"])}
    if c.get("Note"):
        d["description"] = c["Note"][:255]
    return d


def list_by_name(site_id, name):
    status, body = call("GET", f"/sites/{site_id}/lists?$select=id,name,displayName&$top=200")
    must(status, body, "リスト一覧の取得")
    for l in body.get("value", []):
        if l["name"].lower() == name.lower() or l["displayName"].lower() == name.lower():
            return l["id"]
    return None


def ensure_list(site_id, name, columns, template="genericList"):
    lid = list_by_name(site_id, name)
    if not lid:
        info(f"[{'ライブラリ' if template == 'documentLibrary' else 'リスト'}] {name} を作成")
        if DRY:
            return None
        body = {"displayName": name, "list": {"template": template}}
        if columns:
            body["columns"] = [column_def(c) for c in columns]
        created = must(*call("POST", f"/sites/{site_id}/lists", body), f"{name} の作成")
        print(f"    + 列 {len(columns)} 件（インデックス {sum(1 for c in columns if c.get('Indexed'))} 件）")
        return created["id"]

    # 既にある場合は、足りない列だけ足す
    status, body = call("GET", f"/sites/{site_id}/lists/{lid}/columns?$select=name&$top=500")
    have = {c["name"] for c in must(status, body, f"{name} の列一覧").get("value", [])}
    missing = [c for c in columns if c["Name"] not in have]
    info(f"[既存] {name}: 足りない列 {len(missing)} 件")
    for c in missing:
        if not DRY:
            must(*call("POST", f"/sites/{site_id}/lists/{lid}/columns", column_def(c)),
                 f"{name}.{c['Name']} の追加")
        print(f"    + {c['Name']} ({c['Type']})")
    return lid


# ---------------------------------------------------------------------------
# 4. 初期データ
# ---------------------------------------------------------------------------
def count_items(site_id, list_id):
    status, body = call("GET", f"/sites/{site_id}/lists/{list_id}/items?$top=1&$select=id")
    return len(body.get("value", [])) if status == 200 else 0


def batch_create(site_id, list_id, rows):
    """20件ずつ $batch で作る。"""
    done = 0
    for i in range(0, len(rows), 20):
        chunk = rows[i:i + 20]
        reqs = [{"id": str(n), "method": "POST",
                 "url": f"/sites/{site_id}/lists/{list_id}/items",
                 "headers": {"Content-Type": "application/json"},
                 "body": {"fields": r}} for n, r in enumerate(chunk)]
        status, body = call("POST", "/$batch", {"requests": reqs})
        must(status, body, "一括登録")
        bad = [r for r in body.get("responses", []) if r["status"] >= 300]
        if bad:
            err = bad[0].get("body", {}).get("error", {}).get("message", bad[0])
            sys.exit(f"✗ 一括登録で {len(bad)} 件失敗: {err}")
        done += len(chunk)
        print(f"    {done} / {len(rows)} 件", flush=True)


def seed(site_id, ids):
    # --- 組織マスタ ---
    lid = ids["OrgMaster"]
    if count_items(site_id, lid):
        info("[初期データ] OrgMaster は既にデータがあるためスキップ")
    else:
        with (ROOT / "data/OrgMaster.csv").open(encoding="utf-8-sig") as f:
            rows = [{
                "Title": r["Title"], "BranchName": r["BranchName"],
                "BlockCode": r["BlockCode"], "BlockName": r["BlockName"],
                "SiteCode": r["SiteCode"], "SiteName": r["SiteName"],
                "IsActive": r["IsActive"] == "TRUE", "SortOrder": int(r["SortOrder"]),
            } for r in csv.DictReader(f)]
        info(f"[初期データ] OrgMaster {len(rows)} 件")
        if not DRY:
            batch_create(site_id, lid, rows)

    # --- 確認文面 ---
    lid = ids["ConsentMaster"]
    if count_items(site_id, lid):
        info("[初期データ] ConsentMaster は既にデータがあるためスキップ")
    else:
        lines = (ROOT / "data/consent/ConsentText_v1.0.txt").read_text(encoding="utf-8").split("\n")
        info("[初期データ] ConsentMaster 版 1.0")
        if not DRY:
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            today = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime())
            must(*call("POST", f"/sites/{site_id}/lists/{lid}/items", {"fields": {
                "Title": "CANCELFEE-001", "ConsentId": "CANCELFEE-001", "Version": "1.0",
                "EffectiveFrom": today, "IsActive": True,
                "DisplayTitle": lines[0].strip(),
                "Body": "\n".join(lines[2:]).strip(),
                "RevisedBy": "サービス事業推進部（2026-06-02 起案）", "RevisedAt": now,
            }}), "確認文面の登録")

    # --- 管理者（実行者を登録）---
    lid = ids["AppAdmins"]
    if count_items(site_id, lid):
        info("[初期データ] AppAdmins は既にデータがあるためスキップ")
    else:
        me = must(*call("GET", "/me?$select=displayName,userPrincipalName,mail"), "ユーザー取得")
        email = (me.get("mail") or me["userPrincipalName"]).lower()
        info(f"[初期データ] AppAdmins に {email} を登録")
        if not DRY:
            must(*call("POST", f"/sites/{site_id}/lists/{lid}/items", {"fields": {
                "Title": email, "UserEmail": email, "UserName": me.get("displayName", ""),
                "IsActive": True, "Note": "構築時に自動登録",
            }}), "管理者の登録")


def upload_template(site_id):
    lib = CFG["sharePoint"]["libraries"]["docTemplates"]
    status, drives = call("GET", f"/sites/{site_id}/drives?$select=id,name")
    drive = next((d for d in drives.get("value", []) if d["name"] == lib), None)
    if not drive:
        print(f"  ⚠ ライブラリ {lib} が見つからずテンプレートをアップロードできません")
        return
    path = ROOT / "templates" / CFG["wordTemplate"]["fileName"]
    info(f"[テンプレート] {path.name} を {lib} にアップロード")
    if DRY:
        return
    name = urllib.parse.quote(path.name)
    must(*call("PUT", f"/drives/{drive['id']}/root:/{name}:/content", raw=path.read_bytes(),
               content_type="application/octet-stream"), "テンプレートのアップロード")


def main():
    info(f"対象: {SITE_URL}{'（ドライラン）' if DRY else ''}")
    site_id = ensure_site()
    if site_id == "DRY-RUN":
        for name in list(SCHEMA["Lists"]) + list(SCHEMA["Libraries"]):
            print(f"    作成予定: {name}")
        return
    ids = {}
    for name, d in SCHEMA["Lists"].items():
        ids[name] = ensure_list(site_id, name, d["Columns"])
    for name in SCHEMA["Libraries"]:
        ids[name] = ensure_list(site_id, name, [], template="documentLibrary")
    if DRY:
        info("ドライランのため初期データは作りません")
        return
    seed(site_id, ids)
    upload_template(site_id)
    info("完了しました")
    print("\n  画面で行うこと（Graph で設定できないため）: docs/04-permissions.md")
    print("    - SignatureDocs / SignatureImages の権限の継承を中止し、利用者を閲覧のみに")
    print("    - SignatureCases の項目レベルのアクセス許可（編集: 作成した項目のみ）")


if __name__ == "__main__":
    main()
