# YAJ-CancelFee-Delete（管理者による誤登録データの削除）

`DetailScreen` の「削除」（管理者のみ表示）から呼ばれる。
要件定義 5.2 / 15.3 / 15.4 に対応する。

アプリから `Remove()` するだけにしなかったのは、**署名画像と署名済みPDFが
ライブラリに残ってしまう**ため。個人情報（顧客名・署名画像）を含むファイルを
孤立させないよう、リストレコードとファイルをフローで一括削除し、
削除理由を監査ログへ残す。

## トリガー入力（Power Apps (V2)）

| # | 種類 | 名前 | 説明 |
|---|---|---|---|
| 1 | 数値 | `ItemID` | SignatureCases のレコードID |
| 2 | テキスト | `Reason` | 削除理由（アプリ側で5文字以上を必須にしている） |

## 応答の出力

| 名前 | 種類 |
|---|---|
| `Success` | はい/いいえ |
| `ErrorCode` | テキスト |
| `ErrorMessage` | テキスト |

## アクション

### スコープ「Try」

1. `Get_case` — SharePoint「項目の取得」（`SignatureCases` / ID = `ItemID`）
2. `Create_auditlog` — SharePoint「項目の作成」（`AuditLog`）
   **削除の前に記録する。** 削除に失敗しても「削除しようとした事実」が残る。
   - `Title` = `coalesce(outputs('Get_case')?['body/DocumentNo'],concat('ID-',string(triggerBody()?['number'])))`
   - `Action` = `Delete` ／ `CaseId` = `ItemID`
   - `DocumentNo` = `outputs('Get_case')?['body/DocumentNo']`
   - `PerformedAt` = `utcNow()`
   - `Reason` = トリガーの `Reason`
   - `Detail` — 削除した内容の要約（顧客名は監査目的で残す）
     ```
     concat('顧客名: ',coalesce(outputs('Get_case')?['body/CustomerName'],''),' / ステータス: ',coalesce(outputs('Get_case')?['body/Status/Value'],''),' / 署名日時: ',coalesce(string(outputs('Get_case')?['body/SignedAt']),''),' / PDF: ',coalesce(outputs('Get_case')?['body/PdfUrl'],'なし'))
     ```
   - `PerformedBy` — 接続ユーザーになる。操作者を確実に残す場合は
     トリガーに `OperatorEmail` を追加する（`YAJ-CancelFee-Resend` と同じ）
3. `Delete_pdf` — SharePoint「ファイルの削除」
   - ファイル ID:
     ```
     concat('/SignatureDocs/',outputs('Get_case')?['body/DocumentNo'],'.pdf')
     ```
   - 「実行条件の構成」で **失敗時も続行** にする（PDFが未作成のドラフトも削除できるように）
4. `Delete_signature` — SharePoint「ファイルの削除」
   - ファイル ID:
     ```
     concat('/SignatureImages/',outputs('Get_case')?['body/DocumentNo'],'.png')
     ```
   - こちらも **失敗時も続行**
5. `Delete_case` — SharePoint「項目の削除」（`SignatureCases` / ID = `ItemID`）
   - 実行条件: `Delete_pdf` と `Delete_signature` の **成功／失敗** どちらでも実行

### スコープ「Catch」

実行条件: `Try` が **失敗／タイムアウト／スキップ** のとき。

`Respond_failure` — `Success` = `false`、`ErrorCode` = `E-DELETE-010`、
`ErrorMessage` = `削除に失敗しました。管理者に連絡してください。`

### `Respond_success`

実行条件: `Try` が **成功した** ときのみ。`Success` = `true`

## 運用上の注意

- 文書番号が採番済みのレコードを削除しても、`DocumentNumberCounter` の連番は戻さない。
  戻すと、削除済みの番号が別の案件に再利用され、過去に送付済みのPDFと番号が衝突する。
  結果として番号に欠番が生じるが、**欠番より重複のほうが問題が大きい**という判断。
- 削除の承認フロー（誰の承認があれば削除できるか）は未確定。docs/07-open-issues.md D-09。
