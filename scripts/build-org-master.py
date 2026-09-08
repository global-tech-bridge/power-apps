#!/usr/bin/env python3
"""部門マスタ.xlsx -> SharePoint「組織マスタ(OrgMaster)」投入用 CSV を生成する。

変換ルール（docs/07-open-issues.md D-01 / D-02 参照）:
  * BranchName  <- 部門名（営業部 / 販売部 / 系統推進部）
  * BlockName   <- ブロック名。空欄の部門には疑似ブロックを補完する。
  * SiteName    <- 拠点名
  * SortOrder   <- xlsx の行順（画面の並び順を原本と一致させるため）
"""
import csv
import sys
from pathlib import Path

import openpyxl

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../部門マスタ.xlsx")
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/OrgMaster.csv")

# ブロックが設定されていない部門に補完する疑似ブロック（D-02）
PSEUDO_BLOCK = {
    "販売部": ("EAO2ZZ", "販売部（ブロック未設定）"),
    "系統推進部": ("EAO3ZZ", "系統推進部（ブロック未設定）"),
}

wb = openpyxl.load_workbook(SRC, data_only=True)
ws = wb["Sheet1"]

rows = []
for site_code, site_name, block_code, block_name, division in (
    r[1:6] for r in ws.iter_rows(min_row=4, values_only=True)
):
    if not site_code:
        continue
    if not block_code:
        block_code, block_name = PSEUDO_BLOCK[division]
    rows.append(
        {
            "Title": site_code,
            "BranchName": division,
            "BlockCode": block_code,
            "BlockName": block_name,
            "SiteCode": site_code,
            "SiteName": site_name,
            "IsActive": "TRUE",
            "SortOrder": len(rows) + 1,
        }
    )

DST.parent.mkdir(parents=True, exist_ok=True)
with DST.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

print(f"{DST}: {len(rows)} 行")
print("支社(部門):", sorted({r['BranchName'] for r in rows}))
print("ブロック数:", len({r['BlockCode'] for r in rows}))
