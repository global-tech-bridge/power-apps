# YAJ-CancelFee-Resend（保存済みPDFの再送）

`DetailScreen` の「PDFを再送」から呼ばれる。要件定義 13章「同一PDFの二重生成を避け、
再送時は保存済みPDFを使用する」および「再送履歴を別リストへ記録する」に対応する。

**PDFは作り直さない。** SharePoint に保存済みのファイルをそのまま添付する。

## トリガー入力（Power Apps (V2)）

| # | 種類 | 名前 | 説明 |
|---|---|---|---|
| 1 | 数値 | `ItemID` | SignatureCases のレコードID |
| 2 | テキスト | `ToEmail` | 送信先メールアドレス |

同時実行制御は不要（採番を行わないため）。

## 応答の出力

| 名前 | 種類 |
|---|---|
| `Success` | はい/いいえ |
| `ErrorCode` | テキスト |
| `ErrorMessage` | テキスト |
| `RunId` | テキスト |

## アクション

### スコープ「Try」

1. `Get_case` — SharePoint「項目の取得」（`SignatureCases` / ID = `ItemID`）
2. 条件 `Pdf_exists`
   ```
   not(empty(coalesce(outputs('Get_case')?['body/PdfUrl'],'')))
   ```
   「いいえ」の分岐では `Terminate`（状態: `Failed`、コード `E-RESEND-010`、
   メッセージ `保存済みPDFがありません`）で止める。Catch が受けて応答を返す。
3. `Get_pdf_content` — SharePoint「パスによるファイル コンテンツの取得」
   ```
   concat('/SignatureDocs/',outputs('Get_case')?['body/DocumentNo'],'.pdf')
   ```
4. `Send_email` — Office 365 Outlook「メールの送信 (V2)」
   - 宛先: トリガーの `ToEmail`
   - 件名:
     ```
     concat('【再送】【ヤンマーアグリジャパン】整備お見積りに伴うキャンセル料に関する同意書（文書番号 ',outputs('Get_case')?['body/DocumentNo'],'）')
     ```
   - 本文: `YAJ-CancelFee-Submit` と同じ本文の先頭に「本メールは、先にお送りした同意書の
     再送です。」の1文を加えたもの
   - 添付ファイル名:
     ```
     concat(outputs('Get_case')?['body/DocumentNo'],'.pdf')
     ```
   - 添付コンテンツ: `Get_pdf_content` の本文
5. `Update_case` — SharePoint「項目の更新」
   - ID: `ItemID` ／ `SentAt` = `utcNow()`
   - `ResendCount` =
     ```
     add(int(coalesce(outputs('Get_case')?['body/ResendCount'],0)),1)
     ```
6. `Create_sendlog` — SharePoint「項目の作成」（`SendLog`）
   - `Title` / `DocumentNo` = `outputs('Get_case')?['body/DocumentNo']`
   - `CaseId` = `ItemID` ／ `SentTo` = `ToEmail`
   - `SentBy` = `workflow()?['run']?['name']` ではなく **実行ユーザー**。
     Office 365 Outlook の接続ユーザーになるため、確実に記録したい場合は
     アプリから送信者メールを追加入力として渡す（下の「補足」参照）
   - `SentAt` = `utcNow()` ／ `Kind` = `Resend` ／ `Result` = `Success`
7. `Create_auditlog` — SharePoint「項目の作成」（`AuditLog`）
   - `Title` = 文書番号 ／ `Action` = `Resend` ／ `CaseId` = `ItemID`
   - `DocumentNo` = 文書番号 ／ `PerformedAt` = `utcNow()`
   - `Reason` = `PDF再送` ／ `Detail` = 送信先アドレス

### スコープ「Catch」

実行条件: `Try` が **失敗／タイムアウト／スキップ** のとき。

1. `Compose_FailedResult`
   ```
   first(where(result('Try'),or(equals(item()?['status'],'Failed'),equals(item()?['status'],'TimedOut'))))
   ```
2. `Create_sendlog_failure` — `SendLog` に `Kind` = `Resend` / `Result` = `Failure` /
   `ErrorMessage` = `string(coalesce(outputs('Compose_FailedResult')?['error'],''))` で記録
3. `Respond_failure` — `Success` = `false`、`ErrorCode` = `E-RESEND-020`、
   `ErrorMessage` = `再送に失敗しました。宛先を確認してください。`、
   `RunId` = `workflow()['run']['name']`

### `Respond_success`

実行条件: `Try` が **成功した** ときのみ。`Success` = `true`、`RunId` = `workflow()['run']['name']`

## 補足: 再送した人を確実に残す

`SendLog.SentBy` に操作者を確実に残したい場合は、トリガーに 3 番目の入力
`OperatorEmail`（テキスト）を追加し、アプリ側の呼び出しを次のように変える。

```
'YAJ-CancelFee-Resend'.Run(varSelected.ID, Trim(txtResendTo.Text), varUserEmail)
```

MVP では未実装（フロー側は接続ユーザーで記録する）。要件定義 13章
「再送履歴を残す場合、送信日時、送信者、送信先、成否を別リストへ記録する」を
厳密に満たすには、この 3 番目の入力を追加すること。docs/07-open-issues.md D-08。
