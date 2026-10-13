"""Real FFmpeg checks: Facebook audio, regeneration and intact TikTok originals."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'pinfers-library'))
from facebook_video import generate,ready

def run(*args):
    return subprocess.run(args,check=True,capture_output=True)

with tempfile.TemporaryDirectory() as directory:
    folder=Path(directory);song=folder/'music.wav'
    run('ffmpeg','-v','error','-y','-f','lavfi','-i','color=s=360x640:r=30',
        '-t','2','-c:v','libx264','-threads','2',str(folder/'clip.mp4'))
    run('ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=0.5',str(song))
    original=hashlib.sha256((folder/'clip.mp4').read_bytes()).hexdigest()
    with patch.dict(os.environ,{'FACEBOOK_MUSIC_FILE':str(song)}):
        assert not ready(folder)
        generate(folder);assert ready(folder)
        video=folder/'clip-facebook.mp4'
        result=json.loads(run('ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)).stdout)
        assert {s['codec_type'] for s in result['streams']}=={'video','audio'}
        assert abs(float(result['format']['duration'])-2)<0.1
        pcm=run('ffmpeg','-v','error','-i',str(video),'-map','0:a:0','-f','s16le','-').stdout
        assert any(pcm), 'Soundtrack must contain audible samples'
        before=video.stat().st_mtime_ns
        generate(folder);assert video.stat().st_mtime_ns==before
        run('ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=0.5',str(song))
        assert not ready(folder)
        generate(folder);assert ready(folder)
        assert video.stat().st_mtime_ns!=before
        assert hashlib.sha256((folder/'clip.mp4').read_bytes()).hexdigest()==original
    with patch.dict(os.environ,{'FACEBOOK_MUSIC_FILE':str(folder/'missing.mp3')}):
        assert not ready(folder)
        try: generate(folder)
        except FileNotFoundError: pass
        else: raise AssertionError('Missing music must not silently produce a mute clip')
print('Facebook real audio, loop/duration, cache invalidation and original preservation: OK')
