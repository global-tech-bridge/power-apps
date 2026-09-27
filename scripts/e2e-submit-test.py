#!/usr/bin/env python3
"""送信フロー（YAJ-CancelFee-Submit）を CLI から1回通しで動かす疎通テスト。

    export AZURE_CONFIG_DIR=~/.cliauth/yanmar/azure
    YAJ_CONFIG=solution/config.local.json python3 scripts/e2e-submit-test.py <環境ID> [出力先]

やること
  1. SignatureCases にテスト案件を1件作る（顧客名「テスト太郎」、顧客メールは空）
  2. 送信フローのトリガーを呼び出す（アプリの送信ボタンと同じ入力を渡す）
  3. 応答と、SharePoint 側の結果（文書番号・状態・PDF・送信履歴）を読み戻す
  4. 生成された PDF をダウンロードし、日本語の文字と署名画像が入っているかを確かめ、
     1ページ目を PNG にする（目視確認用）

⚠ メールが1通送信される。顧客メールを空にしているので、宛先は担当者（実行者）のみ。
  実顧客の情報は使わない（要件定義 15.3）。

認証
  - Flow API: Azure CLI
  - SharePoint（Graph）: scripts/graph-device-login.py のトークン
"""
import base64
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads(Path(os.environ.get("YAJ_CONFIG", ROOT / "solution/config.json")).read_text())
args = [a for a in sys.argv[1:] if not a.startswith("--")]
ENV_ID = args[0] if args else sys.exit("環境IDを指定してください")
OUT = Path(args[1] if len(args) > 1 else "/tmp/yaj-e2e")
REUSE = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--item-id=")), None)
ORG = next((a.split("=", 1)[1].rstrip("/") for a in sys.argv if a.startswith("--org=")), None) \
    or sys.exit("--org=<環境URL> を指定してください（例 --org=https://xxx.crm7.dynamics.com）")
OUT.mkdir(parents=True, exist_ok=True)
GRAPH = "https://graph.microsoft.com/v1.0"
FLOW_API = f"https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/{ENV_ID}"


def az(resource):
    return subprocess.check_output(["az", "account", "get-access-token", "--resource", resource,
                                    "--query", "accessToken", "-o", "tsv"], text=True).strip()


def sites_token():
    f = Path.home() / ".cliauth/yanmar/graph-sites-token.json"
    t = json.loads(f.read_text())
    if t["expires_at"] < time.time() + 120:
        sys.exit("Sites 用トークンの期限切れ。scripts/graph-device-login.py で取り直してください")
    return t["access_token"]


