# YAJ 整備キャンセル料 電子署名アプリ（キャンバスアプリ ソースコード）

Power Apps キャンバスアプリのソースコード（Power Apps YAML v3.0 / Power Fx）。
[Microsoft 公式 pa.yaml v3.0 スキーマ](https://github.com/microsoft/PowerApps-Tooling/blob/master/schemas/pa-yaml/v3.0/pa.schema.yaml)
で検証済み（`scripts/validate-pa-yaml.py`）。

**取り込み手順は [docs/01-deployment.md](../../docs/01-deployment.md) の「4. キャンバスアプリの作成」。**
**CLI が使えない環境では [docs/08-manual-setup.md](../../docs/08-manual-setup.md) の Part 4。**

`Src/` が定義元。[`paste/`](paste/) は Studio の「コードの貼り付け」に
そのまま貼れるように整形した断片で、`Src/` から自動生成している
（`python3 scripts/gen-paste-files.py pa.schema.yaml`）。**編集は `Src/` 側で行う。**

## 画面構成

**タブレット縦（768 × 1024）**の1カラムレイアウト。
Studio 側で「設定 → 表示 → 向き: **縦**」を選ぶ（向きは YAML ではなくアプリ設定）。
全画面が縦画面に収まっていることは `scripts/check-layout.py` で検証している。

```
ListScreen（一覧・ホーム）
   │
   ├─「＋ 新規作成」──────────> EditScreen（新規作成・編集）
   │                                  │
   │  ドラフト行をタップ ────────────>│  ドラフト保存 ──> ListScreen
   │                                  │
   │                                  ▼
   │                            ConsentScreen（確認・署名）
   │                                  │ 確認ダイアログ → 送信
   │                        ┌─────────┴──────────┐
   │                        ▼                    ▼
   │              CompleteScreen（完了）   ErrorScreen（エラー）
   │                        │                    │ もう一度送信する
   │                        │                    └──> CompleteScreen
   │                        │
   └─ 確定行をタップ ──> DetailScreen（詳細・PDF再送・削除）
```

| ファイル | 画面 | 内容 |
|---|---|---|
| [`Src/App.pa.yaml`](Src/App.pa.yaml) | — | `StartScreen` と `OnStart`（マスタ読み込み・権限判定・初期値） |
| [`Src/ListScreen.pa.yaml`](Src/ListScreen.pa.yaml) | 一覧 | 検索・絞り込み・ギャラリー・新規作成 |
| [`Src/EditScreen.pa.yaml`](Src/EditScreen.pa.yaml) | 新規作成・編集 | 顧客／機体／組織の入力、ドラフト保存 |
| [`Src/ConsentScreen.pa.yaml`](Src/ConsentScreen.pa.yaml) | 確認・署名 | 確認文面の全文表示、確認チェック、手書き署名、送信 |
| [`Src/CompleteScreen.pa.yaml`](Src/CompleteScreen.pa.yaml) | 完了 | 文書番号と各工程の成功表示 |
| [`Src/ErrorScreen.pa.yaml`](Src/ErrorScreen.pa.yaml) | エラー | 失敗した工程の表示と冪等な再実行 |
| [`Src/DetailScreen.pa.yaml`](Src/DetailScreen.pa.yaml) | 詳細 | 参照、文面スナップショット、PDF再送、削除（管理者） |

## 実装上の要点

### 送信は「確認ダイアログ → タイマー → 実処理」の3段

`ConsentScreen` の送信ボタンは、直接フローを呼ばずに `varSubmitting` を立てるだけ。
実処理は非表示の `tmrSubmit`（`Duration: 400`）の `OnTimerEnd` で行う。

Power Fx の `OnSelect` は同期実行されるため、直接フローを呼ぶと
「送信処理中です」のオーバーレイが描画される前に処理が始まってしまう。
タイマーを1段挟むことで、UI が更新されてから実処理に入る。

### 完了画面へ行けるのは1箇所だけ

`Navigate(CompleteScreen, ...)` を書いているのは
`tmrSubmit.OnTimerEnd` と `ErrorScreen.btnRetry.OnSelect` の2箇所で、
どちらも `varFlowResult.Success` が真のときだけ実行する。
要件定義 7.4「保存・PDF生成・メール送信のいずれかが失敗した場合は、
この画面へ遷移しない」を構造として担保している。

### 再実行しても二重にならない

送信の直前に `varRequestId` を1回だけ発番し（`If(IsBlank(varRequestId), Set(...))`）、
エラー画面からの再実行でも同じ値を渡す。フロー側は
`DocumentNo` / `PdfUrl` / `Status` の有無を見て、済んでいる工程を飛ばす。
署名画像は `varSignatureBase64` に保持しているため、
署名画面を離れた後でも再実行できる。

### 確認文面のスナップショット

署名時に保存するのは、マスタの現在値ではなく
**画面に表示していたコントロールの `Text`**（`txtConsentBody.Text`）。
`DisplayMode.View` で読み取り専用にしているため利用者は書き換えられず、
「顧客が実際に見た文面」と保存内容が必ず一致する。
マスタを改訂しても過去の記録とPDFは変わらない（要件定義 11.3）。

### マスタは起動時にコレクションへ読み込む

`OrgMaster`（105件）・`ConsentMaster`・`AppAdmins` は `App.OnStart` で
`ClearCollect` する。いずれも少件数なので、委任制限（既定500件）を
気にせず `Distinct` や `LookUp` で扱える。

一方 `SignatureCases` は件数が増えるため、一覧の絞り込みは
**SharePoint に委任可能な演算子（`=` / `>=` / `<` / `StartsWith`）だけ**で
組んでいる（要件定義 15.2）。

### 組織の初期値

`App.OnStart` で、そのユーザーが最後に登録したレコードの
支社・ブロック・拠点を `varDefaultBranch` / `varDefaultBlock` / `varDefaultSite` に入れる。
一覧の絞り込みと入力画面の両方の初期値になるため、
日常的には自拠点の案件だけが見え、自拠点で登録できる。
異動時は選択し直せば、次回からは新しい値が初期値になる（要件定義 11.2）。

## 依存するデータソースとフロー

Studio で接続が必要なもの。**フローを先に作ってからアプリを作る。**

| 種類 | 名前 |
|---|---|
| SharePoint リスト | `SignatureCases` `OrgMaster` `ConsentMaster` `AppAdmins` `SendLog` `AuditLog` `DocumentNumberCounter` |
| フロー | `YAJ-CancelFee-Submit` `YAJ-CancelFee-Resend` `YAJ-CancelFee-Delete` |

## 検証

```bash
# 公式 v3.0 スキーマでの検証
curl -sLO https://raw.githubusercontent.com/microsoft/PowerApps-Tooling/master/schemas/pa-yaml/v3.0/pa.schema.yaml
python3 scripts/validate-pa-yaml.py pa.schema.yaml apps/yaj-cancelfee-signature/Src/*.pa.yaml

# 相互参照（コントロール名・変数・画面遷移・SharePoint列名）
python3 scripts/check-references.py

# タブレット縦（768×1024）に収まっているか
python3 scripts/check-layout.py

# Word テンプレートとフロー手順書の差し込み欄の一致
python3 scripts/check-template-fields.py

# インポート用ファイルが list-schema.json とずれていないか
python3 scripts/check-import-files.py
```

## `pac canvas pack` で .msapp にする場合

「コードの貼り付け」ではなく `.msapp` を作って取り込む方法。

```bash
# 1. Studio で空アプリ（PenInput を1つ配置しておく）を .msapp としてダウンロード
pac canvas unpack --msapp Base.msapp --sources ./work --layout SourceCode

# 2. ./work/Src/ 配下を本リポジトリの Src/ の内容で置き換える

# 3. 再梱包して Studio にインポート
pac canvas pack --msapp YajCancelFeeSignature.msapp --sources ./work --layout SourceCode
```

### macOS で pac CLI がクラッシュする場合

pac 2.6.x〜2.8.x には macOS で全コマンドが `System.NullReferenceException`
（RuntimeBroker）で落ちる既知の不具合がある
（[powerplatform-build-tools#1352](https://github.com/microsoft/powerplatform-build-tools/issues/1352)）。
回避策は 2.5.1 へのダウングレード。

```bash
dotnet tool uninstall -g microsoft.powerapps.cli.tool
dotnet tool install -g microsoft.powerapps.cli.tool --version 2.5.1
```

ただし 2.5.1 の `pac canvas validate` は旧スキーマ準拠のため、本リポジトリの
v3.0 YAML に対しては誤検知する。スキーマ検証は上記の
`scripts/validate-pa-yaml.py`（公式 v3.0 スキーマ + jsonschema）で行うこと。
