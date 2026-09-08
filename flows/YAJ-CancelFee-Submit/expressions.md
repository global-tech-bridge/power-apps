# YAJ-CancelFee-Submit — 貼り付ける式

`README.md` の `E**` に対応する。Power Automate の式エディタ（`fx`）にそのまま貼れる。

> **トリガー入力の参照について**
> Power Apps (V2) トリガーの入力は、内部キーが宣言名ではなく型ごとの連番
> （`number`, `text`, `text_1`, …）になる。式に手で書くよりも
> **動的コンテンツから `ItemID` / `RequestId` / `SignatureImage` を選ぶほうが確実**。
> 下の式では参考として内部キー表記を載せているが、動的コンテンツで置き換えてよい。
>
> | 宣言名 | 型 | 内部キー |
> |---|---|---|
> | `ItemID` | 数値 | `triggerBody()?['number']` |
> | `RequestId` | テキスト | `triggerBody()?['text']` |
> | `SignatureImage` | テキスト | `triggerBody()?['text_1']` |

## 文書番号（要件定義 8章）

**E1** — 既存の文書番号（無ければ空文字）
```
coalesce(outputs('Get_case')?['body/DocumentNo'],'')
```

**E2** — 採番が必要か（条件）: 左辺に下の式、演算子「次の値に等しい」、右辺 `true`
```
empty(variables('varDocumentNo'))
```

**E3** — 日本時間の日付キー `yyyyMMdd`
```
formatDateTime(convertTimeZone(utcNow(),'UTC','Tokyo Standard Time'),'yyyyMMdd')
```

**E4** — カウンタ取得のフィルター クエリ（式ではなくテキスト欄に入力）
```
Title eq '@{outputs('Compose_DateKey')}'
```

**E5** — カウンタ行が無いか（条件）: 左辺に下の式、「次の値に等しい」、右辺 `true`
```
equals(length(outputs('Get_counter')?['body/value']),0)
```

**E6** — 次の連番
```
add(int(first(outputs('Get_counter_again')?['body/value'])?['LastNumber']),1)
```

**E7** — 更新するカウンタ行のID
```
first(outputs('Get_counter_again')?['body/value'])?['ID']
```

**E8** — 文書番号 `20260909-001`
```
concat(outputs('Compose_DateKey'),'-',formatNumber(outputs('Compose_Next'),'000'))
```
`formatNumber` が使えない環境では次の式でも同じ結果になる（999件/日まで）。
```
concat(outputs('Compose_DateKey'),'-',substring(concat('000',string(outputs('Compose_Next'))),sub(length(concat('000',string(outputs('Compose_Next')))),3),3))
```

**E9** — PDFファイル名（レコードの `PdfFileName` 列に入れる）
```
concat(variables('varDocumentNo'),'.pdf')
```

## 署名画像

**E10** — アプリから画像が渡されたか（条件）: 左辺に下の式、「次の値に等しい」、右辺 `true`
```
not(empty(triggerBody()?['text_1']))
```

**E11** — data URI から base64 本体だけを取り出す
```
last(split(triggerBody()?['text_1'],'base64,'))
```

**E12** — 署名画像のファイル名
```
concat(variables('varDocumentNo'),'.png')
```

**E13** — ファイル コンテンツ（バイナリに戻す）
```
base64ToBinary(variables('varSignatureBase64'))
```

**E14** — 作成した署名画像のURL
```
outputs('Create_signature_png')?['body/{Link}']
```

**E15** — 保存済み署名画像のパス（再実行時）
```
concat('/SignatureImages/',variables('varDocumentNo'),'.png')
```

**E16** — 取得したファイルを base64 に戻す（再実行時）
```
base64(body('Get_existing_png'))
```

**E17** — 保存済み署名画像のURL（再実行時）
```
coalesce(outputs('Get_case')?['body/SignatureImageUrl'],'')
```

## PDF

**E18** — PDF生成が必要か（条件）: 左辺に下の式、「次の値に等しい」、右辺 `true`
```
empty(coalesce(outputs('Get_case')?['body/PdfUrl'],''))
```

**E19** — 中間 .docx のファイル名
```
concat(variables('varDocumentNo'),'.docx')
```

**E20** — 中間 .docx のファイルID（変換元／削除対象）
```
outputs('Create_temp_docx')?['body/Id']
```

**E21** — PDFのファイル名（作成時・メール添付名の両方で使う）
```
concat(variables('varDocumentNo'),'.pdf')
```

**E22** — 作成したPDFのURL
```
outputs('Create_pdf')?['body/{Link}']
```

**E23** — 保存済みPDFのURL（再実行時）
```
coalesce(outputs('Get_case')?['body/PdfUrl'],'')
```

**E24** — PDFのパス（初回・再実行の両方で同じ）
```
concat('/SignatureDocs/',variables('varDocumentNo'),'.pdf')
```

## メール

**E25** — まだ送信していないか（条件）: 左辺に下の式、「次の値に等しい」、右辺 `true`
```
not(equals(outputs('Get_case')?['body/Status/Value'],'Sent'))
```

