#!/usr/bin/env bash
# YAJ 整備キャンセル料 確認書アプリ — キャンバスアプリの CLI デプロイ
#
#   ./scripts/deploy-app.sh <環境URL>
#   ./scripts/deploy-app.sh https://org12345.crm7.dynamics.com
#
# やること
#   1. pac の認証を確認（deploy.sh と同じく、別テナントへの誤デプロイを防ぐ）
#   2. アプリの静的検査（名前の一意性・相互参照・括弧・レイアウト）
#   3. 環境にあるアプリを .msapp でダウンロードし、SourceCode 形式で展開
#   4. Src/*.pa.yaml をリポジトリの内容に差し替えて再パック
#   5. アプリ用ソリューションをエクスポートし、中の .msapp を差し替えてインポート
#      （キャンバスアプリはインポート時に公開される）
#
# なぜ Studio で保存した版を土台にするのか
#   pa.yaml だけからは .msapp を作れない（Studio で一度開いて検証されたアプリが前提）。
#   また、データソースの接続情報（References/DataSources.json）は Studio で
#   追加したときにしか作られない。そこで「Studio で保存した版」をダウンロードし、
#   画面と数式（Src/*.pa.yaml）だけを差し替える。
#
# 前提（初回だけ画面で行う。docs/10-cli-deployment.md の 9 章）
#   - Studio で空のアプリを作り、データソース（SharePoint リスト・ライブラリ、フロー3つ）を追加して保存
#   - そのアプリをソリューション（既定 YAJCancelFeeApp）に追加
#   - データソースを足したら Studio で「公開」まで行う（download は最後に公開した版を返す）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENVIRONMENT="${1:-}"
APP_NAME="${YAJ_APP_NAME:-YAJ 整備キャンセル料 確認書}"
APP_SOLUTION="${YAJ_APP_SOLUTION:-YAJCancelFeeApp}"
APP_SRC="${YAJ_APP_SRC:-apps/yaj-cancelfee-signature/Src}"

info()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[!]\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

command -v pac >/dev/null || die "pac CLI が見つかりません。dotnet tool install -g microsoft.powerapps.cli.tool"
[ -n "$ENVIRONMENT" ] || die "環境URLを引数で指定してください: ./scripts/deploy-app.sh https://<組織>.crm7.dynamics.com"

# ---- 1. 認証 --------------------------------------------------------------
PROFILE="${YAJ_PAC_PROFILE:-yanmar-test}"
info "認証プロファイルを確認します（想定: $PROFILE）"
ACTIVE_LINE="$(pac auth list 2>/dev/null | awk '$2=="*"')"
ACTIVE_NAME="$(printf '%s' "$ACTIVE_LINE" | awk '{print $4}')"
[ -n "$ACTIVE_NAME" ] || die "有効な認証プロファイルがありません: pac auth create --deviceCode --name $PROFILE"
if [ "$ACTIVE_NAME" != "$PROFILE" ]; then
  warn "有効なプロファイルが '$ACTIVE_NAME' です。想定は '$PROFILE' です。"
  die "別テナントへの誤デプロイを防ぐため中止します: pac auth select --name $PROFILE"
fi
printf '    %s\n' "$ACTIVE_LINE"

# ---- 2. 静的検査 ----------------------------------------------------------
info "アプリの定義を検査します"
python3 scripts/check-references.py "$APP_SRC"
python3 scripts/check-formula-balance.py >/dev/null
python3 scripts/check-layout.py >/dev/null
python3 scripts/check-text-fit.py "$APP_SRC"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/yaj-app.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# ---- 3. ダウンロードと展開 -------------------------------------------------
info "環境のアプリをダウンロードします: $APP_NAME"
pac canvas download --environment "$ENVIRONMENT" --name "$APP_NAME" \
  --file-name "$WORK/base.msapp" >/dev/null
pac canvas unpack --msapp "$WORK/base.msapp" --sources "$WORK/src" --layout SourceCode >/dev/null

