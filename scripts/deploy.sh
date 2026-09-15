#!/usr/bin/env bash
# YAJ 整備キャンセル料 確認書アプリ — フローのCLIデプロイ
#
#   ./scripts/deploy.sh <環境URL>
#   ./scripts/deploy.sh https://org12345.crm7.dynamics.com
#
# やること
#   1. pac の認証を確認（未認証なら pac auth create を促す）
#   2. solution/config.json からソリューション ソースを生成
#   3. pac solution pack で zip 化
#   4. 接続参照のマッピング設定ファイルを生成（初回のみ）
#   5. pac solution import でインポートし、変更を発行
#
# 前提
#   - pac CLI                dotnet tool install -g microsoft.powerapps.cli.tool
#   - Python 3 + 依存        pip install openpyxl python-docx jsonschema pyyaml
#   - solution/config.json の siteUrl を実環境に変更済みであること
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SOLUTION_NAME="$(python3 -c "import json;print(json.load(open('solution/config.json'))['solution']['uniqueName'])")"
ZIP="solution/${SOLUTION_NAME}.zip"
SETTINGS="solution/deploy-settings.json"
ENVIRONMENT="${1:-}"

info()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[!]\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

command -v pac >/dev/null || die "pac CLI が見つかりません。dotnet tool install -g microsoft.powerapps.cli.tool"

# ---- 1. 認証 --------------------------------------------------------------
info "認証プロファイルを確認します"
if ! pac auth list 2>/dev/null | grep -q '\*'; then
  warn "有効な認証プロファイルがありません。次を実行してから再実行してください:"
  echo "    pac auth create --deviceCode --environment <環境URL>"
  exit 1
fi
pac auth list | sed 's/^/    /'

# ---- 2. ソース生成 --------------------------------------------------------
info "ソリューション ソースを生成します"
python3 scripts/build-solution.py

SITE_URL="$(python3 -c "import json;print(json.load(open('solution/config.json'))['sharePoint']['siteUrl'])")"
case "$SITE_URL" in
  *CONTOSO*) die "solution/config.json の siteUrl が既定値のままです。実環境のURLに変更してください。" ;;
esac

# ---- 3. パック ------------------------------------------------------------
info "ソリューションをパックします"
rm -f "$ZIP"
pac solution pack --zipfile "$ZIP" --folder solution/src --packagetype Unmanaged \
  | grep -v "^Processing Component" || true
[ -f "$ZIP" ] || die "パックに失敗しました"
ls -la "$ZIP" | sed 's/^/    /'

# ---- 4. 接続参照のマッピング ----------------------------------------------
if [ ! -f "$SETTINGS" ]; then
  info "接続参照の設定ファイルを生成します: $SETTINGS"
  pac solution create-settings --solution-zip "$ZIP" --settings-file "$SETTINGS"
  warn "生成された $SETTINGS を開き、各接続参照に接続IDを入れてから再実行してください。"
  warn "接続IDは Power Apps ポータル → 接続 → 対象の接続を開いたURL末尾のGUIDです。"
  echo
  cat "$SETTINGS" | sed 's/^/    /'
  exit 2
fi

# 未入力の接続IDが残っていないか
if python3 - "$SETTINGS" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
missing = [c.get("LogicalName") for c in s.get("ConnectionReferences", [])
           if not c.get("ConnectionId")]
if missing:
    print("未設定の接続参照: " + ", ".join(map(str, missing)))
    sys.exit(1)
PY
then :; else
  die "$SETTINGS に未設定の接続参照があります。ConnectionId を埋めてください。"
fi

# ---- 5. インポート --------------------------------------------------------
info "インポートします（環境: ${ENVIRONMENT:-認証プロファイルの既定}）"
IMPORT_ARGS=(--path "$ZIP" --settings-file "$SETTINGS"
             --activate-plugins --force-overwrite --publish-changes
             --max-async-wait-time 30)
[ -n "$ENVIRONMENT" ] && IMPORT_ARGS+=(--environment "$ENVIRONMENT")
pac solution import "${IMPORT_ARGS[@]}"

info "完了しました。"
cat <<'EOS'

    次にやること（Power Automate の画面で確認）
      1. 3つのフローがインポートされ、オンになっていること
      2. YAJ-CancelFee-Submit の トリガー → 設定 → 同時実行制御 が
         オン・並列度1 になっていること（定義に含めているが必ず目視確認）
      3. Populate_template と Convert_to_pdf の Word テンプレート指定が
         正しいファイルを指していること
         （solution/config.json の driveId / fileId を解決していない場合は
           ここで選び直す。scripts/resolve-template-ids.sh も参照）
      4. アプリ側でフローを再接続（Power Apps Studio → データ → フロー）

EOS
