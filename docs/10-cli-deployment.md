# CLI でフローをデプロイする

Power Automate のフローを画面で1アクションずつ作るのは手間が大きい（3フローで90〜120分）。
`pac` CLI を使えば、**ソリューションとしてまとめてインポート**できる。

```bash
./scripts/deploy.sh https://<組織>.crm7.dynamics.com
```

## できること・できないこと

| | |
|---|---|
| できる | 3フローの定義（アクション・式・スコープ・実行条件・同時実行制御）を丸ごと投入 |
| できる | 接続参照のマッピング（設定ファイルで指定） |
| **必要** | **Dataverse が有効な環境**。ソリューションは Dataverse の仕組みなので、Dataverse の無い環境にはインポートできない |
| 未検証 | インポートそのもの。**この端末に対象テナントが無いため、パックまでしか確認できていない** |

> **実機で確認できているのはここまで**
> pac 2.11.2（macOS）で `solution init` / `pack` / `unpack` が動作すること、
> 生成したソースが警告1件（後述）だけで zip 化できること、
> zip の中身に3フローと3接続参照が正しく入ることまで。
> `pac solution import` は未実行。

## 1. 前提

| 項目 | 内容 |
|---|---|
| pac CLI | `dotnet tool install -g microsoft.powerapps.cli.tool`（2.11.2 で確認） |
| Python 3 | `pip install openpyxl python-docx jsonschema pyyaml` |
| 環境 | **Dataverse が有効な環境**（既定環境に Dataverse が無い場合は開発者環境を使う） |
| 先に済ませること | [Part 1・2](08-manual-setup.md)（SharePoint のリストと初期データ）。フローが参照するため |

## 2. 設定

[`solution/config.json`](../solution/config.json) を編集する。

| 項目 | 内容 |
|---|---|
| `sharePoint.siteUrl` | **必須**。`https://CONTOSO...` のままだとビルドが止まる |
| `pdfMode` | `html`（既定）= 標準コネクタのみ。`wordTemplate` = Premium が必要 |
| `oneDrive.tempFolder` | 中間 `.doc` の置き場。**サービスアカウントの OneDrive** を使うこと |
| `solution.*` | ソリューション名・発行者・バージョン |

### PDF生成方式

既定は **HTML→.doc 方式**。フロー内で確認書のHTMLを組み立て、UTF-8 BOM を付けて
`.doc` として OneDrive に保存し、**OneDrive for Business（標準コネクタ）の
「ファイルの変換」** で PDF にする。要件定義 10.1 で共有されていた
「中間ファイルを `.doc` 形式にする案」そのもの。

| | HTML→.doc（既定） | Word テンプレート |
|---|---|---|
| ライセンス | **標準コネクタのみ。追加費用なし** | Power Apps / Power Automate **Premium** |
| MFA 条件付きアクセス | 影響なし | **動かない既知の問題あり** |
| CLI デプロイ | **完全に自動化できる** | テンプレートの内部IDを解決するか、インポート後に画面で選び直す必要がある |
| 日本語の文字化け | UTF-8 BOM ＋ フォント指定で対策済み。**要実機確認** | 起きにくい |
| レイアウト | HTML/CSS の範囲 | Word で自由 |

方式を変えるときは `pdfMode` を書き換えて再生成するだけ。両方の定義が入っている。

### 出来上がる文書を先に見る

テナントが無くても、PDFになる前のレイアウトを確認できる。

```bash
python3 scripts/preview-document.py /tmp/preview
```

`preview.html`（ブラウザ用）と `preview.doc`（Word 用）が出る。
`preview.doc` はフローが OneDrive に作るファイルと**同じ中身**なので、
Word で開いて崩れがなければ、変換後のPDFもほぼ同じになる。

## 3. 実行

```bash
# 1. 認証（初回のみ）
pac auth create --deviceCode --environment https://<組織>.crm7.dynamics.com

# 2. デプロイ
./scripts/deploy.sh https://<組織>.crm7.dynamics.com
```

`deploy.sh` がやること。

1. 認証プロファイルの確認
2. `scripts/build-solution.py` でソリューション ソースを生成
3. `pac solution pack` で zip 化
4. **初回は** `pac solution create-settings` で接続参照の設定ファイルを作り、
   「接続IDを埋めて再実行してください」と言って止まる
5. 2回目以降は `pac solution import` でインポートし、変更を発行

### 接続IDの調べ方

初回実行で `solution/deploy-settings.json` が生成される。各接続参照の
`ConnectionId` に、対象テナントの接続のGUIDを入れる。

