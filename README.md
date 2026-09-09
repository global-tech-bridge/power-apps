# YAJ 整備キャンセル料 電子署名 Power App

ヤンマーアグリジャパン 中部近畿の「分解・診断を伴う整備お見積り後のキャンセル料」について、
顧客への説明・確認取得・手書き電子署名・PDF正本化・保管・配信・検索・監査を
一連で扱う業務アプリ。Power Apps キャンバスアプリ + Power Automate + SharePoint で構成する。

要件定義: `YAJ_整備キャンセル料_電子署名PowerApp_要件定義.md`（リポジトリ外）

## 何ができるか

社員がタブレット（縦向き）を顧客に提示し、その場で確認と署名を取る。

1. 社員が案件を登録する（顧客・機体・整備・組織）。訪問前ならドラフト保存して後で再開
2. 顧客に確認文面を全文提示し、確認チェックと**指またはペンでの手書き署名**を取る
3. 送信すると、文書番号が採番され、署名済みPDFが作られて SharePoint に保管され、
   顧客とログイン社員へメール送信される
4. 全工程が成功したときだけ完了画面になる。失敗したら、失敗した工程が分かる
   エラー画面になり、**同じ番号・同じPDFで重複を作らずに再実行**できる
5. 一覧から検索・参照・PDFの再送ができる。誤登録の削除は管理者のみ（理由の記録が必須）

## 構成

```
Power Apps キャンバスアプリ（タブレット縦 768×1024・6画面）
        │
        ├─ SharePoint リスト 7 ─── 署名案件・組織マスタ・確認文面マスタ
        │                          管理者・送信履歴・監査ログ・採番カウンタ
        │
        └─ Power Automate フロー 3
             ├─ Submit … 採番 → 署名画像保存 → PDF生成 → 保管 → メール送信
             ├─ Resend … 保存済みPDFの再送（作り直さない）
             └─ Delete … レコード・画像・PDFの削除と監査記録
                                │
                    Word テンプレート → 中間.docx → PDF
                    （HTML を経由しないので日本語が文字化けしない）
```

## ディレクトリ

| パス | 内容 |
|---|---|
| [`apps/yaj-cancelfee-signature/`](apps/yaj-cancelfee-signature/) | キャンバスアプリのソース（pa.yaml v3.0 / Power Fx） |
| [`flows/`](flows/) | Power Automate フロー3つの作成手順と貼り付ける式 |
| [`docs/`](docs/) | 設計書・デプロイ手順・権限・運用・テスト仕様・未確定事項 |
| [`data/`](data/) | SharePoint スキーマ定義（JSON）と初期データ（組織マスタ・確認文面） |
| [`data/import/`](data/import/) | **画面から取り込むためのインポート用ファイル**。`schema/` が列の一括作成用、直下が初期データ用 |
| [`templates/`](templates/) | PDF生成用 Word テンプレートと、その生成スクリプト |
| [`scripts/`](scripts/) | SharePoint 構築スクリプトと、ソースの検証スクリプト |

## 構築の進め方

**CLI（`pac` / PnP.PowerShell）が使えない場合は
[docs/08-manual-setup.md](docs/08-manual-setup.md) 1本で完結する。**
これが今回の想定。上から順にやれば構築が終わる。

PnP.PowerShell が使える場合は [docs/01-deployment.md](docs/01-deployment.md) の
方法Aでリスト構築を自動化できる（30〜45分ぶん短縮できる）。

### 読む順番

| 順 | やること | 見るドキュメント | 目安 |
|---:|---|---|---|
| 0 | **着手前の確認**（Premium ライセンスと MFA 条件付きアクセス。**ここを飛ばすと作り直しになる**） | [01 デプロイ手順](docs/01-deployment.md) の「0. 前提と準備」 | 30分 |
| 1 | SharePoint サイト・リスト7つ・ライブラリ4つ | [08 手順](docs/08-manual-setup.md) Part 1 ＋ [02 データ設計](docs/02-sharepoint-schema.md) | 30〜45分 |
| 2 | 初期データ（組織マスタ105件・確認文面・管理者・テンプレート） | [08 手順](docs/08-manual-setup.md) Part 2 ＋ [data/import/](data/import/) | 10分 |
| 3 | Power Automate フロー3つ | [flows/](flows/) の各 `README.md` と `expressions.md` | 90〜120分 |
| 4 | キャンバスアプリの取り込み | [08 手順](docs/08-manual-setup.md) Part 4 ＋ [paste/](apps/yaj-cancelfee-signature/paste/) | 40〜60分 |
| 5 | 動作確認 | [06 テスト仕様書](docs/06-test-spec.md) | 60分 |
| 6 | 引き継ぎ | [01 デプロイ手順](docs/01-deployment.md) の「6. 引き継ぎ」 | 30分 |

**順番を入れ替えないこと。** アプリがフローを参照しているため、
フローより先にアプリを取り込むと「フローが見つかりません」エラーになる。

### 運用に入ってから見るもの

