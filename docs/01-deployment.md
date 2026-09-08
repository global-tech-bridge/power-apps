# デプロイ手順

このリポジトリの内容を、実際の Microsoft 365 テナントへ展開する手順。
所要時間は初回でおよそ 2〜3 時間（Power Automate フローの作成に大半を要する）。

## 0. 前提と準備

### 必要なもの

| 項目 | 内容 |
|---|---|
| Power Apps 環境 | 既定環境（要件定義 2章）。ソリューション環境を使う場合は「補遺A」参照 |
| ライセンス | Power Apps（Microsoft 365 付属で可）、Office 365 Outlook、**Word Online (Business)** |
| SharePoint | 専用サイトを1つ新規作成（既存サイトへの混在は避ける） |
| アカウント | 構築用アカウント。**将来的にはサービスアカウントへ移す**（要件定義 15.5） |

> **ライセンスの確認事項**
> `Word Online (Business)` コネクタの「Microsoft Word テンプレートの入力」は
> 標準コネクタだが、テナントの DLP ポリシーでブロックされていることがある。
> 着手前に Power Automate で1つテストフローを作り、このアクションが追加できるか
> 確認しておくこと（要件定義 19章-13）。

### ローカルで必要なもの（任意）

テンプレートやマスタCSVを作り直す場合のみ。

```bash
pip install openpyxl python-docx jsonschema pyyaml
pwsh -Command 'Install-Module PnP.PowerShell -Scope CurrentUser'
```

## 1. SharePoint サイトの作成

1. SharePoint 管理センター、または SharePoint スタート画面から
   **チームサイト**（またはコミュニケーションサイト）を新規作成する
   - サイト名の例: `YAJ整備キャンセル料同意書`
   - URL の例: `https://<テナント>.sharepoint.com/sites/yaj-cancelfee`
2. サイトの **プライバシー設定は「プライベート」** にする。
   顧客名・メールアドレス・電話番号・署名画像を扱うため、既定で全社公開に
   なる設定は使わない（要件定義 15.3）。
3. アクセス権は `docs/04-permissions.md` のとおりに設定する。

## 2. リスト・ライブラリ・初期データの作成

### 方法A（推奨）: スクリプトで自動作成

```bash
pwsh ./scripts/Provision-SharePoint.ps1 \
  -SiteUrl https://<テナント>.sharepoint.com/sites/yaj-cancelfee \
  -ClientId <Entra ID アプリのクライアントID>
```

このスクリプトは `data/list-schema.json` を定義元として、次をすべて冪等に作成する
（何度実行しても既存のものはスキップされる）。

- リスト7つ（`SignatureCases` / `OrgMaster` / `ConsentMaster` / `AppAdmins` /
  `SendLog` / `AuditLog` / `DocumentNumberCounter`）と全列
- 委任可能な絞り込み・件数増加に備えたインデックス（要件定義 15.2）
- ライブラリ4つ（`SignatureDocs` / `SignatureImages` / `DocTemplates` / `WorkTemp`）
- `SignatureDocs` のバージョン管理を有効化
- 組織マスタ 105 件（`data/OrgMaster.csv`）
- 同意文面マスタ 版 `0.9-draft`（`data/consent/ConsentText_v0.9-draft.txt`）
- 実行したユーザーを `AppAdmins` に登録
- `templates/整備キャンセル料同意書.docx` を `DocTemplates` へアップロード

> `ClientId` は PnP.PowerShell 2.x 以降で必須。テナントに PnP 用の Entra ID
> アプリが未登録の場合は、`Register-PnPEntraIDAppForInteractiveLogin` で
> 作成してから実行する。

### 方法B: 画面から手作業で作成（CLI が使えない場合）

**手順は [08 画面だけで構築する手順](08-manual-setup.md) の Part 1 と Part 2 に
全部書き出してある。** リスト7つ（計70列）とライブラリ4つの作り方、
列の種類ごとの注意点、インデックスの設定、初期データの投入方法まで含む。

インポート用のファイルは [`../data/import/`](../data/import/) に用意してある。

| ファイル | 入れ先 | 方法 |
|---|---|---|
| `OrgMaster.xlsx` | `OrgMaster` | 「Excel からリストを作成」 |
| `OrgMaster_grid.tsv` | `OrgMaster` | 既存リストのグリッド ビューへ貼り付け |
| `AppAdmins_grid.tsv` | `AppAdmins` | グリッド ビューへ貼り付け |
| `data/consent/ConsentText_v0.9-draft.txt` | `ConsentMaster` | フォームに貼り付け |
| `templates/整備キャンセル料同意書.docx` | `DocTemplates` | ファイルのアップロード |

