"""Three distinct active offers per selected account/day, scheduled via Postiz."""
import json, os, uuid, hashlib, urllib.request, urllib.error
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from scheduling import payload
from facebook_video import ready as facebook_ready, version as media_version

TZ = ZoneInfo('Europe/Bucharest')
UPLOAD_ONLY = os.environ.get('TIKTOK_UPLOAD_ONLY','false') == 'true'

class PostizAPI:
    def __init__(self):
        self.base = os.environ.get('BACKEND_INTERNAL_URL','http://127.0.0.1:13100').rstrip('/')+'/public/v1/'
        self.key = os.environ.get('POSTIZ_AUTOMATION_API_KEY','')
    def request(self,path,body=None,method=None):
        if not self.key: raise ValueError('Completează POSTIZ_AUTOMATION_API_KEY pe server.')
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base+path,data=data,method=method,
              headers={'Authorization':self.key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=40) as response:
            return json.loads(response.read() or b'{}')
    def upload(self,path):
        # Source files are local generated clips; no remote URL or user token
        # is persisted in the library. This uses the private Postiz API key.
        boundary = 'pinfers-'+uuid.uuid4().hex
        raw = path.read_bytes()
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: video/mp4\r\n\r\n'.encode()
                + raw + f'\r\n--{boundary}--\r\n'.encode())
        req = urllib.request.Request(self.base+'upload',data=data,headers={
              'Authorization':self.key,'Content-Type':'multipart/form-data; boundary='+boundary})
        with urllib.request.urlopen(req,timeout=120) as response: return json.load(response)

def dates(now,times):
    """Fill remaining slots today and tomorrow; never catch up with a burst."""
    for delta in range(2):
        day = now.astimezone(TZ).date()+timedelta(days=delta)
        for clock in sorted(times):
            hour,minute = map(int,clock.split(':'))
            date = datetime(day.year,day.month,day.day,hour,minute,tzinfo=TZ).astimezone(timezone.utc)
            if date > now+timedelta(minutes=5): yield date

def choose(db,org,account,date,media_root,platform):
    day = date.astimezone(TZ).date()
    start = datetime.combine(day,datetime.min.time(),TZ).astimezone(timezone.utc)
    stop = (datetime.combine(day+timedelta(days=1),datetime.min.time(),TZ)).astimezone(timezone.utc)
    used = {r['offer_id'] for r in db.execute('''SELECT v.offer_id FROM plans p JOIN variants v ON v.key=p.key
            WHERE p.org=? AND p.account=? AND p.scheduled>=? AND p.scheduled<? AND p.state IN ('scheduled','published','sending','uncertain','waiting_media','failed')
            UNION SELECT v.offer_id FROM events e JOIN variants v ON v.key=e.key
            WHERE e.org=? AND e.account=? AND e.publish_date>=? AND e.publish_date<?''',
            (org,account,start.isoformat(),stop.isoformat(),org,account,start.isoformat(),stop.isoformat()))}
    candidates=[]
    for row in db.execute("SELECT * FROM variants WHERE active=1 AND state='ready'"):
        item=json.loads(row['data'])
        begin=datetime.fromisoformat(item['offer']['startDate'].replace('Z','+00:00')) if item['offer'].get('startDate') else None
        end=datetime.fromisoformat(item['offer']['endDate'].replace('Z','+00:00'))
        if row['offer_id'] in used or end<date or (begin and begin>date): continue
        folder=media_root/row['key']
        if not (folder/'clip.mp4').exists() or (platform=='facebook' and not facebook_ready(folder)): continue
        # Count each actual Postiz post once, even if history also imported it.
        count,last=db.execute('''SELECT COUNT(DISTINCT identity),COALESCE(MAX(when_at),'') FROM (
          SELECT COALESCE(p.post_id,p.id) AS identity,p.scheduled AS when_at FROM plans p JOIN variants v ON v.key=p.key
          WHERE p.org=? AND p.account=? AND v.offer_id=? AND p.state!='cancelled'
          UNION SELECT e.post_id,e.publish_date FROM events e JOIN variants v ON v.key=e.key
          WHERE e.org=? AND e.account=? AND v.offer_id=?)''',
          (org,account,row['offer_id'],org,account,row['offer_id'])).fetchone()
        tie=hashlib.sha256((account+day.isoformat()+row['key']).encode()).hexdigest()
        candidates.append((count,last,tie,dict(row),item))
    if not candidates: return None
    return sorted(candidates,key=lambda x:x[:3])[0][3:]

