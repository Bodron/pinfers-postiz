"""A separate Facebook safe-area copy; never overwrite the TikTok original."""
import subprocess
import os
import json
from pathlib import Path

def music_path():
    value=os.environ.get('FACEBOOK_MUSIC_FILE','').strip()
    return Path(value).expanduser().resolve() if value else None

def version(path):
    stat=Path(path).stat()
    return f'{stat.st_size}:{stat.st_mtime_ns}'

def signature(folder):
    music=music_path()
    return {'source':version(Path(folder)/'clip.mp4'),
            'music':str(music) if music else '',
            'music_version':version(music) if music else '', 'encoder':3}

def ready(folder):
    folder = Path(folder)
    source, target = folder/'clip.mp4', folder/'clip-facebook.mp4'
    if not source.exists() or not target.exists(): return False
    stamp=folder/'facebook-render.json'
    try:
        if stamp.exists(): return json.loads(stamp.read_text())==signature(folder)
        return False  # Legacy copies used oversized, asymmetric padding.
    except (OSError,ValueError): return False

def generate(folder):
    folder = Path(folder)
    if ready(folder): return
    temporary = folder/f'clip-facebook.{os.getpid()}.tmp.mp4'
    try:
        inputs=signature(folder)
        music=music_path()
        command=[
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', str(folder/'clip.mp4'),
        ]
        if music:
            duration=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                '-of','default=noprint_wrappers=1:nokey=1',str(folder/'clip.mp4')],
                check=True,capture_output=True,text=True,timeout=20).stdout)
            command+=['-stream_loop','-1','-i',str(music),'-map','0:v:0','-map','1:a:0',
                '-af',f'volume=0.65,afade=t=in:d=0.2,afade=t=out:st={max(0,duration-0.6)}:d=0.6',
                '-t',str(duration)]
        command += [
            '-vf', 'scale=1062:1888:flags=lanczos,pad=1080:1920:9:16:color=0xEAF0F6,setsar=1',
            '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(temporary),
        ]
        subprocess.run(command, check=True, timeout=180, capture_output=True)
        temporary.replace(folder/'clip-facebook.mp4')
        stamp=folder/f'facebook-render.{os.getpid()}.tmp.json'
        stamp.write_text(json.dumps(inputs))
        stamp.replace(folder/'facebook-render.json')
    finally:
        temporary.unlink(missing_ok=True)
