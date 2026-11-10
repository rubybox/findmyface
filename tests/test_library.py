import os, json, tempfile, unittest, time, zipfile
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
TMP=tempfile.TemporaryDirectory(); p=Path(TMP.name)
(p/'key').write_bytes(Fernet.generate_key());(p/'oauth.json').write_text(json.dumps({'web':{'client_id':'fake','client_secret':'fake','redirect_uris':['https://photos.example.com/api/auth/google/callback']}}))
os.environ.update(DATA_DIR=str(p/'data'),TOKEN_KEY_FILE=str(p/'key'),OAUTH_FILE=str(p/'oauth.json'))
from app import main as m
from app import library as lib
FILES=[{'id':'photo1','name':'../../photo.jpg','mimeType':'image/jpeg','folder':'HILIGHT','size':3,'downloadable':True}, {'id':'photo2','name':'../../photo.jpg','mimeType':'image/jpeg','folder':'HILIGHT','size':3,'downloadable':True}]
class Google:
    def __init__(self,**kw): pass
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def get(self,url,**kw):
        fid=url.rsplit('/',1)[-1]
        data={'id':fid,'name':'../../photo.jpg','mimeType':'image/jpeg','size':'3','parents':[lib.ROOT],'capabilities':{'canDownload':True}}
        return type('Reply',(),{'status_code':200,'json':lambda self:data})()
    def stream(self,*a,**kw):
        class Stream:
            status_code=200
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def iter_bytes(self,*a): yield b'abc'
        return Stream()
