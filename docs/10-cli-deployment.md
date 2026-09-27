# CLI でデプロイする（フロー・SharePoint・アプリ）

> **ヤンマー様の本番環境に入れるときの手順は [11 本番環境へのデプロイ](11-production-deployment.md)**。
> この文書は、各コマンドのしくみと、テスト用テナントで判明したことの記録。
> コマンドは Mac の表記（`./scripts/deploy.sh`）で書いている。**Windows では `python scripts\deploy.py`・`python scripts\deploy-app.py`**（中身は同じ）。

Power Automate のフローを画面で1アクションずつ作るのは手間が大きい（3フローで90〜120分）。
`pac` CLI を使えば、**ソリューションとしてまとめてインポート**できる。

```bash
./scripts/deploy.sh https://<組織>.crm7.dynamics.com
```

## できること・できないこと

| | |
|---|---|
| できる | 3フローの定義（アクション・式・スコープ・実行条件）を丸ごと投入し、**オンにする** |
| できる | 接続参照のマッピング（設定ファイルで指定） |
| **必要** | **Dataverse が有効な環境**。ソリューションは Dataverse の仕組みなので、Dataverse の無い環境にはインポートできない |
| **検証済み** | **テスト用テナントへのインポート（2026-09-27）**。3フローと3接続参照が入ることを確認 |
| できない | **接続の作成**。SharePoint / OneDrive / Outlook は OAuth の同意が必要で、ポータルで1回だけ手作業になる（`pac connection create` は Dataverse 用のサービスプリンシパル接続しか作れない） |
| **初回だけ画面** | **キャンバスアプリの CLI 投入**。土台のアプリを一度 Studio で作れば、以降は `deploy-app.sh` で反映できる（9章） |

> **実環境で確認した結果（2026-09-27）**
> 検証用に用意したテスト用テナントに開発者環境を CLI で作り、
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
| リスト7つ・全72列（種類・必須・既定値・**インデックス26列**） | `SignatureCases` の項目レベルのアクセス許可 |
| ライブラリ4つ | |
| 組織マスタ105件・確認文面 v1.0・管理者（実行者）・Word テンプレート | |

`SignatureDocs` のバージョン管理は、新規ライブラリの既定でオンになっている。

### 実環境での確認結果

作成後に Graph で読み戻し、次を確認した。

- リスト7つ・ライブラリ4つがすべて存在する
- 全列が `data/list-schema.json` の定義どおり（種類・複数行のプレーンテキスト・
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
| `mail.senderMode` | `operator`（既定）= 送信・再送を押した担当者本人の Outlook で送る。フローの Outlook 接続参照を `runtimeSource: invoker`（実行のみのユーザーが提供）にする。`shared` = フローに登録した共通の接続で送る。**切り替えたら Studio の Power Automate ペインで送信・再送のフローを「最新の情報に更新」し、公開する**（アプリが利用者本人の Outlook 接続を求めるようになる） |
| `solution.*` | ソリューション名・発行者・バージョン。発行者は「YHDAI戦略DX推進G」（一意名 `YHDAIStrategyDX`、接頭辞 `yhdai`）。接続参照の論理名もこの接頭辞で始まる（例: `yhdai_sharepointonline_…`）。**本番に一度入れたら接頭辞は変えない**（変えると別の接続参照として入り、フローの付け替えが要る） |

### PDF生成方式

既定は **HTML→.doc 方式**。フロー内で確認書のHTMLを組み立て、UTF-8 BOM を付けて
`.doc` として OneDrive に保存し、**OneDrive for Business（標準コネクタ）の
「ファイルの変換」** で PDF にする。要件定義 10.1 で共有されていた
「中間ファイルを `.doc` 形式にする案」そのもの。

| | HTML→.doc（既定） | Word テンプレート |
|---|---|---|
| ライセンス | **標準コネクタのみ。追加費用なし** | Power Apps / Power Automate **Premium** |
| MFA 条件付きアクセス | 影響なし | **動かない既知の問題あり** |
| CLI デプロイ | **完全に自動化できる（実環境で確認）** | テンプレートの内部IDを解決するか、インポート後に画面で選び直す必要がある。**実環境では未検証**（PDF変換の入力指定を作り直す必要がある） |
| 日本語の文字化け | UTF-8 BOM ＋ フォント指定で対策。**実環境で文字化けなしを確認（2026-09-27）** | 起きにくい |
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

**テナントがあれば、メールを出さずに実際の変換結果（PDF）まで確かめられる。**

```bash
YAJ_CONFIG=solution/config.local.json python3 scripts/preview-document.py /tmp/preview
YAJ_CONFIG=solution/config.local.json python3 scripts/convert-preview-pdf.py /tmp/preview/preview.doc
```

