import os, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

TMP=tempfile.TemporaryDirectory()
p=Path(TMP.name)
(p/'key').write_bytes(Fernet.generate_key())
(p/'oauth.json').write_text(json.dumps({'web':{'client_id':'test-client','client_secret':'fake-secret','redirect_uris':['https://photos.example.com/api/auth/google/callback']}}))
os.environ.update(DATA_DIR=str(p/'data'),TOKEN_KEY_FILE=str(p/'key'),OAUTH_FILE=str(p/'oauth.json'))
from app import main as m

class Reply:
    def __init__(self,data): self.data=data
    def raise_for_status(self): pass
    def json(self): return self.data

class FakeGoogle:
    email='owner@example.com'
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def post(self,url,**kwargs): return Reply({'access_token':'fake-access','refresh_token':'fake-refresh','scope':m.SCOPE})
    async def get(self,*args,**kwargs): return Reply({'email':self.email,'email_verified':True})

class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(m.app,base_url=m.BASE,follow_redirects=False)
        with m.db() as c:
            c.execute('DELETE FROM sessions');c.execute('DELETE FROM flows')
    def begin(self):
        result=self.client.get('/api/auth/google/start')
        self.assertEqual(result.status_code,303)
        query=parse_qs(urlparse(result.headers['location']).query)
        self.assertEqual(query['redirect_uri'],[m.CALLBACK])
        self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertIn('Secure',result.headers['set-cookie'])
        self.assertIn('HttpOnly',result.headers['set-cookie'])
        return query['state'][0]
    def test_state_binding_pkce_and_replay(self):
        state=self.begin()
        other=TestClient(m.app,base_url=m.BASE,follow_redirects=False)
        self.assertEqual(other.get('/api/auth/google/callback',params={'state':state,'code':'fake'}).status_code,400)
        with patch.object(m.httpx,'AsyncClient',lambda **kw:FakeGoogle()):
            r=self.client.get('/api/auth/google/callback',params={'state':state,'code':'fake'})
        self.assertEqual(r.status_code,303)
        self.assertIn('คัดเลือกรูปของคุณ',self.client.get('/').text)
        with m.db() as c:
            row=c.execute('SELECT * FROM sessions').fetchone()
            self.assertNotIn(b'fake-access',row['tokens'])
            self.assertIn(b'fake-access',m.cipher.decrypt(row['tokens']))
        self.assertEqual(self.client.get('/api/auth/google/callback',params={'state':state,'code':'fake'}).status_code,400)
        self.assertEqual(self.client.post('/api/auth/logout',headers={'origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/logout',headers={'origin':m.BASE}).status_code,303)
        self.assertNotIn('เชื่อมต่อ Google Drive แล้ว',self.client.get('/').text)
    def test_denied_and_expired_flow(self):
        state=self.begin()
        self.assertEqual(self.client.get('/api/auth/google/callback',params={'state':state,'error':'access_denied'}).status_code,400)
        state=self.begin()
        with m.db() as c: c.execute('UPDATE flows SET expires=0')
        self.assertEqual(self.client.get('/api/auth/google/callback',params={'state':state,'code':'fake'}).status_code,400)
    def test_wrong_account_cannot_login(self):
        state=self.begin()
        with patch.object(FakeGoogle,'email','other@example.com'),patch.object(m.httpx,'AsyncClient',lambda **kw:FakeGoogle()):
            self.assertEqual(self.client.get('/api/auth/google/callback',params={'state':state,'code':'fake'}).status_code,403)
        with m.db() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
    def test_login_no_longer_requests_drive_access(self):
        result=self.client.get('/api/auth/google/start')
        query=parse_qs(urlparse(result.headers['location']).query)
        self.assertEqual(query['scope'],['openid email'])
        self.assertNotIn('drive',query['scope'][0])

    def test_headers_and_health(self):
        r=self.client.get('/')
        self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertIn("frame-ancestors 'none'",r.headers['content-security-policy'])
        self.assertEqual(self.client.get('/healthz').text,'ok')

if __name__=='__main__': unittest.main()
