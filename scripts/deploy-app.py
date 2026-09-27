#!/usr/bin/env python3
"""YAJ 整備キャンセル料 確認書アプリ — キャンバスアプリの CLI デプロイ（Windows / macOS 共通）

    python scripts/deploy-app.py https://<組織>.crm7.dynamics.com

やること
  1. pac の認証を確認（別テナントへの誤デプロイを防ぐ）
  2. アプリの静的検査（名前の一意性・相互参照・括弧・レイアウト・文字のはみ出し）
  3. アプリ用ソリューションが無ければ作る。土台のアプリが入っていなければ作り方を示して止まる
  4. 環境のアプリ（最後に公開した版）を .msapp でダウンロードし、SourceCode 形式で展開
  5. データソースがそろっているか確かめ、Src/*.pa.yaml をリポジトリの内容に差し替えて再パック
  6. アプリ用ソリューションをエクスポートし、中の .msapp を差し替えてインポート
     （キャンバスアプリはインポート時に公開される）

なぜ Studio で保存した版を土台にするのか
  pa.yaml だけからは .msapp を作れない（Studio で一度開いて検証されたアプリが前提）。
  また、データソースの接続情報（References/DataSources.json）は Studio で
  追加したときにしか作られない。そこで「Studio で保存・公開した版」をダウンロードし、
  画面と数式（Src/*.pa.yaml）だけを差し替える。

環境変数（任意）
  YAJ_APP_NAME      アプリの表示名（既定「YAJ 整備キャンセル料 確認書」）
  YAJ_APP_SOLUTION  アプリ用ソリューションの一意名（既定 YAJCancelFeeApp）
  YAJ_APP_SRC       差し込む pa.yaml の場所（既定 apps/yaj-cancelfee-signature/Src）
"""
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import yajcli
from yajcli import ROOT, die, info, run

ENV = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else die(
    "環境 URL を引数で指定してください: python scripts/deploy-app.py https://<組織>.crm7.dynamics.com")
APP_NAME = os.environ.get("YAJ_APP_NAME", "YAJ 整備キャンセル料 確認書")
APP_SOLUTION = os.environ.get("YAJ_APP_SOLUTION", "YAJCancelFeeApp")
APP_SRC = ROOT / os.environ.get("YAJ_APP_SRC", "apps/yaj-cancelfee-signature/Src")
CFG_PATH, CFG = yajcli.load_config()

# 数式が使うデータソース。土台（最後に公開した版）に無いと Studio で「Name isn't valid」になる
REQUIRED_SOURCES = [
    "SignatureCases", "OrgMaster", "ConsentMaster", "AppAdmins", "SignatureImages",
    "Office365Users", "YAJ-CancelFee-Submit", "YAJ-CancelFee-Resend", "YAJ-CancelFee-Delete",
]

# ---- 1. 認証 ------------------------------------------------------------------
yajcli.check_pac_profile()

# ---- 2. 静的検査 --------------------------------------------------------------
info("アプリの定義を検査します")
yajcli.python("check-references.py", APP_SRC)
yajcli.python("check-formula-balance.py", capture=True)
yajcli.python("check-layout.py", capture=True)
yajcli.python("check-text-fit.py", APP_SRC)

# ---- 3. アプリ用ソリューションと土台のアプリ ----------------------------------
# 発行者はフロー用ソリューションの初回インポートで作られるので、deploy.py を先に流すこと。
info(f"アプリ用ソリューション {APP_SOLUTION} を確認します")
token = yajcli.az_token(ENV)
if not token:
    die("Azure CLI で Dataverse のトークンを取れません。az login をやり直してください")
call = yajcli.dataverse(ENV, token)

st, sol = call("GET", f"solutions?$select=solutionid&$filter=uniquename eq '{APP_SOLUTION}'")
if st != 200:
    die(f"ソリューションを確認できません（HTTP {st}）: {sol.get('error', {}).get('message', sol)}")
if not sol["value"]:
    pub = CFG["solution"]["publisherUniqueName"]
    st, p = call("GET", f"publishers?$select=publisherid&$filter=uniquename eq '{pub}'")
    if not p.get("value"):
        die(f"発行者 {pub} がまだありません。先に python scripts/deploy.py でフローを入れてください（発行者が作られる）")
    st, r = call("POST", "solutions", {
        "uniquename": APP_SOLUTION, "friendlyname": f"{CFG['solution']['displayName']}（アプリ）",
        "version": "1.0.0.0", "publisherid@odata.bind": f"/publishers({p['value'][0]['publisherid']})",
    })
    if st >= 300:
        die(f"ソリューションを作れません（HTTP {st}）: {r.get('error', {}).get('message', r)}")
    print(f"    ソリューション {APP_SOLUTION} を作りました")
    st, sol = call("GET", f"solutions?$select=solutionid&$filter=uniquename eq '{APP_SOLUTION}'")
sid = sol["value"][0]["solutionid"]

st, comps = call("GET", f"solutioncomponents?$select=objectid&$filter=_solutionid_value eq {sid} and componenttype eq 300")
names = []
for c in comps.get("value", []):
    st, app = call("GET", f"canvasapps({c['objectid']})?$select=displayname")
    if st == 200:
        names.append(app.get("displayname"))