def cancel_pending(connection,org,api,invalid_only=False,now=None,allowed_accounts=None,media_root=None):
    now=now or datetime.now(timezone.utc)
    with connection() as db:
        rows=[dict(r) for r in db.execute("SELECT * FROM plans WHERE org=? AND id LIKE 'auto:%' AND state IN ('scheduled','waiting_media','planned','failed') AND scheduled>?", (org,now.isoformat()))]
    for plan in rows:
        if invalid_only:
            with connection() as db:
                variant=db.execute('SELECT * FROM variants WHERE key=? AND active=1',(plan['key'],)).fetchone()
            if variant and (allowed_accounts is None or plan['account'] in allowed_accounts):
                item=json.loads(variant['data'])
                end=datetime.fromisoformat(item['offer']['endDate'].replace('Z','+00:00'))
                changed_media=False
                if media_root and plan['platform']=='facebook' and plan['post_id'] and datetime.fromisoformat(plan['scheduled'])>now+timedelta(minutes=5):
                    folder=media_root/plan['key']
                    if facebook_ready(folder):
                        changed_media=plan.get('media_version')!=media_version(folder/'clip-facebook.mp4')
                if not changed_media and end>=datetime.fromisoformat(plan['scheduled']) and (not plan.get('source_data') or plan['source_data']==variant['data']): continue
        if plan['post_id']:
            try: api.request('posts/'+plan['post_id'],method='DELETE')
            except urllib.error.HTTPError as error:
                if error.code!=404: raise
        with connection() as db:
            db.execute("UPDATE plans SET state='cancelled',id=? WHERE id=?", (plan['id']+':cancelled:'+uuid.uuid4().hex,plan['id']))

