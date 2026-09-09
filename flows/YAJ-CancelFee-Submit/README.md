# YAJ-CancelFee-Submit（文書番号採番 → PDF生成 → 保存 → メール送信）

アプリの `ConsentScreen` の送信ボタン、および `ErrorScreen` の再送信ボタンから呼ばれる
中核フロー。要件定義 8章（文書番号）／10章（PDF）／13章（メール）／14章（エラー・再実行）に対応する。

> このドキュメントは **画面の操作手順そのまま** に書いてある。Power Automate に
> クリックしてインポートできるパッケージ（.zip）ではない。コネクタの内部
> operationId は環境やコネクタの版で変わるため、手で作るほうが確実だと判断した。
> 貼り付けが必要な式は `expressions.md` に切り出してある。

## 0. 前提

| 項目 | 値 |
|---|---|
| フロー名 | `YAJ-CancelFee-Submit` |
| トリガー | Power Apps (V2) |
| 必要な接続 | SharePoint、**Word Online (Business)（Premium）**、Office 365 Outlook |
| 必要なライセンス | Power Apps Premium または Power Automate Premium（[理由](../../docs/01-deployment.md)） |
| 所有者 | 個人ではなくサービスアカウント（要件定義 15.5） |

### ⚠ 同時実行数を必ず 1 にする

トリガーの […] → **設定** → **同時実行制御** を **オン**、**次の数の並列度** を **1** にする。

文書番号の採番はカウンタリストの読み取り→加算→書き戻しで行うため、並列実行されると
同じ番号を2件に振ってしまう。並列度1に固定することで採番処理が直列化され、
要件定義 8章「同時登録時にも重複しない採番方式」を満たす。

## 1. トリガー入力

Power Apps (V2) トリガーに、この順番で入力を追加する（順番がアプリの `.Run()` の引数順になる）。

| # | 種類 | 名前 | 説明 |
|---|---|---|---|
| 1 | 数値 | `ItemID` | SignatureCases のレコードID |
| 2 | テキスト | `RequestId` | 冪等キー。アプリが1件につき1回だけ発番する |
| 3 | テキスト | `SignatureImage` | 署名画像の data URI。**空文字のときは保存済みの画像を再利用する**（再実行時） |

## 2. 応答（Respond to a Power App or flow）の出力

| 名前 | 種類 |
|---|---|
| `Success` | はい/いいえ |
| `DocumentNo` | テキスト |
| `PdfUrl` | テキスト |
| `Status` | テキスト |
| `ErrorCode` | テキスト |
| `ErrorMessage` | テキスト |
| `RunId` | テキスト |

アプリ側は `varFlowResult.Success` などで参照する。Studio の入力候補で大文字小文字が
違って表示された場合は、候補に出た表記に合わせて `ConsentScreen` / `ErrorScreen` /
`DetailScreen` の数式を直すこと。

## 3. 変数の初期化（トリガー直下・Scope の外）

`Try` が失敗しても `Catch` から読めるように、変数は必ず Scope の外で初期化する。

| アクション | 名前 | 種類 | 初期値 |
|---|---|---|---|
| 変数を初期化する | `varDocumentNo` | 文字列 | （空） |
| 変数を初期化する | `varPdfUrl` | 文字列 | （空） |
| 変数を初期化する | `varSignatureBase64` | 文字列 | （空） |
| 変数を初期化する | `varSignatureUrl` | 文字列 | （空） |

## 4. スコープ「Try」

### 4.1 `Get_case` — SharePoint「項目の取得」
- サイト: 対象サイト / リスト: `SignatureCases`
- ID: トリガーの `ItemID`

### 4.2 `Set_DocumentNo_existing` — 変数の設定
`varDocumentNo` ← `E1`（`expressions.md` 参照。以下同様）

### 4.3 条件 `Need_number` — `E2`
文書番号がまだ無いときだけ採番する。**これが再実行時の二重採番を防ぐ要点。**

**「はい」の分岐:**

