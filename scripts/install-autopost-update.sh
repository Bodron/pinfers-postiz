#!/usr/bin/env bash
set -euo pipefail
umask 077
task_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
task_archive=${1:?Usage: bash scripts/install-autopost-update.sh /tmp/pinfers-autopost-update.tar.gz}
test -f "$task_archive"
test -f "$task_root/config/postiz.env"
task_backup="$task_root/state/backups/autopost-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$task_backup"
cp "$task_root/config/postiz.env" "$task_backup/postiz.env"
tar -tzf "$task_archive" | while IFS= read -r task_file; do
  case "$task_file" in /*|*..*) echo 'Invalid archive path' >&2; exit 1;; esac
  if [[ -f "$task_root/$task_file" ]]; then printf '%s\n' "$task_file"; fi
done > "$task_backup/source-files.txt"
tar -czf "$task_backup/source.tar.gz" -C "$task_root" -T "$task_backup/source-files.txt"
task_data=$(node -e 'const path=require("path");const root=process.argv[1];const env=require(path.join(root,"scripts/env.cjs"))(path.join(root,"config/postiz.env"));process.stdout.write(env.LIBRARY_DATA_DIR||path.join(root,"state"));' "$task_root")
"$task_root/.venv/bin/python" - "$task_data" "$task_backup" <<'PY'
import sqlite3,sys
from pathlib import Path
source=(Path(sys.argv[1])/'library.sqlite3').resolve()
if source.exists():
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old:
        with sqlite3.connect(Path(sys.argv[2])/'library.sqlite3') as target: old.backup(target)
PY
tar -xzf "$task_archive" -C "$task_root"
if ! grep -q '^TIKTOK_UPLOAD_ONLY=' "$task_root/config/postiz.env"; then
  printf '\nTIKTOK_UPLOAD_ONLY="true"\n' >> "$task_root/config/postiz.env"
fi
if ! grep -q '^POSTIZ_AUTOMATION_API_KEY=' "$task_root/config/postiz.env"; then
  printf 'POSTIZ_AUTOMATION_API_KEY=""\n' >> "$task_root/config/postiz.env"
fi
echo "Update extracted. Private configuration and library backup: $task_backup"
echo 'Complete config/postiz.env, then run bash scripts/build.sh and pm2 restart ecosystem.config.cjs --update-env'
