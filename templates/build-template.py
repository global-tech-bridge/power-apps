#!/usr/bin/env python3
"""PDF生成用 Word テンプレート（整備キャンセル料確認書.docx）を生成する。

    python3 templates/build-template.py

元資料「分解・診断を伴う整備お見積り後のキャンセル料について.docx」の書式
（A4縦・宛名／差出人・中央揃えの表題・書簡本文・右寄せの確認欄）を再現し、
差し込み欄をコンテンツ コントロールにしたもの。

.docx はバイナリなので差分レビューができない。テンプレートの構造はこのスクリプトを
唯一の定義元とし、変更はスクリプトを直してから再生成する運用にしている。

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
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

OUT = Path(__file__).with_name("整備キャンセル料確認書.docx")

# 日本語フォント。Word Online (Business) での PDF 変換時に確実に使えるものを指定する。
# 変換後のPDFが豆腐（□）になる場合は "MS Gothic" や "Meiryo" に変更する。
JP_FONT = "Yu Gothic"

# 差し込み欄の定義: 欄名 -> 複数行か
TEXT_FIELDS = {
    "DocumentNo": False,
    "CustomerName": False,
    "BranchName": False,
    "BlockName": False,
    "SiteName": False,
    "OperatorName": False,
    "ConsentTitle": False,
    "ConsentText": True,     # 書簡本文（費用一覧と確認文を含む署名時点のスナップショット）
    "Model": False,
    "SerialNo": False,
    "MaintenanceType": False,
    "Comment": True,
    "SignerName": False,
    "SignedAt": False,
    "ConsentVersion": False,
}


def blank_png(width: int = 1, height: int = 1) -> bytes:
    """画像コンテンツ コントロールの中に置く placeholder PNG（白地）。"""

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


def para(doc, text="", size=10.5, bold=False, align=None, space_after=4,
         color=None, line_spacing=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    if align is not None:
        p.alignment = align
    if line_spacing is not None:
        p.paragraph_format.line_spacing = line_spacing
    if text:
        set_jp_font(p.add_run(text), size, bold, color)
    return p


def placeholder(p, field, size=10.5, bold=False):
    """後段で sdt に差し替えるためのマーカー run を追加する。"""
    set_jp_font(p.add_run(f"«{field}»"), size, bold)
    return p


def no_borders(table):
    """罫線を消す（確認欄の見出しと値を揃えるためのレイアウト用の表）。"""
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        borders.append(el)
    tbl_pr.append(borders)


doc = Document()

# ---- 用紙。元資料は A4・上3.5cm/他3.0cm だが、署名欄まで収めるため余白を詰めている ----
section = doc.sections[0]
section.page_width = Cm(21.0)
section.page_height = Cm(29.7)
section.top_margin = Cm(2.2)
section.bottom_margin = Cm(1.8)
section.left_margin = Cm(2.2)
section.right_margin = Cm(2.2)

style = doc.styles["Normal"]
style.font.size = Pt(10.5)
style.font.name = JP_FONT
style.element.rPr.rFonts.set(qn("w:eastAsia"), JP_FONT)

# ---- 文書番号（右上・小さく） ----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
p.paragraph_format.space_after = Pt(2)
set_jp_font(p.add_run("文書番号 "), 9)
placeholder(p, "DocumentNo", 9, bold=True)

# ---- 宛名（左）----
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(8)
placeholder(p, "CustomerName", 11)
set_jp_font(p.add_run("　様"), 11)

# ---- 差出人（右）----
para(doc, "ヤンマーアグリジャパン株式会社", size=10,
     align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=1)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
p.paragraph_format.space_after = Pt(1)
set_jp_font(p.add_run("中部近畿支社　"), 10)
placeholder(p, "BranchName", 10)
set_jp_font(p.add_run("　"), 10)
placeholder(p, "BlockName", 10)
set_jp_font(p.add_run("　"), 10)
placeholder(p, "SiteName", 10)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
p.paragraph_format.space_after = Pt(12)
set_jp_font(p.add_run("担当　"), 10)
placeholder(p, "OperatorName", 10)

# ---- 表題（中央・太字）----
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(12)
placeholder(p, "ConsentTitle", 13.5, bold=True)

# ---- 書簡本文（署名時点のスナップショット）----
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(12)
p.paragraph_format.line_spacing = 1.2
placeholder(p, "ConsentText", 10)

# ---- 確認欄 ----
para(doc, "確認欄", size=11, bold=True, space_after=4)

rows = [
    ("型式", "Model", False),
    ("機番", "SerialNo", False),
    ("整備区分", "MaintenanceType", False),
    ("ご用命事項", "Comment", True),
    ("お名前", "SignerName", False),
    ("日付", "SignedAt", False),
]
table = doc.add_table(rows=0, cols=2)
table.style = "Table Grid"
for label, field, _ in rows:
    cells = table.add_row().cells
    cells[0].width = Cm(3.6)
    cells[1].width = Cm(13.0)
    lp = cells[0].paragraphs[0]
    lp.paragraph_format.space_after = Pt(2)
    set_jp_font(lp.add_run(label), 10, bold=True)
    vp = cells[1].paragraphs[0]
    vp.paragraph_format.space_after = Pt(2)
    placeholder(vp, field, 10)

# ご署名（画像コンテンツ コントロール）
cells = table.add_row().cells
cells[0].width = Cm(3.6)
cells[1].width = Cm(13.0)
set_jp_font(cells[0].paragraphs[0].add_run("ご署名"), 10, bold=True)
sig_para = cells[1].paragraphs[0]
sig_para.paragraph_format.space_before = Pt(4)
sig_para.paragraph_format.space_after = Pt(4)

png = Path(__file__).with_name("_signature-placeholder.png")
png.write_bytes(blank_png())
sig_para.add_run().add_picture(str(png), width=Cm(11.5), height=Cm(3.4))

# ---- フッター ----
para(doc, space_after=4)
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(0)
set_jp_font(
    p.add_run("本書はヤンマーアグリジャパン株式会社 中部近畿支社の電子署名アプリで作成された電子文書です。"
              "この確認書のPDFが正本として保管されます。（確認文面 版 "), 8,
    color=RGBColor(0x60, 0x5E, 0x5C),
)
placeholder(p, "ConsentVersion", 8)
set_jp_font(p.add_run("）"), 8, color=RGBColor(0x60, 0x5E, 0x5C))

doc.save(OUT)

# --------------------------------------------------------------------------
# 後処理: マーカー run を sdt（コンテンツ コントロール）に差し替える
# --------------------------------------------------------------------------
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
doc = Document(OUT)
body = doc.element.body
sdt_id = 1000
converted = set()


def wrap_in_sdt(run, field, kind):
    """run を w:sdt で包む。kind は 'text' / 'multiline' / 'picture'。"""
    global sdt_id
    sdt_id += 1
    sdt = OxmlElement("w:sdt")
    pr = OxmlElement("w:sdtPr")
    for tag, val in (("w:alias", field), ("w:tag", field), ("w:id", str(sdt_id))):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        pr.append(el)
    if kind == "picture":
        pr.append(OxmlElement("w:picture"))
    else:
        text_el = OxmlElement("w:text")
        if kind == "multiline":
            text_el.set(qn("w:multiLine"), "1")
        pr.append(text_el)
    sdt.append(pr)

    content = OxmlElement("w:sdtContent")
    parent = run.getparent()
    index = list(parent).index(run)
    parent.remove(run)
    content.append(run)
    sdt.append(content)
    parent.insert(index, sdt)
    converted.add(field)


for run in list(body.iter(f"{W}r")):
    texts = run.findall(f"{W}t")
    if len(texts) != 1 or not texts[0].text:
        continue
    value = texts[0].text
    if not (value.startswith("«") and value.endswith("»")):
        continue
    field = value[1:-1]
    if field not in TEXT_FIELDS:
        raise SystemExit(f"未定義の差し込み欄: {field}")
    # Word で開いたときに何の欄か分かるよう、欄名をそのまま残す
    texts[0].text = field
    wrap_in_sdt(run, field, "multiline" if TEXT_FIELDS[field] else "text")

for run in list(body.iter(f"{W}r")):
    if run.find(f"{W}drawing") is not None:
        wrap_in_sdt(run, "SignatureImage", "picture")
        break

doc.save(OUT)
png.unlink(missing_ok=True)

expected = set(TEXT_FIELDS) | {"SignatureImage"}
missing = expected - converted
if missing:
    raise SystemExit(f"コンテンツ コントロールに変換できなかった欄: {sorted(missing)}")

print(f"{OUT.name}: コンテンツ コントロール {len(converted)} 個")
for f in sorted(converted):
    kind = "画像" if f == "SignatureImage" else ("複数行" if TEXT_FIELDS[f] else "テキスト")
    print(f"  - {f} ({kind})")
