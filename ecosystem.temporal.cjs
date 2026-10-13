const path = require('path');
module.exports = { apps: [{ name: 'pinfers-temporal', cwd: __dirname,
  script: path.join(__dirname, 'bin/temporal-server'), interpreter: 'none',
  args: ['--config-dir', path.join(__dirname, 'config/temporal'), '--env', 'production', 'start'],
  instances: 1, autorestart: true, restart_delay: 5000, max_restarts: 20 }] };
