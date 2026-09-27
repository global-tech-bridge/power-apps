#!/usr/bin/env python3
"""文字やチェックボックスがコントロールからはみ出しそうな箇所を、概算で洗い出す。

    python3 scripts/check-text-fit.py [Src ディレクトリ]

check-layout.py は「画面の外に出ていないか」しか見ない。こちらは
「コントロールの中に文字が収まるか」を、文字数とフォントサイズから見積もる。

見積もりの前提（Classic コントロール、Studio の既定値）
  - Size は pt。1pt = 96/72 px。全角1文字 ≒ 1em、半角 ≒ 0.55em
  - Label は既定で折り返す。行の高さ ≒ 1.2em、左右の余白は各 5px。
    1行なら文字そのものが入れば切れない（上下の余白の部分にも描かれる）
  - CheckBox の四角は CheckboxSize（既定 32px）。高さがそれより小さいと四角が切れる
  - Button は1行に収まる前提（折り返すと読みにくいので、収まらなければ指摘する）

Text が固定の文字列（="..."）のものだけを見る。変数や & でつないだものは、
リテラル部分だけで最低限の長さを見積もる。実際の表示は Studio で確かめること。
"""
import re
import sys
import unicodedata
from pathlib import Path

import yaml

import yajcli  # noqa: E402,F401  Windows でも出力を UTF-8 にする（✓ などは cp932 に無い）

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/yaj-cancelfee-signature/Src")
PT = 96 / 72


def num(v, default=None):
    if v is None:
        return default
    m = re.fullmatch(r"=\s*(-?\d+(?:\.\d+)?)", str(v).strip())
    return float(m.group(1)) if m else default


def literal_text(v):
    """数式から文字列リテラルだけを取り出して連結する（最低限の長さの見積もり）。"""
    if v is None:
        return ""
    s = str(v).strip()
    if s.startswith("="):
        s = s[1:]
    parts = [p.replace('""', '"') for p in re.findall(r'"((?:[^"]|"")*)"', s)]
    # If / Switch は分岐のどれか1つが表示される。つなぐと過大になるので最長の1つを使う
    if re.search(r"\b(If|Switch|Coalesce)\(", s):
        return max(parts, key=len, default="")
    return "".join(parts)


def text_width(text, size):
    em = size * PT
    w = 0.0
    for ch in text:
        w += em * (1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.55)
    return w


def walk(children, screen, out):
    for c in children or []:
        for name, body in c.items():
            if not isinstance(body, dict):
                continue
            ctrl = (body.get("Control") or "").split("/")[-1]
            p = body.get("Properties") or {}
            out.append((screen, name, ctrl, p))
            walk(body.get("Children"), screen, out)


problems = []
for path in sorted(SRC.glob("*.pa.yaml")):
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for screen, sbody in (doc.get("Screens") or {}).items():
        ctrls = []
        walk(sbody.get("Children"), screen, ctrls)
        for screen_name, name, ctrl, p in ctrls:
            text = literal_text(p.get("Text"))
            w, h = num(p.get("Width")), num(p.get("Height"))
            if w is None or h is None:
                continue
            size = num(p.get("Size"), 13)
            em = size * PT
            if ctrl == "CheckBox":
                box = num(p.get("CheckboxSize"), 32)
                if h < box:
                    problems.append(f"{screen_name}.{name}: 四角 {box:.0f}px が高さ {h:.0f}px に収まらない（CheckboxSize を指定する）")
                avail = w - box - 10
                if text and text_width(text, size) > avail:
                    problems.append(f"{screen_name}.{name}: 「{text}」が幅 {avail:.0f}px に収まらない（約 {text_width(text, size):.0f}px）")
                if h < em * 1.2:
                    problems.append(f"{screen_name}.{name}: 文字の高さ {em*1.2:.0f}px が高さ {h:.0f}px に収まらない")
            elif ctrl == "Label" and text:
                pl, pr = num(p.get("PaddingLeft"), 5), num(p.get("PaddingRight"), 5)
                pt_, pb = num(p.get("PaddingTop"), 5), num(p.get("PaddingBottom"), 5)
                avail_w = w - pl - pr
                tw = text_width(text, size)
                wrap = str(p.get("Wrap", "=true")).strip().lower() != "=false"
                hard_lines = text.count("\n") + 1
                if wrap:
                    lines = sum(max(1, -(-text_width(seg, size) // max(avail_w, 1))) for seg in text.split("\n"))
                else:
                    lines = hard_lines
                    if tw > avail_w and "\n" not in text:
                        problems.append(f"{screen_name}.{name}: 「{text[:30]}」が幅 {avail_w:.0f}px に収まらない（折り返し無し、約 {tw:.0f}px）")
                # 1行なら文字そのものが入ればよい（余白の部分にも描かれる）。
                # 2行以上は行の高さ＋上下の余白の半分を見込む
                need_h = em * 1.15 if lines <= 1 else lines * em * 1.2 + (pt_ + pb) / 2
                auto = str(p.get("AutoHeight", "")).strip().lower() == "=true"
                if not auto and need_h > h + 1:
                    problems.append(
                        f"{screen_name}.{name}: 「{text[:30]}」は約 {lines:.0f} 行（高さ {need_h:.0f}px 必要）で、高さ {h:.0f}px では切れる"
                    )
            elif ctrl == "Button" and text:
                avail = w - 2 * num(p.get("PaddingLeft"), 5)
                if text_width(text, size) > avail:
                    problems.append(f"{screen_name}.{name}: ボタンの「{text}」が幅 {avail:.0f}px に1行で収まらない")

if problems:
    for p in problems:
        print("✗", p)
    print(f"\n{len(problems)} 件（概算。Studio で実際の表示を確かめること）")
    sys.exit(1)
print("✓ 文字とチェックボックスはコントロール内に収まる見込みです")
