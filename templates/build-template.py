#!/usr/bin/env python3
"""PDF生成用 Word テンプレート（整備キャンセル料同意書.docx）を生成する。

.docx はバイナリなので差分レビューができない。テンプレートの構造はこのスクリプトを
唯一の定義元とし、変更はスクリプトを直してから再生成する運用にしている。

    python3 templates/build-template.py

Power Automate の「Word テンプレートの入力」(Populate a Microsoft Word template)
アクションは、Word のコンテンツ コントロールのタイトル（w:alias）を入力欄名として
読み取る。そのためテキストは「プレーンテキスト コンテンツ コントロール」、署名画像は
「画像コンテンツ コントロール」で作る必要があり、python-docx だけでは作れないため
OOXML を直接組み立てている。
"""
import struct
import zlib
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

OUT = Path(__file__).with_name("整備キャンセル料同意書.docx")

# 日本語フォント。Word Online (Business) での PDF 変換時に確実に使えるものを指定する。
# 変換後のPDFが豆腐（□）になる場合は "MS Gothic" や "Meiryo" に変更する。
JP_FONT = "Yu Gothic"

# 差し込み欄の定義: (欄名, 複数行か)
TEXT_FIELDS = [
    ("DocumentNo", False),
    ("SignedAt", False),
    ("CustomerName", False),
    ("CustomerEmail", False),
    ("CustomerPhone", False),
    ("Model", False),
    ("SerialNo", False),
    ("MaintenanceType", False),
    ("Comment", True),
    ("BranchName", False),
    ("BlockName", False),
    ("SiteName", False),
    ("OperatorName", False),
    ("ConsentTitle", False),
    ("ConsentVersion", False),
    ("ConsentText", True),
    ("SignerName", False),
    ("SignedAtFooter", False),
]


# --------------------------------------------------------------------------
# 署名画像コンテンツ コントロールの中に置く placeholder PNG（白地・1×1）
# --------------------------------------------------------------------------
def blank_png(width: int = 1, height: int = 1) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------
# 文書の組み立て
# --------------------------------------------------------------------------
def set_jp_font(run, size=10.5, bold=False, color=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = JP_FONT
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), JP_FONT)
    return run