> `ConsentMaster` 用のインポート ファイルは意図的に作っていない。本文が3,000字を
> 超えるため、Excel からリストを作成すると1行テキスト（255字）の列になって
> **本文が切り捨てられる**。同意文面は証跡そのものなので、フォームから入れる。

### 確認

- `OrgMaster` が 105 件あること
- `ConsentMaster` に `IsActive` = はい の行が **ちょうど1件** あること
  （複数あると適用開始日が最新のものが使われる）
- `DocTemplates` に `整備キャンセル料同意書.docx` があること

## 3. Power Automate フローの作成

3つのフローを作る。**先にフローを作ってからアプリを作る**こと。
アプリ側がフローを参照するため、逆順にすると数式がエラーになる。

| 順 | フロー名 | 手順書 |
|---|---|---|
| 1 | `YAJ-CancelFee-Submit` | [flows/YAJ-CancelFee-Submit/README.md](../flows/YAJ-CancelFee-Submit/README.md) |
| 2 | `YAJ-CancelFee-Resend` | [flows/YAJ-CancelFee-Resend/README.md](../flows/YAJ-CancelFee-Resend/README.md) |
| 3 | `YAJ-CancelFee-Delete` | [flows/YAJ-CancelFee-Delete/README.md](../flows/YAJ-CancelFee-Delete/README.md) |

各手順書はアクションを1つずつ並べた形で書いてある。貼り付ける式は同じ
フォルダの `expressions.md` にまとめてある。

### 特に間違えやすい2点

1. **`YAJ-CancelFee-Submit` の同時実行数を 1 にする**
   トリガーの […] → 設定 → 同時実行制御をオン → 並列度 1。
   これをしないと、同時に2人が送信したときに同じ文書番号が振られる。
2. **`Catch` スコープの実行条件**
   `Try` の […] ではなく `Catch` の […] → 実行条件の構成 で
   「に失敗した」「がタイムアウトした」「がスキップされた」の3つにチェック。
   既定（成功時のみ）のままだとエラー時に応答が返らず、アプリが固まる。

### フロー単体でのテスト

アプリを作る前に、フローだけで動作確認できる。

1. `SignatureCases` に手でレコードを1件作る
   - `CustomerName` = `テスト太郎`（**実顧客の情報は使わない**。要件定義 15.3）
   - `CustomerEmail` = 自分のアドレス
   - `Model` = `YT5113`、`SerialNo` = `99999`
   - `MaintenanceType` = `点検整備`、`Status` = `Signed`
   - `BranchName` = `営業部`、`BlockName` = `福井ブロック`、`SiteName` = `福井`
   - `SignedAt` = 現在時刻
   - `ConsentTitle` / `ConsentVersion` / `ConsentTextSnapshot` に何か入れる
   - `OperatorEmail` / `OperatorName` に自分の情報
2. `YAJ-CancelFee-Submit` を「テスト」→「手動」で実行し、
   `ItemID` にそのレコードID、`RequestId` に適当なGUID、
   `SignatureImage` は空文字で実行する
3. `SignatureDocs` にPDFができ、日本語が文字化けせず、
   メールが届くことを確認する

> **PDFの日本語が豆腐（□）になる場合**
> `templates/build-template.py` の `JP_FONT` を `MS Gothic` または `Meiryo` に
> 変えて再生成し、`DocTemplates` のファイルを差し替える。
> 要件定義 10.1 で共有されていた文字化けは HTML 経由の変換で起きるもので、
> 本実装は Word テンプレート経由なので通常は発生しない。

## 4. キャンバスアプリの作成

### 4-1. 空のアプリを作る

