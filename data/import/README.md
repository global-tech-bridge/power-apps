# インポート用ファイル

SharePoint へ**画面から**取り込むためのファイル。手順は
[docs/08-manual-setup.md](../../docs/08-manual-setup.md) の Part 1-2 と Part 2。

2種類ある。

| 用途 | 場所 | 何が作られるか |
|---|---|---|
| **列（スキーマ）の一括作成** | [`schema/`](schema/) | リストと列。`OrgMaster.xlsx` と合わせて70列のうち68列がウィザードで作られる |
| **初期データの投入** | このフォルダ | 既存リストへのデータ |

生成コマンド。

```bash
python3 scripts/build-import-files.py         # データ用（このフォルダ）
python3 scripts/build-schema-import-files.py  # スキーマ用（schema/）
```

## 列（スキーマ）の作成 — `schema/`

SharePoint の **＋新規 → リスト → Excel から** はヘッダーから列を作る。
これを使うと列を1つずつ手で作る必要がなくなる。

詳細とリストごとのチェックリストは [`schema/README.md`](schema/README.md)。

| ファイル | 作られる列 | サンプル行 |
|---|---:|---:|
| `schema/SignatureCases.xlsx` | 33 | 6 |
| `schema/ConsentMaster.xlsx` | 9 | 1 |
| `schema/AppAdmins.xlsx` | 4 | 1 |
| `schema/SendLog.xlsx` | 8 | 2 |
| `schema/AuditLog.xlsx` | 7 | 4 |

サンプル行は、ウィザードに**列の種類**と**選択肢の値**を拾わせるためのダミー。
1列目のテキスト列に `★取込後に削除★` と入っているので、取り込み後に削除する。

`OrgMaster` は下の `OrgMaster.xlsx`（実データ入り）が列と105件を同時に作るので
`schema/` には無い。`DocumentNumberCounter` は作る列が1つだけなので手で作る。

## 初期データの投入

| ファイル | 入れ先リスト | 件数 | 取り込み方 |
|---|---|---:|---|
| `OrgMaster.xlsx` | `OrgMaster` | 105 | ＋新規 → リスト → **Excel から**。**列と実データが同時に入る**。列の種類を手で確認する（`IsActive` を「はい/いいえ」、`SortOrder` を「数値」に） |
| `OrgMaster_grid.tsv` | `OrgMaster` | 105 | 既存リストの **グリッド ビューでの編集** へ貼り付け。`IsActive` 列は入っていない（列の既定値を「はい」にしておく） |
| `AppAdmins_grid.tsv` | `AppAdmins` | 1（記入例） | メールアドレスを実際のものに書き換えてから貼り付け |

### 列の順番（グリッド ビューへの貼り付け用）

貼り付け先ビューの列の並びを、TSV のヘッダーと同じ順にしておく必要がある。

```
OrgMaster_grid.tsv   Title / BranchName / BlockCode / BlockName / SiteCode / SiteName / SortOrder
AppAdmins_grid.tsv   Title / UserEmail / UserName / Note
```

## ここに無いもの

| 入れ先 | 理由と方法 |
|---|---|
| `ConsentMaster` の本文 | 本文が2,300字を超えるため、Excel からリストを作成すると1行テキスト（255字）の列ができて**本文が切り捨てられる**。確認文面は証跡そのものなので、その経路は用意していない。列を先に作ってから、[`../consent/ConsentText_v1.0.txt`](../consent/ConsentText_v1.0.txt) の3行目以降をフォームに貼り付ける |
| `SignatureCases` `SendLog` `AuditLog` `DocumentNumberCounter` のデータ | 初期データなし。アプリとフローが書き込む |
| `DocTemplates` | [`../../templates/整備キャンセル料確認書.docx`](../../templates/) をアップロードする |
