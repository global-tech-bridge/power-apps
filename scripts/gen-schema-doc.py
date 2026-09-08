#!/usr/bin/env python3
"""data/list-schema.json から docs/02-sharepoint-schema.md を生成する。

スキーマの定義元は JSON 一つだけにして、ドキュメントとプロビジョニング
スクリプトの内容がずれないようにしている。
"""
import json
from pathlib import Path

schema = json.loads(Path("data/list-schema.json").read_text())
out = Path("docs/02-sharepoint-schema.md")

# 画面の「列の作成」で選ぶ種類の名前
TYPE_JA = {
    "Text": "1行テキスト",
    "Note": "複数行テキスト",
    "Number": "数値",
    "Boolean": "はい/いいえ",
    "DateTime": "日付と時刻",
    "Choice": "選択肢",
    "User": "ユーザーまたはグループ",
    "URL": "ハイパーリンク",
}

# 種類ごとに、画面で追加設定が必要な項目（既定値のままだと困るもの）
TYPE_SETUP = {
    "Text": "",
    "Note": "リッチ テキスト: **いいえ**（プレーン テキスト）／変更内容を追加: **いいえ**",
    "Number": "小数点以下の桁数: **0**",
    "Boolean": "",
    "DateTime": "含める内容: **日付と時刻**",
    "Choice": "値を手動で追加できる: **いいえ**／複数選択: **いいえ**",
    "User": "複数選択: **いいえ**／選択の対象: **ユーザーのみ**",
    "URL": "",
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
    "## 画面から作る場合",
    "",
    "PnP.PowerShell が使えない環境では、下の表のとおりに画面で列を作る。",
    "手順は [08 画面だけで構築する手順](08-manual-setup.md) を参照。",
    "",
    "- **列名は必ず表のまま（英語）で入力する。** 日本語で作ると内部名が壊れる",
    "- 「索引」が ○ の列は、リストの設定 → **インデックスされた列** で追加する",
    "  （委任可能な絞り込みと件数増加のため。要件定義 15.2）",
    "- 列の作成時に「既定のビューに追加する」を外すと、一覧が見やすくなる",
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
        "| 列名 | 画面で選ぶ種類 | 必須 | 索引 | 画面での追加設定 | 内容 |",
        "|---|---|:-:|:-:|---|---|",
        "| `Title` | 1行テキスト | ○ | — | 既定である列。作成不要 | SharePoint の既定必須列 |",
    ]
    for c in d["Columns"]:
        t = TYPE_JA[c["Type"]]
        setup = [TYPE_SETUP[c["Type"]]]
        if c["Type"] == "Choice":
            t += "<br>" + " / ".join(f"`{x}`" for x in c["Choices"])
            setup.insert(0, "選択肢に左記の値を1行ずつ入力")
        if c.get("Default") == "1":
            setup.append("既定値: **はい**")
        elif c.get("Default") == "0" and c["Type"] == "Boolean":
            setup.append("既定値: **いいえ**")
        elif c.get("Default") == "0" and c["Type"] == "Number":
            setup.append("既定値: **0**")
        req = "○" if c.get("Required") else "—"
        idx = "○" if c.get("Indexed") else "—"
        note = c.get("Note", "")
        setup_txt = "／".join(x for x in setup if x) or "—"
        lines.append(f"| `{c['Name']}` | {t} | {req} | {idx} | {setup_txt} | {note} |")
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
