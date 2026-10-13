"""Local Pinfers library. Public catalog GETs only; Postiz auth is delegated.
No social publishing endpoint. Repeated plans are local until explicitly transferred.
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
    CREATE TABLE IF NOT EXISTS events(org TEXT,post_id TEXT PRIMARY KEY,key TEXT,account TEXT,account_name TEXT,platform TEXT,state TEXT,publish_date TEXT,release_url TEXT);
    CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,org TEXT,key TEXT,account TEXT,account_name TEXT,platform TEXT,scheduled TEXT,caption TEXT,state TEXT DEFAULT 'planned',post_id TEXT);
    CREATE TABLE IF NOT EXISTS settings(org TEXT PRIMARY KEY,policy TEXT DEFAULT 'rotation');
    ''')

def get_json(url,headers=None):
    req=urllib.request.Request(url,headers=headers or {})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

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
    (folder/'frames.txt').write_text("file 'scene1.png'\nduration 4.1\nfile 'scene2.png'\nduration 4.2\nfile 'scene3.png'\nduration 4.9\nfile 'scene3.png'\n")
    # Full-resolution clip with smooth diagonal transitions, generated independently per location.
    from motion import render_motion
    render_motion(folder)

def worker():
    while not STOP.is_set():
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            # First one variant per distinct offer, then complete remaining locations.
            row=db.execute("SELECT v.* FROM variants v WHERE active=1 AND state='waiting' ORDER BY EXISTS(SELECT 1 FROM variants r WHERE r.offer_id=v.offer_id AND r.state='ready'),updated,key LIMIT 1").fetchone()
            if row:db.execute("UPDATE variants SET state='rendering',error=NULL WHERE key=?",(row['key'],))
        if not row:STOP.wait(2);continue
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
        try:return self.postiz('user/self')['orgId']
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
            for r in rows:r['data']=json.loads(r['data']);r['caption']=caption(r['data']);r['media']=media.get(r['key'])
            return self.result({'variants':rows,'events':events,'plans':plans,'policy':'rotation','timezone':'Europe/Bucharest'})
        if path=='/pinfers/api/accounts':
            try:
                accounts=self.postiz('integrations/list').get('integrations',[])
                return self.result({'accounts':[a for a in accounts if a.get('identifier') in ['tiktok','tiktok-business','facebook'] and not a.get('disabled')]})
            except Exception:return self.result({'error':'Nu am putut citi conturile Postiz.'},502)
        if path.startswith('/pinfers/clips/'):
            target=(MEDIA/path.removeprefix('/pinfers/clips/')).resolve()
            if not target.is_relative_to(MEDIA.resolve()) or target.name not in ['clip.mp4','poster.jpg']:return self.result({'error':'Not found'},404)
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
            if path=='/pinfers/api/refresh-media':
                return self.result({'updated':False})
            if path=='/pinfers/api/media':
                key=body['key'];media_id=body['mediaId']
                # Check that this real media record is visible to this organization.
                media=self.postiz('media/'+media_id+'/status')
                if not media:raise ValueError('Fișierul nu există în organizația Postiz.')
                # Media response schema varies; use the upload record only with a local path.
                path_value=body['path']
                if not isinstance(path_value,str) or not re.match(r'^(https?://localhost:4007)?/?uploads/',path_value):raise ValueError('Fișierul trebuie să fie încărcat în Postiz local.')
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
                                db.execute('INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?,?,?,?)',(org,p['id'],m['key'],a.get('id',''),a.get('name',''),a.get('providerIdentifier',''),p['state'],p.get('publishDate',''),p.get('releaseURL','')));total+=1
                    if not result.get('hasMore',result.get('hm',False)):break
                return self.result({'ok':True,'matched':total})
            if path=='/pinfers/api/retry':
                with connection() as db:db.execute("UPDATE variants SET state='waiting',error=NULL WHERE active=1 AND state='error'")
                return self.result({'ok':True})
            return self.result({'error':'Not found'},404)
        except ValueError as e:return self.result({'error':str(e)},400)
        except Exception:return self.result({'error':'Operațiunea nu a reușit. Datele existente sunt păstrate.'},500)

if __name__=='__main__':
    if '--sync' in os.sys.argv:
        print('Catalog pairs:',sync_catalog());raise SystemExit()
    import multiprocessing
    with connection() as db:db.execute("UPDATE variants SET state='waiting' WHERE state='rendering'")
    for n in range(max(1,min(3,int(os.environ.get('RENDER_WORKERS','1'))))):multiprocessing.Process(target=worker,daemon=True).start()
    print(f'Pinfers library ready on {BIND}:{PORT}',flush=True)
    ThreadingHTTPServer((BIND,PORT),Handler).serve_forever()
