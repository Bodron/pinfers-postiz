const fs = require('fs');
const path = require('path');
const root = __dirname;
const env = require('./scripts/env.cjs')(path.join(root, 'config/postiz.env'));
const shared = { instances: 1, autorestart: true, restart_delay: 5000, max_restarts: 20, env };
module.exports = { apps: [
  { ...shared, name: 'pinfers-postiz-frontend', cwd: path.join(root, 'postiz/apps/frontend'), script: 'pnpm', args: 'exec dotenv -e ../../.env -- next start -H 127.0.0.1 -p 14200', interpreter: 'none' },
  { ...shared, name: 'pinfers-postiz-backend', cwd: path.join(root, 'postiz'), script: 'pnpm', args: 'start:prod:backend', interpreter: 'none' },
  { ...shared, name: 'pinfers-postiz-orchestrator', cwd: path.join(root, 'postiz'), script: 'pnpm', args: 'start:prod:orchestrator', interpreter: 'none' },
  { ...shared, name: 'pinfers-library', cwd: path.join(root, 'pinfers-library'), script: 'server.py', interpreter: path.join(root, '.venv/bin/python'), env: { ...env, PYTHONUNBUFFERED: '1' } }
] };