**E26** — 宛先（顧客＋ログイン社員）
```
concat(outputs('Get_case')?['body/CustomerEmail'],';',outputs('Get_case')?['body/OperatorEmail'])
```

**E27** — 件名
```
concat('【ヤンマーアグリジャパン】整備お見積りに伴うキャンセル料に関する確認書（文書番号 ',variables('varDocumentNo'),'）')
```

**E28** — 送信日時
```
utcNow()
```

**E28b** — 送信操作者
```
outputs('Get_case')?['body/OperatorEmail']
```

## エラー処理（要件定義 14章）

**E29** — `Try` の中で最初に失敗したアクションの実行結果
```
first(where(result('Try'),or(equals(item()?['status'],'Failed'),equals(item()?['status'],'TimedOut'))))
```

**E30** — 失敗したアクション名
```
coalesce(outputs('Compose_FailedResult')?['name'],'Unknown')
```

**E31** — 失敗の詳細（SharePoint の複数行テキストに収めるため1800文字で切る）
```
substring(string(coalesce(outputs('Compose_FailedResult')?['error'],'')),0,min(1800,length(string(coalesce(outputs('Compose_FailedResult')?['error'],'')))))
```

**E32** — エラーコード（どこで失敗したかを分類する）
```
if(startsWith(outputs('Compose_FailedAction'),'Get_case'),'E-FLOW-010',
if(or(startsWith(outputs('Compose_FailedAction'),'Get_counter'),startsWith(outputs('Compose_FailedAction'),'Create_counter'),startsWith(outputs('Compose_FailedAction'),'Update_counter'),startsWith(outputs('Compose_FailedAction'),'Update_case_number')),'E-FLOW-020',
if(or(startsWith(outputs('Compose_FailedAction'),'Create_signature_png'),startsWith(outputs('Compose_FailedAction'),'Get_existing_png'),startsWith(outputs('Compose_FailedAction'),'Update_case_signature')),'E-FLOW-030',
if(or(startsWith(outputs('Compose_FailedAction'),'Populate_template'),startsWith(outputs('Compose_FailedAction'),'Create_temp_docx'),startsWith(outputs('Compose_FailedAction'),'Convert_to_pdf')),'E-FLOW-040',
if(or(startsWith(outputs('Compose_FailedAction'),'Create_pdf'),startsWith(outputs('Compose_FailedAction'),'Update_case_pdf'),startsWith(outputs('Compose_FailedAction'),'Get_pdf_content')),'E-FLOW-050',
if(or(startsWith(outputs('Compose_FailedAction'),'Send_email'),startsWith(outputs('Compose_FailedAction'),'Update_case_sent'),startsWith(outputs('Compose_FailedAction'),'Create_sendlog')),'E-FLOW-060',
'E-FLOW-000')))))))
```

**E33** — 利用者向けメッセージ（内部例外や個人情報を含めない）
```
if(equals(outputs('Compose_ErrorCode'),'E-FLOW-020'),'文書番号の採番に失敗しました。時間をおいて、もう一度送信してください。',
if(equals(outputs('Compose_ErrorCode'),'E-FLOW-030'),'署名画像の保存に失敗しました。もう一度送信してください。',
if(equals(outputs('Compose_ErrorCode'),'E-FLOW-040'),'確認書PDFの作成に失敗しました。管理者に連絡してください。',
if(equals(outputs('Compose_ErrorCode'),'E-FLOW-050'),'確認書PDFの保存に失敗しました。もう一度送信してください。',
if(equals(outputs('Compose_ErrorCode'),'E-FLOW-060'),'PDFのメール送信に失敗しました。顧客メールアドレスを確認して、もう一度送信してください。',
'処理中にエラーが発生しました。もう一度送信してください。')))))
```

**E34** — フロー実行ID（調査用）
```
workflow()['run']['name']
```

## Word テンプレート差し込み

**E40** — 署名日時（日本時間・和暦風の表記）
```
formatDateTime(convertTimeZone(outputs('Get_case')?['body/SignedAt'],'UTC','Tokyo Standard Time'),'yyyy年MM月dd日 HH:mm')
```

**E42** — 機番（機番なしの機体はその旨を印字）
```
if(equals(outputs('Get_case')?['body/NoSerialNo'],true),'（機番なしの機体）',coalesce(outputs('Get_case')?['body/SerialNo'],''))
```

**E43** — コメント
```
coalesce(outputs('Get_case')?['body/Comment'],'（記載なし）')
```

**E44** — 署名者お名前
```
coalesce(outputs('Get_case')?['body/SignerName'],'（記名なし）')
```

**E45** — 署名画像。画像コンテンツ コントロールにはオブジェクトを渡す。
`Populate_template` の `SignatureImage` 欄をコード表示に切り替えて、次を貼る。
```json
{
  "$content-type": "image/png",
  "$content": "@{variables('varSignatureBase64')}"
}
```
