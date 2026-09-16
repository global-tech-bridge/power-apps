# デモ版 — 画面遷移だけを確認する（外部接続なし）

クライアントに**画面遷移と操作感を見てもらう**ためだけの版。

- **SharePoint リスト／ドキュメント ライブラリに接続しない**
- **Power Automate フローに接続しない**
- データはすべて `App.OnStart` で作るコレクション。**アプリを閉じると消える**

画面・コントロール・レイアウトは本番版と同一。
本番版は [`../yaj-cancelfee-signature/`](../yaj-cancelfee-signature/)。

## 取り込み手順（15〜20分）

接続作業が要らないので、本番版の手順から Part 1〜3 が丸ごと不要になる。

1. [make.powerapps.com](https://make.powerapps.com) → **アプリ** → **新しいアプリ** →
   **キャンバス** → **タブレット**
2. **設定 → 表示 → 向き: 縦**（768 × 1024）
3. **データの追加はしない。** ここが本番版との唯一の違い
4. `Screen1` を `ListScreen` に改名し、空の画面を5つ追加して改名する
   `EditScreen` `ConsentScreen` `CompleteScreen` `ErrorScreen` `DetailScreen`
   - **名前は一字一句このとおりに。** `Navigate()` が画面名を直接参照している
5. ツリー ビュー最上部の **アプリ** を選択し
   - `StartScreen` に `ListScreen`
   - `OnStart` に [`paste/App-OnStart.txt`](paste/App-OnStart.txt) の中身を全部貼る
6. **アプリ** を右クリック → **OnStart を実行**
7. [`paste/README.md`](paste/README.md) の順に、各画面へ
   `<画面名>.controls.yaml` を **コードの貼り付け**
8. 各画面の `Fill` / `OnVisible` を `<画面名>.properties.md` のとおりに手で入力
9. 保存して **プレビュー**

詳しい貼り付け操作は [docs/08-manual-setup.md](../../docs/08-manual-setup.md) の Part 4 と同じ。

## 入っているデータ

| | 内容 |
|---|---|
| 組織マスタ | **15拠点**（本番は105拠点）。営業部（福井／愛知／兵庫ブロック）・販売部・系統推進部 |
| 確認文面 | **元資料 v1.0 の全文**。本番と同じものを埋め込んでいる |
| 申請一覧 | **サンプル6件**。メール送信済み3件・エラー1件・作成中2件 |
| 管理者 | ログインユーザーを常に管理者として扱う（削除ボタンを見せるため） |

サンプル案件は `Now()` からの相対日付で作っているので、いつ開いても最近の日付になる。

## デモで見せられること

| 画面 | 見せられること |
|---|---|
| 一覧 | 検索・絞り込み（支社／ブロック／拠点／ステータス／日付範囲／自分の分のみ）、ステータスの色分け |
| 新規作成 | 入力チェック、**支社→ブロック→拠点の連動**、機番なしの扱い、ドラフト保存 |
| 確認・署名 | 確認文面の全文表示とスクロール、チェックなし／署名なしでは送信できないこと、**手書き署名**、送信前の最終確認ダイアログ |
| 完了 | 採番された文書番号、各工程の成功表示 |
| エラー | 失敗した工程の表示、再実行 |
| 詳細 | 参照、署名時点の文面、**手書き署名の再表示**、再送、削除（理由必須） |

### エラー画面を見せる

一覧画面の絞り込みパネルに **「【デモ】次の送信をエラーにする」** チェックボックスがある。
オンにしてから署名を送信すると、完了画面ではなくエラー画面に進む。
エラー画面の「もう一度送信する」を押すと成功して完了画面に進む。

**このチェックボックスはデモ版にしか無い。** 本番版には存在しない。

## 本番版との違い

| | デモ版 | 本番版 |
|---|---|---|
| データの保存先 | コレクション（閉じると消える） | SharePoint リスト |
| 文書番号 | その場で採番（当日の件数+1） | Power Automate が採番カウンタで直列化 |
| PDF | **生成しない。** ボタンを押すと通知が出るだけ | HTML→.doc→PDF を生成し SharePoint に保存 |
| メール送信 | **送らない。** 送信したことにするだけ | 顧客とログイン社員へPDFを添付して送信 |
| 手書き署名 | 画面に表示される（セッション内のみ） | PNG として SharePoint に保存 |
| 削除 | コレクションから消すだけ | PDF・署名画像も削除し監査ログに記録 |
| 管理者判定 | 常に管理者 | `AppAdmins` リストで判定 |
| 組織マスタ | 15拠点 | 105拠点 |

## 生成方法

**このフォルダは本番ソースからの自動生成物。直接編集しない。**

```bash
python3 scripts/build-demo-app.py
python3 scripts/gen-paste-files.py pa.schema.yaml apps/yaj-cancelfee-signature-demo
```

本番版の `Src/` を直したら、上を実行し直せばデモ版も追随する。
差し替えている箇所（保存処理・送信処理・再送・削除・PDF表示）は
`scripts/build-demo-app.py` の `DEMO_*` 定数にまとまっている。

生成後、外部参照（`SignatureCases` / `OrgMaster` / `YAJ-CancelFee-*` など）が
1つでも残っていればスクリプトが止まるようにしてある。

## 検証

```bash
python3 scripts/validate-pa-yaml.py pa.schema.yaml apps/yaj-cancelfee-signature-demo/Src/*.pa.yaml
python3 scripts/check-references.py apps/yaj-cancelfee-signature-demo/Src
python3 scripts/check-layout.py apps/yaj-cancelfee-signature-demo/Src
python3 scripts/check-formula-balance.py apps/yaj-cancelfee-signature-demo/Src
```

## 注意

デモ版で**実際の顧客情報を入力しないこと**（要件定義 15.3）。
サンプルの顧客名はすべて架空のもの。
