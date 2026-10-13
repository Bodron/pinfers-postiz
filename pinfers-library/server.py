"""Local Pinfers library. Public catalog GETs only; Postiz auth is delegated.
Continuous publishing is opt-in and delegated to Postiz with a private API key.
"""
import json, sqlite3, threading, urllib.request, urllib.error, hashlib, mimetypes
import os, time, subprocess, re, uuid
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

ROOT=Path(__file__).resolve().parent
POSTIZ_BASE=os.environ.get('POSTIZ_BASE','http://127.0.0.1:4007')
BIND=os.environ.get('LIBRARY_BIND','127.0.0.1')
PORT=int(os.environ.get('LIBRARY_PORT','4011'))
DATA_ROOT=Path(os.environ.get('LIBRARY_DATA_DIR',str(ROOT))).resolve()
DATA_ROOT.mkdir(parents=True,exist_ok=True)
PUBLIC_ORIGIN=os.environ.get('PUBLIC_ORIGIN','http://localhost:4007').rstrip('/')
DB=DATA_ROOT/'library.sqlite3'
ASSETS=ROOT/'assets'; ASSETS.mkdir(exist_ok=True)
MEDIA=DATA_ROOT/'clips'; MEDIA.mkdir(exist_ok=True)
LOCK=threading.Lock()
STOP=threading.Event()
def connection():
    db=sqlite3.connect(DB,timeout=30);db.row_factory=sqlite3.Row
    return db
with connection() as db:
    db.executescript('''PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS variants(key TEXT PRIMARY KEY,offer_id TEXT,location_id TEXT,data TEXT,active INTEGER DEFAULT 1,state TEXT DEFAULT 'waiting',error TEXT,updated TEXT);
    CREATE TABLE IF NOT EXISTS media(org TEXT,key TEXT,media_id TEXT,path TEXT,PRIMARY KEY(org,key));
    CREATE TABLE IF NOT EXISTS media_versions(org TEXT,key TEXT,media_id TEXT,path TEXT,PRIMARY KEY(org,media_id));
    CREATE TABLE IF NOT EXISTS events(org TEXT,post_id TEXT PRIMARY KEY,key TEXT,account TEXT,account_name TEXT,platform TEXT,state TEXT,publish_date TEXT,release_url TEXT,caption TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,org TEXT,key TEXT,account TEXT,account_name TEXT,platform TEXT,scheduled TEXT,caption TEXT,state TEXT DEFAULT 'planned',post_id TEXT);
    CREATE TABLE IF NOT EXISTS settings(org TEXT PRIMARY KEY,policy TEXT DEFAULT 'rotation');
    CREATE TABLE IF NOT EXISTS platform_media(org TEXT,key TEXT,platform TEXT,media_id TEXT,path TEXT,PRIMARY KEY(org,key,platform));
    CREATE TABLE IF NOT EXISTS automation(org TEXT PRIMARY KEY,enabled INTEGER DEFAULT 0,accounts TEXT,times TEXT,last_run TEXT,last_error TEXT);
    ''')
    event_columns={r['name'] for r in db.execute('PRAGMA table_info(events)')}
    if 'caption' not in event_columns:
        db.execute("ALTER TABLE events ADD COLUMN caption TEXT NOT NULL DEFAULT ''")
    if 'source_data' not in {r['name'] for r in db.execute('PRAGMA table_info(plans)')}:
        db.execute('ALTER TABLE plans ADD COLUMN source_data TEXT')
    if 'media_version' not in {r['name'] for r in db.execute('PRAGMA table_info(plans)')}:
        db.execute("ALTER TABLE plans ADD COLUMN media_version TEXT DEFAULT ''")
    if 'source_version' not in {r['name'] for r in db.execute('PRAGMA table_info(platform_media)')}:
        db.execute("ALTER TABLE platform_media ADD COLUMN source_version TEXT DEFAULT ''")

def get_json(url,headers=None):
    req=urllib.request.Request(url,headers=headers or {})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def queue_outdated_motion():
    from video_timing import current
    with connection() as db:
        keys=[r['key'] for r in db.execute("SELECT key FROM variants WHERE active=1 AND state='ready'") if not current(MEDIA/r['key'])]
        for key in keys:
            db.execute("UPDATE variants SET state='waiting',error=NULL WHERE key=? AND state='ready'",(key,))
            db.execute('DELETE FROM media WHERE key=?',(key,))
    return len(keys)

