"""A separate Facebook safe-area copy; never overwrite the TikTok original."""
import subprocess
import os
from pathlib import Path

def ready(folder):
    folder = Path(folder)
    source, target = folder/'clip.mp4', folder/'clip-facebook.mp4'
    return source.exists() and target.exists() and target.stat().st_mtime >= source.stat().st_mtime

def generate(folder):
    folder = Path(folder)
    if ready(folder): return
    temporary = folder/f'clip-facebook.{os.getpid()}.tmp.mp4'
    try:
        subprocess.run([
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', str(folder/'clip.mp4'),
            '-vf', 'scale=810:1440:flags=lanczos,pad=1080:1920:90:150:color=0xEAF0F6,setsar=1',
            '-c:v', 'libx264', '-threads', '2', '-preset', 'veryfast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(temporary),
        ], check=True, timeout=180, capture_output=True)
        temporary.replace(folder/'clip-facebook.mp4')
    finally:
        temporary.unlink(missing_ok=True)
