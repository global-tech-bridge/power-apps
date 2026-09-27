#!/usr/bin/env python3
"""deploy-settings.json の ConnectionId を、対象環境の接続から自動で埋める。

    python3 scripts/fill-connection-ids.py <環境URL> [設定ファイル]

`pac connection list` の結果をコネクタ（ConnectorId）で突き合わせる。
取り違えを防ぐため、次の場合は埋めずに止める。
  * そのコネクタの接続が1つも無い（ポータルで作る必要がある）
  * そのコネクタの接続が複数ある（どれを使うかは人が決める）
  * 接続の状態が Connected でない
既に ConnectionId が入っているものは上書きしない。
"""
import json
import sys
from pathlib import Path

import yajcli

ENV = sys.argv[1] if len(sys.argv) > 1 else sys.exit("環境URLを指定してください")
SETTINGS = Path(sys.argv[2] if len(sys.argv) > 2 else "solution/deploy-settings.json")

_, out = yajcli.run(["pac", "connection", "list", "--environment", ENV])
conns = []
for line in out.splitlines():
    parts = line.split()
    # Id / Name / API Id / Status の4列（Name に空白は入らない前提。入る場合は末尾2列で判定）
    if len(parts) >= 4 and parts[-2].startswith("/providers/"):
        conns.append({"id": parts[0], "api": parts[-2], "status": parts[-1]})

settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
problems, filled = [], []
for ref in settings.get("ConnectionReferences", []):
    if ref.get("ConnectionId"):
        continue
    matches = [c for c in conns if c["api"].lower() == ref["ConnectorId"].lower()]
    name = ref["ConnectorId"].rsplit("/", 1)[-1]
    if not matches:
        problems.append(f"{name}: 接続がありません。ポータルの「接続」で作成してください")
    elif len(matches) > 1:
        ids = ", ".join(c["id"] for c in matches)
        problems.append(f"{name}: 接続が {len(matches)} 個あります（{ids}）。使うものを手で指定してください")
    elif matches[0]["status"].lower() != "connected":
        problems.append(f"{name}: 接続の状態が {matches[0]['status']} です。ポータルで修復してください")
    else:
        ref["ConnectionId"] = matches[0]["id"]
        filled.append(f"{name} → {matches[0]['id']}")

SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for f in filled:
    print(f"  ✓ {f}")
if problems:
    for p in problems:
        print(f"  ✗ {p}")
    sys.exit(1)
print(f"  接続参照 {len(settings.get('ConnectionReferences', []))} 件すべてに接続IDが入っています")
