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
| **検証済み** | **テスト用テナントへのインポート（2026-09-27）**。3フローと3接続参照が入ることを確認 |
| できない | **接続の作成**。SharePoint / OneDrive / Outlook は OAuth の同意が必要で、ポータルで1回だけ手作業になる（`pac connection create` は Dataverse 用のサービスプリンシパル接続しか作れない） |
| できない | **キャンバスアプリの CLI 投入**。後述 |

> **実環境で確認した結果（2026-09-27）**
> テスト用テナント（`tentoten067.onmicrosoft.com`）に開発者環境を CLI で作り、
> `pac solution import` でソリューションを投入した。
> 3フロー（Submit / Resend / Delete）と3接続参照がすべて入り、
> フローは接続が無いため「下書き（オフ）」になる。これは想定どおり。

## 0. SharePoint も CLI で作れる（2026-09-27 実環境で確認）

フローより先に、SharePoint のサイト・リスト7つ・ライブラリ4つ・初期データを
**Microsoft Graph 経由で一括作成**できる。PowerShell もアプリ登録も不要。

```bash
export AZURE_CONFIG_DIR=~/.cliauth/yanmar/azure

# 1. Azure CLI でサインイン（グループ＝チームサイトの作成に使う）
az login --use-device-code --tenant <テナント>.onmicrosoft.com --allow-no-subscriptions

# 2. リスト作成用のトークンを取得（Sites.Manage.All。初回は同意画面が出る）
python3 scripts/graph-device-login.py <テナント>.onmicrosoft.com

# 3. 作成（何度実行しても安全。既にあるものは飛ばし、足りない列だけ足す）
YAJ_CONFIG=solution/config.local.json python3 scripts/provision-sharepoint-graph.py --dry-run
YAJ_CONFIG=solution/config.local.json python3 scripts/provision-sharepoint-graph.py
```

### トークンが2種類要る理由

**Azure CLI のトークンではリストを作れない**（実環境で 403 を確認）。
Azure CLI のアプリは Graph に対して `Group.ReadWrite.All` などは持つが
`Sites.*` を持たず、サイトの読み取りはできても書き込みができない。
SharePoint の REST API も Azure CLI のトークンを 401 で拒否する。

そこで、リスト作成には Microsoft 公式の **Microsoft Graph Command Line Tools**
（Microsoft Graph PowerShell が使うアプリ）で device code サインインし、
`Sites.Manage.All` と `User.Read` だけを要求する。

| | 用途 | 権限 |
|---|---|---|
| Azure CLI | Microsoft 365 グループ（チームサイト）の作成 | `Group.ReadWrite.All` |
| Graph Command Line Tools | リスト・列・初期データ・ファイル | `Sites.Manage.All` / `User.Read` |

取得するのはアクセストークンだけ（約1時間で失効。リフレッシュトークンは要求しない）。
保存先はリポジトリ外の `~/.cliauth/yanmar/graph-sites-token.json`（本人のみ読み取り可）。
同意は Entra 管理センター → エンタープライズ アプリケーション →
Microsoft Graph Command Line Tools から取り消せる。

### 作られるもの・作られないもの

| 作られる | 作られない（Graph で設定できない。画面で行う） |
|---|---|
| Microsoft 365 グループと**プライベート**のチームサイト | ライブラリ単位の権限（`SignatureDocs` / `SignatureImages` の継承の中止） |
| リスト7つ・全70列（種類・必須・既定値・**インデックス25列**） | `SignatureCases` の項目レベルのアクセス許可 |
| ライブラリ4つ | |
| 組織マスタ105件・確認文面 v1.0・管理者（実行者）・Word テンプレート | |

`SignatureDocs` のバージョン管理は、新規ライブラリの既定でオンになっている。

### 実環境での確認結果

作成後に Graph で読み戻し、次を確認した。

- リスト7つ・ライブラリ4つがすべて存在する
- 70列すべてが `data/list-schema.json` の定義どおり（種類・複数行のプレーンテキスト・
  選択肢の値・日時の時刻・インデックス・必須）
- 組織マスタ105件（支社3種・ブロック13種）
- 確認文面の本文が元資料と**完全一致**（切り捨てなし）

## 1. 前提

| 項目 | 内容 |
|---|---|
| pac CLI | **2.12.2 以上**。`dotnet tool update -g microsoft.powerapps.cli.tool`。2.11.2 以前は `pac admin create`（環境作成）が動かない（後述） |
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

## 7. 実環境で判明した落とし穴

### 接続参照を RootComponents に載せるとインポートが失敗する

