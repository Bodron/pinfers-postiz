from pathlib import Path
import math,subprocess
from video_timing import VERSION, DURATIONS
import json
from PIL import Image,ImageDraw
W,H,FPS=1080,1920,30
BG='#EAF0F6'
def ease(u):
    return u*u*(3-2*u)

def moved(scene,dx=0,scale=1):
    if scale!=1:
        scene=scene.resize((round(W*scale),round(H*scale)),Image.Resampling.LANCZOS)
    frame=Image.new('RGB',(W,H),BG)
    frame.paste(scene,(round((W-scene.width)/2+dx),round((H-scene.height)/2)))
    return frame

def wipe(a,b,u):
    e=ease(u)
    if u<.5:
        frame=moved(a,-90*ease(min(1,u*2)))
    else:
        v=(u-.5)*2
        rebound=math.sin(v*math.pi*2.5)*math.exp(-5*v)*65
        frame=moved(b,rebound,.985+.015*ease(v))
    d=ImageDraw.Draw(frame)
    center=W/2+(0.5-e)*6200
    tilt=.28
    width=2300
    def band(c,width,color):
        top=c-tilt*H/2; bottom=c+tilt*H/2
        d.polygon([(top-width/2,0),(top+width/2,0),(bottom+width/2,H),(bottom-width/2,H)],fill=color)
    band(center+130, width+140,'#FFFFFF')
    band(center+55,width+70,'#F4A09F')
    band(center,width,'#C20302')
    # A glossy diagonal accent travels with the red wipe.
    band(center-850,95,'#D51918')
    band(center-950,16,'#EF4D48')
    return frame

def render_motion(folder):
    scenes=[Image.open(folder/f'scene{n}.png').convert('RGB') for n in range(1,4)]
    duration=sum(DURATIONS)
    proc=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'clip.tmp.mp4')],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    cache={}
    try:
        for n in range(round(duration*FPS)):
            t=n/FPS
            if 1.8<=t<2.2: frame=wipe(scenes[0],scenes[1],(t-1.8)/.4)
            elif 4.0<=t<4.4: frame=wipe(scenes[1],scenes[2],(t-4.0)/.4)
            else:
                idx=0 if t<1.8 else 1 if t<4.0 else 2
                start=[0,2.2,4.4][idx];end=[1.8,4.0,duration][idx]
                progress=max(0,min(1,(t-start)/(end-start)))
                step=round(ease(progress)*20)
                if (idx,step) not in cache:
                    cache.clear()
                    cache[idx,step]=moved(scenes[idx],scale=1+.006*step/20).tobytes()
                proc.stdin.write(cache[idx,step]);continue
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait(timeout=90)!=0:raise RuntimeError('Motion encoding failed')
        (folder/'clip.tmp.mp4').replace(folder/'clip.mp4')
        (folder/'motion-version.json').write_text(json.dumps({'version':VERSION,'durations':DURATIONS}))
    except BaseException:
        proc.kill();raise
