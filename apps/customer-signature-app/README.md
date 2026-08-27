# 顧客デジタル署名受付アプリ（キャンバスアプリ ソースコード）

Power Apps キャンバスアプリ「顧客デジタル署名受付アプリ」のソースコード（Power Apps YAML v3.0 / Power Fx）。

生成元プロンプト: [prompts/power-apps/customer-digital-signature-app.md](../../prompts/power-apps/customer-digital-signature-app.md)

## ファイル構成

| ファイル | 内容 |
|---|---|
| [Src/App.pa.yaml](Src/App.pa.yaml) | アプリ定義（開始画面の指定） |
| [Src/SignScreen.pa.yaml](Src/SignScreen.pa.yaml) | 署名受付画面（顧客・機器情報フォーム＋同意＋署名エリア） |
| [Src/CompleteScreen.pa.yaml](Src/CompleteScreen.pa.yaml) | 受付完了画面 |

YAMLは [Microsoft公式 pa.yaml v3.0 スキーマ](https://github.com/microsoft/PowerApps-Tooling/blob/master/schemas/pa-yaml/v3.0/pa.schema.yaml)（現行の Power Apps Studio「コードの表示」と同じ形式）で検証済みです。

## 画面設計

- **タブレット縦型（768×1024）** を想定した1カラムレイアウト。Studio 側で「設定 → 表示 → 向き: 縦」を選択してください（向きはYAMLではなくアプリ設定です）
- 上から順に：ヘッダー（タイトル＋署名日時）→ 顧客情報 → 同意内容（キャンセルポリシー）＋同意チェック → 署名方法 → 署名エリア → 送信ボタン

## 実装済みの要件

- 顧客名（必須）・メールアドレス・電話番号・**メーカー・型式・機番** の入力フォーム（縦型に収めるためメール／電話は2列、メーカー／型式／機番は3列配置）
- 同意内容は **事前記載のキャンセルポリシー** を読み取り専用で表示（署名者は入力しない）。チェックボックス「上記のキャンセルポリシーを確認し、同意します」への同意が送信の必須条件
  - ポリシー本文は `SignScreen.pa.yaml` の `txtConsent.Default` に定義（キャンセル料率・期限はテンプレートなので実際の規定に合わせて修正してください）
  - 送信時は表示した本文がそのまま `同意内容` 列に保存されるため、「どの文言に同意したか」が記録に残ります
- 署名方法のラジオ切り替え：「手書き署名」⇔「テキスト署名」
  - 手書き署名: `PenInput` コントロール＋「署名をクリア」ボタン（`Reset(penSignature)`）
  - テキスト署名: 氏名タイピング用テキスト入力
- バリデーション: 顧客名未入力／メール形式不正／同意チェック未了／署名未完了の間は送信ボタンが無効化（`DisplayMode.Disabled`）され、赤字でエラー理由を表示
- 送信時: SharePoint リスト `顧客署名` へ `Patch`（署名日時=Now()、ステータス=完了）→ 完了画面へ遷移
- 完了画面から「新しい署名を開始」でフォームをリセットして再開

## 事前準備：SharePoint リスト

データソースは **SharePoint リスト** です。任意のSharePointサイトで「＋ 新規 → リスト → 空白のリスト」を選び、リスト名を **顧客署名** にして以下の列を作成してください（列名はPower Fxから参照しているため一致させること）。

| 列名 | 種類 | 備考 |
|---|---|---|
| 顧客名 | 1行テキスト | 既定の **「タイトル」列の名前を「顧客名」に変更** して使う（必須列のため） |
| メールアドレス | 1行テキスト | |
| 電話番号 | 1行テキスト | |
| メーカー | 1行テキスト | |
| 型式 | 1行テキスト | |
| 機番 | 1行テキスト | |
| 同意内容 | 複数行テキスト | 「プレーンテキスト」。既定の行数上限は無視して全文保存されます |
| 署名種別 | 選択肢 | 選択肢: `手書き署名` / `テキスト署名`（「値を手動で追加できる」はOFF） |
| 署名画像 | 画像 | 手書き署名の保存用（モダンリストの「画像」列） |
| テキスト代替署名 | 1行テキスト | タイピング署名の保存用 |
| 署名日時 | 日付と時刻 | 「時刻を含める」をON |
| ステータス | 選択肢 | 選択肢: `完了` / `キャンセル` |

> **列名の注意**: SharePoint の列は「表示名」で参照します。作成後に列名を変えても内部名は最初の名前のまま残りますが、Power Apps は表示名を使うため問題ありません。`Patch(顧客署名, ...)` のリスト名も表示名です。

> **署名画像について**: SharePoint の画像列への `Patch` はサポートされていますが、環境によって制約が出ることがあります。うまく保存できない場合は「署名画像」を複数行テキスト列に変え、`署名画像: penSignature.Image` の代わりに `署名画像: JSON(penSignature.Image, JSONFormat.IncludeBinaryData)` で Base64 文字列として保存する方法に切り替えてください。

## Studio への取り込み方法

### 方法A（推奨・簡単）: コードの貼り付け

1. Studio で空のキャンバスアプリ（タブレット形式）を新規作成し、「設定 → 表示」で向きを **縦** に変更（768×1024）
2. 「データ → データの追加 → SharePoint」→ サイトURLを入力 → リスト「顧客署名」にチェックして接続
3. ツリービューで画面を右クリック →「コードの貼り付け」に `SignScreen.pa.yaml` / `CompleteScreen.pa.yaml` の `Screens:` 配下の内容を貼り付け
4. 初期の Screen1 を削除し、プレビューで手書き／テキスト両方を送信してリストに行が入ることを確認 → 保存・公開

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
