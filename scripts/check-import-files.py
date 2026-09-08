#!/usr/bin/env python3
"""インポート用ファイルが list-schema.json / OrgMaster.csv とずれていないか検査する。

    python3 scripts/check-import-files.py

xlsx はバイナリで差分が読めないため、スキーマを直したのに取り込みファイルを
作り直し忘れる、という事故をここで止める。検査するのは次の4点。

  1. schema/*.xlsx のヘッダーが list-schema.json の列と一致している
     （SharePoint 既定の Title と、ウィザードで作れない User 列は除く）
  2. 選択肢列の選択肢が、サンプル行に全部登場している
     （ウィザードはデータに出てきた値からしか選択肢を作らない）
  3. サンプル行の目印がテキスト列に入っている
     （数値列や日付列に文字列が入ると型推測が壊れる）
  4. OrgMaster.xlsx / OrgMaster_grid.tsv の件数が OrgMaster.csv と一致している
"""
import csv
import json
import sys
from pathlib import Path

import openpyxl

SCHEMA = json.loads(Path("data/list-schema.json").read_text())
IMPORT = Path("data/import")
MARKER = "★取込後に削除★"
SKIP_TYPES = {"User"}

problems = []


def header_and_rows(path):
    ws = openpyxl.load_workbook(path).active
    rows = list(ws.iter_rows(values_only=True))
    return list(rows[0]), rows[1:]


# --- 1〜3: schema/*.xlsx ---
for path in sorted((IMPORT / "schema").glob("*.xlsx")):
    name = path.stem
    if name not in SCHEMA["Lists"]:
        problems.append(f"[{name}] list-schema.json に無いリストのファイルがある")
        continue
    cols = [c for c in SCHEMA["Lists"][name]["Columns"] if c["Type"] not in SKIP_TYPES]
    expected = [c["Name"] for c in cols]
    header, rows = header_and_rows(path)

    if header != expected:
        problems.append(
            f"[{name}] ヘッダーが定義と違う\n"
            f"      余分: {sorted(set(header) - set(expected)) or 'なし'}\n"
            f"      不足: {sorted(set(expected) - set(header)) or 'なし'}"
        )
        continue

    if "Title" in header:
        problems.append(f"[{name}] ヘッダーに Title がある（SharePoint 既定列と衝突する）")

    for c in cols:
        if c["Type"] != "Choice":
            continue
        i = header.index(c["Name"])
        seen = {r[i] for r in rows}
        missing = set(c["Choices"]) - seen
        if missing:
            problems.append(
                f"[{name}.{c['Name']}] 選択肢 {sorted(missing)} がサンプル行に登場しない"
                f"（ウィザードがその選択肢を作れない）"
            )

    marker_cols = [header[i] for i, v in enumerate(rows[0]) if v == MARKER]
    if not marker_cols:
        problems.append(f"[{name}] サンプル行に目印 {MARKER} が無い")
    else:
        types = {c["Name"]: c["Type"] for c in cols}
        for mc in marker_cols:
            if types[mc] != "Text":
                problems.append(
                    f"[{name}.{mc}] 目印がテキスト列以外（{types[mc]}）に入っている"
                    f"。型推測が壊れる"
                )

# --- 4: OrgMaster の件数 ---
with (Path("data/OrgMaster.csv")).open(encoding="utf-8-sig", newline="") as f:
    csv_rows = list(csv.DictReader(f))

_, xlsx_rows = header_and_rows(IMPORT / "OrgMaster.xlsx")
if len(xlsx_rows) != len(csv_rows):
    problems.append(
        f"[OrgMaster.xlsx] {len(xlsx_rows)} 行。OrgMaster.csv は {len(csv_rows)} 行"
    )

tsv = (IMPORT / "OrgMaster_grid.tsv").read_text(encoding="utf-8").rstrip("\n").split("\n")
if len(tsv) - 1 != len(csv_rows):
    problems.append(
        f"[OrgMaster_grid.tsv] {len(tsv) - 1} 行。OrgMaster.csv は {len(csv_rows)} 行"
    )
if "IsActive" in tsv[0].split("\t"):
    problems.append("[OrgMaster_grid.tsv] IsActive 列が入っている（貼り付けの相性が悪い）")

n_schema = len(list((IMPORT / "schema").glob("*.xlsx")))
print(f"schema/ {n_schema} ファイル / OrgMaster {len(csv_rows)} 行")
if problems:
    for p in problems:
        print("✗", p)
    sys.exit(1)
print("✓ インポート用ファイルは定義と一致しています")