# 土台（最後に公開した版）に、数式が使うデータソースがそろっているか。
# 足りないと Studio で「Name isn't valid」になる。Studio で追加して「公開」まで行うこと。
python3 - "$WORK/src" <<'PY'
import json, sys, zipfile
from pathlib import Path

REQUIRED = [
    "SignatureCases", "OrgMaster", "ConsentMaster", "AppAdmins", "SignatureImages",
    "Office365Users", "YAJ-CancelFee-Submit", "YAJ-CancelFee-Resend", "YAJ-CancelFee-Delete",
]
msapr = next(Path(sys.argv[1]).glob("*.msapr"))
with zipfile.ZipFile(msapr) as z:
    name = next(n for n in z.namelist() if n.replace("\\", "/").endswith("References/DataSources.json"))
    ds = json.loads(z.read(name))["DataSources"]
have = {d.get("Name") for d in ds}
missing = [r for r in REQUIRED if r not in have]
if missing:
    sys.exit("土台のアプリにデータソースが足りません: " + ", ".join(missing)
             + "\n  Studio で追加して保存し、「公開」まで行ってから再実行してください。"
             + "\n  （あるもの: " + ", ".join(sorted(n for n in have if n)) + "）")
print("    データソース: そろっています（" + str(len(REQUIRED)) + " 件）")
PY

# ---- 4. Src を差し替えて再パック --------------------------------------------
info "画面と数式をリポジトリの内容に差し替えます"
python3 - "$APP_SRC" "$WORK/src/Src" <<'PY'
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
# EditorState（画面の並び順）は _EditorState.pa.yaml の1か所だけに書く。
# 2か所にあると「Only one module may specify the EditorState」で開けない。
for f in dst.glob("*.pa.yaml"):
    f.unlink()
names = []
for f in sorted(src.glob("*.pa.yaml")):
    (dst / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    names.append(f.name)
print("    " + " ".join(names))
PY
pac canvas pack --sources "$WORK/src" --msapp "$WORK/app.msapp" --layout SourceCode --overwrite \
  | grep -v "must be validated first" || true
[ -s "$WORK/app.msapp" ] || die "パックに失敗しました"

# ---- 5. ソリューションに入れてインポート ------------------------------------
info "ソリューション $APP_SOLUTION をエクスポートします"
pac solution export --environment "$ENVIRONMENT" --name "$APP_SOLUTION" \
  --path "$WORK/solution.zip" --overwrite >/dev/null

python3 - "$WORK/solution.zip" "$WORK/app.msapp" "$WORK/solution-new.zip" "$APP_NAME" <<'PY'
import re
import sys
import zipfile

src, msapp, out, app_name = sys.argv[1:]
with zipfile.ZipFile(src) as z:
    custom = z.read("customizations.xml").decode("utf-8")
    apps = re.findall(
        r"<CanvasApp>.*?<Name>([^<]+)</Name>.*?<DisplayName>([^<]*)</DisplayName>.*?</CanvasApp>",
        custom, re.S,
    )
    targets = [n for n, d in apps if d == app_name]
    if len(targets) != 1:
        sys.exit(f"ソリューション内に '{app_name}' のキャンバスアプリが1つだけある前提です: {apps}")
    doc = f"CanvasApps/{targets[0]}_DocumentUri.msapp"
    if doc not in z.namelist():
        sys.exit(f"{doc} がソリューションにありません")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
        for item in z.infolist():
            data = open(msapp, "rb").read() if item.filename == doc else z.read(item.filename)
            w.writestr(item, data)
print(f"    差し替え: {doc}")
PY

info "インポートします（環境: $ENVIRONMENT）"
# --publish-changes は付けない。キャンバスアプリはインポート時に公開され、
# 「すべてのカスタマイズの公開」はこの環境で10分以上戻らなかった（2026-09-28）。
pac solution import --environment "$ENVIRONMENT" --path "$WORK/solution-new.zip" \
  --force-overwrite --max-async-wait-time 30 | grep -v -E "Processing asynchronous|^$"

info "完了しました。Studio で開き直すと差し替えた画面が読み込まれます。"
echo "    編集中の Studio が開いている場合は、閉じてから開き直すこと（古い版で上書き保存しないように）"
