#!/usr/bin/env python3
"""apps/*/Src/*.pa.yaml を Power Apps 公式 pa.yaml v3.0 スキーマで検証する。

使い方:
    curl -sLO https://raw.githubusercontent.com/microsoft/PowerApps-Tooling/master/schemas/pa-yaml/v3.0/pa.schema.yaml
    python3 scripts/validate-pa-yaml.py pa.schema.yaml apps/yaj-cancelfee-signature/Src/*.pa.yaml
"""
import sys
from pathlib import Path

import jsonschema
import yaml

schema = yaml.safe_load(Path(sys.argv[1]).read_text())
validator = jsonschema.Draft7Validator(schema)

# 画面をまたいだ参照の検証用に、全ファイルの画面名とコントロール名を集める
failed = 0
for path in (Path(p) for p in sys.argv[2:]):
    doc = yaml.safe_load(path.read_text())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        failed += 1
        print(f"✗ {path}")
        for e in errors:
            loc = "/".join(str(x) for x in e.path)
            print(f"    {loc}: {e.message}")
    else:
        n = sum(
            len(s.get("Children", [])) for s in (doc.get("Screens") or {}).values()
        )
        kind = "App" if "App" in doc else f"{n} controls"
        print(f"✓ {path}  ({kind})")

if failed:
    print(f"\n{failed} file(s) failed schema validation")
sys.exit(1 if failed else 0)