def http(method, url, token=None, body=None, raw=False, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
            return r.status, content if raw else (json.loads(content) if content.strip() else {})
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, {"raw": content[:500].decode(errors="replace")}


def signature_png(w=520, h=150):
    """手書き風の線が入った PNG（署名の代わり）。"""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    import math
    rows = b""
    for y in range(h):
        row = b"\x00"
        for x in range(w):
            wave = 75 + 30 * math.sin(x / 28.0) * math.cos(x / 71.0)
            ink = 40 < x < 480 and abs(y - wave) < 3
            row += b"\x10\x10\x60" if ink else b"\xff\xff\xff"
        rows += row
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def step(msg):
    print(f"\n\033[36m==>\033[0m {msg}", flush=True)


SITE = CFG["sharePoint"]["siteUrl"]
host = urllib.parse.urlparse(SITE).hostname
path = urllib.parse.urlparse(SITE).path
ST = sites_token()
FT = az("https://service.flow.microsoft.com/")

status, site = http("GET", f"{GRAPH}/sites/{host}:{path}?$select=id", ST)
site_id = site["id"]
status, ls = http("GET", f"{GRAPH}/sites/{site_id}/lists?$select=id,name&$top=200", ST)
lists = {l["name"]: l["id"] for l in ls["value"]}
status, me = http("GET", f"{GRAPH}/me?$select=displayName,userPrincipalName,mail", ST)
operator = (me.get("mail") or me["userPrincipalName"]).lower()

# ---- 1. テスト案件 ----------------------------------------------------------
if REUSE:
    step(f"既存のテスト案件 ItemID={REUSE} を使います")
    status, it = http("GET", f"{GRAPH}/sites/{site_id}/lists/{lists['SignatureCases']}/items/{REUSE}"
                             f"?expand=fields(select=CustomerName,Status,DocumentNo)", ST)
    if status >= 300 or it["fields"].get("CustomerName") != "テスト太郎":
        sys.exit("✗ 指定の案件がテスト案件（テスト太郎）ではありません。実データでは実行しない")
    item_id = REUSE
else:
    step("テスト案件を作成します（テスト太郎・顧客メールなし）")
    consent = (ROOT / "data/consent/ConsentText_v1.0.txt").read_text().split("\n")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status, item = http("POST", f"{GRAPH}/sites/{site_id}/lists/{lists['SignatureCases']}/items", ST, {"fields": {
        "Title": "（作成中）",
        "CustomerName": "テスト太郎",
        "CustomerEmail": "",
        "CustomerPhone": "0776-00-0000",
        "Model": "YT5113",
        "SerialNo": "99999",
        "NoSerialNo": False,
        "MaintenanceType": "点検整備",
        "Comment": "疎通テスト。エンジンの掛かりが悪い。\n始動時に白煙が出る。",
        "BranchName": "営業部", "BlockName": "福井ブロック", "SiteName": "福井",
        "Status": "Signed",
        "ConsentId": "CANCELFEE-001", "ConsentTitle": consent[0].strip(), "ConsentVersion": "1.0",
        "ConsentTextSnapshot": "\n".join(consent[2:]).strip(),
        "SignedAt": now, "RegisteredAt": now, "SignerName": "テスト太郎",
        "OperatorEmail": operator, "OperatorName": me.get("displayName", ""),
    }})
    if status >= 300:
        sys.exit(f"✗ テスト案件の作成に失敗（HTTP {status}）: {item}")
    item_id = int(item["id"])
    print(f"    ItemID = {item_id}")

# ---- 2. 送信フローの起動 ----------------------------------------------------
# Power Apps (V2) トリガーは、呼び出し元が Power Apps であることをトークンで確認するため、
# CLI からは呼べない（Flow API 向け・Power Platform API 向けのトークンとも 403/401。実環境で確認）。
# そこで、同じ定義のままトリガーだけ「手動実行（Button）」に変えた一時コピーを作り、
# Flow API から実行する。処理（採番・PDF・保存・メール・エラー処理）は本物と同一。
# 応答（Response）アクションは手動実行では使えないので Compose に置き換える。
# コピーは実行後に削除する。
step("送信フローの一時コピー（手動実行版）を作ります")
DV = az(ORG)
src = next((ROOT / "solution/src/Workflows").glob("*Submit*.json"))
wf = json.loads(src.read_text())
d = wf["properties"]["definition"]
d["triggers"]["manual"]["kind"] = "Button"
# Flow API の実行 API は本文を捨てるため、必須入力のある手動実行フローは入力付きで
# 起動できない（既知の不具合 microsoft/power-platform-skills#625。実環境で確認）。
# テスト用コピーではトリガーの入力を空にし、渡すはずの値をフロー内に直接埋め込む。
data_uri = "data:image/png;base64," + base64.b64encode(signature_png()).decode()
request_id = str(uuid.uuid4())
d["triggers"]["manual"]["inputs"]["schema"] = {"type": "object", "properties": {}, "required": []}
txt = json.dumps(d, ensure_ascii=False)
txt = txt.replace("triggerBody()?['number']", f"int('{item_id}')")
txt = txt.replace("triggerBody()?['text_1']", f"'{data_uri}'")
txt = txt.replace("triggerBody()?['text']", f"'{request_id}'")
assert "triggerBody()" not in txt, "トリガー入力の参照が残っている"
wf["properties"]["definition"] = d = json.loads(txt)


# Response を Compose にしたとき runAfter を失わないよう、先に退避して戻す
def strip_keep(actions):
    for name, a in list(actions.items()):
        if a.get("type") == "Response":
            actions[name] = {"type": "Compose", "inputs": a["inputs"].get("body", {}),
                             "runAfter": a.get("runAfter", {})}
        else:
            if isinstance(a.get("actions"), dict):
                strip_keep(a["actions"])
            if isinstance(a.get("else"), dict):
                strip_keep(a["else"]["actions"])


strip_keep(d["actions"])
TEST_NAME = "YAJ-CancelFee-Submit-E2ETest"
status, created = http("POST", f"{ORG}/api/data/v9.2/workflows", DV, {
    "name": TEST_NAME, "category": 5, "type": 1, "primaryentity": "none",
    "clientdata": json.dumps(wf, ensure_ascii=False),
})
# 作成直後の ID は OData-EntityId ヘッダで返るため、名前で引き直す
flt = urllib.parse.quote(f"name eq '{TEST_NAME}' and category eq 5")
status, found = http("GET", f"{ORG}/api/data/v9.2/workflows?$select=workflowid&$filter={flt}", DV)
if not found.get("value"):
    sys.exit(f"✗ 一時コピーを作れませんでした: {created}")
test_wf = found["value"][0]["workflowid"]
status, body = http("PATCH", f"{ORG}/api/data/v9.2/workflows({test_wf})", DV,
                    {"statecode": 1, "statuscode": 2})
if status >= 300:
    http("DELETE", f"{ORG}/api/data/v9.2/workflows({test_wf})", DV)
    sys.exit(f"✗ 一時コピーをオンにできませんでした: {json.dumps(body, ensure_ascii=False)[:600]}")
print(f"    作成してオンにしました（{TEST_NAME}）")


def cleanup():
    http("PATCH", f"{ORG}/api/data/v9.2/workflows({test_wf})", DV, {"statecode": 0, "statuscode": 1})
    s2, _ = http("DELETE", f"{ORG}/api/data/v9.2/workflows({test_wf})", DV)
    print(f"    一時コピーを削除しました（HTTP {s2}）")


try:
    step("一時コピーを実行します（PDF生成とメール送信で1〜2分かかります）")
    flow = None
    for _ in range(12):
        status, flows = http("GET", f"{FLOW_API}/flows?api-version=2016-11-01", FT)
        flow = next((f for f in flows.get("value", [])
                     if f["properties"]["displayName"] == TEST_NAME), None)
        if flow:
            break
        time.sleep(5)
    if not flow:
        sys.exit("✗ Flow API から一時コピーが見えません")
    payload = {}   # 値はフロー内に埋め込み済み
    t0 = time.time()
    # 手動実行版のトリガーの呼び方を順に試し、最初に受け付けられたところで止める
    status, cb = http("POST", f"{FLOW_API}/flows/{flow['name']}/triggers/manual/listCallbackUrl"
                              f"?api-version=2016-11-01", FT, {})
    callback = cb.get("response", {}).get("value") or cb.get("value")
    attempts = [
        ("コールバックURL（認証なし）", callback, None, payload),
        ("コールバックURL（Flow API トークン）", callback, FT, payload),
        ("実行API（本文をそのまま）",
         f"{FLOW_API}/flows/{flow['name']}/triggers/manual/run?api-version=2016-11-01", FT, payload),
    ]
    accepted = False
    for label, url, tok, body in attempts:
        if not url:
            continue
        status, resp = http("POST", url, tok, body, timeout=600)
        print(f"    {label}: HTTP {status}")
        if status < 300:
            accepted = True
            break
        print(f"      {json.dumps(resp, ensure_ascii=False)[:240]}")
    if not accepted:
        sys.exit("✗ どの呼び方でも起動できませんでした")

    run = None
    while time.time() - t0 < 480:
        time.sleep(10)
        status, runs = http("GET", f"{FLOW_API}/flows/{flow['name']}/runs?api-version=2016-11-01", FT)
        if runs.get("value"):
            run = runs["value"][0]
            st = run["properties"]["status"]
            if st not in ("Running", "Waiting"):
                break
    st = run["properties"]["status"] if run else "不明"
    print(f"    実行結果: {st}（{time.time() - t0:.0f}秒）")

    # 失敗したアクションを特定する
    status, acts = http("GET", f"{FLOW_API}/flows/{flow['name']}/runs/{run['name']}/actions"
                               f"?api-version=2016-11-01", FT)
    for a in acts.get("value", []):
        ap = a["properties"]
        if ap.get("status") in ("Failed", "TimedOut"):
            err = ap.get("error", {})
            print(f"    ✗ {a['name']}: {err.get('code', '')} {str(err.get('message', ''))[:300]}")
    (OUT / "run.json").write_text(json.dumps(acts, ensure_ascii=False, indent=2))
finally:
    cleanup()

# ---- 3. SharePoint 側の結果 --------------------------------------------------
step("SharePoint 側の結果を読み戻します")
status, it = http("GET", f"{GRAPH}/sites/{site_id}/lists/{lists['SignatureCases']}/items/{item_id}"
                         f"?expand=fields", ST)
f = it["fields"]
for k in ("Title", "DocumentNo", "Status", "PdfUrl", "PdfFileName", "SignatureImageUrl",
          "SentAt", "ErrorCode", "ErrorMessage", "FlowRunId"):
    v = f.get(k)
    print(f"    {k:<18} {str(v)[:110] if v not in (None, '') else '（空）'}")

doc_no = f.get("DocumentNo")
status, logs = http("GET", f"{GRAPH}/sites/{site_id}/lists/{lists['SendLog']}/items"
                           f"?expand=fields(select=DocumentNo,SentTo,Kind,Result)&$top=50", ST)
mine = [l["fields"] for l in logs.get("value", []) if l["fields"].get("DocumentNo") == doc_no]
print(f"    送信履歴           {mine if mine else '（なし）'}")

status, cl = http("GET", f"{GRAPH}/sites/{site_id}/lists/{lists['DocumentNumberCounter']}/items"
                         f"?expand=fields(select=Title,CaseId,LastNumber)&$top=50", ST)
claim = [c["fields"] for c in cl.get("value", []) if int(c["fields"].get("CaseId") or 0) == item_id]
print(f"    採番台帳           {claim if claim else '（なし）'}")

# ---- 4. PDF -----------------------------------------------------------------
if not doc_no:
    sys.exit("\n✗ 文書番号が採番されていないため PDF の確認はできません")
step("PDF をダウンロードして中身を確認します")
status, drives = http("GET", f"{GRAPH}/sites/{site_id}/drives?$select=id,name", ST)
drive = next(d for d in drives["value"] if d["name"] == CFG["sharePoint"]["libraries"]["signatureDocs"])
status, pdf = http("GET", f"{GRAPH}/drives/{drive['id']}/root:/{doc_no}.pdf:/content", ST, raw=True)
if status >= 300:
    sys.exit(f"✗ PDF が見つかりません（HTTP {status}）")
pdf_path = OUT / f"{doc_no}.pdf"
pdf_path.write_bytes(pdf)
print(f"    {pdf_path}（{len(pdf):,} バイト）")

text = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, text=True).stdout
(OUT / f"{doc_no}.txt").write_text(text)
checks = {
    "文書番号": doc_no, "宛名": "テスト太郎", "表題": "分解・診断を伴う整備お見積り後のキャンセル料について",
    "拝啓": "拝啓", "費用一覧": "点検整備", "確認文": "私は上記内容について確認いたしました",
    "型式": "YT5113", "機番": "99999", "拠点": "福井ブロック", "確認欄": "確認欄",
}
for k, needle in checks.items():
    print(f"    {'✓' if needle in text.replace(' ', '') or needle in text else '✗'} 本文に「{k}」")
mojibake = sum(text.count(c) for c in ("□", "�", "縺", "繧"))
print(f"    {'✓' if mojibake == 0 else '✗'} 文字化けの痕跡 {mojibake} 文字")

try:
    from pypdf import PdfReader
    r = PdfReader(str(pdf_path))
    images = sum(len(p.images) for p in r.pages)
    print(f"    {'✓' if images else '✗'} 埋め込み画像 {images} 個（署名画像）  / ページ数 {len(r.pages)}")
except Exception as e:
    print(f"    画像の確認に失敗: {e}")

subprocess.run(["pdftoppm", "-png", "-r", "70", str(pdf_path), str(OUT / doc_no)],
               capture_output=True)
pngs = sorted(OUT.glob(f"{doc_no}*.png"))
for p in pngs:
    print(f"    ページ画像: {p}")
print(f"\n出力先: {OUT}")
