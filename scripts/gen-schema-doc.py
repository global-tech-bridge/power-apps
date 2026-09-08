#!/usr/bin/env python3
"""data/list-schema.json から docs/02-sharepoint-schema.md を生成する。

スキーマの定義元は JSON 一つだけにして、ドキュメントとプロビジョニング
スクリプトの内容がずれないようにしている。
"""
import json
from pathlib import Path

schema = json.loads(Path("data/list-schema.json").read_text())
out = Path("docs/02-sharepoint-schema.md")

TYPE_JA = {
    "Text": "1行テキスト",
    "Note": "複数行テキスト（プレーン）",
    "Number": "数値",
    "Boolean": "はい/いいえ",
    "DateTime": "日付と時刻",
    "Choice": "選択肢",
    "User": "ユーザー",
    "URL": "ハイパーリンク",
}

lines = [
    "# SharePoint データ設計",
    "",
    "> このファイルは `data/list-schema.json` から自動生成される。",
    "> 直接編集せず、JSON を直して `python3 scripts/gen-schema-doc.py` を実行すること。",
    "",
    "要件定義 11章に対応する。`scripts/Provision-SharePoint.ps1` が同じ JSON を読んで",
    "リスト・列・インデックスを作成するため、ここに書かれている内容がそのまま構築される。",
    "",
    "## 列名を英語にしている理由",
    "",
    "SharePoint は列を日本語名で作ると、内部名が `_x9867__x5ba2__x540d_` のような",
    "エスケープ文字列になる。Power Automate の OData フィルター、Word テンプレートの",
    "差し込み、REST 呼び出しはすべて内部名を使うため、日本語名にすると式が読めなくなり",
    "保守できない。そのため列は英語名で作り、画面上の日本語ラベルは Power Apps 側の",
    "ラベルコントロールで与えている（要件定義 11.1 の列名定義にも合わせている）。",
    "",
    "## リスト",
    "",
]

for name, d in schema["Lists"].items():
    lines += [
        f"### {name}",
        "",
        d["Description"],
        "",
        "| 列名 | 型 | 必須 | インデックス | 内容 |",
        "|---|---|:-:|:-:|---|",
        "| `Title` | 1行テキスト | ○ | — | SharePoint の既定必須列 |",
    ]
    for c in d["Columns"]:
        t = TYPE_JA[c["Type"]]
        if c["Type"] == "Choice":
            t += "<br>" + " / ".join(f"`{x}`" for x in c["Choices"])
        req = "○" if c.get("Required") else "—"
        idx = "○" if c.get("Indexed") else "—"
        note = c.get("Note", "")
        lines.append(f"| `{c['Name']}` | {t} | {req} | {idx} | {note} |")
    if d.get("SeedCsv"):
        lines += ["", f"初期データ: `{d['SeedCsv']}`"]
    lines.append("")

lines += ["## ドキュメント ライブラリ", "", "| 名前 | 用途 |", "|---|---|"]
for name, d in schema["Libraries"].items():
    lines.append(f"| `{name}` | {d['Description']} |")

lines += [
    "",
    "### ファイル名の付け方",
    "",
    "| ライブラリ | ファイル名 |",
    "|---|---|",
    "| `SignatureDocs` | `<文書番号>.pdf` — 例 `20260909-001.pdf` |",
    "| `SignatureImages` | `<文書番号>.png` |",
    "| `WorkTemp` | `<文書番号>.docx`（変換後にフローが削除する） |",
    "",
    "顧客名をファイル名に含めないのは、顧客へ送るメールやPDFのプロパティに",
    "余分な情報を残さないため（要件定義 15.3）。また、文書番号だけで一意に決まるので、",
    "初回送信でも再実行でもフローが同じパスでファイルを取得できる。",
    "",
    "## ステータスの遷移",
    "",
    "```",
    "Draft ──署名送信──> Signed ──PDF作成──> Stored ──メール送信──> Sent",
    "  │                    │                  │                    │",
    "  └────────────────────┴──────────────────┴────────────────────┘",
    "                    いずれかで失敗すると Error",
    "                    （エラー画面から再実行すると失敗箇所から再開する）",
    "```",
    "",
    "`PdfCreated` は要件定義 9章で定義されているが、本実装では PDF の作成と",
    "SharePoint への保存を1つのフロー内で連続して行うため、`Stored` に集約している。",
    "選択肢としては残してあるので、将来 PDF 作成と保存を分離する場合に使える。",
    "",
]

out.write_text("\n".join(lines) + "\n")
print(f"{out}: {len(lines)} 行")