class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(m.app,base_url=m.BASE,follow_redirects=False)
        self.client.cookies.set(m.COOKIE,'fake-session',domain='photos.example.com',path='/')
        self.diskpatch=patch.object(lib.shutil,'disk_usage',lambda p:type('Disk',(),{'free':20*1024**3})())
        self.diskpatch.start();self.addCleanup(self.diskpatch.stop)
        self.now=int(time.time())
        tokens={'access_token':'fake-access','expires_in':3600,'obtained_at':self.now}
        with m.db() as c:
            c.execute('DELETE FROM sessions');c.execute('DELETE FROM exports');c.execute('DELETE FROM library_cache')
            c.execute('INSERT INTO sessions VALUES (?,?,?,?)',(m.digest('fake-session'),m.ALLOWED,m.cipher.encrypt(json.dumps(tokens).encode()),self.now+3600))
            c.execute('INSERT INTO library_cache VALUES (?,?,?)',(lib.ROOT,json.dumps({'root':lib.ROOT,'name':'Test album','files':FILES,'updated':self.now}),self.now))
    def test_auth_and_root_allowlist(self):
        anonymous=TestClient(m.app,base_url=m.BASE)
        self.assertEqual(anonymous.get('/api/library').status_code,401)
        data=self.client.get('/api/library').json()
        self.assertEqual(len(data['files']),2)
        self.assertNotIn('thumbnailLink',str(data))
        self.assertEqual(self.client.get('/api/photos/outside/thumbnail').status_code,404)
        self.assertEqual(self.client.post('/api/exports',json={'ids':['outside']},headers={'origin':m.BASE}).status_code,403)
        self.assertEqual(self.client.post('/api/exports',json={'ids':['photo1','photo1']},headers={'origin':m.BASE}).status_code,400)
        self.assertEqual(self.client.post('/api/exports',json={'ids':['photo1']},headers={'origin':'https://evil.example'}).status_code,403)
    def test_zip_integrity_names_and_ownership(self):
        with patch.object(lib.httpx,'Client',Google),patch.object(lib.executor,'submit',lambda fn,*args:fn(*args)):
            response=self.client.post('/api/exports',json={'ids':['photo1','photo2']},headers={'origin':m.BASE})
        self.assertEqual(response.status_code,202,response.text)
        jid=response.json()['id']
        job=self.client.get('/api/exports/'+jid).json()
        self.assertEqual(job['status'],'ready',job)
        self.assertEqual(job['done'],2)
        result=self.client.get('/api/exports/'+jid+'/download')
        self.assertEqual(result.status_code,200)
        import io
        with zipfile.ZipFile(io.BytesIO(result.content)) as z:
            self.assertEqual(len(z.namelist()),2)
            self.assertEqual(len(set(z.namelist())),2)
            self.assertTrue(all('/' not in n and '\\' not in n for n in z.namelist()))
            self.assertIsNone(z.testzip())
            self.assertTrue(all(z.read(n)==b'abc' for n in z.namelist()))
        with m.db() as c:
            c.execute('UPDATE exports SET owner=? WHERE id=?',('another-session',jid))
        self.assertEqual(self.client.get('/api/exports/'+jid+'/download').status_code,404)
    def test_restart_and_busy_rules(self):
        with m.db() as c:
            c.execute('INSERT INTO exports VALUES (?,?,?,?,?,?,?,?,?)',('busy',m.digest('fake-session'),'running',1,0,0,'',self.now,self.now+1000))
        self.assertEqual(self.client.post('/api/exports',json={'ids':['photo1']},headers={'origin':m.BASE}).status_code,409)
        self.assertEqual(self.client.post('/api/exports/busy/cancel',headers={'origin':m.BASE}).status_code,200)
        self.assertEqual(self.client.get('/api/exports/busy').json()['status'],'cancelled')
        self.assertEqual(self.client.get('/api/exports/busy/download').status_code,409)
    def test_low_disk_is_rejected(self):
        with patch.object(lib.shutil,'disk_usage',lambda p:type('Disk',(),{'free':1024})()):
            self.assertEqual(self.client.post('/api/exports',json={'ids':['photo1']},headers={'origin':m.BASE}).status_code,413)
    def test_zip_filename_collision(self):
        used=set();names=[lib.safe_name(n,used) for n in ['../x.jpg','../x.jpg','UPPER.JPG','upper.jpg','\x00']]
        self.assertEqual(len(set(n.casefold() for n in names)),5)
        self.assertTrue(all('/' not in n and '\\' not in n for n in names))
    def test_hidden_parents_verified_by_fresh_listing(self):
        class HiddenParents(Google):
            def get(self,url,**kw):
                if url.endswith('/files/'+lib.ROOT):
                    data={'id':lib.ROOT,'name':'Album','mimeType':'application/vnd.google-apps.folder','capabilities':{'canListChildren':True}}
                elif url.endswith('/files'):
                    data={'files':[{**f,'capabilities':{'canDownload':True}} for f in FILES]}
                else:
                    original=super().get(url,**kw)
                    data=original.json();data.pop('parents',None)
                return type('Reply',(),{'status_code':200,'json':lambda self:data})()
        with patch.object(lib.httpx,'Client',HiddenParents),patch.object(lib.executor,'submit',lambda fn,*args:fn(*args)):
            r=self.client.post('/api/exports',json={'ids':['photo1']},headers={'origin':m.BASE})
        self.assertEqual(r.status_code,202,r.text)
        self.assertEqual(self.client.get('/api/exports/'+r.json()['id']).json()['status'],'ready')

    def test_public_no_login_and_isolated_download_jobs(self):
        with patch.object(m,'PUBLIC_ACCESS',True):
            visitor=TestClient(m.app,base_url=m.BASE,follow_redirects=False)
            r=visitor.get('/')
            self.assertEqual(r.status_code,200)
            self.assertNotIn('ออกจากระบบ',r.text)
            self.assertIn('value="0.46"',r.text)
            self.assertIn('/static/analytics.js',r.text)
            self.assertIn('HttpOnly',r.headers['set-cookie'])
            self.assertIn('Secure',r.headers['set-cookie'])
            self.assertEqual(visitor.get('/api/library').status_code,200)
            self.assertEqual(visitor.get('/api/library').json()['email'],'')
            self.assertEqual(visitor.post('/api/faces/index',headers={'origin':'https://evil.example'}).status_code,403)
            owner=m.digest(visitor.cookies.get(m.VISITOR_COOKIE))
            with m.db() as c:
                c.execute('INSERT INTO exports VALUES (?,?,?,?,?,?,?,?,?)',('public-job',owner,'ready',1,1,3,'',self.now,self.now+1000))
            self.assertEqual(visitor.get('/api/exports/public-job').status_code,200)
            other=TestClient(m.app,base_url=m.BASE)
            self.assertEqual(other.get('/api/exports/public-job').status_code,404)
            self.assertEqual(visitor.get('/api/auth/google/start').status_code,303)

    def test_optional_analytics_configuration(self):
        with patch.dict(os.environ, {'GA_MEASUREMENT_ID': ''}):
            self.assertEqual(self.client.get('/api/config').json()['analytics_measurement_id'],'')
        with patch.dict(os.environ, {'GA_MEASUREMENT_ID': 'G-EXAMPLE1234'}):
            self.assertEqual(self.client.get('/api/config').json()['analytics_measurement_id'],'G-EXAMPLE1234')
        with patch.dict(os.environ, {'GA_MEASUREMENT_ID': 'invalid-id'}):
            self.assertEqual(self.client.get('/api/config').json()['analytics_measurement_id'],'')

    def test_default_threshold_and_analytics_policy(self):
        import numpy as np
        from app.matching_core import FaceEngine
        with patch.object(FaceEngine,'extract',lambda self,raw:[({},np.zeros(128))]):
            r=self.client.post('/api/faces/search',content=b'ref',headers={'origin':m.BASE})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['threshold'],0.46)
        r=self.client.get('/')
        self.assertIn('https://www.googletagmanager.com',r.headers['content-security-policy'])
        self.assertIn('https://*.google-analytics.com',r.headers['content-security-policy'])
        self.assertEqual(self.client.get('/static/analytics.js').status_code,200)

    def test_invalid_archive_format(self):
        result=self.client.post('/api/exports',json={'ids':['photo1'],'format':'exe'},headers={'origin':m.BASE})
        self.assertEqual(result.status_code,400)

    def test_tar_integrity_and_ownership(self):
        import tarfile, io
        with patch.object(lib.httpx,'Client',Google),patch.object(lib.executor,'submit',lambda fn,*args:fn(*args)):
            response=self.client.post('/api/exports',json={'ids':['photo1','photo2'],'format':'tar'},headers={'origin':m.BASE})
        self.assertEqual(response.status_code,202,response.text)
        jid=response.json()['id']
        job=self.client.get('/api/exports/'+jid).json()
        self.assertEqual(job['status'],'ready',job)
        self.assertEqual(job['format'],'tar')
        result=self.client.get('/api/exports/'+jid+'/download')
        self.assertEqual(result.headers['content-type'],'application/x-tar')
        with tarfile.open(fileobj=io.BytesIO(result.content)) as archive:
            members=archive.getmembers()
            self.assertEqual(len(members),2)
            self.assertTrue(all('/' not in f.name for f in members))
            self.assertTrue(all(archive.extractfile(f).read()==b'abc' for f in members))
        with m.db() as c:c.execute('UPDATE exports SET owner=? WHERE id=?',('other',jid))
        self.assertEqual(self.client.get('/api/exports/'+jid+'/download').status_code,404)

    def test_face_search_review_boundary(self):
        import numpy as np
        from app.matching_core import Store, FaceEngine
        store=Store(m.DATA/('faces-yunet-'+lib.ROOT+'.sqlite3'))
        files=[]
        for i in range(21):
            file={**FILES[0],'id':'match'+str(i)};files.append(file)
            store.replace({'id':file['id'],'name':'photo.jpg','modifiedTime':'v1'},[({},np.zeros(128))],FaceEngine.model_id)
        file={**FILES[0],'id':'review'};files.append(file)
        vector=np.zeros(128);vector[0]=.55
        store.replace({'id':'review','name':'review.jpg','modifiedTime':'v1'},[({},vector)],FaceEngine.model_id)
        for i in range(24):
            fid='review'+str(i);files.append({**FILES[0],'id':fid})
            store.replace({'id':fid,'name':'review.jpg','modifiedTime':'v1'},[({},vector)],FaceEngine.model_id)
        def update_cache(items):
            with m.db() as c:c.execute('INSERT OR REPLACE INTO library_cache VALUES (?,?,?)',(lib.ROOT,json.dumps({'root':lib.ROOT,'name':'Test','files':items,'updated':self.now}),self.now))
        update_cache(files)
        with patch.object(FaceEngine,'extract',lambda self,raw:[({},np.zeros(128))]):
            r=self.client.post('/api/faces/search',content=b'ref',headers={'origin':m.BASE})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(len(r.json()['matches']),21)
            self.assertEqual(len(r.json()['review']),25)
            update_cache(files[1:])
            r=self.client.post('/api/faces/search',content=b'ref',headers={'origin':m.BASE})
            self.assertEqual(len(r.json()['matches']),20)
            self.assertEqual(r.json()['review'],[])
        self.assertEqual(self.client.post('/api/faces/search',content=b'ref',headers={'origin':'https://evil.example'}).status_code,403)

if __name__=='__main__': unittest.main()
