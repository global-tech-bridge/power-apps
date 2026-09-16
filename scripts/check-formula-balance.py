#!/usr/bin/env python3
"""数式の括弧・引用符の対応を検査する。

    python3 scripts/check-formula-balance.py <Srcディレクトリ>

生成した数式は目視で追いにくいので、機械的に確認する。
Power Fx の文字列は "" でエスケープするため、その扱いも考慮する。
"""
import sys
from pathlib import Path

import yaml

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/yaj-cancelfee-signature/Src")

PAIRS = {")": "(", "]": "[", "}": "{"}
OPEN = set(PAIRS.values())


def collect(node, out, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "Properties" and isinstance(v, dict):
                for prop, formula in v.items():
                    if isinstance(formula, str):
                        out.append((f"{path}.{prop}", formula))
            else:
                collect(v, out, f"{path}/{k}" if k not in ("Children",) else path)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and len(item) == 1:
                (name, body), = item.items()
                collect(body, out, f"{path}/{name}")
            else:
                collect(item, out, path)


def check(formula):
    stack, i, n = [], 0, len(formula)
    in_str = False
    while i < n:
        c = formula[i]
        if in_str:
            if c == '"':
                if i + 1 < n and formula[i + 1] == '"':   # "" はエスケープ
                    i += 2
                    continue
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "/" and i + 1 < n and formula[i + 1] == "/":
                j = formula.find("\n", i)                  # 行コメントは読み飛ばす
                i = n if j < 0 else j
                continue
            elif c in OPEN:
                stack.append(c)
            elif c in PAIRS:
                if not stack or stack[-1] != PAIRS[c]:
                    return f"対応しない '{c}'"
                stack.pop()
        i += 1
    if in_str:
        return '閉じていない引用符'
    if stack:
        return f"閉じられていない '{stack[-1]}' が {len(stack)} 個"
    return None


problems = []
total = 0
for path in sorted(SRC.glob("*.pa.yaml")):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = []
    if "App" in doc:
        collect({"Properties": doc["App"].get("Properties", {})}, items, "App")
    for screen, body in (doc.get("Screens") or {}).items():
        collect(body, items, screen)
    for where, formula in items:
        total += 1
        err = check(formula)
        if err:
            problems.append(f"{path.name} {where}: {err}")

print(f"数式 {total} 件を検査しました")
if problems:
    for p in problems:
        print("✗", p)
    sys.exit(1)
print("✓ 括弧と引用符の対応に問題はありません")