1. [make.powerapps.com](https://make.powerapps.com) → **接続**
2. 対象の接続（SharePoint / OneDrive for Business / Office 365 Outlook）を開く
3. URL 末尾のGUIDが接続ID

接続が無い場合は、先に各コネクタで接続を作っておく。

## 4. インポート後にやること

CLI で入るのは**フローの定義だけ**。次は画面で確認する。

- [ ] 3つのフローがインポートされ、**オンになっている**こと
- [ ] `YAJ-CancelFee-Submit` の トリガー → 設定 → **同時実行制御がオン・並列度1**
      （定義に含めているが、採番の重複に直結するので必ず目視確認）
- [ ] `Catch` スコープの実行条件が「失敗／タイムアウト／スキップ」の3つ
- [ ] `oneDrive.tempFolder` のフォルダーが OneDrive に存在すること（無ければ作る）
- [ ] Power Apps Studio → データ → フロー で3フローを再接続

## 5. ソースの構成

```
solution/
  config.json              サイトURL・方式・ソリューション名などの設定（ここだけ編集する）
  src/                     pac がパックする対象（自動生成。直接編集しない）
    Other/Solution.xml         マニフェストと RootComponents
    Other/Customizations.xml   接続参照
    Workflows/*.json           フロー定義
    Workflows/*.json.data.xml  フローのメタデータ
scripts/
  flow_definitions.py      3フローの定義（ここが実体。手順書と1対1）
  build-solution.py        config + 定義 → solution/src
  check-solution.py        インポート前の静的検査
  preview-document.py      確認書のプレビュー生成
  deploy.sh                認証確認 → 生成 → パック → インポート
  resolve-template-ids.sh  Word テンプレートの内部ID解決（wordTemplate 方式のときだけ）
```

**`solution/src/` は生成物。** 定義を直すときは `scripts/flow_definitions.py` を編集して
`python3 scripts/build-solution.py` で再生成する。GUID は名前から決定的に作っているので、
再生成しても差分が出るのは実際に変えたところだけ。

## 6. インポート前の検査

```bash
python3 scripts/check-solution.py
```

見るもの。

1. 未解決のプレースホルダが残っていないか
2. `runAfter` が参照するアクションが同じスコープにあるか
3. 式が参照する `outputs('X')` の `X` が実在するアクションか
4. 接続参照の論理名が定義JSONと Customizations.xml で一致しているか
5. 生成HTMLに必要な項目（文書番号・顧客名・確認文面・署名画像・
   日本語フォント・UTF-8 BOM）が揃っているか
   （`wordTemplate` 方式のときは、テンプレートの差し込み欄との一致を検査）

## 7. パック時に出る警告について

```
Following root components are not defined in customizations:
  Type='10088', Id (or schema name)='GenericComponent-gtb_office365_...'
```

接続参照（コンポーネント種別 10088）について SolutionPackager が出す警告。
**パックされた `customizations.xml` には接続参照が正しく入っている**ので
（`check-solution.py` で確認している）、この警告のままインポートして問題ないと判断している。
ただし**インポート自体が未検証**なので、ここでつまずいた場合は
接続参照を手で作り直す（フローを開いて接続を選び直す）ことで回避できる。

## 8. うまくいかないとき

| 症状 | 対処 |
|---|---|
| `solution import` が Dataverse 不在で失敗 | 対象環境に Dataverse が無い。開発者環境を作るか、環境に Dataverse を追加する |
| 接続参照が解決されない | `solution/deploy-settings.json` の `ConnectionId` を確認。接続が対象環境にあるか |
| フローがオフのままになる | `--activate-plugins` を付けているが、接続未解決だと有効化できない。接続を直してから画面でオンにする |
| PDFの日本語が文字化けする | `preview.doc` を Word で開いて再現するか確認。再現するなら `scripts/flow_definitions.py` の `build_confirmation_html()` のフォント指定を `MS Gothic` に変える |
| 変換が Bad gateway で失敗 | OneDrive コネクタの既知の問題。`Wait_for_file` の待ち時間（既定15秒）を増やす |

## 9. キャンバスアプリについて

アプリ本体はこのソリューションに含めていない。
`pac canvas pack` で `.msapp` を作る方法は
[apps/yaj-cancelfee-signature/README.md](../apps/yaj-cancelfee-signature/README.md)、
画面から取り込む方法は [08 手順](08-manual-setup.md) の Part 4 を参照。

アプリをソリューションに入れると環境間の移行は楽になるが、
Studio で編集するたびにソリューションから取り出し直す運用になり、
今の開発フェーズでは手数が増える。**フローだけ CLI 化する**のが現状のバランス。