def sync_catalog():
    with LOCK:
        items=[]
        for page in range(1,21):
            result=get_json(f'https://api.pinfers.com/companies/locations/active-content?view=items&limit=100&page={page}')
            items.extend(i for i in result.get('items',[]) if i.get('type')=='offer')
            if not result.get('hasMore'):break
        else:raise ValueError('Catalog pagination limit reached')
        now=datetime.now(timezone.utc).isoformat()
        with connection() as db:
            db.execute('UPDATE variants SET active=0')
            for item in items:
                o,l=item['offer'],item['location'];key=o['_id']+'_'+l['_id']
                old=db.execute('SELECT data FROM variants WHERE key=?',(key,)).fetchone()
                data=json.dumps(item,ensure_ascii=False,sort_keys=True)
                changed=old and old['data']!=data
                db.execute('INSERT INTO variants(key,offer_id,location_id,data,updated) VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data,active=1,updated=excluded.updated', (key,o['_id'],l['_id'],data,now))
                if changed:
                    db.execute("UPDATE variants SET state='waiting',error=NULL WHERE key=?",(key,))
                    db.execute('DELETE FROM media WHERE key=?',(key,))
                    db.execute('DELETE FROM platform_media WHERE key=?',(key,))
        queue_outdated_motion()
        return len(items)

def download(url,target):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password:raise ValueError('Public HTTPS images required')
    if target.exists():return
    with urllib.request.urlopen(url,timeout=25) as r:raw=r.read(20*1024*1024+1)
    if len(raw)>20*1024*1024:raise ValueError('Image too large')
    temporary=target.with_name(target.name+'.'+str(os.getpid())+'.tmp')
    temporary.write_bytes(raw);temporary.replace(target)

