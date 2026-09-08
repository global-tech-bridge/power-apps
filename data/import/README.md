# インポート用ファイル

SharePoint へ**画面から**取り込むためのファイル。
`python3 scripts/build-import-files.py` で `data/OrgMaster.csv` から生成している。

手順は [docs/08-manual-setup.md](../../docs/08-manual-setup.md) の Part 2。

| ファイル | 入れ先リスト | 件数 | 取り込み方 |
|---|---|---:|---|
| `OrgMaster.xlsx` | `OrgMaster` | 105 | ＋新規 → リスト → **Excel から**。列の種類を手で確認する（`IsActive` を「はい/いいえ」、`SortOrder` を「数値」に） |
| `OrgMaster_grid.tsv` | `OrgMaster` | 105 | 既存リストの **グリッド ビューでの編集** へ貼り付け。`IsActive` 列は入っていない（列の既定値を「はい」にしておく） |
| `AppAdmins_grid.tsv` | `AppAdmins` | 1（記入例） | メールアドレスを実際のものに書き換えてから貼り付け |

## ここに無いもの

| 入れ先 | 理由と方法 |
|---|---|
| `ConsentMaster` | 本文が3,000字を超えるため、Excel からリストを作成すると1行テキスト（255字）の列ができて**本文が切り捨てられる**。同意文面は証跡そのものなので、その経路は用意していない。列を先に作ってから、[`../consent/ConsentText_v0.9-draft.txt`](../consent/ConsentText_v0.9-draft.txt) の3行目以降をフォームに貼り付ける |
| `SignatureCases` `SendLog` `AuditLog` `DocumentNumberCounter` | 初期データなし。アプリとフローが書き込む |
| `DocTemplates` | [`../../templates/整備キャンセル料同意書.docx`](../../templates/) をアップロードする |

## 列の順番（グリッド ビューへの貼り付け用）

貼り付け先ビューの列の並びを、TSV のヘッダーと同じ順にしておく必要がある。

```
OrgMaster_grid.tsv   Title / BranchName / BlockCode / BlockName / SiteCode / SiteName / SortOrder
AppAdmins_grid.tsv   Title / UserEmail / UserName / Note
```
