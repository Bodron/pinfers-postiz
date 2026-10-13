"""Install the chosen soundtrack from Pixabay into private runtime storage."""
import argparse,hashlib,json,re,subprocess,tempfile
from datetime import datetime
from pathlib import Path

URL='https://cdn.pixabay.com/audio/2025/12/25/audio_2be1458a60.mp3'
SHA256='3a6c6ffed432663139ecb772e032d7d7a23515c86b79704b929a864e2a44e6b8'

def install(root):
    root=Path(root).resolve()
    config=root/'config/postiz.env'
    if not config.is_file():raise RuntimeError('Missing config/postiz.env; run in the installed project.')
    folder=root/'state/music';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'facebook-house.mp3'
    matches=target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==SHA256
    if not matches:
        with tempfile.NamedTemporaryFile(dir=folder,suffix='.mp3',delete=False) as handle:
            temporary=Path(handle.name)
        try:
            subprocess.run(['curl','--fail','--location','--proto','=https','--proto-redir','=https',
                '--connect-timeout','15','--max-time','120','--retry','2',URL,'--output',str(temporary)],check=True)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=SHA256:
                raise RuntimeError('Downloaded file differs from the verified soundtrack; installation stopped.')
            if target.exists():
                backup=folder/('facebook-house-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.mp3.bak')
                target.replace(backup)
            temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
    old=config.read_text()
    lines=[line for line in old.splitlines() if not re.match(r'^\s*(?:export\s+)?FACEBOOK_MUSIC_FILE\s*=',line)]
    updated='\n'.join(lines)+'\nFACEBOOK_MUSIC_FILE='+json.dumps(str(target))+'\n'
    if old!=updated:
        backup=config.with_name('postiz.env.music-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        with backup.open('xb') as handle:
            backup.chmod(0o600);handle.write(config.read_bytes())
        with tempfile.NamedTemporaryFile(dir=config.parent,mode='w',delete=False) as handle:
            temporary=Path(handle.name);handle.write(updated)
        try:
            temporary.chmod(0o600);temporary.replace(config)
        finally:temporary.unlink(missing_ok=True)
    (folder/'facebook-house-source.json').write_text(json.dumps({
        'title':'House Energetic Upbeat','author':'PaulYudin / Pavel Bekirov',
        'source':'https://pixabay.com/music/edm-house-energetic-upbeat-456608/',
        'license':'https://pixabay.com/service/terms/','sha256':SHA256},indent=2))
    print('Soundtrack installed and FACEBOOK_MUSIC_FILE configured. Restart PM2 to apply.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    install(parser.parse_args().root)
