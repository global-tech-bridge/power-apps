# スキーマ取り込み用ファイル（列の一括作成）

`python3 scripts/build-schema-import-files.py` で `data/list-schema.json` から生成している。
手順は [docs/08-manual-setup.md](../../../docs/08-manual-setup.md) の Part 1-2 方法A。

各ファイルを SharePoint の **＋新規 → リスト → Excel から** で取り込むと、
ヘッダーから列がまとめて作られる。列を1つずつ手で作るより速い。

> **サンプル行は取り込み後に必ず削除する。**
> 1列目に `★取込後に削除★` と入っている行がサンプル行。
> 選択肢列の選択肢をウィザードに拾わせるために入れてあるだけのダミーである。

## 一覧

| リスト | 作られる列 | 手作業の列 | サンプル行 | 取り込み後の手当て |
|---|---:|---:|---:|---:|
| [`SignatureCases.xlsx`](SignatureCases.xlsx) | 33 | 1 | 6 | 14 項目 |
| [`ConsentMaster.xlsx`](ConsentMaster.xlsx) | 9 | 0 | 1 | 7 項目 |
| [`AppAdmins.xlsx`](AppAdmins.xlsx) | 4 | 0 | 1 | 3 項目 |
| [`SendLog.xlsx`](SendLog.xlsx) | 8 | 0 | 2 | 7 項目 |
| [`AuditLog.xlsx`](AuditLog.xlsx) | 7 | 0 | 4 | 7 項目 |

このフォルダの 5 ファイルで **61 列**。
`../OrgMaster.xlsx` の 7 列を足すと、全 **70 列**のうち **68 列**がウィザードで作られる。

手作業で作るのは残る **2 列**だけ。

| 手作業で作る列 | 種類 | 理由 |
|---|---|---|
| `SignatureCases.Operator` | ユーザーまたはグループ | ウィザードがユーザー列を作れない |
| `DocumentNumberCounter.LastNumber` | 数値 | 1列だけなので取り込む意味がない |

### ここに無いリスト

| リスト | 理由 |
|---|---|
| `OrgMaster` | 実データ入りの `../OrgMaster.xlsx` が列と105件をまとめて作るため |
| `DocumentNumberCounter` | 作る列が `LastNumber` の1つだけで、手で作るほうが速いため |


## SignatureCases

`SignatureCases.xlsx` … 作られる列 **33** / サンプル行 **6**

### ウィザードの列マッピングで選ぶ種類

| 列 | 選ぶ種類 |
|---|---|
| `DocumentNo` | 1行テキスト |
| `CustomerName` | 1行テキスト |
| `CustomerEmail` | 1行テキスト |
| `CustomerPhone` | 1行テキスト |
| `Model` | 1行テキスト |
| `SerialNo` | 1行テキスト |
| `NoSerialNo` | はい/いいえ |
| `MaintenanceType` | 選択肢 |
| `Comment` | 1行テキスト（取り込み後に複数行テキストへ変更） |
| `BranchName` | 1行テキスト |
| `BlockName` | 1行テキスト |
| `BlockCode` | 1行テキスト |
| `SiteName` | 1行テキスト |
| `SiteCode` | 1行テキスト |
| `Status` | 選択肢 |
| `ConsentId` | 1行テキスト |
| `ConsentTitle` | 1行テキスト |
| `ConsentVersion` | 1行テキスト |
| `ConsentTextSnapshot` | 1行テキスト（取り込み後に複数行テキストへ変更） |
| `SignedAt` | 日付と時刻 |
| `SignerName` | 1行テキスト |
| `OperatorEmail` | 1行テキスト |
| `OperatorName` | 1行テキスト |
| `SignatureImageUrl` | 1行テキスト |
| `PdfUrl` | 1行テキスト |
| `PdfFileName` | 1行テキスト |
| `RegisteredAt` | 日付と時刻 |
| `SentAt` | 日付と時刻 |
| `ResendCount` | 数値 |
| `ClientRequestId` | 1行テキスト |
| `ErrorCode` | 1行テキスト |
| `ErrorMessage` | 1行テキスト（取り込み後に複数行テキストへ変更） |
| `FlowRunId` | 1行テキスト |

### 取り込み後の手当て

- [ ] `Operator` … **User** 型なのでウィザードでは作れない。手作業で「ユーザーまたはグループ」列として追加する
- [ ] `CustomerName` … **必須**にする
- [ ] `NoSerialNo` … 既定値を**いいえ**にする
- [ ] `MaintenanceType` … 「値を手動で追加できる」を**いいえ**にし、選択肢が全部揃っているか確認する
- [ ] `Comment` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] `Status` … 「値を手動で追加できる」を**いいえ**にし、選択肢が全部揃っているか確認する
- [ ] `ConsentTextSnapshot` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] `SignedAt` … 含める内容を**日付と時刻**にする
- [ ] `RegisteredAt` … 含める内容を**日付と時刻**にする
- [ ] `SentAt` … 含める内容を**日付と時刻**にする
- [ ] `ResendCount` … 小数点以下の桁数を**0**にする
- [ ] `ErrorMessage` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] インデックスを作る: `DocumentNo` `CustomerName` `BranchName` `BlockName` `SiteName` `SiteCode` `Status` `SignedAt` `OperatorEmail` `OperatorName` `RegisteredAt` `ClientRequestId`
- [ ] `DocumentNo` が `★取込後に削除★` の行 **6 件**を削除する

