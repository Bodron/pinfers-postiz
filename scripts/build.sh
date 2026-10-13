#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$task_root"
node -e 'const [major,minor]=process.versions.node.split(".").map(Number); if(major!==22||minor<12) throw Error("Use Node.js 22.12+ from the 22.x series")'
test -f config/postiz.env || { echo 'Create config/postiz.env first; see README.md'; exit 1; }
chmod 600 config/postiz.env
mkdir -p state uploads logs
if [[ -e postiz/.env && ! -L postiz/.env ]]; then
  echo 'postiz/.env already exists. Preserve it and configure the link manually.'; exit 1
fi
ln -sfn ../config/postiz.env postiz/.env
python3 -m venv .venv
.venv/bin/python -m pip install -r pinfers-library/requirements.txt
command -v ffmpeg >/dev/null
cd postiz
pnpm install --frozen-lockfile
pnpm exec dotenv -e .env -- pnpm run prisma-generate
# Compile one workspace at a time with room for Nest's TypeScript compiler.
# Apply after dotenv so runtime NODE_OPTIONS cannot lower the build limit.
task_build_node_options="${NODE_OPTIONS:-} --max-old-space-size=${BUILD_HEAP_MB:-4096}"
pnpm exec dotenv -e .env -- env NODE_OPTIONS="$task_build_node_options" pnpm run build
echo 'Build complete. Database schema setup is a separate step in README.md.'
