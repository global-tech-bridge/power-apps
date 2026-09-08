#!/usr/bin/env python3
"""タブレット縦（768×1024）に全コントロールが収まっているか検証する。

X/Y/Width/Height が定数の（= 数式でない）コントロールだけを対象に、
右端・下端が画面外へはみ出していないかを見る。
Parent.Width / Parent.Height などの相対指定は画面に追従するので対象外。
"""
import re
import sys
from pathlib import Path

import yaml

SCREEN_W, SCREEN_H = 768, 1024
SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/yaj-cancelfee-signature/Src")

NUM = re.compile(r"^=\s*(-?\d+(?:\.\d+)?)\s*$")


def const(props, key):
    v = props.get(key)
    if not isinstance(v, str):
        return None
    m = NUM.match(v)
    return float(m.group(1)) if m else None


def walk(children, screen, rows, depth=0):
    for item in children or []:
        (name, body), = item.items()
        props = body.get("Properties") or {}
        x, y = const(props, "X"), const(props, "Y")
        w, h = const(props, "Width"), const(props, "Height")
        if None not in (x, y, w, h) and depth == 0:
            rows.append((screen, name, x + w, y + h))
        # ギャラリーの Children は TemplateWidth 基準の相対座標なので見ない
        if body.get("Control") != "Gallery":
            walk(body.get("Children"), screen, rows, depth + 1)


rows = []
for path in sorted(SRC.glob("*.pa.yaml")):
    doc = yaml.safe_load(path.read_text())
    for screen, body in (doc.get("Screens") or {}).items():
        walk(body.get("Children"), screen, rows)

problems = []
by_screen = {}
for screen, name, right, bottom in rows:
    r, b = by_screen.get(screen, (0, 0))
    by_screen[screen] = (max(r, right), max(b, bottom))
    if right > SCREEN_W:
        problems.append(f"{screen}.{name}: 右端 {right:.0f} > {SCREEN_W}")
    if bottom > SCREEN_H:
        problems.append(f"{screen}.{name}: 下端 {bottom:.0f} > {SCREEN_H}")

print(f"想定画面サイズ: {SCREEN_W} x {SCREEN_H}（タブレット縦）")
for screen in sorted(by_screen):
    r, b = by_screen[screen]
    print(f"  {screen:<16} 最大右端 {r:>5.0f} / 最大下端 {b:>5.0f}")

if problems:
    for p in problems:
        print("✗", p)
    sys.exit(1)
print("✓ すべてのコントロールが縦画面内に収まっています")