def caption(item):
    o,l=item['offer'],item['location']
    end=datetime.fromisoformat(o['endDate'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Bucharest'))
    price=f"{o['price']:g}".replace('.',',')
    desc=(o.get('description') or '').strip()
    return f"{o['title']} la {l['name']} ✨\n\nPreț în Pinfers: {price} {o.get('currency','RON')}.\nValabilă până la {end:%d.%m.%Y, ora %H:%M}.\n\n{desc}\n\nVerifică disponibilitatea și condițiile în aplicația Pinfers.\n#Pinfers #Iasi #OferteLocale"[:2100]

def generate(row):
    from PIL import Image
    import template as template
    import scenes as scenes
    item=json.loads(row['data']);key=row['key'];o,l=item['offer'],item['location']
    folder=MEDIA/key;folder.mkdir(exist_ok=True)
    local_assets=folder/'assets';local_assets.mkdir(exist_ok=True)
    template.ROOT=folder;scenes.ROOT=folder
    (local_assets/'pinfers-logo.png').write_bytes((ASSETS/'pinfers-logo.png').read_bytes())
    for kind,url in [('offer',o.get('imageUrl')),('logo',l.get('imageUrl'))]:
        if not url:raise ValueError('Lipsește imaginea ofertei sau logo-ul locației')
        download(url,ASSETS/(hashlib.sha256(url.encode()).hexdigest()+'.img'))
        target=local_assets/f'0-{kind}.img';target.write_bytes((ASSETS/(hashlib.sha256(url.encode()).hexdigest()+'.img')).read_bytes())
    folder=MEDIA/key;folder.mkdir(exist_ok=True)
    template.render(item,0,1920).save(folder/'scene1.png')
    desc=(o.get('description') or o['title']).strip()
    if len(desc)>230:
        sentences=re.split(r'(?<=[.!?])\s+',desc)
        desc=sentences[0] if len(sentences[0])<=230 else o['title']+'. Condițiile complete sunt în aplicație.'
    scenes.COPY=[desc]
    scenes.explanation(0,item).save(folder/'scene2.png')
    scenes.ROOT=ROOT
    scenes.download().save(folder/'scene3.png')
    template.render(item,0,1350).resize((432,540)).save(folder/'poster.jpg',quality=88)
    (folder/'frames.txt').write_text("file 'scene1.png'\nduration 2.2\nfile 'scene2.png'\nduration 2.2\nfile 'scene3.png'\nduration 4.0\nfile 'scene3.png'\n")
    # Full-resolution clip with smooth diagonal transitions, generated independently per location.
    from motion import render_motion
    render_motion(folder)
    from facebook_video import generate as facebook_copy
    facebook_copy(folder)

def worker():
    while not STOP.is_set():
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            # First one variant per distinct offer, then complete remaining locations.
            row=db.execute("SELECT v.* FROM variants v WHERE active=1 AND state='waiting' ORDER BY EXISTS(SELECT 1 FROM variants r WHERE r.offer_id=v.offer_id AND r.state='ready'),updated,key LIMIT 1").fetchone()
            if row:db.execute("UPDATE variants SET state='rendering',error=NULL WHERE key=?",(row['key'],))
        if not row:
            from facebook_video import ready as facebook_ready, generate as facebook_copy
            with connection() as db:
                backfill=next((r for r in db.execute("SELECT key FROM variants WHERE state='ready' AND active=1") if (MEDIA/r['key']/'clip.mp4').exists() and not facebook_ready(MEDIA/r['key'])),None)
            if backfill:
                try: facebook_copy(MEDIA/backfill['key'])
                except Exception: STOP.wait(30)
            else: STOP.wait(2)
            continue
        try:
            generate(row)
            with connection() as db:db.execute("UPDATE variants SET state='ready',error=NULL WHERE key=? AND data=?",(row['key'],row['data']))
        except Exception as e:
            message='Generarea clipului a eșuat. Verifică imaginile și descrierea.'
            if isinstance(e,ValueError):message=str(e)
            with connection() as db:db.execute("UPDATE variants SET state='error',error=? WHERE key=?",(message,row['key']))
            print('Render error:',row['key'],type(e).__name__,flush=True)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def headers_out(self,status,mime='application/json',length=None):
        self.send_response(status);self.send_header('Content-Type',mime)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if length is not None:self.send_header('Content-Length',str(length))
    def result(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False).encode();self.headers_out(status,length=len(raw));self.end_headers();self.wfile.write(raw)
    def postiz(self,path):
        return get_json(POSTIZ_BASE+'/api/'+path,{'Cookie':self.headers.get('Cookie',''),'Accept':'application/json'})
    def auth(self):
        try:
            user=self.postiz('user/self');self.user_role=user.get('role')
            return user['orgId']
        except Exception:return None
    def do_GET(self):
        path=unquote(urlparse(self.path).path)
        if path=='/health':return self.result({'ok':True})
        if path=='/pinfers/nav.js':
            raw=b"document.addEventListener('click',function(e){var a=e.target.closest('a');if(a&&new URL(a.href).pathname==='/media'){e.preventDefault();e.stopImmediatePropagation();location.assign(a.href)}},true);"
            self.headers_out(200,'application/javascript',len(raw));self.end_headers();self.wfile.write(raw);return
        org=self.auth()
        if not org:
            if path in ['/','/media','/pinfers/']:
                self.send_response(302);self.send_header('Location','/auth/login');self.end_headers();return
            return self.result({'error':'Autentifică-te în Postiz.'},401)
        if path in ['/','/media','/pinfers/']:
            raw=(ROOT/'index.html').read_bytes();self.headers_out(200,'text/html; charset=utf-8',len(raw));self.end_headers();return self.wfile.write(raw)
        if path=='/pinfers/api/library':
            with connection() as db:
                rows=[dict(r) for r in db.execute('SELECT * FROM variants WHERE active=1 ORDER BY offer_id,location_id')]
                events=[dict(r) for r in db.execute('SELECT * FROM events WHERE org=? ORDER BY publish_date DESC',(org,))]
                plans=[dict(r) for r in db.execute('SELECT * FROM plans WHERE org=? ORDER BY scheduled',(org,))]
                media={r['key']:dict(r) for r in db.execute('SELECT * FROM media WHERE org=?',(org,))}
                automation=db.execute('SELECT * FROM automation WHERE org=?',(org,)).fetchone()
            from facebook_video import ready as facebook_ready
            for r in rows:
                r['data']=json.loads(r['data']);r['caption']=caption(r['data']);r['media']=media.get(r['key'])
                r['facebookReady']=facebook_ready(MEDIA/r['key'])
            auto=dict(automation) if automation else {'enabled':False,'accounts':'[]','times':'["10:00","15:00","20:00"]'}
            auto['accounts']=json.loads(auto['accounts']);auto['times']=json.loads(auto['times'])
            auto['keyConfigured']=bool(os.environ.get('POSTIZ_AUTOMATION_API_KEY'))
            auto['canManage']=getattr(self,'user_role',None) in ('SUPERADMIN','ADMIN')
            auto['tiktokDirect']=os.environ.get('TIKTOK_UPLOAD_ONLY','false')!='true'
            return self.result({'variants':rows,'events':events,'plans':plans,'automation':auto,'policy':'rotation','timezone':'Europe/Bucharest'})
        if path=='/pinfers/api/accounts':
            try:
                accounts=self.postiz('integrations/list').get('integrations',[])
                return self.result({'accounts':[a for a in accounts if a.get('identifier') in ['tiktok','tiktok-business','facebook'] and not a.get('disabled')]})
            except Exception:return self.result({'error':'Nu am putut citi conturile Postiz.'},502)
        if path.startswith('/pinfers/clips/'):
            target=(MEDIA/path.removeprefix('/pinfers/clips/')).resolve()
            if not target.is_relative_to(MEDIA.resolve()) or target.name not in ['clip.mp4','clip-facebook.mp4','poster.jpg']:return self.result({'error':'Not found'},404)
            if not target.exists():return self.result({'error':'Clipul încă se generează.'},404)
            size=target.stat().st_size;start=0;end=size-1;status=200
            match=re.match(r'bytes=(\d+)-(\d*)',self.headers.get('Range',''))
            if match:
                start=int(match[1]);end=min(end,int(match[2]) if match[2] else end);status=206
                if start>end:return self.result({'error':'Invalid range'},416)
            self.headers_out(status,mimetypes.guess_type(target)[0] or 'application/octet-stream',end-start+1)
            self.send_header('Accept-Ranges','bytes')
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            try:
                with target.open('rb') as f:
                    f.seek(start);remaining=end-start+1
                    while remaining:
                        chunk=f.read(min(65536,remaining));self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        return self.result({'error':'Not found'},404)
    def do_POST(self):
        if self.headers.get('Origin')!=PUBLIC_ORIGIN:return self.result({'error':'Origine invalidă.'},403)
        org=self.auth()
        if not org:return self.result({'error':'Autentifică-te în Postiz.'},401)
        if int(self.headers.get('Content-Length',0))>100000:return self.result({'error':'Too large'},413)
        try:
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
            path=urlparse(self.path).path
            if path=='/pinfers/api/sync':return self.result({'count':sync_catalog()})
            if path=='/pinfers/api/automation':
                if getattr(self,'user_role',None) not in ('SUPERADMIN','ADMIN'):
                    return self.result({'error':'Doar administratorul poate modifica publicarea automată.'},403)
                from autopost import PostizAPI
                api=PostizAPI()
                if body.get('enabled') is not True:
                    with connection() as db: db.execute('UPDATE automation SET enabled=0 WHERE org=?',(org,))
                    try:
                        from autopost import cancel_pending
                        cancel_pending(connection,org,api)
                    except Exception:
                        message='Automatizarea este oprită, dar anularea unor programări a eșuat. Verifică calendarul Postiz.'
                        with connection() as db: db.execute('UPDATE automation SET last_error=? WHERE org=?',(message,org))
                        return self.result({'error':message},502)
                    return self.result({'ok':True})
                if not api.key: raise ValueError('Completează POSTIZ_AUTOMATION_API_KEY pe server.')
                owned={a['id']:a for a in self.postiz('integrations/list')['integrations']}
                allowed={a['id']:a for a in api.request('integrations')}
                ids=list(dict.fromkeys(body.get('accounts',[])))
                enabled=body.get('enabled') is True
                times=body.get('times',['10:00','15:00','20:00'])
                if len(times)!=3 or len(set(times))!=3 or any(not isinstance(t,str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',t) for t in times):
                    raise ValueError('Alege 3 ore diferite, în format HH:MM.')
                if enabled and not ids: raise ValueError('Selectează cel puțin un cont.')
                if any(i not in owned or i not in allowed or owned[i].get('disabled') or allowed[i]['identifier'] not in ('facebook','tiktok') for i in ids):
                    raise ValueError('Cheia API și conturile trebuie să aparțină aceleiași organizații Postiz.')
                with connection() as db:
                    other=db.execute('SELECT org FROM automation WHERE enabled=1 AND org!=?',(org,)).fetchone()
                    if other: raise ValueError('Automatizarea acestei instalări aparține deja altei organizații.')
                    db.execute('INSERT INTO automation(org,enabled,accounts,times) VALUES(?,?,?,?) ON CONFLICT(org) DO UPDATE SET enabled=excluded.enabled,accounts=excluded.accounts,times=excluded.times,last_error=NULL',
                               (org,int(enabled),json.dumps(ids),json.dumps(times)))
                return self.result({'ok':True})
            if path=='/pinfers/api/refresh-media':
                return self.result({'updated':False})
            if path=='/pinfers/api/media':
                key=body['key'];media_id=body['mediaId']
                # Check that this real media record is visible to this organization.
                media=self.postiz('media/'+media_id+'/status')
                if not media:raise ValueError('Fișierul nu există în organizația Postiz.')
                # Media response schema varies; use the upload record only with a local path.
                path_value=body['path']
                if not isinstance(path_value,str) or path_value!=media.get('path'):raise ValueError('Calea nu corespunde fișierului încărcat în Postiz.')
                with connection() as db:
                    if not db.execute('SELECT 1 FROM variants WHERE key=?',(key,)).fetchone():raise ValueError('Ofertă invalidă')
                    db.execute('INSERT OR REPLACE INTO media VALUES(?,?,?,?)',(org,key,media_id,path_value))
                    db.execute('INSERT OR REPLACE INTO media_versions VALUES(?,?,?,?)',(org,key,media_id,path_value))
                return self.result({'ok':True})
            if path=='/pinfers/api/plan':
                count=int(body.get('repeat',1));gap=int(body.get('gapHours',4))
                if not 1<=count<=12 or not 1<=gap<=168:raise ValueError('Repetări: 1–12; interval: 1–168 ore.')
                date=datetime.fromisoformat(body['date']).astimezone(timezone.utc)
                if date<=datetime.now(timezone.utc):raise ValueError('Alege o dată viitoare.')
                from datetime import timedelta
                accounts=self.postiz('integrations/list').get('integrations',[])
                selected=[a for a in accounts if a['id'] in body.get('accounts',[]) and a.get('identifier') in ['facebook','tiktok'] and not a.get('disabled')]
                if not selected:raise ValueError('Conectează și selectează cel puțin un cont.')
                with connection() as db:
                    variant=db.execute('SELECT * FROM variants WHERE key=? AND active=1',(body['key'],)).fetchone()
                    if not variant:raise ValueError('Oferta nu mai este activă.')
                    item=json.loads(variant['data']);end=datetime.fromisoformat(item['offer']['endDate'].replace('Z','+00:00'))
                    dates=[date+timedelta(hours=n*gap) for n in range(count)]
                    if any(d>end for d in dates):raise ValueError('O repetare depășește valabilitatea ofertei.')
                    for a in selected:
                        for d in dates:db.execute('INSERT INTO plans(id,org,key,account,account_name,platform,scheduled,caption) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),org,variant['key'],a['id'],a['name'],a['identifier'],d.isoformat(),body.get('caption') or caption(item)))
                return self.result({'ok':True,'count':len(selected)*count})
            if path=='/pinfers/api/history':
                total=0
                # Published-only listing has no future-date filter. Never infer success from upload.
                for page in range(100):
                    result=self.postiz(f'posts/list?state=published&limit=100&page={page}')
                    posts=result.get('posts',result.get('p',[]))
                    posts=[{ {'i':'id','c':'content','d':'publishDate','u':'releaseURL','s':'state','n':'integration'}.get(k,k):v for k,v in p.items()} for p in posts]
                    for p in posts:
                        if isinstance(p.get('integration'),dict):p['integration']={ {'i':'id','n':'name','pi':'providerIdentifier','p':'picture'}.get(k,k):v for k,v in p['integration'].items()}
                    with connection() as db:
                        for p in posts:
                            details=self.postiz('posts/'+p['id'])
                            detail_list=details if isinstance(details,list) else [details]
                            raw=json.dumps(detail_list)
                            matches=[m for m in db.execute('SELECT * FROM media_versions WHERE org=?',(org,)) if m['media_id'] in raw or m['path'] in raw]
                            for m in matches:
                                a=p.get('integration') or {}
                                if p.get('state')!='PUBLISHED':continue
                                state='INBOX' if a.get('providerIdentifier','').startswith('tiktok') and '/messages' in (p.get('releaseURL') or '') else p['state']
                                db.execute('INSERT OR REPLACE INTO events (org,post_id,key,account,account_name,platform,state,publish_date,release_url,caption) VALUES(?,?,?,?,?,?,?,?,?,?)',(org,p['id'],m['key'],a.get('id',''),a.get('name',''),a.get('providerIdentifier',''),state,p.get('publishDate',''),p.get('releaseURL',''),p.get('content','')));total+=1
                    if not result.get('hasMore',result.get('hm',False)):break
                return self.result({'ok':True,'matched':total})
            if path=='/pinfers/api/retry':
                with connection() as db:db.execute("UPDATE variants SET state='waiting',error=NULL WHERE active=1 AND state='error'")
                return self.result({'ok':True})
            if path=='/pinfers/api/manual-post':
                key=str(body.get('key','')).strip()
                platform=str(body.get('platform','')).strip().lower()
                account_name=str(body.get('accountName','')).strip()
                post_caption=str(body.get('caption','')).strip()
                published_at=str(body.get('publishedAt','')).strip()
                release_url=str(body.get('releaseUrl','')).strip()
                if platform not in ['tiktok','facebook']:raise ValueError('Alege TikTok sau Facebook.')
                if not account_name or len(account_name)>160:raise ValueError('Scrie numele contului (maximum 160 de caractere).')
                if len(post_caption)>5000:raise ValueError('Descrierea este prea lungă.')
                try:
                    published=datetime.fromisoformat(published_at)
                    if published.tzinfo is None:published=published.replace(tzinfo=ZoneInfo('Europe/Bucharest'))
                    published=published.astimezone(timezone.utc).isoformat()
                except Exception:raise ValueError('Alege data și ora publicării.')
                if release_url:
                    parsed=urlparse(release_url)
                    if parsed.scheme not in ['http','https'] or not parsed.netloc:raise ValueError('Linkul postării trebuie să înceapă cu http:// sau https://.')
                with connection() as db:
                    variant=db.execute('SELECT data FROM variants WHERE key=? AND active=1',(key,)).fetchone()
                    if not variant:raise ValueError('Oferta nu mai este activă.')
                    if not post_caption:post_caption=caption(json.loads(variant['data']))
                    account_id='manual:'+hashlib.sha256((platform+'\0'+account_name.casefold()).encode()).hexdigest()[:24]
                    db.execute('INSERT INTO events (org,post_id,key,account,account_name,platform,state,publish_date,release_url,caption) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (org,'manual:'+str(uuid.uuid4()),key,account_id,account_name,platform,'PUBLISHED',published,release_url,post_caption))
                return self.result({'ok':True})
            return self.result({'error':'Not found'},404)
        except ValueError as e:return self.result({'error':str(e)},400)
        except Exception:return self.result({'error':'Operațiunea nu a reușit. Datele existente sunt păstrate.'},500)

def automation_worker():
    from autopost import run_once
    last_sync=0
    while not STOP.is_set():
        with connection() as db: config=db.execute('SELECT org FROM automation WHERE enabled=1').fetchone()
        if config:
            try:
                if time.monotonic()-last_sync>900:
                    sync_catalog();last_sync=time.monotonic()
                run_once(connection,MEDIA,caption)
            except Exception as error:
                with connection() as db:
                    db.execute('UPDATE automation SET last_error=? WHERE org=?',
                               ('Automatizarea are o eroare. Verifică cheia API, conturile și planificările.',config['org']))
                print('Automation error:',type(error).__name__,flush=True)
        STOP.wait(60)

if __name__=='__main__':
    if '--sync' in os.sys.argv:
        print('Catalog pairs:',sync_catalog());raise SystemExit()
    import multiprocessing
    with connection() as db:
        db.execute("UPDATE variants SET state='waiting' WHERE state='rendering'")
        db.execute("UPDATE plans SET state='uncertain' WHERE state='sending'")
    print('Clips queued for timing update:',queue_outdated_motion(),flush=True)
    for n in range(max(1,min(3,int(os.environ.get('RENDER_WORKERS','1'))))):multiprocessing.Process(target=worker,daemon=True).start()
    threading.Thread(target=automation_worker,daemon=True).start()
    print(f'Pinfers library ready on {BIND}:{PORT}',flush=True)
    ThreadingHTTPServer((BIND,PORT),Handler).serve_forever()