| 場面 | ドキュメント |
|---|---|
| 確認文面を改訂する／拠点が増えた／管理者を追加する | [05 運用・障害対応](docs/05-operations.md) |
| 利用者がエラー画面になった／PDFが作られない | [05 運用・障害対応](docs/05-operations.md) の「4. 障害対応」＋ [03 Power Automate 設計](docs/03-power-automate.md) のエラーコード一覧 |
| 権限を見直す | [04 権限設計](docs/04-permissions.md) |
| 業務側の決定事項を確認する | [07 未確定事項と暫定判断](docs/07-open-issues.md) |

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [01 デプロイ手順](docs/01-deployment.md) | サイト作成 → リスト構築 → フロー作成 → アプリ取り込み → 動作確認 → 引き継ぎ |
| [02 SharePoint データ設計](docs/02-sharepoint-schema.md) | リスト・列・インデックス・ファイル命名・ステータス遷移 |
| [03 Power Automate 設計](docs/03-power-automate.md) | 3フローの役割、冪等性、エラーコード一覧、PDF生成経路、採番方式 |
| [04 権限設計](docs/04-permissions.md) | SharePoint のアクセス権、アプリ内の権限判定、管理者の付与 |
| [05 運用・障害対応](docs/05-operations.md) | 確認文面の改訂、組織の変更、障害切り分け、定期点検 |
| [06 テスト仕様書](docs/06-test-spec.md) | 受入条件（要件定義17章）に対応した69件のテストケース |
| [07 未確定事項と暫定判断](docs/07-open-issues.md) | **要件定義19章の20項目＋追加11項目の判断と変更コスト** |
| [08 画面だけで構築する手順](docs/08-manual-setup.md) | **CLI を使わず、ブラウザ操作だけで SharePoint とアプリを構築する** |

## 本番運用の前に必ず決めること

`docs/07-open-issues.md` に全件あるが、特に次は**決まらないまま本番で使うと事故になる**。

1. **確認文面の上申結果** — 現在入っているのは元資料そのままの文面（版 `1.0`、
   2026-06-02 サービス事業推進部 起案）だが、`整備キャンセル料について.pptx`
   スライド3に「文面について問題ないかご意見を賜りたい」とあり、**上申中**。
   社内承認が完了した版ではない
2. **収入印紙の取扱い** — 同 pptx が「署名を求めるにあたり、収入印紙を貼付する
   必要があると推定される」と明記している。電子交付にした場合の扱いを
   所管部門に確認する必要がある（要件定義16章）
3. **署名欄の過不足** — 元資料の署名欄は 型式／ご用命事項／日付／ご署名 の4つ。
   本実装は要件定義10章に合わせて機番・整備区分・お名前を加えた7行にしている（D-16）
4. **PDF生成のライセンス** — 現在の実装は `Word Online (Business)`（**Premium コネクタ**）を
   使うため、**Power Apps Premium または Power Automate Premium が必要**。
   Microsoft 365 付属の seeded ライセンスでは動かない。費用をかけない方針なら
   標準コネクタだけで作る方式に切り替える改修が必要（19章-13）
5. **記録・PDF・署名画像の保管期間** — 決まるまで削除しない運用にする
6. **メール送信元アカウント** — 顧客に見えるアドレス。個人アカウントのままにしない
7. **「支社」の定義** — 提供された `部門マスタ.xlsx` に `支社` 列がなく、
   上位階層は `部門名`（営業部／販売部／系統推進部）だった。現在は部門名を
   「支社」として扱っている。PDFと一覧に印字されるので確認が必要（D-01）
8. **元資料の誤字** — 費用表の見出し「組戻し**せずせず**そのままお返し」の
   「せず」が重複している。本実装では1回に直しているので、元資料側の修正が必要（D-14）

## ソースの検証

CI に載せる前でも、手元で3種類の検証ができる。

```bash
pip install openpyxl python-docx jsonschema pyyaml

# Power Apps 公式 pa.yaml v3.0 スキーマでの検証
curl -sLO https://raw.githubusercontent.com/microsoft/PowerApps-Tooling/master/schemas/pa-yaml/v3.0/pa.schema.yaml
python3 scripts/validate-pa-yaml.py pa.schema.yaml apps/yaj-cancelfee-signature/Src/*.pa.yaml

# コントロール名・変数・画面遷移・SharePoint列名の相互参照
python3 scripts/check-references.py

# タブレット縦（768×1024）にすべてのコントロールが収まっているか
python3 scripts/check-layout.py

# Word テンプレートの差し込み欄とフロー手順書の差し込み表が一致しているか
python3 scripts/check-template-fields.py

# インポート用ファイルが list-schema.json とずれていないか
python3 scripts/check-import-files.py
```

生成物を作り直す場合。

```bash
# 部門マスタ.xlsx から組織マスタCSVを作る
python3 scripts/build-org-master.py ../部門マスタ.xlsx data/OrgMaster.csv

# SharePoint へ画面から取り込むためのインポート用ファイル（xlsx / tsv）を作る
python3 scripts/build-import-files.py         # 初期データ用
python3 scripts/build-schema-import-files.py  # 列（スキーマ）の一括作成用

# Studio の「コードの貼り付け」に貼れる断片を作る
python3 scripts/gen-paste-files.py pa.schema.yaml

# SharePoint スキーマ定義から設計書を作る
python3 scripts/gen-schema-doc.py

# PDF生成用 Word テンプレートを作る
python3 templates/build-template.py
```

## スコープ外（要件定義 4.2）

顧客マスタ連携、商品・型式マスタ連携、テキスト入力による代替署名、
社外ユーザーの直接利用、写真・動画付き見積、AI画像認識による概算見積、
キャンセル料の自動計算・請求連携。

写真付き見積と AI 概算見積は、既存または別途開発中の基幹・見積システムとの
重複を避ける方針がヒアリングで確認されているため、本アプリから分離している。
