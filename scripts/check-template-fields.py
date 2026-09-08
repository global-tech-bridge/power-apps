#!/usr/bin/env python3
"""Word テンプレートの差し込み欄と、フロー手順書の差し込み表が一致しているか検査する。

    python3 scripts/check-template-fields.py

テンプレートを作り直したときに、フロー手順書の表を直し忘れると、
Power Automate の「Word テンプレートの入力」で欄が空のまま出力されてしまう。
.docx はバイナリで差分が読めないため、この検査で担保する。
"""
import re
import sys
import zipfile
from pathlib import Path

TPL = Path("templates/整備キャンセル料確認書.docx")
SPEC = Path("flows/YAJ-CancelFee-Submit/README.md")

xml = zipfile.ZipFile(TPL).read("word/document.xml").decode()
tpl_fields = set(re.findall(r'<w:alias w:val="([^"]+)"', xml))

spec = SPEC.read_text()
start = spec.index("## 7. テンプレート差し込み表")
end = spec.index("## 8. メール本文")
doc_fields = set(re.findall(r"^\| `([A-Za-z]+)` \|", spec[start:end], re.M))

print(f"{TPL.name}: {len(tpl_fields)} 欄")
print(f"{SPEC}: {len(doc_fields)} 欄")

problems = []
for f in sorted(tpl_fields - doc_fields):
    problems.append(f"[手順書に無い] テンプレートの {f} が差し込み表に載っていない")
for f in sorted(doc_fields - tpl_fields):
    problems.append(f"[テンプレートに無い] 差し込み表の {f} がテンプレートに無い")

if problems:
    for x in problems:
        print("✗", x)
    sys.exit(1)
print("✓ テンプレートとフロー手順書の差し込み欄が一致しています")
