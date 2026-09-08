#!/usr/bin/env python3
"""Studio の「コードの貼り付け」にそのまま貼れる断片を Src/*.pa.yaml から生成する。

    python3 scripts/gen-paste-files.py

pac CLI が使えない環境では、Studio の コピー/貼り付けのコード 機能で取り込む。
この機能は「コントロールの並び（YAML のシーケンス）」を受け取るため、
Src/*.pa.yaml の Children: 配下をインデント6文字ぶん左に寄せた形にしておく。

生成物（apps/yaj-cancelfee-signature/paste/）:
  App-OnStart.txt              … アプリの OnStart に貼る数式（先頭の = を除いたもの）
  <画面名>.controls.yaml       … その画面へ貼るコントロール一式
  <画面名>.properties.md       … その画面自身のプロパティ（手で入力する）
"""
import re
import sys
from pathlib import Path

import jsonschema
import yaml

SRC = Path("apps/yaj-cancelfee-signature/Src")
DST = Path("apps/yaj-cancelfee-signature/paste")
DST.mkdir(parents=True, exist_ok=True)

INDENT = 6  # "      - ctrl:" の 6 文字


def dedent(lines, n=INDENT):
    out = []
    for ln in lines:
        if not ln.strip():
            out.append("")
        elif ln.startswith(" " * n):
            out.append(ln[n:])
        else:
            raise SystemExit(f"インデントが想定と違う行: {ln!r}")
    return out


schema = None
schema_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pa.schema.yaml")
if schema_path.exists():
    schema = yaml.safe_load(schema_path.read_text())

# ---------------------------------------------------------------------------
# App.pa.yaml → OnStart の数式だけを取り出す
# ---------------------------------------------------------------------------
app_doc = yaml.safe_load((SRC / "App.pa.yaml").read_text())
onstart = app_doc["App"]["Properties"]["OnStart"]
assert onstart.startswith("=")
(DST / "App-OnStart.txt").write_text(onstart[1:].lstrip("\n"))
print("App-OnStart.txt")

# ---------------------------------------------------------------------------
# 各画面 → コントロール一式と画面プロパティ
# ---------------------------------------------------------------------------
order = app_doc.get("EditorState", {}).get("ScreensOrder", [])
summary = []

for path in sorted(SRC.glob("*.pa.yaml")):
    doc = yaml.safe_load(path.read_text())
    if "Screens" not in doc:
        continue
    (screen, body), = doc["Screens"].items()

    lines = path.read_text().split("\n")
    i_props = next((i for i, l in enumerate(lines) if l == "    Properties:"), None)
    i_children = next((i for i, l in enumerate(lines) if l == "    Children:"), None)
    if i_children is None:
        raise SystemExit(f"{path}: Children: が見つからない")
    if i_props is not None and i_props > i_children:
        raise SystemExit(f"{path}: Properties が Children より後ろにある（想定外）")

    # --- コントロール一式 ---
    child_lines = dedent(lines[i_children + 1:])
    while child_lines and not child_lines[-1].strip():
        child_lines.pop()
    text = "\n".join(child_lines) + "\n"

    parsed = yaml.safe_load(text)
    if schema:
        jsonschema.Draft7Validator(schema).validate(
            {"Screens": {screen: {"Children": parsed}}}
        )

    out = DST / f"{screen}.controls.yaml"
    out.write_text(text)

    # --- 画面自身のプロパティ ---
    props = body.get("Properties") or {}
    md = [
        f"# {screen} — 画面自身のプロパティ",
        "",
        "`コードの貼り付け` はコントロールしか取り込まないため、画面自身のプロパティは",
        "Studio でこの画面を選択し、右側のプロパティ ペイン → **詳細設定** で手で入力する。",
        "",
    ]
    if not props:
        md += ["設定するプロパティはない（既定のまま）。", ""]
    for name, value in props.items():
        # 先頭の = は Studio の数式バーでは不要
        v = value[1:] if isinstance(value, str) and value.startswith("=") else value
        md += [f"## {name}", "", "```", str(v).rstrip(), "```", ""]
    (DST / f"{screen}.properties.md").write_text("\n".join(md))

    summary.append((screen, len(parsed), list(props)))
    print(f"{out.name}  ({len(parsed)} controls)   {screen}.properties.md")

# ---------------------------------------------------------------------------
# 貼り付け順の一覧
# ---------------------------------------------------------------------------
idx = ["# 貼り付け用ファイル一覧", "",
       "`docs/08-manual-setup.md` の手順で、この順に取り込む。", "",
       "| 順 | 画面 | コントロール | 貼り付けるファイル | 手で入れる画面プロパティ |",
       "|---:|---|---:|---|---|"]
ranked = sorted(summary, key=lambda s: order.index(s[0]) if s[0] in order else 99)
for n, (screen, count, props) in enumerate(ranked, start=1):
    idx.append(f"| {n} | `{screen}` | {count} | `{screen}.controls.yaml` | "
               f"{' / '.join(f'`{p}`' for p in props) or '—'} |")
idx += ["", "アプリ自身（ツリー ビュー最上部の **アプリ**）には次を手で入れる。", "",
        "| プロパティ | 値 |", "|---|---|",
        "| `StartScreen` | `ListScreen` |",
        "| `OnStart` | `App-OnStart.txt` の内容をそのまま貼る |", ""]
(DST / "README.md").write_text("\n".join(idx))
print("README.md")