当初は接続参照を `Solution.xml` の RootComponents に種別 `10088` で載せていたが、
**インポートが `Invalid component type provided 10088` で失敗した**。
接続参照（connectionreference）は環境ごとに種別コードが変わるカスタム エンティティ扱いで、
固定値を書けない。パック時に出ていた
`Following root components are not defined in customizations: Type='10088'` の警告は
これを指していた（当初「無害」と判断していたのは誤り）。

**RootComponents から外し、`customizations.xml` の `<connectionreferences>` だけで定義する**
ように直した。これでパック時の警告も消え、インポートでは接続参照も一緒に入る。

### pac 2.11.2 では環境を作れない

`pac admin create` が、どの `--region` を指定しても失敗する。

| 指定 | エラー |
|---|---|
| `--region japan` | `macroRegion 'japan' is not valid`（サーバーがマクロリージョン名を要求） |
| `--region asia-pacific` | `environment location is not valid`（pac 自身が旧形式を要求） |

新しいテナントは**マクロリージョン**で環境を作る方式に変わっており、pac 2.4〜2.12 の
既知の不具合。**2.12.2 で追加された `--macro-region` を使う**。

```bash
pac admin create --type Developer --name "YAJ CancelFee Test" \
  --macro-region asia-pacific --language 1041 --currency JPY --domain yajcancelfeetest
```

### 新しいテナントでは「日本」を直接選べない

Advanced Data Residency（ADR）が無いテナントは、日本を単独では指定できず、
**Asia-Pacific**（シンガポール・オーストラリア・インド・日本・韓国）の中から自動配置になる。
今回は `crm7`（日本）に配置された。本番の Yanmar テナントに既存の日本リージョン環境が
あるなら、そちらを使うのが確実。

### 別案件の pac プロファイルに注意

同じマシンに別テナントの pac 認証プロファイルがあると、`pac solution import` は
**有効なプロファイルのテナントに向けて**実行される。`deploy.sh` は
`YAJ_PAC_PROFILE`（既定 `yanmar-test`）と有効プロファイルが一致しないと止まるようにした。

```bash
pac auth create --deviceCode --name yanmar-test   # 初回
pac auth select --name yanmar-test                # 切り替え
```

### テナント固有の設定は `config.local.json` に

`solution/config.json` は Yanmar 向けの配布状態のまま保ち、テスト用テナントの
サイトURLなどは `solution/config.local.json`（Git 管理外）に書いて `YAJ_CONFIG` で指定する。

```bash
YAJ_CONFIG=solution/config.local.json ./scripts/deploy.sh https://yajcancelfeetest.crm7.dynamics.com/
```

## 8. うまくいかないとき

| 症状 | 対処 |
|---|---|
| `solution import` が Dataverse 不在で失敗 | 対象環境に Dataverse が無い。開発者環境を作るか、環境に Dataverse を追加する |
| 接続参照が解決されない | `solution/deploy-settings.json` の `ConnectionId` を確認。接続が対象環境にあるか |
| フローがオフのままになる | `--activate-plugins` を付けているが、接続未解決だと有効化できない。接続を直してから画面でオンにする |
| PDFの日本語が文字化けする | `preview.doc` を Word で開いて再現するか確認。再現するなら `scripts/flow_definitions.py` の `build_confirmation_html()` のフォント指定を `MS Gothic` に変える |
| 変換が Bad gateway で失敗 | OneDrive コネクタの既知の問題。`Wait_for_file` の待ち時間（既定15秒）を増やす |

## 9. キャンバスアプリについて

**`.pa.yaml` だけからは CLI で `.msapp` を作れない**（実機で確認）。
`pac canvas pack --layout SourceCode` を実行すると次のように言われて止まる。

> Canvas apps packed using yaml SourceCode must be validated first by opening
> the app for edit within the Power Apps studio.

Studio で一度開いて検証されたアプリが前提になっている Microsoft 側の仕様で、
回避できない。アプリは画面から取り込む（[08 手順](08-manual-setup.md) の Part 4）。

アプリ本体はこのソリューションに含めていない。
`pac canvas pack` で `.msapp` を作る方法は
[apps/yaj-cancelfee-signature/README.md](../apps/yaj-cancelfee-signature/README.md)、
画面から取り込む方法は [08 手順](08-manual-setup.md) の Part 4 を参照。

アプリをソリューションに入れると環境間の移行は楽になるが、
Studio で編集するたびにソリューションから取り出し直す運用になり、
今の開発フェーズでは手数が増える。**フローだけ CLI 化する**のが現状のバランス。
