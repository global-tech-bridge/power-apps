#!/usr/bin/env python3
"""列（スキーマ）を「Excel からリストを作成」で一括生成するための xlsx を作る。

    python3 scripts/build-schema-import-files.py

生成物: data/import/schema/<リスト名>.xlsx

SharePoint の「＋新規 → リスト → Excel から」は、取り込んだ表のヘッダーから
列を作る。列を1つずつ手で作る代わりにこれを使えば、70列の作成を7回の
取り込みに置き換えられる。

ただしウィザードには次の制約があるため、取り込み後の手当てが必要になる。
このスクリプトは、その手当てを最小にするための工夫を入れてある。

  * 列の種類はデータから推測される
    → 型が分かる値を入れたサンプル行を付ける
  * 選択肢列の選択肢は、データに出てきた値から作られる
    → 全部の選択肢が1回は登場するだけのサンプル行数を用意する
  * Title 列は SharePoint の既定列と衝突する
    → ヘッダーに Title を入れない
  * ユーザー列（Operator）はウィザードで作れない
    → ヘッダーから除外し、手作業で作る列として書き出す
  * リッチテキストOFF・時刻を含める・既定値・必須・インデックスは設定できない
    → data/import/schema/README.md に取り込み後のチェックリストを出力する
"""
import json
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

SCHEMA = json.loads(Path("data/list-schema.json").read_text())
DST = Path("data/import/schema")
DST.mkdir(parents=True, exist_ok=True)

# ここでは作らないリストと、その理由
EXCLUDE = {
    "OrgMaster": "実データ入りの `../OrgMaster.xlsx` が列と105件をまとめて作るため",
    "DocumentNumberCounter": "作る列が `LastNumber` の1つだけで、手で作るほうが速いため",
}

# 取り込み後に削除するサンプル行の目印
MARKER = "★取込後に削除★"

# ウィザードで作れない種類
UNSUPPORTED = {"User"}

# ウィザードの列マッピング画面で選ぶ種類
WIZARD_TYPE = {
    "Text": "1行テキスト",
    "Note": "1行テキスト（取り込み後に複数行テキストへ変更）",
    "Number": "数値",
    "Boolean": "はい/いいえ",
    "DateTime": "日付と時刻",
    "Choice": "選択肢",
    "URL": "ハイパーリンク",
}

# 取り込み後に手当てが必要な設定
FIXUP = {
    "Note": "種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする",
    "DateTime": "含める内容を**日付と時刻**にする",
    "Number": "小数点以下の桁数を**0**にする",
    "Choice": "「値を手動で追加できる」を**いいえ**にし、選択肢が全部揃っているか確認する",
    "Boolean": "",
    "Text": "",
    "URL": "",
}

readme = [
    "# スキーマ取り込み用ファイル（列の一括作成）",
    "",
    "`python3 scripts/build-schema-import-files.py` で `data/list-schema.json` から生成している。",
    "手順は [docs/08-manual-setup.md](../../../docs/08-manual-setup.md) の Part 1-2 方法A。",
    "",
    "各ファイルを SharePoint の **＋新規 → リスト → Excel から** で取り込むと、",
    "ヘッダーから列がまとめて作られる。列を1つずつ手で作るより速い。",
    "",
    "> **サンプル行は取り込み後に必ず削除する。**",
    f"> 1列目に `{MARKER}` と入っている行がサンプル行。",
    "> 選択肢列の選択肢をウィザードに拾わせるために入れてあるだけのダミーである。",
    "",
]

summary_rows = []

