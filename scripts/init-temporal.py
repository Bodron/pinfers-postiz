"""Initialize ONLY fresh dedicated Temporal databases; never reset existing data."""
import getpass, os, subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
env = dict(os.environ, SQL_USER='temporal', SQL_PASSWORD=getpass.getpass('PostgreSQL temporal password: '))
tool = str(root / 'bin/temporal-sql-tool')
for database, schema in [('temporal', 'temporal'), ('temporal_visibility', 'visibility')]:
    prefix = [tool, '--ep', '127.0.0.1', '-p', '5432', '--plugin', 'postgres12', '--db', database]
    subprocess.run(prefix + ['setup-schema', '-v', '0.0'], env=env, check=True)
    subprocess.run(prefix + ['update-schema', '-d', str(root / '.runtime/temporal/schema/postgresql/v12' / schema / 'versioned')], env=env, check=True)
print('Temporal schemas initialized. Do not run this on an existing cluster.')
