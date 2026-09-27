# ヤンマー本番環境へのデプロイ手順（CLI 中心・管理者権限なし）

テスト用テナントで通した手順（2026-09-27〜28）を、**管理者権限が無いアカウント**で
ヤンマー様のテナントに入れる前提で並べ直したもの。
コマンドの意味や、つまずいた経緯の詳細は [10 CLIデプロイ](10-cli-deployment.md) を参照。

## 0. 全体像

| # | 作業 | 方法 | 時間 | 管理者権限が無いと止まる可能性 |
|---:|---|---|---:|---|
| 1 | IT 部門への依頼事項を確認する | 下の「1.」の表 | — | — |
| 2 | この PC の準備（テスト用テナントと混ぜない） | CLI | 10分 | — |
| 3 | 環境を決めて、事前チェック | CLI | 10分 | **Dataverse の環境と権限** |
| 4 | SharePoint（サイト・リスト・初期データ） | CLI（だめなら Excel 取り込み） | 5〜45分 | **サイトの作成、Graph への同意** |
| 5 | 接続3つと OneDrive のフォルダを作る | 画面 | 5分 | DLP ポリシー |
| 6 | フロー3つを入れる | CLI | 5分 | 環境の権限 |
| 7 | アプリを入れる | 初回だけ画面15分 → CLI | 20分 | 環境の権限 |
| 8 | 動作確認（自分宛てに1通だけ送る） | 画面 | 15分 | — |
| 9 | 利用者に公開する | 画面 | 15分 | 共有先のグループ |

**3 の事前チェック（`preflight.py`）で ✗ が出たところだけ IT 部門に依頼すればよい。**
何も作らない・変えないので、最初に何度流してもよい。

## 1. 管理者権限が無いと止まるもの（IT 部門への依頼候補）

| 必要なもの | 自分でできる条件 | できないときに依頼すること |
|---|---|---|
| **Dataverse が有効な環境** | 自分で**開発者環境**を作れる設定になっている（多くのテナントの既定） | 専用の環境を用意してもらう。本番運用はこちらを推奨（開発者環境は個人の検証用） |
| その環境での **System Customizer（システム カスタマイザー）** ロール | 自分で作った開発者環境なら自動で管理者になる | 環境にロールを付けてもらう。ソリューションのインポートとアプリ用ソリューションの作成に要る |
| **SharePoint のプライベートなサイト**と、その**所有者** | Microsoft 365 グループ（チームサイト）を自分で作れる | サイトを作って所有者に追加してもらう。URL をもらえば以降は CLI で進められる |
| **Microsoft Graph Command Line Tools への同意**（Sites.Manage.All） | ユーザーによる同意が許可されている | 同意してもらう。**できなければ Excel からリストを作る手順に切り替える**（4-3） |
| DLP で SharePoint / OneDrive for Business / Office 365 Outlook / Office 365 ユーザーが**同じ分類** | — | 分類をそろえてもらう。違うとフローとアプリが保存・実行できない |
| （推奨）**サービスアカウント** | — | SharePoint と OneDrive の接続に使う。試行は自分のアカウントでよい |
| 利用者の**セキュリティ グループ** | — | アプリと SharePoint サイトの共有先 |

テナント全体の設定の確認項目は [09 環境確認シート](09-environment-checklist.md) にまとめてある。

> **条件付きアクセスで「デバイス コード」のサインインが禁止されている**テナントが多い。
> 本手順のサインインは、すべて**ブラウザーでのサインイン**でもできるようにしてある
> （`pac auth create` と `az login` は既定でブラウザー、Graph は `--browser`）。

## 2. この PC の準備（Windows）

**デプロイ作業は Windows の PowerShell で行う前提**で書いている（Mac でも同じスクリプトが動く。末尾の補足を参照）。
スクリプトは Python で書いてあり、`python scripts\xxx.py` で実行する。bash は要らない。

### 2-1. ツール（PC の管理者権限なしで入れられる方法）