for list_name, d in SCHEMA["Lists"].items():
    if list_name in EXCLUDE:
        continue
    cols = [c for c in d["Columns"] if c["Type"] not in UNSUPPORTED]
    skipped = [c for c in d["Columns"] if c["Type"] in UNSUPPORTED]

    # 選択肢を全部登場させるために必要なサンプル行数
    n_rows = max([len(c["Choices"]) for c in cols if c["Type"] == "Choice"] or [1])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = list_name
    header = [c["Name"] for c in cols]
    ws.append(header)

    # 目印は最初のテキスト型の列に入れる。
    # 数値列や日付列に文字列を入れると、ウィザードの型推測が壊れる。
    marker_col = next((c["Name"] for c in cols if c["Type"] == "Text"), None)

    for i in range(n_rows):
        row = []
        for j, c in enumerate(cols):
            t = c["Type"]
            if c["Name"] == marker_col:
                row.append(MARKER)
            elif t == "Choice":
                row.append(c["Choices"][i % len(c["Choices"])])
            elif t == "Number":
                row.append(i + 1)
            elif t == "Boolean":
                row.append(True)
            elif t == "DateTime":
                row.append(datetime(2026, 1, 1, 9, 0))
            elif t == "Note":
                row.append("サンプル本文")
            else:
                row.append("サンプル")
        ws.append(row)

    ref = f"A1:{get_column_letter(len(header))}{n_rows + 1}"
    table = Table(displayName=list_name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(table)

    fill = PatternFill("solid", fgColor="DEEBF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    for i, c in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(26, len(c["Name"]) + 6))
    ws.freeze_panes = "A2"

    wb.save(DST / f"{list_name}.xlsx")

    # --- README: リストごとの取り込み表と後始末 ---
    readme += [
        f"## {list_name}",
        "",
        f"`{list_name}.xlsx` … 作られる列 **{len(cols)}** / サンプル行 **{n_rows}**",
        "",
        "### ウィザードの列マッピングで選ぶ種類",
        "",
        "| 列 | 選ぶ種類 |",
        "|---|---|",
    ]
    for c in cols:
        readme.append(f"| `{c['Name']}` | {WIZARD_TYPE[c['Type']]} |")
    readme.append("")

    fixups = []
    for c in cols:
        f = FIXUP[c["Type"]]
        if f:
            fixups.append(f"- [ ] `{c['Name']}` … {f}")
        if c.get("Required"):
            fixups.append(f"- [ ] `{c['Name']}` … **必須**にする")
        if c.get("Default") == "1":
            fixups.append(f"- [ ] `{c['Name']}` … 既定値を**はい**にする")
        elif c.get("Default") == "0" and c["Type"] == "Boolean":
            fixups.append(f"- [ ] `{c['Name']}` … 既定値を**いいえ**にする")
    for c in skipped:
        fixups.insert(0, f"- [ ] `{c['Name']}` … **{c['Type']}** 型なのでウィザードでは作れない。"
                         f"手作業で「ユーザーまたはグループ」列として追加する")
    idx = [c["Name"] for c in d["Columns"] if c.get("Indexed")]
    if idx:
        fixups.append("- [ ] インデックスを作る: " + " ".join(f"`{x}`" for x in idx))
    if marker_col:
        fixups.append(f"- [ ] `{marker_col}` が `{MARKER}` の行 **{n_rows} 件**を削除する")
    else:
        fixups.append(f"- [ ] サンプル行 **{n_rows} 件**を削除する")

    readme += ["### 取り込み後の手当て", ""] + fixups + [""]

    summary_rows.append((list_name, len(cols), len(skipped), n_rows, len(fixups)))

# --- 先頭にサマリを差し込む ---
summary = ["## 一覧", "", "| リスト | 作られる列 | 手作業の列 | サンプル行 | 取り込み後の手当て |",
           "|---|---:|---:|---:|---:|"]
total_cols = total_manual = 0
for name, ncols, nskip, nrows, nfix in summary_rows:
    summary.append(f"| [`{name}.xlsx`]({name}.xlsx) | {ncols} | {nskip} | {nrows} | {nfix} 項目 |")
    total_cols += ncols
    total_manual += nskip
# 除外したリストの列数も合算して、全体像を示す
excluded_wizard = len(SCHEMA["Lists"]["OrgMaster"]["Columns"])   # OrgMaster.xlsx が作る
excluded_manual = len(SCHEMA["Lists"]["DocumentNumberCounter"]["Columns"])
grand_total = sum(len(v["Columns"]) for v in SCHEMA["Lists"].values())
by_wizard = total_cols + excluded_wizard
by_hand = total_manual + excluded_manual

summary += ["", f"このフォルダの {len(summary_rows)} ファイルで **{total_cols} 列**。",
            f"`../OrgMaster.xlsx` の {excluded_wizard} 列を足すと、"
            f"全 **{grand_total} 列**のうち **{by_wizard} 列**がウィザードで作られる。",
            "", f"手作業で作るのは残る **{by_hand} 列**だけ。", "",
            "| 手作業で作る列 | 種類 | 理由 |", "|---|---|---|",
            "| `SignatureCases.Operator` | ユーザーまたはグループ | ウィザードがユーザー列を作れない |",
            "| `DocumentNumberCounter.LastNumber` | 数値 | 1列だけなので取り込む意味がない |",
            "",
            "### ここに無いリスト", "", "| リスト | 理由 |", "|---|---|"]
for name, reason in EXCLUDE.items():
    summary.append(f"| `{name}` | {reason} |")
summary.append("")

readme = readme[:11] + [""] + summary + readme[11:]
(DST / "README.md").write_text("\n".join(readme))

print(f"{DST}/ に {len(summary_rows)} ファイル")
for name, ncols, nskip, nrows, nfix in summary_rows:
    print(f"  {name:<24} 列 {ncols:>2}  手作業 {nskip}  サンプル {nrows}行  手当て {nfix}項目")
print(f"\nこのフォルダで {total_cols} 列 / ../OrgMaster.xlsx で {excluded_wizard} 列 "
      f"= 全 {grand_total} 列のうち {by_wizard} 列をウィザードで作成")
print(f"手作業で作るのは {by_hand} 列（SignatureCases.Operator, DocumentNumberCounter.LastNumber）")