if APP_NAME not in names:
    die(f"""ソリューション {APP_SOLUTION} に、土台のアプリ「{APP_NAME}」がありません（あるもの: {names or 'なし'}）。
  初回だけ画面で作ります（docs/11-production-deployment.md の 7-2）:
    1. make.powerapps.com → ソリューション → {CFG['solution']['displayName']}（アプリ）→ 新規 → アプリ → キャンバス アプリ
       名前「{APP_NAME}」、形式「タブレット」
    2. 設定 → 表示: 縦向き・4:3（768×1024）／ 全般: データ行の制限 2000
    3. データを追加: SharePoint のリスト7つ＋ライブラリ SignatureImages、Office 365 ユーザー、
       Power Automate のフロー3つ
    4. 保存して「公開」→ Studio を閉じて、このスクリプトを再実行""")
print(f"    土台のアプリ「{APP_NAME}」が入っています")

with tempfile.TemporaryDirectory(prefix="yaj-app-") as tmp:
    work = Path(tmp)

    # ---- 4. ダウンロードと展開 ------------------------------------------------
    info(f"環境のアプリをダウンロードします: {APP_NAME}")
    run(["pac", "canvas", "download", "--environment", ENV, "--name", APP_NAME,
         "--file-name", str(work / "base.msapp")], check=True)
    run(["pac", "canvas", "unpack", "--msapp", str(work / "base.msapp"), "--sources", str(work / "src"),
         "--layout", "SourceCode"], check=True)

    # ---- 5. データソースの確認と Src の差し替え ----------------------------------
    msapr = next((work / "src").glob("*.msapr"))
    with zipfile.ZipFile(msapr) as z:
        ds_name = next(n for n in z.namelist() if n.replace("\\", "/").endswith("References/DataSources.json"))
        have = {d.get("Name") for d in json.loads(z.read(ds_name))["DataSources"]}
    missing = [r for r in REQUIRED_SOURCES if r not in have]
    if missing:
        die("土台のアプリにデータソースが足りません: " + ", ".join(missing)
            + "\n  Studio で追加して保存し、「公開」まで行ってから再実行してください。"
            + "\n  （あるもの: " + ", ".join(sorted(n for n in have if n)) + "）")
    print(f"    データソース: そろっています（{len(REQUIRED_SOURCES)} 件）")

    info("画面と数式をリポジトリの内容に差し替えます")
    dst = work / "src" / "Src"
    # EditorState（画面の並び順）は _EditorState.pa.yaml の1か所だけに書く。
    # 2か所にあると「Only one module may specify the EditorState」で開けない。
    for f in dst.glob("*.pa.yaml"):
        f.unlink()
    copied = []
    for f in sorted(APP_SRC.glob("*.pa.yaml")):
        # 改行は LF にそろえる（Windows で CRLF になっていても Studio は読めるが、差分を増やさない）
        (dst / f.name).write_bytes(f.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
        copied.append(f.name)
    print("    " + " ".join(copied))
    code, out = run(["pac", "canvas", "pack", "--sources", str(work / "src"), "--msapp", str(work / "app.msapp"),
                     "--layout", "SourceCode", "--overwrite"])
    if not (work / "app.msapp").exists() or (work / "app.msapp").stat().st_size == 0:
        die("パックに失敗しました\n" + out[-2000:])

    # ---- 6. ソリューションに入れてインポート --------------------------------------
    info(f"ソリューション {APP_SOLUTION} をエクスポートします")
    run(["pac", "solution", "export", "--environment", ENV, "--name", APP_SOLUTION,
         "--path", str(work / "solution.zip"), "--overwrite"], check=True)
    with zipfile.ZipFile(work / "solution.zip") as z:
        custom = z.read("customizations.xml").decode("utf-8")
        apps = re.findall(r"<CanvasApp>.*?<Name>([^<]+)</Name>.*?<DisplayName>([^<]*)</DisplayName>.*?</CanvasApp>",
                          custom, re.S)
        targets = [n for n, d in apps if d == APP_NAME]
        if len(targets) != 1:
            die(f"ソリューション内に「{APP_NAME}」のキャンバスアプリが1つだけある前提です: {apps}")
        doc = f"CanvasApps/{targets[0]}_DocumentUri.msapp"
        if doc not in z.namelist():
            die(f"{doc} がソリューションにありません")
        with zipfile.ZipFile(work / "solution-new.zip", "w", zipfile.ZIP_DEFLATED) as w:
            for item in z.infolist():
                data = (work / "app.msapp").read_bytes() if item.filename == doc else z.read(item.filename)
                w.writestr(item, data)
    print(f"    差し替え: {doc}")

    info(f"インポートします（環境: {ENV}）")
    # --publish-changes は付けない。キャンバスアプリはインポート時に公開され、
    # 「すべてのカスタマイズの公開」はテスト用テナントで10分以上戻らなかった（2026-09-28）。
    if not yajcli.import_solution(ENV, work / "solution-new.zip", APP_SOLUTION, ["--force-overwrite"]):
        die("インポートに失敗しました。上のメッセージを確認してください")

info("完了しました。Studio で開き直すと差し替えた画面が読み込まれます。")
print("    編集中の Studio が開いている場合は、閉じてから開き直すこと（古い版で上書き保存しないように）")