| ツール | 入れ方 | 確認 |
|---|---|---|
| **Python 3.10 以降** | [python.org](https://www.python.org/downloads/windows/) のインストーラーで「**Install for all users」のチェックを外し**、「**Add python.exe to PATH**」にチェック。または Microsoft Store の Python | `python --version` |
| **Power Platform CLI（pac）** | どちらか。① VS Code に拡張機能「**Power Platform Tools**」を入れる（VS Code のターミナルで `pac` が使える）② .NET SDK を個人用に入れてから `dotnet tool install --global Microsoft.PowerApps.CLI.Tool` | `pac help` |
| **Azure CLI** | **ZIP 版**を展開して、`bin` フォルダを自分の PATH に足す（MSI 版は PC の管理者権限が要る）。下のコマンド参照 | `az --version` |
| Python のモジュール | `python -m pip install --user pyyaml jsonschema openpyxl python-docx` | — |
| このリポジトリ | Git があれば `git clone`。無ければ GitHub の **Code → Download ZIP** で取ってきて展開 | — |

Azure CLI の ZIP 版（PowerShell。管理者権限は不要）:

```powershell
$dest = "$HOME\azure-cli"
Invoke-WebRequest https://aka.ms/installazurecliwindowszipx64 -OutFile "$HOME\azure-cli.zip"
Expand-Archive "$HOME\azure-cli.zip" -DestinationPath $dest -Force
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$dest\bin", "User")
# PowerShell を開き直して az --version
```

### 2-2. サインイン情報の置き場と設定（環境変数）

ほかのテナント（テスト用テナントなど）のサインイン情報と混ぜないよう、置き場を本番用に分ける。
**この PC をヤンマー様の作業にしか使わないなら、ユーザーの環境変数に一度登録しておけばよい**
（管理者権限は不要。PowerShell を開き直すと効く）。

```powershell
[Environment]::SetEnvironmentVariable("AZURE_CONFIG_DIR", "$HOME\.cliauth\yanmar-prod\azure", "User")  # Azure CLI のサインイン情報
[Environment]::SetEnvironmentVariable("YAJ_CRED_HOME",   "$HOME\.cliauth\yanmar-prod",        "User")  # Graph のトークン
[Environment]::SetEnvironmentVariable("YAJ_PAC_PROFILE", "yanmar-prod",                         "User")  # 違うと deploy が止まる
[Environment]::SetEnvironmentVariable("YAJ_CONFIG",      "solution\config.local.yanmar.json",   "User")  # 本番用の設定（git に入らない）
[Environment]::SetEnvironmentVariable("PYTHONUTF8",      "1",                                   "User")  # Python を UTF-8 で動かす
```

ほかの作業にも使う PC なら、登録せずに**毎回 PowerShell に貼り付ける**（そのウィンドウだけに効く）:

```powershell
$env:AZURE_CONFIG_DIR = "$HOME\.cliauth\yanmar-prod\azure"
$env:YAJ_CRED_HOME    = "$HOME\.cliauth\yanmar-prod"
$env:YAJ_PAC_PROFILE  = "yanmar-prod"
$env:YAJ_CONFIG       = "solution\config.local.yanmar.json"
$env:PYTHONUTF8       = "1"
```

> `.ps1` ファイルに保存して実行する方法は、会社の PC ではスクリプトの実行が禁止されている
> （実行ポリシー）ことが多いので使っていない。

以降のコマンドは、**リポジトリのフォルダ（`power-apps`）で**実行する。

```powershell
cd $HOME\power-apps
```

### 2-3. サインイン

```powershell
# pac（ブラウザーが開く。開けない環境では --deviceCode）
pac auth create --name yanmar-prod
pac auth select --name yanmar-prod

# Azure CLI（フローをオンにする処理と、事前チェックで使う。ブラウザーが開く）
az login --tenant <テナント>.onmicrosoft.com --allow-no-subscriptions
```

`<テナント>` は、SharePoint の URL が `https://yanmar.sharepoint.com` なら `yanmar.onmicrosoft.com`。

### 2-4. 設定ファイル

```powershell
Copy-Item solution\config.json solution\config.local.yanmar.json
notepad solution\config.local.yanmar.json
```

次を直す（ほかはそのまま）。**UTF-8 のまま保存する**（メモ帳の既定は UTF-8 なのでそのままでよい）。

| 項目 | 値 |
|---|---|
| `sharePoint.siteUrl` | 使うサイトの URL（例 `https://yanmar.sharepoint.com/sites/yaj-cancelfee`） |
| `mail.senderMode` | `operator`（既定。送信を押した担当者本人の Outlook から送る）／`shared` |
| `oneDrive.tempFolder` | 中間ファイルの置き場（既定 `/YAJ-CancelFee-Temp`）。5 で作る |

`solution\config.json` 自体は配布用の既定値のまま触らない（`config.local*.json` は git に入らない）。

## 3. 環境を決めて、事前チェック

### 3-1. 使う環境を決める

```powershell
pac env list          # 自分が入れる Dataverse 環境の一覧（管理者権限は不要）
```

| 候補 | 使ってよいか |
|---|---|
| IT 部門が用意した専用環境 | **本番はこれ**。System Customizer ロールをもらう |
| 自分で作る開発者環境 | **試行ならこれでよい**。本番の利用者が使う運用には向かない（個人の環境のため） |
| 既定の環境 | Dataverse が無いことが多く、無ければソリューションを入れられない |

開発者環境を自分で作る場合（テナントで許可されていれば、管理者権限は不要）:

```powershell
pac admin create --name "YAJ CancelFee" --type Developer --macro-region asia-pacific
```

拒否された場合は、[Power Platform 管理センター](https://admin.powerplatform.microsoft.com/) →
環境 → **新規** → 種類「開発者」でも作れる。それも拒否されたら IT 部門に依頼する。

> 開発者環境で試した後に専用環境へ移すときは、**同じ手順を専用環境の URL でやり直す**だけでよい
> （SharePoint のサイトはそのまま使える）。

### 3-2. 事前チェック

```powershell
python scripts\preflight.py https://<組織>.crm7.dynamics.com
```

ツール・設定・pac・Azure CLI・**Dataverse の権限**・既存のソリューション・接続・SharePoint を順に調べ、
✗ の項目には「→ 次にやること」を出す。例:

```text
✓ Dataverse   必要な権限はそろっています（ロール: System Customizer, Basic User）
✗ 接続        Office 365 Outlook の接続がありません（または切断中）
              → make.powerapps.com → 接続 → 新しい接続 で作る（サインインして許可するだけ）
! SharePoint  サイトがまだありません
              → 自分でチームサイトを作れるなら provision-sharepoint-graph.py が作る。…
```

権限はロール名ではなく**実際に持っている権限**（インポート・エクスポート・ソリューション作成・
フロー作成など）で判定する。ロール名は言語で変わるため。

## 4. SharePoint

### 4-1. サイト

- **自分で作れる場合**: 4-2 のスクリプトが、`siteUrl` の末尾（`yaj-cancelfee`）を名前にして
  プライベートなチームサイトを作る（Microsoft 365 グループを作れる設定のとき）
- **作れない場合**: IT 部門にプライベートなサイトを作ってもらい、**所有者**に追加してもらう。
  もらった URL を `sharePoint.siteUrl` に入れる

### 4-2. リスト・ライブラリ・初期データ（CLI）

```powershell
# リスト作成用のトークン（Sites.Manage.All）。初回は同意画面が出る
python scripts\graph-device-login.py <テナント>.onmicrosoft.com --browser
#   device code が使えるテナントなら --browser は不要

python scripts\provision-sharepoint-graph.py --dry-run   # 作られるものを確認
python scripts\provision-sharepoint-graph.py
```

作られるもの: リスト7つ（72列、インデックス26列）、ライブラリ4つ、組織マスタ105件、
確認文面 v1.0、管理者（**実行した本人**を `AppAdmins` に登録）。
何度流しても安全（あるものは飛ばし、足りない列だけ足す）。

### 4-3. 同意が禁止されている場合（Excel から作る）

`graph-device-login.py` で「管理者の承認が必要」と出たら、CLI ではリストを作れない。
画面で、Excel から列ごとまとめて作る（30〜45分）。

- 手順: [08 手順](08-manual-setup.md) の **Part 1（方法A）** と **Part 2**
- ファイル: [data/import/](../data/import/)（列の定義入りの Excel と初期データ）

### 4-4. 権限（画面・サイトの所有者が行う）

[04 権限設計](04-permissions.md) のとおり、`SignatureDocs` / `SignatureImages` の権限の継承を止め、
利用者を閲覧のみにする。`SignatureCases` の項目レベルのアクセス許可も設定する。
**試行の段階では後回しでよい**（利用者に公開する前には必ず行う）。

## 5. 接続と OneDrive のフォルダ（画面・5分）

接続は OAuth の許可が要るため、CLI では作れない。

1. [make.powerapps.com](https://make.powerapps.com) → 右上で**対象の環境**を選ぶ
2. 左の **接続** → **新しい接続** で、次の3つを作る（サインインして許可するだけ）
   - **SharePoint**
   - **OneDrive for Business**
   - **Office 365 Outlook**
3. OneDrive（接続に使ったアカウント）をブラウザーで開き、フォルダ `YAJ-CancelFee-Temp` を作る

> `mail.senderMode = operator` でも Office 365 Outlook の接続は1つ要る（フローの接続参照に結び付けるため）。
> 実際のメールは、送信を押した担当者本人の接続で送られる。
>
> 本番運用では、SharePoint と OneDrive の接続は**サービスアカウント**で作る
> （個人の異動・退職でフローが止まらないように。要件定義 15.5）。

## 6. フローを入れる（CLI）

```powershell
python scripts\deploy.py https://<組織>.crm7.dynamics.com
```

ソリューションの生成 → 接続 ID の自動設定 → インポート → **3フローをオン**まで行う。

- 「接続が複数あります」で止まったら、使わない接続を消すか、`solution\deploy-settings.json` の
  `ConnectionId` を手で入れてから再実行
- インポート後に pac が戻らないことがある（テスト用テナントで2回）。スクリプトは15分で pac を打ち切り、
  Dataverse のインポートジョブが完了していれば成功として先に進む（ジョブ自体は数十秒で終わっている）

## 7. アプリを入れる（初回だけ画面 → CLI）

### 7-1. まず流す

```powershell
python scripts\deploy-app.py https://<組織>.crm7.dynamics.com
```

初回は、アプリ用のソリューション `YAJCancelFeeApp`（発行者は 6 で作られた YHDAI戦略DX推進G）を作ったうえで、
「土台のアプリがありません」と言って止まる。

### 7-2. 土台のアプリを作る（画面・15分）

`.pa.yaml` だけからはアプリを作れないため（[10](10-cli-deployment.md) の 9章）、空のアプリを1回だけ画面で作る。

1. make.powerapps.com → **ソリューション** → `YAJ 整備キャンセル料 確認書（アプリ）` →
   **新規** → **アプリ** → **キャンバス アプリ**。名前 `YAJ 整備キャンセル料 確認書`、形式 **タブレット**
2. **設定** → **表示**: 向き **縦**、サイズ **4:3**（768×1024）／ **全般**: データ行の制限 **2000**
3. **データの追加**
   - **SharePoint** → サイトの URL → リスト7つ（`SignatureCases` `OrgMaster` `ConsentMaster` `AppAdmins`
     `SendLog` `AuditLog` `DocumentNumberCounter`）と**ライブラリ `SignatureImages`**
   - **Office 365 ユーザー**
4. 左の **…** → **Power Automate** → **フローの追加** → `YAJ-CancelFee-Submit` `-Resend` `-Delete`
5. **保存** → **公開**（公開しないと 7-3 で「データソースが足りません」になる）→ **Studio を閉じる**

画面やコントロールは作らなくてよい。7-3 でリポジトリの内容が入る。

### 7-3. もう一度流す

```powershell
python scripts\deploy-app.py https://<組織>.crm7.dynamics.com
```

データソースがそろっているかを確かめてから、6画面・211コントロールを差し替えてインポートする。
以後、アプリを直したときはこのコマンドだけでよい（**Studio を閉じてから**流す）。

## 8. 動作確認

1. `python scripts\preflight.py <環境URL>` がすべて ✓ になること
2. アプリを開く（make.powerapps.com → アプリ → 再生）。**初回は接続の許可画面**が出るので「許可」
3. 画面を一通り触る: 一覧 → 新規作成 → 下書き保存 → 下書きを削除（メールは出ない）
4. **送信テスト**: 顧客メールを**空欄**にして送信 → 自分宛てに1通だけ届く。
   受信した PDF（2ページ、確認欄と署名）と、詳細画面の署名画像を確かめる
5. テストの記録は、詳細画面の **削除**（管理者のみ）で消す。理由は監査ログに残る

メールを出さずに PDF のレイアウトだけ確かめる方法もある（[10](10-cli-deployment.md) の「出来上がる文書を先に見る」）。

## 9. 利用者に公開する（画面）

| 作業 | 場所 |
|---|---|
| アプリを利用者のセキュリティ グループに共有する。**共同所有者**を自分以外に2名以上 | アプリ → 共有 |
| SharePoint サイトに利用者を**メンバー**で追加する | サイト → 設定 → サイトのアクセス許可 |
| ライブラリの権限を絞る（4-4 を後回しにした場合） | [04 権限設計](04-permissions.md) |
| 管理者を `AppAdmins` に登録する | SharePoint の `AppAdmins` リスト |
| 利用者への案内: **初回起動時に接続の許可画面が出るので「許可」を押す** | — |

利用者に追加のライセンスは要らない（標準コネクタのみ。Microsoft 365 のライセンスに含まれる範囲）。

## 10. 更新するとき

| 変えたもの | コマンド |
|---|---|
| フロー（`scripts\flow_definitions.py`） | `python scripts\deploy.py <環境URL>` |
| アプリ（`apps\yaj-cancelfee-signature\Src\`） | `python scripts\deploy-app.py <環境URL>`（Studio を閉じてから） |
| リストの列（`data\list-schema.json`） | `python scripts\provision-sharepoint-graph.py`（足りない列だけ足す） |
| データソース（アプリが使うリストやコネクタを増やした） | Studio で追加 → **公開** → `deploy-app.py` |
| メールの差出人の方式（`mail.senderMode`） | `deploy.py` → Studio で送信・再送のフローを「最新の情報に更新」→ 公開 |

## 11. うまくいかないとき

| 症状 | 対処 |
|---|---|
| サインインで「このデバイスからはアクセスできません」など | 条件付きアクセスで device code が禁止されている。ブラウザー方式を使う（`pac auth create` は `--deviceCode` なし、Graph は `--browser`） |
| Graph で「管理者の承認が必要」 | 4-3（Excel から作る）に切り替えるか、IT 部門に同意を依頼 |
| `provision-sharepoint-graph.py` でグループの作成に失敗（403） | サイトを IT 部門に作ってもらう（4-1） |
| `deploy.py` のインポートで権限エラー | System Customizer ロールが要る（`preflight.py` の Dataverse の行で分かる） |
| フローをオンにできない（接続が無い） | 5 の接続を作る。`preflight.py` の接続の行で分かる |
| DLP の違反でフローやアプリを保存できない | SharePoint / OneDrive / Outlook / Office 365 ユーザーの分類をそろえてもらう |
| `deploy-app.py` が「データソースが足りません」 | 7-2 の 3〜5（追加して**公開**）をやり直す |
| Studio で開くと読み取り専用 | 前のセッションが編集権を持っている。画面上部の **Override** |
| アプリの画面が古いまま | 実行画面の「新しいバージョンがあります」→ 再読み込み |
| 詳細画面の手書き署名が空白 | データソースに `SignatureImages` が無い（7-2 の 3） |
| `python` と打つと Microsoft Store が開く | Python が入っていない（Windows の「アプリ実行エイリアス」が反応している）。2-1 で入れる |
| `pac` / `az` が見つからない | PATH に入っていない。pac は VS Code のターミナルで試す。az は ZIP 版の `bin` を PATH に足して PowerShell を開き直す |
| `UnicodeDecodeError` / 文字化け | 設定ファイルを UTF-8 以外で保存した。メモ帳で「名前を付けて保存」→ 文字コード **UTF-8** で保存し直す |

## 12. 片付け（試行をやめる場合）

- 環境: 開発者環境なら環境ごと削除（Power Platform 管理センター）。専用環境なら
  ソリューション → `YAJCancelFeeApp` と `YAJCancelFeeSignature` を削除
- SharePoint: サイトを削除（顧客の個人情報が入っていれば、社内の手続きに従う）
- サインイン情報: `Remove-Item -Recurse $HOME\.cliauth\yanmar-prod` と `pac auth delete --name yanmar-prod`

## 補足: Mac で作業する場合

同じスクリプトがそのまま動く。表記だけ次のように読み替える。

| Windows（PowerShell） | Mac（ターミナル） |
|---|---|
| `python scripts\deploy.py <URL>` | `./scripts/deploy.sh <URL>`（中で `deploy.py` を呼ぶ） |
| `python scripts\deploy-app.py <URL>` | `./scripts/deploy-app.sh <URL>` |
| `python scripts\xxx.py` | `python3 scripts/xxx.py` |
| `$env:NAME = "値"` | `export NAME=値` |
| ツールの入れ方 | `brew install azure-cli`、`dotnet tool install -g microsoft.powerapps.cli.tool` |

