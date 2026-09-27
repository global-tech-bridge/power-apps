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
import os
import re
import sys
import zipfile
from pathlib import Path

import yajcli  # noqa: E402,F401  Windows でも出力を UTF-8 にする（✓ などは cp932 に無い）

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "solution/src"
TPL = ROOT / "templates/整備キャンセル料確認書.docx"
# YAJ_CONFIG で別の設定ファイルを指定できる（テスト用テナントなど）。
# 既定の solution/config.json は Yanmar 向けの配布状態を保つ。
CFG_PATH = Path(os.environ.get("YAJ_CONFIG", ROOT / "solution/config.json"))
CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
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


def _expr_segments(value):
    """文字列から Workflow 式の部分を取り出す。

    "@expr"  → 全体が式
    "..@{expr}.." → @{ } の中が式（'...' 内の } は無視する）
    """
    if value.startswith("@") and not value.startswith("@{") and not value.startswith("@@"):
        yield value[1:]
        return
    i = 0
    while True:
        j = value.find("@{", i)
        if j < 0:
            return
        k, depth, in_str = j + 2, 1, False
        while k < len(value):
            c = value[k]
            if in_str:
                if c == "'":
                    if k + 1 < len(value) and value[k + 1] == "'":
                        k += 2
                        continue
                    in_str = False
            elif c == "'":
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        yield value[j + 2:k]
        i = k + 1


def _expr_balance(expr):
    """括弧の対応を見る。'...'（'' はエスケープ）の中は数えない。"""
    pairs = {")": "(", "]": "["}
    stack, in_str, i = [], False, 0
    while i < len(expr):
        c = expr[i]
        if in_str:
            if c == "'":
                if i + 1 < len(expr) and expr[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
        elif c == "'":
            in_str = True
        elif c in "([":
            stack.append(c)
        elif c in ")]":
            if not stack or stack[-1] != pairs[c]:
                return f"対応しない '{c}'（{i}文字目付近）"
            stack.pop()
        i += 1
    if in_str:
        return "閉じていない引用符"
    if stack:
        return f"閉じられていない '{stack[-1]}' が {len(stack)} 個"
    return None


def _walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


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

    # --- 3b. 式の括弧の対応 ---
    # 閉じ括弧が1つ多い式は、インポートは通るがフローをオンにする時点で
    # 「Unable to parse template language expression」で弾かれる（実環境で確認）。
    for where, value in _walk_strings(definition):
        for expr in _expr_segments(value):
            err = _expr_balance(expr)
            if err:
                action = where.split("/inputs")[0].split("/")[-1]
                problems.append(f"[{label}] {action}: 式の括弧 — {err}: {expr[:80]}…")

    # --- 3c. SharePoint の項目の更新・作成にはリストの必須列をすべて渡す ---
    # 「項目の更新」も含め、コネクタは必須列（Title と Required の列）を毎回要求する。
    # 渡さないとフローをオンにする時点で
    # 「missing required property 'item/Title'」「'item/CustomerName'」で弾かれる（実環境で確認）。
    list_schema = json.loads((ROOT / "data/list-schema.json").read_text(encoding="utf-8"))["Lists"]
    for _, actions in walk_actions(definition["actions"]):
        for name, action in actions.items():
            inputs = action.get("inputs")
            host = inputs.get("host") or {} if isinstance(inputs, dict) else {}
            if host.get("connectionName") == "shared_sharepointonline" and \
                    host.get("operationId") in ("PatchItem", "PostItem"):
                params = inputs.get("parameters", {})
                table = params.get("table")
                required = ["Title"] + [c["Name"] for c in list_schema.get(table, {}).get("Columns", [])
                                        if c.get("Required")]
                for col in required:
                    if f"item/{col}" not in params:
                        problems.append(f"[{label}] {name}: {host['operationId']}（{table}）に必須列 item/{col} が無い")

    # --- 3c-2. SharePoint「ファイルの作成」の出力で、存在しない項目を参照していないか ---
    # 以前は {Link} を参照して URL が常に空になっていた（実環境で確認）。
    # 実際の出力項目は実行結果で確認したもの。
    SP_CREATEFILE_OUT = {"ItemId", "Id", "Name", "DisplayName", "Path", "LastModified", "Size",
                         "MediaType", "IsFolder", "ETag", "FileLocator"}
    create_file_actions = {n for _, acts in walk_actions(definition["actions"]) for n, a in acts.items()
                           if isinstance(a.get("inputs"), dict)
                           and a["inputs"].get("host", {}).get("connectionName") == "shared_sharepointonline"
                           and a["inputs"]["host"].get("operationId") == "CreateFile"}
    for act, field in set(re.findall(r"outputs\('([^']+)'\)\?\['body/([^'\]]+)'\]", blob)):
        if act in create_file_actions and field not in SP_CREATEFILE_OUT:
            problems.append(f"[{label}] {act} の出力に '{field}' は無い（あるのは {', '.join(sorted(SP_CREATEFILE_OUT))}）")

    # --- 3d. 同時実行制御と同期の「応答」は併用できない ---
    # フローをオンにする時点で InvalidConcurrencyConfiguration で弾かれる（実環境で確認）。
    has_response = any(a.get("type") == "Response"
                       for _, acts in walk_actions(definition["actions"]) for a in acts.values())
    for tname, trig in definition.get("triggers", {}).items():
        if has_response and trig.get("runtimeConfiguration", {}).get("concurrency"):
            problems.append(f"[{label}] トリガー {tname}: 同時実行制御は同期の応答アクションと併用できない")

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
