# 顧客デジタル署名受付アプリ（キャンバスアプリ ソースコード）

Power Apps キャンバスアプリ「顧客デジタル署名受付アプリ」のソースコード（Power Apps YAML v3.0 / Power Fx）。

生成元プロンプト: [prompts/power-apps/customer-digital-signature-app.md](../../prompts/power-apps/customer-digital-signature-app.md)

## ファイル構成

| ファイル | 内容 |
|---|---|
| [Src/App.pa.yaml](Src/App.pa.yaml) | アプリ定義（開始画面の指定） |
| [Src/SignScreen.pa.yaml](Src/SignScreen.pa.yaml) | 署名受付画面（顧客情報フォーム＋署名エリア） |
| [Src/CompleteScreen.pa.yaml](Src/CompleteScreen.pa.yaml) | 受付完了画面 |

YAMLは [Microsoft公式 pa.yaml v3.0 スキーマ](https://github.com/microsoft/PowerApps-Tooling/blob/master/schemas/pa-yaml/v3.0/pa.schema.yaml)（現行の Power Apps Studio「コードの表示」と同じ形式）で検証済みです。

## 画面設計

- **タブレット縦型（768×1024）** を想定した1カラムレイアウト。Studio 側で「設定 → 表示 → 向き: 縦」を選択してください（向きはYAMLではなくアプリ設定です）
- 上から順に：ヘッダー（タイトル＋署名日時）→ 顧客情報 → 同意内容（キャンセルポリシー）＋同意チェック → 署名方法 → 署名エリア → 送信ボタン

## 実装済みの要件

- 顧客名・メールアドレス・電話番号の入力フォーム
- 同意内容は **事前記載のキャンセルポリシー** を読み取り専用で表示（署名者は入力しない）。チェックボックス「上記のキャンセルポリシーを確認し、同意します」への同意が送信の必須条件
  - ポリシー本文は `SignScreen.pa.yaml` の `txtConsent.Default` に定義（キャンセル料率・期限はテンプレートなので実際の規定に合わせて修正してください）
  - 送信時は表示した本文がそのまま `同意内容` 列に保存されるため、「どの文言に同意したか」が記録に残ります
- 署名方法のラジオ切り替え：「手書き署名」⇔「テキスト署名」
  - 手書き署名: `PenInput` コントロール＋「署名をクリア」ボタン（`Reset(penSignature)`）
  - テキスト署名: 氏名タイピング用テキスト入力
- バリデーション: 顧客名未入力／メール形式不正／同意チェック未了／署名未完了の間は送信ボタンが無効化（`DisplayMode.Disabled`）され、赤字でエラー理由を表示
- 送信時: Dataverse `顧客署名` テーブルへ `Patch`（署名日時=Now()、ステータス=完了）→ 完了画面へ遷移
- 完了画面から「新しい署名を開始」でフォームをリセットして再開

## 事前準備：Dataverse テーブル

[make.powerapps.com](https://make.powerapps.com) → テーブル → 「新しいテーブル」で **顧客署名** テーブルを作成し、以下の列を追加してください（表示名はPower Fxから参照しているため一致させること）。

| 表示名 | 型 | 備考 |
|---|---|---|
| 顧客名 | テキスト | 必須。プライマリ列にしてもよい |
| メールアドレス | テキスト（形式: メール） | |
| 電話番号 | テキスト | |
| 同意内容 | 複数行テキスト | |
| 署名種別 | 選択肢 | 選択肢: `手書き署名` / `テキスト署名` |
| 署名画像 | 画像 | 手書き署名の保存用 |
| テキスト代替署名 | テキスト | タイピング署名の保存用 |
| 署名日時 | 日時 | |
| ステータス | 選択肢 | 選択肢: `完了` / `キャンセル` |

> **注意**: `SignScreen.pa.yaml` の送信ボタンでは選択肢列を `'署名種別 (顧客署名)'.手書き署名` のように参照しています。実際に生成される選択肢セット名が異なる場合は、Studio の数式バーの候補に合わせて修正してください。

## Studio への取り込み方法

### 方法A（推奨・簡単）: コードの貼り付け

1. Studio で空のキャンバスアプリ（タブレット形式）を新規作成し、「設定 → 表示」で向きを **縦** に変更（768×1024）
2. 「データ」→ 顧客署名 テーブルを追加
3. ツリービューで画面を右クリック →「コードの貼り付け」に `SignScreen.pa.yaml` / `CompleteScreen.pa.yaml` の `Screens:` 配下の内容を貼り付け
4. 数式エラーが出た場合は選択肢列の参照名を修正 → 保存・公開

### 方法B: pac canvas pack（.msapp 経由）

```bash
# 1. Studioで空アプリ（PenInputを1つ配置推奨）を .msapp としてダウンロード
# 2. ソースに展開
pac canvas unpack --msapp Base.msapp --sources ./work --layout SourceCode

# 3. ./work/Src/ 配下の *.pa.yaml を本リポジトリの Src/ の内容で置き換え

# 4. 再梱包して Studio にインポート
pac canvas pack --msapp CustomerSignatureApp.msapp --sources ./work --layout SourceCode
```

### ⚠️ macOS で pac CLI がクラッシュする場合

pac 2.6.x〜2.8.x には macOS で全コマンドが `System.NullReferenceException`（RuntimeBroker）で落ちる既知の不具合があります（[powerplatform-build-tools#1352](https://github.com/microsoft/powerplatform-build-tools/issues/1352)）。回避策は 2.5.1 へのダウングレード:

```bash
dotnet tool uninstall -g microsoft.powerapps.cli.tool
dotnet tool install -g microsoft.powerapps.cli.tool --version 2.5.1
```

ただし 2.5.1 の `pac canvas validate` は旧スキーマ準拠のため、本リポジトリの v3.0 YAML に対しては誤検知します。スキーマ検証は公式 v3.0 スキーマ＋`jsonschema` で行ってください（検証済み）。
