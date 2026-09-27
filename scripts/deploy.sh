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
#   4. 接続参照の設定ファイルを生成し、対象環境の接続から接続IDを自動で埋める
#   5. pac solution import でインポートし、変更を発行
#   6. フローをオンにする（オンにできない場合は理由を表示して止まる）
#
# 前提
#   - pac CLI                dotnet tool install -g microsoft.powerapps.cli.tool
#   - Python 3 + 依存        pip install openpyxl python-docx jsonschema pyyaml
#   - solution/config.json の siteUrl を実環境に変更済みであること
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# YAJ_CONFIG で別の設定ファイルを使える（テスト用テナントなど）
CONFIG="${YAJ_CONFIG:-solution/config.json}"
export YAJ_CONFIG="$CONFIG"
SOLUTION_NAME="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['solution']['uniqueName'])" "$CONFIG")"
ZIP="solution/${SOLUTION_NAME}.zip"
SETTINGS="solution/deploy-settings.json"
ENVIRONMENT="${1:-}"

info()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[!]\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

command -v pac >/dev/null || die "pac CLI が見つかりません。dotnet tool install -g microsoft.powerapps.cli.tool"

# ---- 1. 認証 --------------------------------------------------------------
# 同じマシンに別案件（別テナント）の pac プロファイルがあると、
# 「たまたま有効だったプロファイル」に向けてデプロイしてしまう。
# 必ず名前付きのプロファイルを明示し、それが有効になっていることを確かめる。
PROFILE="${YAJ_PAC_PROFILE:-yanmar-test}"
info "認証プロファイルを確認します（想定: $PROFILE）"
ACTIVE_LINE="$(pac auth list 2>/dev/null | awk '$2=="*"')"
ACTIVE_NAME="$(printf '%s' "$ACTIVE_LINE" | awk '{print $4}')"
if [ -z "$ACTIVE_NAME" ]; then
  warn "有効な認証プロファイルがありません。次を実行してから再実行してください:"
  echo "    pac auth create --deviceCode --name $PROFILE"
  exit 1
fi
if [ "$ACTIVE_NAME" != "$PROFILE" ]; then
  warn "有効なプロファイルが '$ACTIVE_NAME' です。想定は '$PROFILE' です。"
  warn "別案件のテナントにデプロイする事故を防ぐため中止します。切り替えるには:"
  echo "    pac auth select --name $PROFILE"
  echo "    （別名のプロファイルを使う場合は YAJ_PAC_PROFILE=<名前> を指定）"
  exit 1
fi
printf '    %s\n' "$ACTIVE_LINE"
[ -n "$ENVIRONMENT" ] || die "環境URLを引数で指定してください: ./scripts/deploy.sh https://<組織>.crm7.dynamics.com"

# ---- 2. ソース生成 --------------------------------------------------------
info "ソリューション ソースを生成します"
python3 scripts/build-solution.py

SITE_URL="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['sharePoint']['siteUrl'])" "$CONFIG")"
case "$SITE_URL" in
  *CONTOSO*) die "$CONFIG の siteUrl が既定値のままです。実環境のURLに変更してください。" ;;
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
fi

# 対象環境の接続から接続IDを自動で埋める。
# 接続が無い・複数ある場合は取り違えを防ぐため止まる。
info "接続IDを対象環境の接続から埋めます"
if ! python3 scripts/fill-connection-ids.py "$ENVIRONMENT" "$SETTINGS"; then
  warn "接続が足りないか、どれを使うか決められませんでした。"
  warn "ポータルの「接続」で作成するか、$SETTINGS の ConnectionId を手で入れてから再実行してください。"
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

# ---- 6. フローをオンにする -------------------------------------------------
# --activate-plugins では再インポート時にフローがオンにならなかった（実環境で確認）。
# オンにする時点で定義が検証されるので、インポートでは見逃される式の誤りもここで分かる。
info "フローをオンにします"
if command -v az >/dev/null && az account show >/dev/null 2>&1; then
  if ! python3 scripts/activate-flows.py "$ENVIRONMENT"; then
    die "オンにできないフローがあります。上の理由を確認してください。"
  fi
else
  warn "Azure CLI にサインインしていないため、フローをオンにできません。"
  warn "az login の後に python3 scripts/activate-flows.py $ENVIRONMENT を実行するか、"
  warn "Power Automate の画面で3つのフローをオンにしてください。"
  exit 3
fi

info "完了しました。"
cat <<'EOS'

    次にやること
      1. OneDrive に中間ファイル用のフォルダ（config の oneDrive.tempFolder）があること
      2. アプリ側でフローを追加（Power Apps Studio → データ → フロー）

EOS