1. `Compose_DateKey` — 作成: `E3`（JSTの yyyyMMdd）
2. `Get_counter` — SharePoint「複数の項目の取得」
   - リスト: `DocumentNumberCounter` / フィルター クエリ: `E4` / 上位の数: `1`
3. 条件 `Counter_missing` — `E5`
   - 「はい」: `Create_counter` — SharePoint「項目の作成」
     `Title` = `Compose_DateKey` の出力 / `LastNumber` = `0`
   - 「いいえ」: 何もしない
4. `Get_counter_again` — SharePoint「複数の項目の取得」（2 と同じ条件）
5. `Compose_Next` — 作成: `E6`（現在値 + 1）
6. `Update_counter` — SharePoint「項目の更新」
   - ID: `E7` / `Title` = `Compose_DateKey` の出力 / `LastNumber` = `Compose_Next` の出力
7. `Set_DocumentNo` — 変数の設定: `varDocumentNo` ← `E8`（`20260909-001` 形式）

> 手順3〜4でカウンタを「必ず存在させてから読み直す」構成にしているのは、
> 分岐ごとに次の番号を組み立てると式が二重になり、片方を直し忘れる事故が起きるため。

### 4.4 `Update_case_number` — SharePoint「項目の更新」
- ID: トリガーの `ItemID`
- `Title` = `varDocumentNo` ／ `DocumentNo` = `varDocumentNo`
- `Status` の値 = `Signed`
- `ClientRequestId` = トリガーの `RequestId`
- `PdfFileName` = `E9`

### 4.5 条件 `Has_new_signature` — `E10`

**「はい」（アプリから署名画像が来た＝初回送信）:**
1. `Set_SignatureBase64` — 変数の設定: `varSignatureBase64` ← `E11`
   （`data:image/png;base64,` の接頭辞を落として base64 本体だけにする）
2. `Create_signature_png` — SharePoint「ファイルの作成」
   - フォルダー パス: `/SignatureImages`
   - ファイル名: `E12` ／ ファイル コンテンツ: `E13`
3. `Set_SignatureUrl` — 変数の設定: `varSignatureUrl` ← `E14`

**「いいえ」（再実行で画像を持っていない）:**
1. `Get_existing_png` — SharePoint「パスによるファイル コンテンツの取得」
   - ファイル パス: `E15`
2. `Set_SignatureBase64_existing` — 変数の設定: `varSignatureBase64` ← `E16`
3. `Set_SignatureUrl_existing` — 変数の設定: `varSignatureUrl` ← `E17`

### 4.6 `Update_case_signature` — SharePoint「項目の更新」
- ID: `ItemID` ／ `SignatureImageUrl` = `varSignatureUrl`

### 4.7 条件 `Need_pdf` — `E18`
PDFがまだ無いときだけ作る。**再実行時の二重PDF生成を防ぐ要点。**

**「はい」の分岐:**

1. `Populate_template` — Word Online (Business)「Microsoft Word テンプレートの入力」
   - 場所: 対象の SharePoint サイト
   - ドキュメント ライブラリ: `DocTemplates`
   - ファイル: `整備キャンセル料確認書.docx`
   - 差し込み欄は下の「6. テンプレート差し込み表」のとおり
2. `Create_temp_docx` — SharePoint「ファイルの作成」
   - フォルダー パス: `/WorkTemp` ／ ファイル名: `E19` ／ コンテンツ: `Populate_template` の本文
3. `Convert_to_pdf` — SharePoint「ファイルの変換」
   - ファイル: `E20`（`Create_temp_docx` の Id）／ ターゲットの種類: `PDF`
   - この方式なら中間ファイルが本物の .docx なので、HTML経由で起きていた
     日本語の文字化けは発生しない（要件定義 10.1）
4. `Create_pdf` — SharePoint「ファイルの作成」
   - フォルダー パス: `/SignatureDocs` ／ ファイル名: `E21` ／ コンテンツ: `Convert_to_pdf` の本文
5. `Set_PdfUrl` — 変数の設定: `varPdfUrl` ← `E22`
6. `Update_case_pdf` — SharePoint「項目の更新」
   - ID: `ItemID` ／ `Status` = `Stored` ／ `PdfUrl` = `varPdfUrl`
