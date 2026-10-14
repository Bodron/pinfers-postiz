"""Check HTTPS CSRF, authentication and isolated runtime data without network/catalog access."""
import importlib.util, json, os, tempfile, io, unittest
from pathlib import Path

root = Path(__file__).resolve().parent.parent

class DeploymentChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = {key: os.environ.get(key) for key in ('LIBRARY_DATA_DIR', 'PUBLIC_ORIGIN')}
        os.environ['LIBRARY_DATA_DIR'] = self.temp.name
        os.environ['PUBLIC_ORIGIN'] = 'https://pinferspostiz.bcmenu.ro'
        spec = importlib.util.spec_from_file_location('isolated_library', root / 'pinfers-library/server.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.temp.cleanup()
        for key, value in self.previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value

    def request(self, origin, authenticated=True):
        handler = object.__new__(self.module.Handler)
        handler.headers = {'Origin': origin, 'Content-Length': '2'}
        handler.path = '/pinfers/api/retry'
        handler.rfile = io.BytesIO(b'{}')
        handler.auth = lambda: 'test-org' if authenticated else None
        result = []
        handler.result = lambda body, status=200: result.append((status, body))
        handler.do_POST()
        return result[0]

    def test_state_is_outside_source(self):
        self.assertEqual(self.module.DB.parent, Path(self.temp.name).resolve())
        self.assertEqual(self.module.MEDIA.parent, Path(self.temp.name).resolve())
        self.assertTrue(self.module.DB.exists())

    def test_download_links_survive_long_offer_descriptions(self):
        item={'offer':{'title':'Oferta de test','price':19.99,'endDate':'2026-12-31T21:00:00Z',
            'description':'Descriere lungă. '*1000},'location':{'name':'Locația de test'}}
        caption=self.module.caption(item)
        self.assertLessEqual(len(caption),2000)
        self.assertIn('iPhone: https://apps.apple.com/pl/app/pinfers/id6754986771',caption)
        self.assertIn('Android: https://play.google.com/store/apps/details?id=com.voucherino.ro&pli=1',caption)
        self.assertTrue(caption.startswith('Oferta de test la Locația de test'))

    def test_https_origin_works(self):
        self.assertEqual(self.request('https://pinferspostiz.bcmenu.ro')[0], 200)

    def test_other_and_missing_origins_are_denied(self):
        for origin in ('http://localhost:4007', 'https://evil.example', None):
            self.assertEqual(self.request(origin)[0], 403)

    def test_auth_required_even_for_correct_origin(self):
        self.assertEqual(self.request('https://pinferspostiz.bcmenu.ro', False)[0], 401)

    def test_no_posts_or_plans_created(self):
        self.request('https://pinferspostiz.bcmenu.ro')
        with self.module.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plans').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)

    def test_non_admin_cannot_use_server_api_key_to_enable_automation(self):
        handler = object.__new__(self.module.Handler)
        handler.headers = {'Origin':'https://pinferspostiz.bcmenu.ro','Content-Length':'2'}
        handler.path='/pinfers/api/automation';handler.rfile=io.BytesIO(b'{}')
        handler.auth=lambda:'test-org';handler.user_role='USER'
        results=[];handler.result=lambda body,status=200:results.append((status,body))
        handler.do_POST()
        self.assertEqual(results[0][0],403)

if __name__ == '__main__': unittest.main()