def para(doc, text="", size=10.5, bold=False, align=None, space_after=4, color=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    if align is not None:
        p.alignment = align
    if text:
        set_jp_font(p.add_run(text), size, bold, color)
    return p


def placeholder(p, field, size=10.5, bold=False):
    """後段で sdt に差し替えるためのマーカー run を追加する。"""
    set_jp_font(p.add_run(f"«{field}»"), size, bold)
    return p


doc = Document()

# 用紙・既定スタイル
section = doc.sections[0]
section.top_margin = Cm(1.8)
section.bottom_margin = Cm(1.6)
section.left_margin = Cm(1.9)
section.right_margin = Cm(1.9)

style = doc.styles["Normal"]
style.font.size = Pt(10.5)
style.font.name = JP_FONT
style.element.rPr.rFonts.set(qn("w:eastAsia"), JP_FONT)

# ---- タイトル ----
para(
    doc,
    "分解・診断を伴う整備お見積り後のキャンセル料に関する同意書",
    size=15,
    bold=True,
    align=WD_ALIGN_PARAGRAPH.CENTER,
    space_after=10,
)

# ---- 文書番号・署名日時（右寄せ）----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
p.paragraph_format.space_after = Pt(10)
set_jp_font(p.add_run("文書番号 "), 9)
placeholder(p, "DocumentNo", 9, bold=True)
set_jp_font(p.add_run("　　署名日時 "), 9)
placeholder(p, "SignedAt", 9)


def info_table(doc, rows):
    """左に見出し、右に差し込み欄を置く2列表。"""
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for label, field, multiline in rows:
        cells = table.add_row().cells
        cells[0].width = Cm(4.2)
        cells[1].width = Cm(12.6)
        lp = cells[0].paragraphs[0]
        lp.paragraph_format.space_after = Pt(2)
        set_jp_font(lp.add_run(label), 10, bold=True)
        vp = cells[1].paragraphs[0]
        vp.paragraph_format.space_after = Pt(2)
        placeholder(vp, field, 10)
    return table


# ---- お客様情報 ----
para(doc, "1. お客様情報", size=11, bold=True, space_after=4)
info_table(
    doc,
    [
        ("お名前", "CustomerName", False),
        ("メールアドレス", "CustomerEmail", False),
        ("電話番号", "CustomerPhone", False),
    ],
)
para(doc, space_after=6)

# ---- 機体・整備情報 ----
para(doc, "2. 機体・整備情報", size=11, bold=True, space_after=4)
info_table(
    doc,
    [
        ("型式", "Model", False),
        ("機番", "SerialNo", False),
        ("整備区分", "MaintenanceType", False),
        ("ご用命事項・コメント", "Comment", True),
    ],
)
para(doc, space_after=6)

# ---- 取扱拠点 ----
para(doc, "3. 取扱拠点", size=11, bold=True, space_after=4)
info_table(
    doc,
    [
        ("支社", "BranchName", False),
        ("ブロック", "BlockName", False),
        ("拠点", "SiteName", False),
        ("担当者", "OperatorName", False),
    ],
)
para(doc, space_after=8)

# ---- 同意事項 ----
para(doc, "4. 同意事項", size=11, bold=True, space_after=2)
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(4)
set_jp_font(p.add_run("（"), 9)
placeholder(p, "ConsentTitle", 9)
set_jp_font(p.add_run("　版 "), 9)
placeholder(p, "ConsentVersion", 9)
set_jp_font(p.add_run("）"), 9)

# 同意文面の全文（署名時点のスナップショット）
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(10)
p.paragraph_format.line_spacing = 1.15
placeholder(p, "ConsentText", 9.5)

# ---- 署名 ----
para(doc, "5. ご署名", size=11, bold=True, space_after=4)
para(
    doc,
    "私は、上記4.の同意事項について説明を受け、その内容を理解し、同意のうえ署名します。",
    size=10,
    space_after=6,
)

sig_table = doc.add_table(rows=0, cols=2)
sig_table.style = "Table Grid"

row = sig_table.add_row().cells
row[0].width = Cm(4.2)
row[1].width = Cm(12.6)
set_jp_font(row[0].paragraphs[0].add_run("署名者お名前"), 10, bold=True)
placeholder(row[1].paragraphs[0], "SignerName", 10)

row = sig_table.add_row().cells
row[0].width = Cm(4.2)
row[1].width = Cm(12.6)
set_jp_font(row[0].paragraphs[0].add_run("ご署名"), 10, bold=True)
sig_para = row[1].paragraphs[0]
sig_para.paragraph_format.space_before = Pt(4)
sig_para.paragraph_format.space_after = Pt(4)

# 画像コンテンツ コントロールの中身になる placeholder 画像
png = Path(__file__).with_name("_signature-placeholder.png")
png.write_bytes(blank_png())
sig_run = sig_para.add_run()
sig_run.add_picture(str(png), width=Cm(11.0), height=Cm(3.2))

row = sig_table.add_row().cells
row[0].width = Cm(4.2)
row[1].width = Cm(12.6)
set_jp_font(row[0].paragraphs[0].add_run("署名日時"), 10, bold=True)
placeholder(row[1].paragraphs[0], "SignedAtFooter", 10)

para(doc, space_after=6)
para(
    doc,
    "本書はヤンマーアグリジャパン株式会社の電子署名アプリで作成された電子文書です。"
    "署名済みPDFが正本として保管されます。",
    size=8,
    color=RGBColor(0x60, 0x5E, 0x5C),
)

doc.save(OUT)

# --------------------------------------------------------------------------
# 後処理: マーカー run を sdt（コンテンツ コントロール）に差し替える
# --------------------------------------------------------------------------
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
doc = Document(OUT)
body = doc.element.body
sdt_id = 1000
converted = set()

multiline = dict(TEXT_FIELDS)

for run in body.iter(f"{W}r"):
    texts = run.findall(f"{W}t")
    if len(texts) != 1 or not texts[0].text:
        continue
    value = texts[0].text
    if not (value.startswith("«") and value.endswith("»")):
        continue
    field = value[1:-1]
    if field not in multiline:
        raise SystemExit(f"未定義の差し込み欄: {field}")

    sdt_id += 1
    sdt = OxmlElement("w:sdt")
    pr = OxmlElement("w:sdtPr")
    for tag, attrs in (
        ("w:alias", {"w:val": field}),
        ("w:tag", {"w:val": field}),
        ("w:id", {"w:val": str(sdt_id)}),
    ):
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        pr.append(el)
    text_el = OxmlElement("w:text")
    if multiline[field]:
        text_el.set(qn("w:multiLine"), "1")
    pr.append(text_el)
    sdt.append(pr)

    content = OxmlElement("w:sdtContent")
    parent = run.getparent()
    index = list(parent).index(run)
    parent.remove(run)
    # プレースホルダとして欄名を残す（Studio/Word で見たときに何の欄か分かる）
    texts[0].text = field
    content.append(run)
    sdt.append(content)
    parent.insert(index, sdt)
    converted.add(field)

# 署名画像を picture コンテンツ コントロールで包む
for run in list(body.iter(f"{W}r")):
    if run.find(f"{W}drawing") is None:
        continue
    sdt_id += 1
    sdt = OxmlElement("w:sdt")
    pr = OxmlElement("w:sdtPr")
    for tag, attrs in (
        ("w:alias", {"w:val": "SignatureImage"}),
        ("w:tag", {"w:val": "SignatureImage"}),
        ("w:id", {"w:val": str(sdt_id)}),
    ):
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        pr.append(el)
    pr.append(OxmlElement("w:picture"))
    sdt.append(pr)
    content = OxmlElement("w:sdtContent")
    parent = run.getparent()
    index = list(parent).index(run)
    parent.remove(run)
    content.append(run)
    sdt.append(content)
    parent.insert(index, sdt)
    converted.add("SignatureImage")
    break

doc.save(OUT)
png.unlink(missing_ok=True)

expected = {f for f, _ in TEXT_FIELDS} | {"SignatureImage"}
missing = expected - converted
if missing:
    raise SystemExit(f"コンテンツ コントロールに変換できなかった欄: {sorted(missing)}")

print(f"{OUT.name}: コンテンツ コントロール {len(converted)} 個")
for f in sorted(converted):
    print(f"  - {f}{' (複数行)' if multiline.get(f) else ''}")
