"""Offline tests: daily rotation, restart safety, expiration, and cancellation."""
import importlib.util, json, os, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'pinfers-library'))
from autopost import run_once, cancel_pending, dates, TZ

class FakeAPI:
    def __init__(self):
        self.posts=[];self.uploads=0;self.cancelled=[];self.ambiguous=False
        self.accounts=[{'id':'page','name':'Page','identifier':'facebook','disabled':False}]
        self.history=[]
    def upload(self,path):
        self.uploads+=1
        return {'id':str(self.uploads),'path':'https://example.test/uploads/'+str(self.uploads)+'.mp4'}
    def request(self,path,body=None,method=None):
        if path.startswith('posts?'): return {'posts':self.history}
        if path=='integrations': return self.accounts
        if path.startswith('media/'): return {'status':'ready','path':'https://example.test/uploads/ready.mp4'}
        if method=='DELETE': self.cancelled.append(path);return {}
        if path=='posts':
            self.posts.append(body)
            if self.ambiguous: self.ambiguous=False;raise TimeoutError('response lost after acceptance')
            return [{'postId':'post-'+str(len(self.posts))}]
        raise AssertionError(path)

class AutomationChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=os.environ.get('LIBRARY_DATA_DIR')
        os.environ['LIBRARY_DATA_DIR']=self.temp.name
        spec=importlib.util.spec_from_file_location('test_library',root/'pinfers-library/server.py')
        self.lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.lib)
        self.now=datetime(2026,10,14,5,0,tzinfo=timezone.utc);self.api=FakeAPI()
        with self.lib.connection() as db:
            db.execute('INSERT INTO automation(org,enabled,accounts,times) VALUES(?,?,?,?)',('org',1,'["page"]','["10:00","15:00","20:00"]'))
            for i in range(4): self.add_offer(db,'offer'+str(i))
            # Two locations for one offer must not become two videos that day.
            self.add_offer(db,'offer0','other-location')
    def tearDown(self):
        self.temp.cleanup()
        if self.old is None: os.environ.pop('LIBRARY_DATA_DIR',None)
        else: os.environ['LIBRARY_DATA_DIR']=self.old
    def add_offer(self,db,offer,location='location'):
        key=offer+'_'+location
        item={'offer':{'_id':offer,'title':offer,'startDate':'2026-01-01T00:00:00Z','endDate':'2027-01-01T00:00:00Z'},'location':{'name':location}}
        db.execute('INSERT INTO variants(key,offer_id,location_id,data,state) VALUES(?,?,?,?,?)',(key,offer,location,json.dumps(item),'ready'))
        folder=self.lib.MEDIA/key;folder.mkdir()
        (folder/'clip.mp4').write_bytes(b'original')
        (folder/'clip-facebook.mp4').write_bytes(b'padded')
    def run_cycle(self): run_once(self.lib.connection,self.lib.MEDIA,lambda x:x['offer']['title'],api=self.api,now=self.now)
    def test_three_different_offers_each_day_and_no_duplicate_rerun(self):
        self.run_cycle();self.run_cycle()
        self.assertEqual(len(self.api.posts),6)
        for day in (self.now.date(),(self.now+timedelta(days=1)).date()):
            titles=[p['posts'][0]['value'][0]['content'] for p in self.api.posts if datetime.fromisoformat(p['date']).astimezone(TZ).date()==day]
            self.assertEqual(len(titles),3);self.assertEqual(len(set(titles)),3)
        self.assertTrue(all(p['type']=='schedule' for p in self.api.posts))
        self.assertTrue(all(p['posts'][0]['settings']['post_type']=='post' for p in self.api.posts))
    def test_new_offer_is_picked_first_in_next_day(self):
        self.run_cycle()
        self.now+=timedelta(days=1)
        with self.lib.connection() as db: self.add_offer(db,'brand-new')
        self.run_cycle()
        self.assertEqual(self.api.posts[6]['posts'][0]['value'][0]['content'],'brand-new')
    def test_ambiguous_write_is_never_resent(self):
        self.api.ambiguous=True
        with self.assertRaises(TimeoutError):self.run_cycle()
        self.run_cycle()
        with self.lib.connection() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM plans WHERE state='uncertain'").fetchone()[0],1)
        groups=[p['posts'][0]['group'] for p in self.api.posts]
        self.assertEqual(len(groups),len(set(groups)))
    def test_stop_cancels_only_own_future_automation_jobs(self):
        self.run_cycle()
        with self.lib.connection() as db:db.execute('UPDATE automation SET enabled=0')
        cancel_pending(self.lib.connection,'org',self.api,now=self.now)
        self.run_cycle();self.assertEqual(len(self.api.posts),6)
        self.assertEqual(len(self.api.cancelled),6)
    def test_inactive_offer_is_cancelled_and_replaced_without_erasing_history(self):
        self.run_cycle()
        with self.lib.connection() as db:
            db.execute("UPDATE variants SET active=0 WHERE offer_id='offer0'")
            db.execute("INSERT INTO events(org,post_id,key,account,state) VALUES('org','manual:1','offer0_location','page','PUBLISHED')")
        self.run_cycle()
        self.assertTrue(self.api.cancelled)
        with self.lib.connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
    def test_slot_timezone_around_dst(self):
        slots=list(dates(datetime(2026,10,25,0,0,tzinfo=timezone.utc),['10:00','15:00','20:00']))
        self.assertEqual([d.astimezone(TZ).hour for d in slots],[10,15,20,10,15,20])
    def test_each_page_gets_three_distinct_offers_independently(self):
        self.api.accounts += [{'id':'page2','name':'Page2','identifier':'facebook','disabled':False}]
        with self.lib.connection() as db:db.execute('UPDATE automation SET accounts=?',('["page","page2"]',))
        self.run_cycle();self.run_cycle();self.assertEqual(len(self.api.posts),12)
        for account in ('page','page2'):
            for day in (self.now.date(),(self.now+timedelta(days=1)).date()):
                titles=[p['posts'][0]['value'][0]['content'] for p in self.api.posts if p['posts'][0]['integration']['id']==account and datetime.fromisoformat(p['date']).astimezone(TZ).date()==day]
                self.assertEqual(len(set(titles)),3)
    def test_publication_history_is_synced_without_double_counting(self):
        self.run_cycle()
        self.api.history=[{'id':'post-1','state':'PUBLISHED','publishDate':self.api.posts[0]['date'],'releaseURL':'https://facebook.com/example'}]
        self.run_cycle();self.run_cycle()
        with self.lib.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM plans WHERE state='published'").fetchone()[0],1)

if __name__=='__main__':unittest.main()