7. `Delete_temp_docx` — SharePoint「ファイルの削除」
   - ファイル ID: `E20`
   - 「実行条件の構成」で **成功時のみ** ではなく **成功／失敗／スキップ** すべてを
     選び、変換が失敗しても中間ファイルが残らないようにする

**「いいえ」の分岐:**
1. `Set_PdfUrl_existing` — 変数の設定: `varPdfUrl` ← `E23`

### 4.8 `Get_pdf_content` — SharePoint「パスによるファイル コンテンツの取得」
- ファイル パス: `E24`

ファイル名を「文書番号.pdf」に固定しているため、初回でも再実行でも同じパスで取得できる。
（顧客名をファイル名やURLに入れないのは、顧客へ送るメールに余分な情報を含めないため。要件定義 15.3）

### 4.9 条件 `Not_sent_yet` — `E25`
すでに `Sent` のレコードに対して再実行された場合にメールを二重送信しないためのガード。

**「はい」の分岐:**
1. `Send_email` — Office 365 Outlook「メールの送信 (V2)」
   - 宛先: `E26`（顧客＋ログイン社員）
   - 件名: `E27`
   - 本文: 下の「7. メール本文」
   - 詳細オプション → 添付ファイル
     - 名前: `E21` ／ コンテンツ: `Get_pdf_content` の本文
2. `Update_case_sent` — SharePoint「項目の更新」
   - ID: `ItemID` ／ `Status` = `Sent` ／ `SentAt` = `E28`
   - `ErrorCode` = （空文字）／ `ErrorMessage` = （空文字）／ `FlowRunId` = （空文字）
3. `Create_sendlog` — SharePoint「項目の作成」（リスト `SendLog`）
   - `Title` = `varDocumentNo` ／ `CaseId` = `ItemID` ／ `DocumentNo` = `varDocumentNo`
   - `SentTo` = `E26` ／ `SentBy` = `E28b` ／ `SentAt` = `E28`
   - `Kind` = `Initial` ／ `Result` = `Success`

## 5. スコープ「Catch」

`Try` と同じ階層に置き、［…］→ **実行条件の構成** で
**に失敗した／がタイムアウトした／がスキップされた** の3つにチェックを入れる。

1. `Compose_FailedResult` — 作成: `E29`（`Try` の中で最初に失敗したアクションの実行結果）
2. `Compose_FailedAction` — 作成: `E30`（失敗したアクション名）
3. `Compose_ErrorDetail` — 作成: `E31`（失敗の詳細。**利用者には見せず記録用**）
4. `Compose_ErrorCode` — 作成: `E32`（失敗箇所からエラーコードを決める）
5. `Compose_UserMessage` — 作成: `E33`（利用者向けの日本語。個人情報や例外文を含めない）
6. `Update_case_error` — SharePoint「項目の更新」
   - ID: `ItemID` ／ `Status` = `Error`
   - `ErrorCode` = `Compose_ErrorCode` ／ `ErrorMessage` = `Compose_ErrorDetail`
   - `FlowRunId` = `E34`
7. `Respond_failure` — 「Power Apps または flow に応答する」
   - `Success` = `false` ／ `DocumentNo` = `varDocumentNo` ／ `PdfUrl` = `varPdfUrl`
   - `Status` = `Error` ／ `ErrorCode` = `Compose_ErrorCode`
   - `ErrorMessage` = `Compose_UserMessage` ／ `RunId` = `E34`

## 6. `Respond_success`

`Try` と同じ階層。**実行条件の構成** は **に成功した** のみ。

- `Success` = `true` ／ `DocumentNo` = `varDocumentNo` ／ `PdfUrl` = `varPdfUrl`
- `Status` = `Sent` ／ `ErrorCode` =（空）／ `ErrorMessage` =（空）／ `RunId` = `E34`

`Catch` と `Respond_success` は実行条件が排他なので、1回の実行で応答は必ず1つだけ返る。
アプリが完了画面へ進むのは `Success` が true のときだけであり、
要件定義 7.4「いずれかが失敗した場合はこの画面へ遷移しない」を満たす。

