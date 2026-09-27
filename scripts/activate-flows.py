#!/usr/bin/env python3
"""インポートしたクラウドフローをオンにする。オンにできない理由も表示する。

    python3 scripts/activate-flows.py <環境URL>

pac solution import の --activate-plugins では、既に入っているフローの再インポートで
オンにならなかった（実環境で確認）。pac にフローをオンにするコマンドは無いため、
Dataverse Web API で workflow の statecode を 1（アクティブ）にする。

フローをオンにする時点で Power Automate が定義を検証するので、インポートでは
通ってしまう式の誤り（括弧の不一致、必須パラメータ漏れなど）がここで分かる。

認証は Azure CLI（AZURE_CONFIG_DIR の設定に従う）。
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

ORG = (sys.argv[1] if len(sys.argv) > 1 else sys.exit("環境URLを指定してください")).rstrip("/")
PREFIX = "YAJ-CancelFee-"

import yajcli  # noqa: E402,F401  Windows でも出力を UTF-8 にする（✓ などは cp932 に無い）

token = yajcli.az_token(ORG) or sys.exit("Azure CLI で Dataverse のトークンを取れません。az login をやり直してください")


def call(method, path, body=None):
    req = urllib.request.Request(
        f"{ORG}/api/data/v9.2/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "OData-Version": "4.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            txt = r.read().decode()
            return r.status, json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        return e.code, json.loads(txt) if txt.startswith("{") else {"raw": txt}


flt = urllib.parse.quote(f"category eq 5 and startswith(name,'{PREFIX}')")
status, body = call("GET", f"workflows?$select=name,statecode,workflowid&$filter={flt}")
if status != 200:
    sys.exit(f"フロー一覧の取得に失敗（HTTP {status}）: {body}")

flows = sorted(body["value"], key=lambda f: f["name"])
if not flows:
    sys.exit(f"'{PREFIX}' で始まるフローが見つかりません")

failed = 0
for f in flows:
    if f["statecode"] == 1:
        print(f"  ✓ {f['name']}: 既にオン")
        continue
    status, body = call("PATCH", f"workflows({f['workflowid']})", {"statecode": 1, "statuscode": 2})
    if status in (200, 204):
        print(f"  ✓ {f['name']}: オンにしました")
    else:
        failed += 1
        msg = body.get("error", {}).get("message", body)
        print(f"  ✗ {f['name']}: オンにできません")
        print(f"      {str(msg)[:700]}")

sys.exit(1 if failed else 0)
