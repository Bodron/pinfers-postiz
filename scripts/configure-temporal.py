"""Create ignored, mode-600 native Temporal config. No credentials in Git."""
import getpass, json, os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
password = getpass.getpass('Password for PostgreSQL role temporal (not stored in Git): ')
stores = {}
for name, database in [('main', 'temporal'), ('visibility', 'temporal_visibility')]:
    stores[name] = {'sql': {'pluginName': 'postgres12', 'databaseName': database,
        'connectAddr': '127.0.0.1:5432', 'connectProtocol': 'tcp',
        'user': 'temporal', 'password': password, 'maxConns': 10,
        'maxIdleConns': 5, 'maxConnLifetime': '1h'}}
config = {'log': {'stdout': True, 'level': 'info'},
    'persistence': {'defaultStore': 'main', 'visibilityStore': 'visibility',
                    'numHistoryShards': 4, 'datastores': stores},
    'global': {'membership': {'maxJoinDuration': '30s', 'broadcastAddress': '127.0.0.1'}},
    'services': {name: {'rpc': {'grpcPort': port, 'membershipPort': port - 300,
                               'bindOnLocalHost': True}}
                 for name, port in [('frontend', 7233), ('history', 7234), ('matching', 7235), ('worker', 7239)]},
    'clusterMetadata': {'enableGlobalNamespace': False, 'failoverVersionIncrement': 10,
        'masterClusterName': 'active', 'currentClusterName': 'active',
        'clusterInformation': {'active': {'enabled': True, 'initialFailoverVersion': 1,
                                'rpcName': 'frontend', 'rpcAddress': '127.0.0.1:7233'}}},
    'archival': {'history': {'state': 'disabled'}, 'visibility': {'state': 'disabled'}},
    'namespaceDefaults': {'archival': {'history': {'state': 'disabled'}, 'visibility': {'state': 'disabled'}}}}
folder = root / 'config/temporal'
folder.mkdir(parents=True, exist_ok=True)
target = folder / 'production.yaml'
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f: json.dump(config, f, indent=2)
os.chmod(target, 0o600)
print('Created config/temporal/production.yaml; keep this file private.')
