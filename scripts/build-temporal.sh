#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$task_root/.runtime" "$task_root/bin"
if [[ ! -d "$task_root/.runtime/temporal" ]]; then
  git clone --depth 1 --branch v1.28.1 https://github.com/temporalio/temporal.git "$task_root/.runtime/temporal"
fi
cd "$task_root/.runtime/temporal"
test "$(git describe --tags --exact-match)" = v1.28.1
export GOTOOLCHAIN=auto
go build -o "$task_root/bin/temporal-server" ./cmd/server
go build -o "$task_root/bin/temporal-sql-tool" ./cmd/tools/sql
echo 'Temporal built from official v1.28.1 source. Go 1.24.5 toolchain is required/downloaded by Go.'
