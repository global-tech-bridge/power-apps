#!/usr/bin/env python3
"""pa.yaml 内の相互参照を静的に検査する。

Studio に貼り付ける前に、次の食い違いを機械的に見つけるためのもの。
  1. 同一画面に存在しないコントロールを参照している
  2. どこでも Set されていない変数を読んでいる
  3. 存在しない画面へ Navigate している
  4. SharePoint 列の綴りが docs/02-sharepoint-schema.md の定義と合っていない
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/yaj-cancelfee-signature/Src")
SCHEMA = Path(sys.argv[2] if len(sys.argv) > 2 else "data/list-schema.json")

CONTROL_PREFIXES = (
    "txt", "btn", "dd", "chk", "dp", "gal", "lbl", "rec", "pen", "img", "tmr",
)
CTRL_REF = re.compile(
    r"\b((?:" + "|".join(CONTROL_PREFIXES) + r")[A-Za-z0-9]*)\s*\."
)
VAR_REF = re.compile(r"\b(var[A-Z][A-Za-z0-9]*)\b")
VAR_SET = re.compile(r"Set\(\s*(var[A-Z][A-Za-z0-9]*)")
COL_REF = re.compile(r"\b(col[A-Z][A-Za-z0-9]*)\b")
COL_SET = re.compile(r"(?:ClearCollect|Collect)\(\s*(col[A-Z][A-Za-z0-9]*)")
NAVIGATE = re.compile(r"Navigate\(\s*([A-Za-z][A-Za-z0-9]*)")


def formulas(node, out):
    """Properties 配下の数式文字列をすべて集める。"""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "Properties" and isinstance(v, dict):
                out.extend(str(x) for x in v.values() if x)
            else:
                formulas(v, out)
    elif isinstance(node, list):
        for v in node:
            formulas(v, out)


def control_names(node, out):
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and len(item) == 1:
                (name, body), = item.items()
                out.add(name)
                if isinstance(body, dict):
                    control_names(body.get("Children"), out)


docs = {p: yaml.safe_load(p.read_text()) for p in sorted(SRC.glob("*.pa.yaml"))}

screens = set()
per_screen_controls = {}
per_screen_formulas = defaultdict(list)
app_formulas = []

for path, doc in docs.items():
    if "App" in doc:
        formulas(doc["App"], app_formulas)
    for screen, body in (doc.get("Screens") or {}).items():
        screens.add(screen)
        names = set()
        control_names(body.get("Children"), names)
        per_screen_controls[screen] = names
        fx = []
        formulas(body, fx)
        per_screen_formulas[screen] = fx

all_formulas = app_formulas + [f for v in per_screen_formulas.values() for f in v]
blob = "\n".join(all_formulas)

problems = []

# --- 1. コントロール参照 ---
for screen, fx in per_screen_formulas.items():
    text = "\n".join(fx)
    for ref in sorted(set(CTRL_REF.findall(text))):
        if ref not in per_screen_controls[screen]:
            problems.append(f"[control] {screen}: {ref} は同画面に存在しない")

# --- 2. 変数 ---
declared_vars = set(VAR_SET.findall(blob))
for ref in sorted(set(VAR_REF.findall(blob))):
    if ref not in declared_vars:
        problems.append(f"[variable] {ref} はどこでも Set されていない")

# --- 3. コレクション ---
declared_cols = set(COL_SET.findall(blob))
for ref in sorted(set(COL_REF.findall(blob))):
    if ref not in declared_cols:
        problems.append(f"[collection] {ref} はどこでも ClearCollect されていない")

# --- 4. 画面遷移 ---
for ref in sorted(set(NAVIGATE.findall(blob))):
    if ref not in screens:
        problems.append(f"[navigate] {ref} という画面は存在しない")

# --- 5. SharePoint 列 ---
if SCHEMA.exists():
    schema = json.loads(SCHEMA.read_text())
    known = {
        lst: {c["Name"] for c in cols["Columns"]} | {
            "ID", "Title", "Created", "Modified", "Author", "Editor"
        }
        for lst, cols in schema["Lists"].items()
    }
    case_cols = known["SignatureCases"]
    # varEdit / varSelected / varCompleted / ThisItem は SignatureCases のレコード
    record_ref = re.compile(
        r"\b(?:varEdit|varSelected|varCompleted|varLastCase|ThisItem)\.([A-Za-z][A-Za-z0-9_]*)"
    )
    for ref in sorted(set(record_ref.findall(blob))):
        if ref not in case_cols:
            problems.append(f"[column] SignatureCases.{ref} はスキーマ定義に無い")
    # Patch( SignatureCases, ... ) のレコードリテラルのキー。
    # Operator 列に渡す SPListExpandedUser のような入れ子レコードのキーは
    # 列名ではないので、最も浅いインデントのキーだけを列名として扱う。
    for m in re.finditer(r"Patch\(\s*SignatureCases\b(.*?)\n\s*\)\s*\)", blob, re.S):
        hits = re.findall(r"^(\s{2,})([A-Za-z][A-Za-z0-9_]*):", m.group(1), re.M)
        if not hits:
            continue
        top = min(len(indent) for indent, _ in hits)
        for indent, key in hits:
            if len(indent) == top and key not in case_cols:
                problems.append(f"[column] Patch(SignatureCases) の {key} はスキーマ定義に無い")

print(f"画面 {len(screens)}  コントロール {sum(len(v) for v in per_screen_controls.values())}  "
      f"変数 {len(declared_vars)}  コレクション {len(declared_cols)}")
if problems:
    for p in sorted(set(problems)):
        print("✗", p)
    print(f"\n{len(set(problems))} problem(s)")
    sys.exit(1)
print("✓ 相互参照の不整合はありません")
