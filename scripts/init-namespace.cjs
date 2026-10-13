const path = require('path');
const { createRequire } = require('module');
const root = path.resolve(__dirname, '..');
const postizRequire = createRequire(path.join(root, 'postiz/package.json'));
const { Connection } = postizRequire('@temporalio/client');
const env = require('./env.cjs')(path.join(root, 'config/postiz.env'));
(async () => {
  const connection = await Connection.connect({ address: env.TEMPORAL_ADDRESS || '127.0.0.1:7233' });
  const namespace = env.TEMPORAL_NAMESPACE || 'default';
  try {
    await connection.workflowService.describeNamespace({ namespace });
    console.log('Namespace already exists.');
  } catch (error) {
    if (error.code !== 5) throw error;
    await connection.workflowService.registerNamespace({ namespace,
      workflowExecutionRetentionPeriod: { seconds: 604800 } });
    console.log('Namespace registered.');
  } finally { await connection.close(); }
})().catch(error => { console.error(error.message); process.exit(1); });
