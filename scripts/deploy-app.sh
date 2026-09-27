#!/usr/bin/env bash
# macOS / Linux 用の入口。中身は scripts/deploy-app.py（Windows と共通。Windows では python scripts\deploy-app.py）
exec python3 -X utf8 "$(dirname "$0")/deploy-app.py" "$@"
