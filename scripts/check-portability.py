#!/usr/bin/env python3
"""Windows でも動くように書かれているかを静的に検査する。

    python scripts/check-portability.py

  1. ファイルの読み書き（open / read_text / write_text）に encoding を指定しているか
     （Windows の既定は cp932。UTF-8 の日本語を読むと UnicodeDecodeError になる）
  2. az / pac を subprocess で名前だけで呼んでいないか
     （Windows の az は az.cmd なので見つからない。yajcli.run / yajcli.az_token を使う）
  3. 入口になるスクリプトが yajcli を読み込んでいるか
     （出力を UTF-8 にする。✓ ✗ ⚠ は cp932 に無く、パイプに流すと落ちる）
  4. bash のスクリプトが、Python 版を呼ぶだけの入口になっているか
"""
import ast
import sys
from pathlib import Path

import yajcli  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
MODULES = {"yajcli.py", "flow_definitions.py"}      # 他から読み込まれるだけのもの
BASH_OK = {"resolve-template-ids.sh"}                # Word テンプレート方式専用（html 方式では使わない）

problems = []
for f in sorted(SCRIPTS.glob("*.py")):
    src = f.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        if name in ("open", "read_text", "write_text") and not any(k.arg == "encoding" for k in n.keywords):
            mode = n.args[1] if name == "open" and len(n.args) > 1 else next(
                (k.value for k in n.keywords if k.arg == "mode"), None)
            if not (isinstance(mode, ast.Constant) and "b" in str(mode.value)):
                problems.append(f"{f.name}:{n.lineno}: {name}() に encoding の指定がない")
        if name in ("run", "check_output", "Popen", "call") and n.args and isinstance(n.args[0], ast.List):
            first = n.args[0].elts[0] if n.args[0].elts else None
            if isinstance(first, ast.Constant) and first.value in ("az", "pac"):
                owner = n.func.value.id if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) else ""
                if owner == "subprocess":
                    problems.append(f"{f.name}:{n.lineno}: {first.value} を subprocess で名前だけで呼んでいる（yajcli.run を使う）")
    if f.name not in MODULES and "import yajcli" not in src:
        problems.append(f"{f.name}: yajcli を読み込んでいない（Windows で出力が cp932 になる）")

for f in sorted(SCRIPTS.glob("*.sh")):
    if f.name in BASH_OK:
        continue
    body = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    if len(body) != 1 or not body[0].startswith("exec python3"):
        problems.append(f"{f.name}: bash で処理を書いている（Windows で動かない。Python 版を呼ぶだけにする）")

if problems:
    for p in problems:
        print("✗", p)
    print(f"\n{len(problems)} 件")
    sys.exit(1)
print("✓ Windows でも動く書き方になっています")
