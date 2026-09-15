#!/usr/bin/env python3
"""フローが生成する確認書HTMLに、サンプル値を流し込んでプレビューを作る。

    python3 scripts/preview-document.py [出力先ディレクトリ]

テナントが無くても、PDFになる前のレイアウトをブラウザと Word で確認できる。
出力:
    preview.html  ブラウザで開いて内容を確認する
    preview.doc   Word で開くと、実際の変換結果に近い見え方になる
                  （フローが OneDrive に作るファイルと同じ中身＋UTF-8 BOM）

pdfMode が wordTemplate のときは、この方式ではHTMLを作らないので何もしない。
"""
import base64
import json
import re
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp")
CFG = json.loads((ROOT / "solution/config.json").read_text(encoding="utf-8"))

if CFG.get("pdfMode") != "html":
    sys.exit("pdfMode が html ではありません。プレビューは HTML→.doc 方式のときだけ作れます。")

wf = json.loads(next((ROOT / "solution/src/Workflows").glob("*Submit*.json")).read_text())
html = wf["properties"]["definition"]["actions"]["Try"]["actions"]["Need_pdf"]["actions"][
    "Compose_Html"
]["inputs"]


def sample_signature(width=520, height=150):
    """署名画像の代わりに、手書き風の線が入った PNG を作る。"""

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    rows = b""
    for y in range(height):
        row = b"\x00"
        for x in range(width):
            ink = 60 < y < 110 and 40 < x < 480 and (x + y * 3) % 37 < 6
            row += b"\x20\x20\x20" if ink else b"\xff\xff\xff"
        rows += row
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


consent_lines = (ROOT / "data/consent/ConsentText_v1.0.txt").read_text(
    encoding="utf-8"
).split("\n")

SAMPLE = {
    "varDocumentNo": "20260916-001",
    "varSignatureBase64": base64.b64encode(sample_signature()).decode(),
    "CustomerName": "テスト太郎",
    "BranchName": "営業部",
    "BlockName": "福井ブロック",
    "SiteName": "福井",
    "OperatorName": "山田 花子",
    "ConsentTitle": consent_lines[0].strip(),
    "ConsentVersion": "1.0",
    "Model": "YT5113",
    "MaintenanceType/Value": "点検整備",
}
CONSENT_BODY = "<br>".join(consent_lines[2:]).strip()


def resolve(match):
    expr = match.group(1)
    for key, value in SAMPLE.items():
        if key in expr:
            return value
    if "ConsentTextSnapshot" in expr:
        return CONSENT_BODY
    if "SignedAt" in expr:
        return "2026年09月16日 14:30"
    if "SerialNo" in expr or "NoSerialNo" in expr:
        return "12345"
    if "Comment" in expr:
        return "エンジンの掛かりが悪い。始動時に白煙が出る。"
    if "SignerName" in expr:
        return "テスト太郎"
    return "（未置換）"


rendered = re.sub(r"@\{(.*?)\}", resolve, html, flags=re.S)
unresolved = rendered.count("（未置換）")

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "preview.html").write_text(rendered, encoding="utf-8")
# フローは UTF-8 BOM を付けて .doc を作る。同じものを再現する。
(OUT / "preview.doc").write_text("﻿" + rendered, encoding="utf-8")

print(f"HTML {len(html)} 文字 / 未置換の式 {unresolved} 個")
print(f"  {OUT / 'preview.html'}   ブラウザで開いて内容を確認")
print(f"  {OUT / 'preview.doc'}    Word で開いて変換後の見え方を確認")
if unresolved:
    sys.exit("未置換の式が残っています。SAMPLE に値を追加してください。")
