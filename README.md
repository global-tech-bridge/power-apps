# YAJ 整備キャンセル料 電子署名 Power App

ヤンマーアグリジャパン 中部近畿の「分解・診断を伴う整備お見積り後のキャンセル料」について、
顧客への説明・同意取得・手書き電子署名・PDF正本化・保管・配信・検索・監査を
一連で扱う業務アプリ。Power Apps キャンバスアプリ + Power Automate + SharePoint で構成する。

要件定義: `YAJ_整備キャンセル料_電子署名PowerApp_要件定義.md`（リポジトリ外）

## 何ができるか

社員がタブレット（縦向き）を顧客に提示し、その場で同意と署名を取る。

1. 社員が案件を登録する（顧客・機体・整備・組織）。訪問前ならドラフト保存して後で再開
2. 顧客に同意文面を全文提示し、同意チェックと**指またはペンでの手書き署名**を取る
3. 送信すると、文書番号が採番され、署名済みPDFが作られて SharePoint に保管され、
   顧客とログイン社員へメール送信される
4. 全工程が成功したときだけ完了画面になる。失敗したら、失敗した工程が分かる
   エラー画面になり、**同じ番号・同じPDFで重複を作らずに再実行**できる
5. 一覧から検索・参照・PDFの再送ができる。誤登録の削除は管理者のみ（理由の記録が必須）

## 構成

```
Power Apps キャンバスアプリ（タブレット縦 768×1024・6画面）
        │
        ├─ SharePoint リスト 7 ─── 署名案件・組織マスタ・同意文面マスタ
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
| [`data/`](data/) | SharePoint スキーマ定義（JSON）と初期データ（組織マスタ・同意文面） |
| [`templates/`](templates/) | PDF生成用 Word テンプレートと、その生成スクリプト |
| [`scripts/`](scripts/) | SharePoint 構築スクリプトと、ソースの検証スクリプト |

## ドキュメント

**まずここから: [docs/01-deployment.md](docs/01-deployment.md) — デプロイ手順**

| ドキュメント | 内容 |
|---|---|
| [01 デプロイ手順](docs/01-deployment.md) | サイト作成 → リスト構築 → フロー作成 → アプリ取り込み → 動作確認 → 引き継ぎ |
| [02 SharePoint データ設計](docs/02-sharepoint-schema.md) | リスト・列・インデックス・ファイル命名・ステータス遷移 |
| [03 Power Automate 設計](docs/03-power-automate.md) | 3フローの役割、冪等性、エラーコード一覧、PDF生成経路、採番方式 |
| [04 権限設計](docs/04-permissions.md) | SharePoint のアクセス権、アプリ内の権限判定、管理者の付与 |
| [05 運用・障害対応](docs/05-operations.md) | 同意文面の改訂、組織の変更、障害切り分け、定期点検 |
| [06 テスト仕様書](docs/06-test-spec.md) | 受入条件（要件定義17章）に対応した66件のテストケース |
| [07 未確定事項と暫定判断](docs/07-open-issues.md) | **要件定義19章の20項目＋追加11項目の判断と変更コスト** |

## 本番運用の前に必ず決めること

`docs/07-open-issues.md` に全件あるが、特に次は**決まらないまま本番で使うと事故になる**。

1. **正式な同意文面** — 現在入っているのは仮の起草（版 `0.9-draft`）。
   元資料の `.docx` を取得できなかったため、要件定義の記述から組み立てたもの。
   **法務確認前に顧客の署名を取ってはいけない**
2. **法務・経理・税務の確認** — 収入印紙の扱い、電子署名の証拠性、
   署名済みPDFが必要な証拠性を満たすか（要件定義16章）
3. **記録・PDF・署名画像の保管期間** — 決まるまで削除しない運用にする
4. **メール送信元アカウント** — 顧客に見えるアドレス。個人アカウントのままにしない
5. **「支社」の定義** — 提供された `部門マスタ.xlsx` に `支社` 列がなく、
   上位階層は `部門名`（営業部／販売部／系統推進部）だった。現在は部門名を
   「支社」として扱っている。PDFと一覧に印字されるので確認が必要（D-01）

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
```

生成物を作り直す場合。

```bash
# 部門マスタ.xlsx から組織マスタCSVを作る
python3 scripts/build-org-master.py ../部門マスタ.xlsx data/OrgMaster.csv

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