def sync_results(connection,org,api,now):
    with connection() as db:
        plans={p['post_id']:dict(p) for p in db.execute("SELECT * FROM plans WHERE org=? AND id LIKE 'auto:%' AND state='scheduled'",(org,)) if p['post_id']}
    if not plans: return
    start=min(datetime.fromisoformat(p['scheduled']) for p in plans.values())-timedelta(days=1)
    query=urlencode({'startDate':start.isoformat(),'endDate':(now+timedelta(days=2)).isoformat()})
    result=api.request('posts?'+query)
    with connection() as db:
        for post in result.get('posts',[]):
            plan=plans.get(post['id'])
            if not plan: continue
            if post['state']=='PUBLISHED':
                inbox='/messages' in (post.get('releaseURL') or '') and plan['platform']=='tiktok'
                state='INBOX' if inbox else 'PUBLISHED'
                db.execute('INSERT OR REPLACE INTO events(org,post_id,key,account,account_name,platform,state,publish_date,release_url,caption) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (org,post['id'],plan['key'],plan['account'],plan['account_name'],plan['platform'],state,post.get('publishDate') or plan['scheduled'],post.get('releaseURL',''),plan['caption']))
                db.execute('UPDATE plans SET state=? WHERE id=?',('inbox' if inbox else 'published',plan['id']))
            elif post['state']=='ERROR':
                db.execute("UPDATE plans SET state='publish_error' WHERE id=?",(plan['id'],))
                db.execute('UPDATE automation SET last_error=? WHERE org=?',('Postiz nu a putut publica un clip. Verifică eroarea în calendar.',org))

def run_once(connection,media_root,caption,api=None,now=None):
    api=api or PostizAPI();now=now or datetime.now(timezone.utc)
    with connection() as db: config=db.execute('SELECT * FROM automation WHERE enabled=1').fetchone()
    if not config: return
    org=config['org'];account_ids=json.loads(config['accounts']);times=json.loads(config['times'])
    sync_results(connection,org,api,now)
    accounts={a['id']:a for a in api.request('integrations')}
    eligible=[i for i in account_ids if i in accounts and not accounts[i].get('disabled') and
              accounts[i]['identifier'] in ('facebook','tiktok')]
    cancel_pending(connection,org,api,invalid_only=True,now=now,allowed_accounts=eligible,media_root=media_root)
    media_statuses={};sent_this_run=0
    for account_id in account_ids:
        account=accounts.get(account_id)
        if not account or account.get('disabled'): continue
        platform=account['identifier']
        if platform not in ('facebook','tiktok'): continue
        for date in dates(now,times):
            slot='auto:'+str(uuid.uuid5(uuid.NAMESPACE_URL,org+'/'+account_id+'/'+date.isoformat()))
            with connection() as db:
                if not db.execute('SELECT 1 FROM automation WHERE org=? AND enabled=1',(org,)).fetchone(): return
                existing=db.execute('SELECT * FROM plans WHERE id=?',(slot,)).fetchone()
                if existing and existing['state'] not in ('waiting_media','planned','failed'): continue
                if existing:
                    variant=db.execute('SELECT * FROM variants WHERE key=? AND active=1',(existing['key'],)).fetchone()
                    if not variant:
                        db.execute("UPDATE plans SET state='cancelled' WHERE id=?",(slot,));continue
                    variant=dict(variant);item=json.loads(variant['data'])
                    if datetime.fromisoformat(item['offer']['endDate'].replace('Z','+00:00'))<date:
                        db.execute("UPDATE plans SET state='cancelled' WHERE id=?",(slot,));continue
                else:
                    chosen=choose(db,org,account_id,date,media_root,platform)
                    if not chosen: continue
                    variant,item=chosen
                    db.execute('INSERT OR IGNORE INTO plans(id,org,key,account,account_name,platform,scheduled,caption,state,source_data) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (slot,org,variant['key'],account_id,account['name'],platform,date.isoformat(),caption(item)[:2000] if platform=='tiktok' else caption(item),'waiting_media',variant['data']))
                plan=dict(db.execute('SELECT * FROM plans WHERE id=?',(slot,)).fetchone())
                media=db.execute('SELECT * FROM platform_media WHERE org=? AND key=? AND platform=?', (org,plan['key'],platform)).fetchone()
            source=media_root/plan['key']/('clip-facebook.mp4' if platform=='facebook' else 'clip.mp4')
            if platform=='facebook' and not facebook_ready(source.parent): continue
            source_version=media_version(source)
            if not media or media['source_version']!=source_version:
                record=api.upload(source)
                with connection() as db:
                    db.execute('INSERT OR REPLACE INTO platform_media(org,key,platform,media_id,path,source_version) VALUES(?,?,?,?,?,?)', (org,plan['key'],platform,record['id'],record['path'],source_version))
                    db.execute('INSERT OR REPLACE INTO media_versions VALUES(?,?,?,?)', (org,plan['key'],record['id'],record['path']))
                media={'media_id':record['id'],'path':record['path']}
            if media['media_id'] not in media_statuses:
                media_statuses[media['media_id']]=api.request('media/'+media['media_id']+'/status')
            status=media_statuses[media['media_id']]
            if status.get('status') != 'ready':
                if status.get('status') == 'error': raise ValueError('Procesarea clipului în Postiz a eșuat.')
                continue
            media=dict(media);media['path']=status['path']
            with connection() as db:
                if not db.execute('SELECT 1 FROM automation WHERE org=? AND enabled=1',(org,)).fetchone(): return
                claimed=db.execute("UPDATE plans SET state='sending' WHERE id=? AND state IN ('waiting_media','planned','failed')", (slot,)).rowcount
            if not claimed: continue
            try:
                body=payload(plan,media,item['offer']['title'])
                if platform=='tiktok' and not UPLOAD_ONLY: body['posts'][0]['settings'].update(content_posting_method='DIRECT_POST',privacy_level='PUBLIC_TO_EVERYONE')
                result=api.request('posts',body)
                post_id=result[0]['postId']
                if not post_id: raise ValueError('No Postiz post id')
            except Exception as error:
                # Explicit 4xx validation means no schedule was accepted.
                # Network/5xx writes are ambiguous: never resend automatically.
                state='failed' if isinstance(error,urllib.error.HTTPError) and 400<=error.code<500 else 'uncertain'
                with connection() as db:
                    db.execute('UPDATE plans SET state=? WHERE id=?',(state,slot))
                    db.execute('UPDATE automation SET last_error=? WHERE org=?',('O programare a eșuat; verifică planificările și calendarul Postiz.',org))
                raise
            with connection() as db:
                db.execute("UPDATE plans SET state='scheduled',post_id=?,media_version=? WHERE id=?", (post_id,source_version,slot))
                active=db.execute('SELECT enabled FROM automation WHERE org=?',(org,)).fetchone()
            # Stop may have raced with the in-flight schedule request.
            if not active or not active['enabled']:
                cancel_pending(connection,org,api,now=now)
                return
            sent_this_run+=1
            if sent_this_run>=6:
                # Fill large batches over several minute-long cycles instead
                # of bursting through the public API's rate limit.
                with connection() as db:db.execute('UPDATE automation SET last_run=? WHERE org=?',(now.isoformat(),org))
                return
    with connection() as db:
        unresolved=db.execute("SELECT COUNT(*) FROM plans WHERE org=? AND state IN ('uncertain','failed','publish_error')",(org,)).fetchone()[0]
        warning='Există programări cu eroare sau în verificare. Verifică lista și calendarul Postiz.' if unresolved else None
        db.execute('UPDATE automation SET last_run=?,last_error=? WHERE org=?',(now.isoformat(),warning,org))