フローと同じ Office の変換サービス（Graph の `/content?format=pdf`）で PDF にする。
一時ファイルは `WorkTemp` ライブラリに置き、変換後に消す。トークンは
`graph-device-login.py` で取得したもの（Sites.Manage.All）を使う。

> 2026-09-28、アプリから送信した確認書で**確認欄の見出し列が1文字ずつ縦に折り返し、
> 3ページになった**。Word が署名画像の元の寸法（736×200px＝約19.5cm）で表の幅を割り振り、
> 見出し列を押し潰していた。見本の署名画像が小さかったため、プレビューでは再現しなかった。
> 見本をペン入力と同じ 736×200 にし、表の列幅と画像の大きさを属性でも与えるように直した。

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
- [ ] 3つのフローがオンになっていること（`deploy.sh` が自動でオンにする。失敗したら理由が表示される）
      （定義に含めているが、採番の重複に直結するので必ず目視確認）
- [ ] `Catch` スコープの実行条件が「失敗／タイムアウト／スキップ」の3つ
- [ ] `oneDrive.tempFolder` のフォルダーが OneDrive に存在すること（無ければ作る）
- [ ] Power Apps Studio → データ → フロー で3フローを再接続

## 4b. 送信フローを CLI で1回通しで動かす（疎通テスト）

```bash
export AZURE_CONFIG_DIR=~/.cliauth/yanmar/azure
YAJ_CONFIG=solution/config.local.json python3 scripts/build-solution.py
YAJ_CONFIG=solution/config.local.json python3 scripts/e2e-submit-test.py <環境ID> /tmp/yaj-e2e \
  --org=https://<組織>.crm7.dynamics.com
```

テスト案件（顧客名「テスト太郎」、顧客メールなし）を作り、送信フローを1回実行して、
文書番号・状態・送信履歴・採番台帳を読み戻し、生成された PDF の中身（日本語の文字、
署名画像）を確かめて1ページずつ PNG にする。**メールが1通、実行者宛にだけ送られる。**

### Power Apps トリガーは CLI から呼べない

Power Apps (V2) トリガーは、呼び出し元が Power Apps であることをトークンで確認する。
Flow API 向け・Power Platform API 向けのトークンとも `MisMatchingOAuthClaims` /
`DirectApiAuthorizationRequired` で拒否された（2026-09-27 実環境で確認）。

