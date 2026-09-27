#!/usr/bin/env python3
"""YAJ 整備キャンセル料 確認書アプリ — フローの CLI デプロイ（Windows / macOS 共通）

    python scripts/deploy.py https://<組織>.crm7.dynamics.com

やること
  1. pac の認証を確認（別テナントへの誤デプロイを防ぐ）
  2. 設定ファイル（YAJ_CONFIG、既定 solution/config.json）からソリューション ソースを生成
  3. pac solution pack で zip 化
  4. 接続参照の設定ファイルを生成し、対象環境の接続から接続 ID を自動で埋める
  5. pac solution import でインポートし、変更を発行
  6. フローをオンにする（オンにできない場合は理由を表示して止まる）

前提
  - pac CLI / Azure CLI / Python 3 + pyyaml jsonschema openpyxl
  - 設定ファイルの sharePoint.siteUrl を実環境に変更済みであること
"""
import json
import sys

import yajcli
from yajcli import ROOT, die, info, run, warn

ENV = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else die(
    "環境 URL を引数で指定してください: python scripts/deploy.py https://<組織>.crm7.dynamics.com")
CFG_PATH, CFG = yajcli.load_config()
ZIP = ROOT / "solution" / f"{CFG['solution']['uniqueName']}.zip"
SETTINGS = ROOT / "solution" / "deploy-settings.json"

# ---- 1. 認証 ------------------------------------------------------------------
yajcli.check_pac_profile()

# ---- 2. ソース生成 ------------------------------------------------------------
info(f"ソリューション ソースを生成します（設定: {CFG_PATH.name}）")
if "CONTOSO" in CFG["sharePoint"]["siteUrl"]:
    die(f"{CFG_PATH} の siteUrl が既定値のままです。実環境の URL に変更してください。")
yajcli.python("build-solution.py")
yajcli.python("check-solution.py")

# ---- 3. パック ----------------------------------------------------------------
info("ソリューションをパックします")
ZIP.unlink(missing_ok=True)
code, out = run(["pac", "solution", "pack", "--zipfile", str(ZIP), "--folder", str(ROOT / "solution/src"),
                 "--packagetype", "Unmanaged"])
print("\n".join(l for l in out.splitlines() if not l.startswith("Processing Component")))
if not ZIP.exists():
    die("パックに失敗しました")
print(f"    {ZIP.relative_to(ROOT)}  {ZIP.stat().st_size:,} bytes")

# ---- 4. 接続参照のマッピング --------------------------------------------------
# 毎回 zip から作り直す。以前の設定ファイルを使い回すと、発行者の接頭辞を
# 変えたときに古い論理名のまま取り込まれ、新しい接続参照に接続が入らない（実環境で確認）。
info(f"接続参照の設定ファイルを生成します: {SETTINGS.relative_to(ROOT)}")
SETTINGS.unlink(missing_ok=True)
run(["pac", "solution", "create-settings", "--solution-zip", str(ZIP), "--settings-file", str(SETTINGS)], check=True)

# 対象環境の接続から接続 ID を自動で埋める。接続が無い・複数ある場合は取り違えを防ぐため止まる。
info("接続 ID を対象環境の接続から埋めます")
code, _ = yajcli.python("fill-connection-ids.py", ENV, SETTINGS, check=False)
if code != 0:
    warn("接続が足りないか、どれを使うか決められませんでした。")
    die(f"ポータルの「接続」で作成するか、{SETTINGS.name} の ConnectionId を手で入れてから再実行してください。", 2)
settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
missing = [c.get("LogicalName") for c in settings.get("ConnectionReferences", []) if not c.get("ConnectionId")]
if missing:
    die(f"{SETTINGS.name} に未設定の接続参照があります: {', '.join(map(str, missing))}")

# ---- 5. インポート ------------------------------------------------------------
info(f"インポートします（環境: {ENV}）")
ok = yajcli.import_solution(ENV, ZIP, CFG["solution"]["uniqueName"], [
    "--settings-file", str(SETTINGS), "--activate-plugins", "--force-overwrite", "--publish-changes"])
if not ok:
    die("インポートに失敗しました。上のメッセージを確認してください（権限が足りない場合は preflight.py で分かる）")

# ---- 6. フローをオンにする ----------------------------------------------------
# --activate-plugins では再インポート時にフローがオンにならなかった（実環境で確認）。
# オンにする時点で定義が検証されるので、インポートでは見逃される式の誤りもここで分かる。
info("フローをオンにします")
if not yajcli.az_token(ENV):
    warn("Azure CLI にサインインしていないため、フローをオンにできません。")
    warn(f"az login の後に python scripts/activate-flows.py {ENV} を実行するか、")
    die("Power Automate の画面で3つのフローをオンにしてください。", 3)
code, _ = yajcli.python("activate-flows.py", ENV, check=False)
if code != 0:
    die("オンにできないフローがあります。上の理由を確認してください。")

info("完了しました。")
print("""
    次にやること
      1. OneDrive に中間ファイル用のフォルダ（設定の oneDrive.tempFolder）があること
      2. アプリを入れる: python scripts/deploy-app.py <環境URL>
         （初回は土台のアプリを Studio で作る。手順は docs/11-production-deployment.md の 7）
""")
