# 貼り付け用ファイル一覧

`docs/08-manual-setup.md` の手順で、この順に取り込む。

| 順 | 画面 | コントロール | 貼り付けるファイル | 手で入れる画面プロパティ |
|---:|---|---:|---|---|
| 1 | `ListScreen` | 20 | `ListScreen.controls.yaml` | `Fill` |
| 2 | `EditScreen` | 41 | `EditScreen.controls.yaml` | `Fill` / `OnVisible` |
| 3 | `ConsentScreen` | 28 | `ConsentScreen.controls.yaml` | `Fill` / `OnVisible` |
| 4 | `CompleteScreen` | 12 | `CompleteScreen.controls.yaml` | `Fill` |
| 5 | `ErrorScreen` | 12 | `ErrorScreen.controls.yaml` | `Fill` / `OnVisible` |
| 6 | `DetailScreen` | 75 | `DetailScreen.controls.yaml` | `Fill` / `OnVisible` |

アプリ自身（ツリー ビュー最上部の **アプリ**）には次を手で入れる。

| プロパティ | 値 |
|---|---|
| `StartScreen` | `ListScreen` |
| `OnStart` | `App-OnStart.txt` の内容をそのまま貼る |