さらに、手動実行（Button）トリガーに変えても、Flow API の実行 API が**本文を捨てる**
既知の不具合（[microsoft/power-platform-skills#625](https://github.com/microsoft/power-platform-skills/issues/625)）
で、必須入力付きでは起動できない（`TriggerInputSchemaMismatch`）。

そこで `e2e-submit-test.py` は、**同じ定義のままトリガーを入力なしの手動実行に変え、
渡すはずの値（案件ID・受付キー・署名画像）をフロー内に埋め込んだ一時コピー**を作って実行し、
終わったら削除する。採番・PDF生成・保存・メール送信・エラー処理は本物と同一の定義で動く。

### 実環境での結果（2026-09-27）

| 確認項目 | 結果 |
|---|---|
| 実行 | 成功（32秒） |
| 採番 | `20260927-001`。採番台帳に `CaseId` / 連番が記録された |
| 状態 | `Sent` |
| メール | 顧客メールが空のとき、担当者にだけ送られた（送信履歴にも記録） |
| PDF の日本語 | **文字化けなし**。本文・費用一覧・確認文・確認欄まですべて入っている |
| 署名画像 | **PDF に埋め込まれて表示された**（data URI 方式が有効） |
| レイアウト | 元資料の書簡形式どおり（2ページ） |

この実行で、`PdfUrl` と `SignatureImageUrl` が空になる不具合が見つかった
（SharePoint「ファイルの作成」の出力に存在しない `{Link}` を参照していた）。
`Path` から組み立てるように直し、組み立てた URL が実在するファイルを指すことを Graph で確認した。

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

## 9. キャンバスアプリも CLI で入れる（2026-09-28 実環境で確認）

```bash
./scripts/deploy-app.sh https://<組織>.crm7.dynamics.com
```

`apps/yaj-cancelfee-signature/Src/*.pa.yaml` の画面と数式を、環境のアプリに反映する。
**初回だけ**、土台になるアプリを画面で作っておく必要がある（下記 9-1）。
2回目以降は、pa.yaml を直して上のコマンドを流すだけでよい。

### しくみ

`.pa.yaml` だけからは `.msapp` を作れない。`pac canvas pack` は
「Studio で一度開いて検証されたアプリ」を前提にしていて、
データソースの接続情報（`References/DataSources.json`）も Studio で追加したときにしか作られない。

そこで **Studio で保存した版を土台にして、画面と数式だけを差し替える**。

1. `pac canvas download` で環境のアプリを `.msapp` として取得する
2. `pac canvas unpack --layout SourceCode` で展開し、`Src/*.pa.yaml` をリポジトリの内容に置き換える
   （画面の並び順を持つ `_EditorState.pa.yaml` もリポジトリの版に置き換える）
3. `pac canvas pack --layout SourceCode` で詰め直す。
   中の `packed.json` に `LoadFromYaml: true` が入り、Studio は開くときに pa.yaml から読み込む
4. アプリ用ソリューション（`YAJCancelFeeApp`）をエクスポートし、
   `CanvasApps/<名前>_DocumentUri.msapp` を差し替えてインポートする。
   キャンバスアプリはインポート時に公開される

### 9-1. 初回だけ画面で行うこと（15分ほど）

0. `./scripts/deploy-app.sh` を一度流す。アプリ用ソリューション `YAJCancelFeeApp`（発行者 YHDAI戦略DX推進G）を
   作ったうえで、土台のアプリが無いと言って止まる（手順は [11](11-production-deployment.md) の 7-2 と同じ）
1. そのソリューションの中で **新規 → アプリ → キャンバス アプリ**（タブレット）を作り、[08 手順](08-manual-setup.md) の 4-1 の設定
   （縦向き・4:3 = 768×1024、データ行の制限 2000）を行う
2. 4-2 のとおりデータソースを追加する
   （リスト7つ、**ライブラリ `SignatureImages`**、**Office 365 ユーザー**、フロー3つ）。
   `deploy-app.sh` は、土台にこれらがそろっていないと止まる
3. **保存して公開する**（画面やコントロールは作らなくてよい。次の手順で入る）。
   `pac canvas download` は**最後に公開した版**を取ってくるので、保存だけでは土台に反映されない。
   後からデータソースを足したときも、必ず公開まで行う
4. Studio を閉じてから `./scripts/deploy-app.sh` をもう一度実行する

> ソリューションの外で作ってしまったアプリは、**ソリューション → 既存を追加 → アプリ →
> キャンバス アプリ → Dataverse の外部** タブから追加すれば使える（テスト用テナントではこの方法で入れた）。

> **Studio を開いたまま実行しない。** 開いていた Studio が古い版で上書き保存すると、
> 差し替えが消える。また、前のセッションが編集権を持ったままだと読み取り専用で開くので、
> そのときは画面上部の **Override** で編集権を取り直す。

### 実環境で判明したこと

| 事象 | 内容 |
|---|---|
| **コントロール名の重複で開けない** | 名前はアプリ全体で一意でなければならない。`lblTitle` が6画面にあり、`PA2110 An entity with name 'lblTitle' already exists` で開けなかった。**コードの貼り付けでは Studio が黙って `lblTitle_1` と改名するため気づけず、数式が別の画面の同名コントロールを指す不具合になっていた**。画面名を付けた名前に直し、`check-references.py` で検出するようにした |
| `EditorState` が2か所にあると開けない | `Only one module may specify the EditorState top-level property`。以前は `App.pa.yaml` の末尾に書いていたが、Studio が保存すると別ファイル `_EditorState.pa.yaml` にも書くため重なった。Studio と同じく `_EditorState.pa.yaml` だけに書く |
| `--publish-changes` が戻らない | インポート自体は9秒で終わるが、「すべてのカスタマイズの公開」が10分以上戻らなかった。キャンバスアプリには不要なので付けない |
| インポート後に pac が戻らないことがある | 通信が不安定なとき、インポートジョブは完了しているのに pac が応答待ちのまま止まった（SSL タイムアウトも1回）。10分以上止まったら pac を止め、Studio で開いて反映を確かめる |
| 下書きを削除しても一覧に残る | 更新・削除はフロー側で行うため、アプリが持つ一覧が古いまま。フロー呼び出しの成功後に `Refresh(SignatureCases)` を入れた |
| 詳細画面の手書き署名が空白 | 画像の URL を `Image` に渡しても認証が付かない。ライブラリをデータソースにして `'{Thumbnail}'.Large` で表示するように変えた（`SignatureImageItemId` 列を追加） |
| データソースを足したのに `Name isn't valid` | `pac canvas download` は最後に**公開**した版を返す。Studio で保存しただけでは土台に入らない |
| 表示名が言語で変わる | ライブラリの `{Thumbnail}` 列は日本語テナントでは表示名が「サムネイル」になり、`Thumbnail` では通らなかった。論理名 `'{Thumbnail}'` で書く |
| 内蔵ブラウザーから貼り付けできない | 自動操作用のブラウザーではクリップボードの読み取りが拒否され、「コードの貼り付け」が使えなかった。手作業で貼る場合は普段のブラウザーで行う |

### 画面から取り込む方法（CLI を使わない場合）

[08 手順](08-manual-setup.md) の Part 4（コードの貼り付け）。