1. [make.powerapps.com](https://make.powerapps.com) → **アプリ** → **新しいアプリ** →
   **キャンバス** → **タブレット**
2. **設定 → 表示 → 向き** を **縦** にする
   （画面サイズは 768 × 1024。本リポジトリの座標はこの前提で作ってある）
3. **設定 → 全般 → データ行の制限** を **2000** にする
   一覧のキーワード検索が3列の OR 条件になっており、
   既定の 500 件では取りこぼす可能性があるため（要件定義 15.2）

### 4-2. データとフローを接続する

1. 左の **データ** → **データの追加** → **SharePoint** → サイトURLを入力
2. 次の7つのリストにチェックを入れて接続する
   `SignatureCases` / `OrgMaster` / `ConsentMaster` / `AppAdmins` /
   `SendLog` / `AuditLog` / `DocumentNumberCounter`
   （`SendLog` と `AuditLog` はフロー側で書くのでアプリからは使わないが、
   将来の履歴表示のために接続しておく）
3. **データの追加** → 検索欄に `YAJ-CancelFee` と入力し、
   3つのフローすべてを追加する

### 4-3. 画面を作り、コードを貼り付ける

**詳細な手順は [08 画面だけで構築する手順](08-manual-setup.md) の Part 3。**
貼り付け用に整形した断片が
[`../apps/yaj-cancelfee-signature/paste/`](../apps/yaj-cancelfee-signature/paste/)
にある（`Src/` から自動生成）。

要点だけ再掲する。

1. **コントロールを貼る前に、6画面すべてを作って正しい名前を付ける**
   （`ListScreen` `EditScreen` `ConsentScreen` `CompleteScreen` `ErrorScreen`
   `DetailScreen`）。画面をまたぐ `Navigate()` があるため、
   遷移先が未作成のまま貼るとエラーが大量に出る
2. **アプリ** の `StartScreen` と `OnStart` を先に設定する
   （`OnStart` は `paste/App-OnStart.txt` をそのまま貼る）
3. 各画面を右クリック → **コードの貼り付け** に
   `paste/<画面名>.controls.yaml` を貼る
4. 続けて `paste/<画面名>.properties.md` の `Fill` / `OnVisible` を
   その画面自身に手で入力する

### 4-4. 残るエラーの解消

貼り付け直後にエラーが出る場合、原因はほぼ次の3つ。

| 症状 | 対処 |
|---|---|
| `Distinct(...)` の `Value` が見つからない | `Value` を `Result` に置き換える。Power Fx の版によって `Distinct` の返す列名が異なる。該当箇所は `ListScreen`（3箇所）と `EditScreen`（3箇所）の `Sort(Distinct(...), Value)` |
| フロー呼び出しの `.Success` が見つからない | Studio の入力候補に出る表記に合わせる。「Power Apps または flow に応答する」で付けた出力名の大文字小文字がそのまま反映される |
| `varSelected.SignatureImageUrl` が画像として扱われない | `imgSignature.Image` を `varSelected.SignatureImageUrl & ""` にする（テキストとして明示する） |

### 4-5. 保存と公開

1. **ファイル → 名前を付けて保存**。アプリ名は
   `YAJ 整備キャンセル料 同意書` など
2. **公開**する
3. **共有** で利用者のセキュリティグループを追加する
   （フローの接続も一緒に共有されることを確認する）

## 5. 動作確認

`docs/06-test-spec.md` のテストケースを上から実行する。
最低限、次の4つが通れば MVP として使い始められる。

1. 新規作成 → ドラフト保存 → 一覧から再開できる
2. 同意チェックなし・署名なしでは送信ボタンが押せない
3. 送信すると文書番号が採番され、PDFが届き、ステータスが「メール送信済み」になる
4. 同じ日に2件送信すると `-001` `-002` と連番になる

## 6. 引き継ぎ（要件定義 15.5）

本番運用に移す前に、次を必ず行う。

- [ ] アプリの **共同所有者** に、構築者以外を2名以上追加する
- [ ] 3つのフローの **共同所有者** に同じ2名を追加する
- [ ] 各コネクタの接続を、個人アカウントからサービスアカウントへ張り替える
      （特に Office 365 Outlook。個人の退職・異動で送信が止まるのを防ぐ）
- [ ] SharePoint サイトの **サイト管理者** を2名以上にする
- [ ] `AppAdmins` リストに運用管理者を登録し、構築者の行は残すか判断する
- [ ] 下の「引き継ぎ情報シート」を埋めて、運用担当へ渡す

### 引き継ぎ情報シート

| 項目 | 値 |
|---|---|
| SharePoint サイトURL | |
| Power Apps 環境名 | |
| アプリ名 / アプリID | |
| フロー名 × 3 | |
| メール送信元アカウント | |
| SharePoint サイト管理者 | |
| アプリ・フローの共同所有者 | |
| 利用対象セキュリティグループ | |
| 同意文面の現行版 | |
| 記録・PDFの保管期間 | （要件定義 19章-10 が未確定） |

## 補遺A: ソリューション環境で構築する場合

既定環境ではなくソリューション（Dataverse）環境に入れる場合は、
次を追加で行う。要件定義 2章では既定環境が前提なので、MVP では不要。

1. ソリューションを新規作成し、アプリ・フロー・接続参照をその中に作る
2. SharePoint サイトURL とリスト名を **環境変数** にする
   （開発／本番でサイトを分ける場合に必須）
3. 接続参照を使い、環境間でインポートしても接続が壊れないようにする

環境変数化した場合、Power Fx のデータソース参照は変わらないが、
フロー側の SharePoint アクションのサイトURLを環境変数に差し替える必要がある。
