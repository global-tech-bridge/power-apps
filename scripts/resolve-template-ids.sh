#!/usr/bin/env bash
# Word テンプレートの driveId / fileId を Microsoft Graph から取得し、
# solution/config.json に書き戻す。
#
#   ./scripts/resolve-template-ids.sh
#
# Word Online (Business) の「Microsoft Word テンプレートの入力」は、
# ファイルを表示名ではなく内部ID（drive id と driveItem id）で指定する。
# 画面で作る場合はファイル ピッカーが解決してくれるが、
# CLI でデプロイする場合は自分で解決して定義に埋める必要がある。
#
# 前提: az CLI でテナントにログイン済みであること
#   az login --tenant <テナントID>
#
# ⚠ このスクリプトは実テナントで未検証。失敗する場合は、インポート後に
#   Power Automate の画面で Populate_template のテンプレートを選び直せば済む。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$ROOT/solution/config.json"

command -v az >/dev/null || { echo "az CLI が必要です" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq が必要です（brew install jq）" >&2; exit 1; }

SITE_URL="$(jq -r '.sharePoint.siteUrl' "$CONFIG")"
LIBRARY="$(jq -r '.sharePoint.libraries.docTemplates' "$CONFIG")"
FILE_NAME="$(jq -r '.wordTemplate.fileName' "$CONFIG")"

# https://contoso.sharepoint.com/sites/foo -> contoso.sharepoint.com と /sites/foo
HOST="$(printf '%s' "$SITE_URL" | sed -E 's#^https?://([^/]+).*#\1#')"
PATH_PART="$(printf '%s' "$SITE_URL" | sed -E 's#^https?://[^/]+##')"

echo "==> アクセストークンを取得します"
TOKEN="$(az account get-access-token --resource https://graph.microsoft.com --query accessToken -o tsv)"
g() { curl -sS -H "Authorization: Bearer $TOKEN" "https://graph.microsoft.com/v1.0$1"; }

echo "==> サイトIDを取得します: $HOST$PATH_PART"
SITE_ID="$(g "/sites/${HOST}:${PATH_PART}" | jq -r '.id // empty')"
[ -n "$SITE_ID" ] || { echo "サイトが見つかりません: $SITE_URL" >&2; exit 1; }
echo "    $SITE_ID"

echo "==> ドキュメント ライブラリ '$LIBRARY' のドライブIDを取得します"
DRIVE_ID="$(g "/sites/${SITE_ID}/drives" | jq -r --arg n "$LIBRARY" '.value[] | select(.name==$n) | .id' | head -1)"
[ -n "$DRIVE_ID" ] || { echo "ライブラリが見つかりません: $LIBRARY" >&2; exit 1; }
echo "    $DRIVE_ID"

echo "==> テンプレート '$FILE_NAME' のファイルIDを取得します"
ENCODED="$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$FILE_NAME")"
FILE_ID="$(g "/drives/${DRIVE_ID}/root:/${ENCODED}" | jq -r '.id // empty')"
[ -n "$FILE_ID" ] || { echo "テンプレートが見つかりません: $LIBRARY/$FILE_NAME" >&2; exit 1; }
echo "    $FILE_ID"

echo "==> solution/config.json を更新します"
python3 - "$CONFIG" "$SITE_URL" "$DRIVE_ID" "$FILE_ID" <<'PY'
import json, sys
path, site, drive, file_id = sys.argv[1:5]
cfg = json.load(open(path, encoding="utf-8"))
cfg["wordTemplate"]["source"] = site
cfg["wordTemplate"]["driveId"] = drive
cfg["wordTemplate"]["fileId"] = file_id
open(path, "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
print("    更新しました")
PY

echo
echo "次に ./scripts/deploy.sh を実行してください。"