## ConsentMaster

`ConsentMaster.xlsx` … 作られる列 **9** / サンプル行 **1**

### ウィザードの列マッピングで選ぶ種類

| 列 | 選ぶ種類 |
|---|---|
| `ConsentId` | 1行テキスト |
| `Version` | 1行テキスト |
| `EffectiveFrom` | 日付と時刻 |
| `EffectiveTo` | 日付と時刻 |
| `IsActive` | はい/いいえ |
| `DisplayTitle` | 1行テキスト |
| `Body` | 1行テキスト（取り込み後に複数行テキストへ変更） |
| `RevisedBy` | 1行テキスト |
| `RevisedAt` | 日付と時刻 |

### 取り込み後の手当て

- [ ] `EffectiveFrom` … 含める内容を**日付と時刻**にする
- [ ] `EffectiveTo` … 含める内容を**日付と時刻**にする
- [ ] `IsActive` … 既定値を**はい**にする
- [ ] `Body` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] `RevisedAt` … 含める内容を**日付と時刻**にする
- [ ] インデックスを作る: `ConsentId` `EffectiveFrom`
- [ ] `ConsentId` が `★取込後に削除★` の行 **1 件**を削除する

## AppAdmins

`AppAdmins.xlsx` … 作られる列 **4** / サンプル行 **1**

### ウィザードの列マッピングで選ぶ種類

| 列 | 選ぶ種類 |
|---|---|
| `UserEmail` | 1行テキスト |
| `UserName` | 1行テキスト |
| `IsActive` | はい/いいえ |
| `Note` | 1行テキスト |

### 取り込み後の手当て

- [ ] `IsActive` … 既定値を**はい**にする
- [ ] インデックスを作る: `UserEmail`
- [ ] `UserEmail` が `★取込後に削除★` の行 **1 件**を削除する

## SendLog

`SendLog.xlsx` … 作られる列 **8** / サンプル行 **2**

### ウィザードの列マッピングで選ぶ種類

| 列 | 選ぶ種類 |
|---|---|
| `CaseId` | 数値 |
| `DocumentNo` | 1行テキスト |
| `SentTo` | 1行テキスト |
| `SentBy` | 1行テキスト |
| `SentAt` | 日付と時刻 |
| `Kind` | 選択肢 |
| `Result` | 選択肢 |
| `ErrorMessage` | 1行テキスト（取り込み後に複数行テキストへ変更） |

### 取り込み後の手当て

- [ ] `CaseId` … 小数点以下の桁数を**0**にする
- [ ] `SentAt` … 含める内容を**日付と時刻**にする
- [ ] `Kind` … 「値を手動で追加できる」を**いいえ**にし、選択肢が全部揃っているか確認する
- [ ] `Result` … 「値を手動で追加できる」を**いいえ**にし、選択肢が全部揃っているか確認する
- [ ] `ErrorMessage` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] インデックスを作る: `CaseId` `DocumentNo` `SentAt`
- [ ] `DocumentNo` が `★取込後に削除★` の行 **2 件**を削除する

## AuditLog

`AuditLog.xlsx` … 作られる列 **7** / サンプル行 **4**

### ウィザードの列マッピングで選ぶ種類

| 列 | 選ぶ種類 |
|---|---|
| `Action` | 選択肢 |
| `CaseId` | 数値 |
| `DocumentNo` | 1行テキスト |
| `PerformedBy` | 1行テキスト |
| `PerformedAt` | 日付と時刻 |
| `Reason` | 1行テキスト（取り込み後に複数行テキストへ変更） |
| `Detail` | 1行テキスト（取り込み後に複数行テキストへ変更） |

### 取り込み後の手当て

- [ ] `Action` … 「値を手動で追加できる」を**いいえ**にし、選択肢が全部揃っているか確認する
- [ ] `CaseId` … 小数点以下の桁数を**0**にする
- [ ] `PerformedAt` … 含める内容を**日付と時刻**にする
- [ ] `Reason` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] `Detail` … 種類を**複数行テキスト**に変更し、リッチ テキストを**いいえ**にする
- [ ] インデックスを作る: `CaseId` `DocumentNo` `PerformedBy` `PerformedAt`
- [ ] `DocumentNo` が `★取込後に削除★` の行 **4 件**を削除する