## 7. テンプレート差し込み表

`Populate_template` の各欄に入れる値。左列は Word のコンテンツ コントロール名
（`templates/build-template.py` が付けている名前）で、全16欄ある。

テンプレートは元資料「分解・診断を伴う整備お見積り後のキャンセル料について.docx」の
書式（A4縦の書簡形式＋確認欄）を再現している。

| 欄 | 値 |
|---|---|
| `DocumentNo` | `varDocumentNo` |
| `CustomerName` | `Get_case` の `CustomerName` |
| `BranchName` | `Get_case` の `BranchName` |
| `BlockName` | `Get_case` の `BlockName` |
| `SiteName` | `Get_case` の `SiteName` |
| `OperatorName` | `Get_case` の `OperatorName` |
| `ConsentTitle` | `Get_case` の `ConsentTitle` |
| `ConsentText` | `Get_case` の `ConsentTextSnapshot` |
| `Model` | `Get_case` の `Model` |
| `SerialNo` | `E42`（機番なしの機体はその旨を印字） |
| `MaintenanceType` | `Get_case` の `MaintenanceType Value` |
| `Comment` | `E43` |
| `SignerName` | `E44` |
| `SignedAt` | `E40` |
| `ConsentVersion` | `Get_case` の `ConsentVersion` |
| `SignatureImage` | `E45`（画像欄はオブジェクト形式で渡す） |

### 押さえておく2点

1. **`ConsentText` に渡すのはマスタの現在値ではなく、レコードの
   `ConsentTextSnapshot`。** これにより、後日マスタが改訂されても、PDFには
   署名時点の文面が残る（要件定義 11.3）。
   スナップショットには確認文（「私は上記内容について確認いたしました。」）まで
   含まれているため、確認欄の直前にその一文が印字される。
2. **顧客のメールアドレスと電話番号はPDFに印字しない。** 要件定義 10章が求める
   PDF記載項目に含まれておらず、顧客へ渡す文書に不要な個人情報を載せないため
   （要件定義 15.3）。リストには保持しているので、一覧・詳細画面からは参照できる。

## 8. メール本文（HTML）

`Send_email` の本文にそのまま貼る。`@{...}` は動的コンテンツとして解決される。

```html
<p>@{outputs('Get_case')?['body/CustomerName']} 様</p>
<p>
  いつもお世話になっております。ヤンマーアグリジャパン @{outputs('Get_case')?['body/SiteName']} です。<br>
  このたびは、分解・診断を伴う整備お見積り後のキャンセル料についてご確認・ご署名をいただき、ありがとうございました。
</p>
<p>ご署名いただいた確認書をPDFで添付いたします。内容をご確認のうえ、控えとして保管をお願いいたします。</p>
<table>
  <tr><td>文書番号</td><td>@{variables('varDocumentNo')}</td></tr>
  <tr><td>署名日時</td><td>@{formatDateTime(convertTimeZone(outputs('Get_case')?['body/SignedAt'],'UTC','Tokyo Standard Time'),'yyyy年MM月dd日 HH:mm')}</td></tr>
  <tr><td>型式・機番</td><td>@{outputs('Get_case')?['body/Model']} / @{if(equals(outputs('Get_case')?['body/NoSerialNo'],true),'機番なし',coalesce(outputs('Get_case')?['body/SerialNo'],''))}</td></tr>
  <tr><td>整備区分</td><td>@{outputs('Get_case')?['body/MaintenanceType/Value']}</td></tr>
  <tr><td>担当者</td><td>@{outputs('Get_case')?['body/OperatorName']}</td></tr>
</table>
<p>本メールの内容にお心当たりがない場合、またご不明な点がある場合は、担当者までご連絡ください。</p>
<p>ヤンマーアグリジャパン株式会社</p>
```

顧客にも社員にも同一のPDFを同一の本文で送る（要件定義 17.3）。
SharePoint への内部リンクは本文に入れない（要件定義 15.3）。
