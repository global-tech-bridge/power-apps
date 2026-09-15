#!/usr/bin/env python3
"""生成したソリューション ソースを、インポート前に静的検査する。

    python3 scripts/check-solution.py

検査するもの
  1. 未解決のプレースホルダが定義に残っていないか
  2. runAfter が参照するアクションが同じスコープに存在するか
  3. 式が参照する outputs('X') / body('X') の X が定義済みのアクションか
  4. 接続参照の論理名が、定義JSONと Customizations.xml で一致しているか
  5. Word テンプレートの差し込み欄が、実テンプレートの欄と一致しているか
"""
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "solution/src"
TPL = ROOT / "templates/整備キャンセル料確認書.docx"
CFG = json.loads((ROOT / "solution/config.json").read_text(encoding="utf-8"))
MODE = CFG.get("pdfMode", "html")
# 配布状態（siteUrl が既定値のまま）かどうか
UNCONFIGURED = "CONTOSO" in CFG["sharePoint"]["siteUrl"]

problems = []


def walk_actions(actions, scope_path=""):
    """(スコープ内の名前一覧, そのスコープのアクション辞書) を再帰的に返す。"""
    yield scope_path, actions
    for name, action in actions.items():
        for key in ("actions",):
            if isinstance(action.get(key), dict):
                yield from walk_actions(action[key], f"{scope_path}/{name}")
        if isinstance(action.get("else"), dict) and isinstance(action["else"].get("actions"), dict):
            yield from walk_actions(action["else"]["actions"], f"{scope_path}/{name}/else")


for wf in sorted(SRC.glob("Workflows/*.json")):
    doc = json.loads(wf.read_text(encoding="utf-8"))
    props = doc["properties"]
    definition = props["definition"]
    label = wf.name.split("-")[0]
    blob = json.dumps(doc, ensure_ascii=False)

    # --- 1. プレースホルダ ---
    # config.json が既定値のままなら「まだ設定していない」だけなので
    # エラーにはしない。一部だけ設定済みのときは取りこぼしなので止める。
    if not UNCONFIGURED:
        for ph in sorted(set(re.findall(r"[A-Z_]*PLACEHOLDER|CONTOSO", blob))):
            problems.append(f"[{label}] 未解決のプレースホルダ: {ph}")

    # --- 2 & 3. アクション参照 ---
    all_names = set()
    for _, actions in walk_actions(definition["actions"]):
        all_names |= set(actions)

    for scope_path, actions in walk_actions(definition["actions"]):
        names = set(actions)
        for name, action in actions.items():
            for dep in (action.get("runAfter") or {}):
                if dep not in names:
                    problems.append(
                        f"[{label}] {scope_path}/{name}: runAfter '{dep}' が同じスコープに無い"
                    )
    for ref in set(re.findall(r"(?:outputs|body)\('([^']+)'\)", blob)):
        if ref not in all_names:
            problems.append(f"[{label}] 式が参照する '{ref}' というアクションが存在しない")

    # --- 4. 接続参照 ---
    declared = {v["connection"]["connectionReferenceLogicalName"]
                for v in props["connectionReferences"].values()}
    customizations = (SRC / "Other/Customizations.xml").read_text(encoding="utf-8")
    for logical in declared:
        if logical not in customizations:
            problems.append(f"[{label}] 接続参照 {logical} が Customizations.xml に無い")

    # --- 5a. HTML→.doc 方式: HTML が組み立てられているか ---
    if MODE == "html" and "Compose_Html" in all_names:
        html = definition["actions"]["Try"]["actions"]["Need_pdf"]["actions"]["Compose_Html"][
            "inputs"
        ]
        for needed in ("<html", "charset=utf-8", "@page", "</html>"):
            if needed not in html:
                problems.append(f"[{label}] 生成HTMLに '{needed}' が無い")
        # 日本語フォント指定が無いと変換後のPDFが文字化けする
        if "Yu Gothic" not in html and "MS Gothic" not in html:
            problems.append(f"[{label}] 生成HTMLに日本語フォント指定が無い")
        # 署名画像の埋め込み
        if "data:image/png;base64," not in html:
            problems.append(f"[{label}] 生成HTMLに署名画像の data URI が無い")
        # 確認書に必要な項目（要件定義 10章）がすべて差し込まれているか
        for field in ("CustomerName", "Model", "MaintenanceType", "Comment",
                      "BranchName", "BlockName", "SiteName", "OperatorName",
                      "ConsentTitle", "ConsentTextSnapshot", "ConsentVersion",
                      "SignedAt", "SignerName"):
            if field not in html:
                problems.append(f"[{label}] 生成HTMLに {field} が差し込まれていない")
        if "varDocumentNo" not in html:
            problems.append(f"[{label}] 生成HTMLに文書番号が差し込まれていない")
        # BOM を付けずに .doc を作ると Word が文字コードを取り違える
        doc_body = definition["actions"]["Try"]["actions"]["Need_pdf"]["actions"][
            "Create_temp_doc"
        ]["inputs"]["parameters"]["body"]
        if "%EF%BB%BF" not in doc_body:
            problems.append(f"[{label}] 中間 .doc に UTF-8 BOM を付けていない")

    # --- 5b. Word テンプレート方式: 差し込み欄が一致しているか ---
    if MODE == "wordTemplate" and "Populate_template" in all_names and TPL.exists():
        xml = zipfile.ZipFile(TPL).read("word/document.xml").decode()
        tpl_fields = set(re.findall(r'<w:alias w:val="([^"]+)"', xml))
        used = set(re.findall(r'"dynamicFileSchema/([^"]+)"', blob))
        for f in sorted(used - tpl_fields):
            problems.append(f"[{label}] テンプレートに無い差し込み欄を指定: {f}")
        for f in sorted(tpl_fields - used):
            problems.append(f"[{label}] テンプレートの差し込み欄が未指定: {f}")

n = len(list(SRC.glob("Workflows/*.json")))
print(f"フロー定義 {n} 件を検査しました（PDF生成方式: {MODE}）")
if UNCONFIGURED:
    print("  ※ solution/config.json が配布状態です。"
          "デプロイ前に sharePoint.siteUrl を実環境のURLに変更してください。")
if problems:
    for p in sorted(set(problems)):
        print("✗", p)
    print(f"\n{len(set(problems))} problem(s)")
    sys.exit(1)
print("✓ ソリューション定義に不整合はありません")
