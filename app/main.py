import base64
from contextlib import contextmanager
import hashlib
import html
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, FileResponse

BASE = os.getenv('APP_BASE_URL', 'https://photos.example.com').rstrip('/')
CALLBACK = BASE + '/api/auth/google/callback'
SCOPE = 'openid email'
COOKIE = '__Host-findme'
VISITOR_COOKIE = '__Host-findme-visitor'
PUBLIC_ACCESS = os.getenv('PUBLIC_ACCESS', 'false').lower() == 'true'
if PUBLIC_ACCESS and not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
    raise RuntimeError('Public access requires the server Service Account')
DATA = Path(os.environ.get('DATA_DIR', '/data'))
DATA.mkdir(parents=True, exist_ok=True)
os.umask(0o077)
KEY = Path(os.environ.get('TOKEN_KEY_FILE', '/run/secrets/token_key')).read_bytes().strip()
cipher = Fernet(KEY)
CREDENTIALS = Path(os.environ.get('OAUTH_FILE', '/run/secrets/oauth.json'))
ALLOWED = os.environ.get('ALLOWED_EMAIL', 'owner@example.com').lower()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@contextmanager
def db():
    conn = sqlite3.connect(DATA / 'findme.sqlite3', timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


with db() as c:
    c.execute('CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, email TEXT, tokens BLOB, expires INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS flows (state TEXT PRIMARY KEY, binding TEXT, verifier TEXT, expires INTEGER)')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def credentials():
    try:
        cfg = json.loads(CREDENTIALS.read_text())['web']
        assert CALLBACK in cfg['redirect_uris']
        assert cfg['client_id'] and cfg['client_secret']
        return cfg
    except (OSError, KeyError, ValueError, AssertionError):
        return None


def session(request):
    if getattr(request.state, 'visitor_session', None) is not None:
        return request.state.visitor_session
    sid = request.cookies.get(VISITOR_COOKIE if PUBLIC_ACCESS else COOKIE, '')
    with db() as c:
        return c.execute('SELECT * FROM sessions WHERE sid=? AND expires>?', (digest(sid), int(time.time()))).fetchone()


def page(content, status=200):
    return HTMLResponse('''<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FindMe · คลังรูปของคุณ</title><style>body{margin:0;background:#f3f7f5;color:#183d34;font-family:system-ui,sans-serif}main{max-width:800px;margin:10vh auto;padding:28px}.brand{letter-spacing:.15em;font-size:14px;font-weight:700}.card{background:white;border:1px solid #dce7e1;border-radius:24px;padding:36px;margin-top:32px}h1{font-size:clamp(30px,6vw,48px);line-height:1.25}p{line-height:1.9;color:#51685e}.button,button{display:inline-block;background:#195e49;color:white;border:0;border-radius:12px;padding:14px 22px;text-decoration:none;font:inherit;cursor:pointer}.pill{font-size:13px;color:#517063}footer{margin-top:25px;color:#60766c;font-size:13px}code{overflow-wrap:anywhere}</style><main><div class="brand">FINDME / PHOTO LIBRARY</div><div class="card">''' + content + '''</div><footer>รุ่นทดสอบส่วนตัว · รูปต้นฉบับจัดเก็บบน Google Drive</footer></main></html>''', status_code=status)


@app.middleware('http')
async def security(request, call_next):
    visitor = None
    if PUBLIC_ACCESS and (request.url.path == '/' or request.url.path.startswith('/api/')) and not session(request):
        visitor = secrets.token_urlsafe(32)
        now = int(time.time())
        with db() as c:
            c.execute('DELETE FROM sessions WHERE expires<?', (now,))
            c.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                      (digest(visitor), 'visitor', cipher.encrypt(b'{}'), now + 86400))
            request.state.visitor_session = c.execute('SELECT * FROM sessions WHERE sid=?', (digest(visitor),)).fetchone()
    response = await call_next(request)
    if visitor:
        response.set_cookie(VISITOR_COOKIE, visitor, max_age=86400, secure=True, httponly=True, samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; script-src 'self' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline'; img-src 'self' blob: https://*.google-analytics.com https://www.googletagmanager.com; connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get('/api/config')
def public_config():
    import re
    measurement_id = os.getenv('GA_MEASUREMENT_ID', '').strip()
    return {'analytics_measurement_id': measurement_id if re.fullmatch(r'G-[A-Z0-9]+', measurement_id) else ''}


@app.get('/healthz')
def health():
    return PlainTextResponse('ok')


@app.get('/')
def home(request: Request):
    current = session(request)
    if PUBLIC_ACCESS or current:
        return FileResponse(Path(__file__).parent / 'static' / 'gallery.html', media_type='text/html')
    if not credentials():
        return page('<span class="pill">กำลังตั้งค่า</span><h1>คลังรูปของคุณ<br>อยู่ในที่เดียว</h1><p>กำลังติดตั้งการเชื่อมต่อ Google Drive กรุณากลับมาอีกครั้งเมื่อการตั้งค่าเสร็จ</p>')
    return page('<span class="pill">รุ่นทดสอบส่วนตัว</span><h1>ค้นหารูปของคุณ<br>ในคลังภาพ</h1><p>เข้าสู่ระบบด้วยบัญชีที่ได้รับอนุญาต คลังภาพถูกกำหนดไว้แล้วโดยผู้ดูแลระบบ</p><a class="button" href="/api/auth/google/start">เข้าสู่ระบบด้วย Google</a><p class="pill">ช่วงทดสอบเปิดให้บัญชีที่กำหนดเท่านั้น</p>')


@app.get('/api/auth/google/start')
def start():
    if PUBLIC_ACCESS:
        return RedirectResponse('/', 303)
    cfg = credentials()
    if not cfg:
        return page('<h1>ยังตั้งค่าไม่เสร็จ</h1><p>ข้อมูลการเชื่อมต่อยังไม่พร้อม</p>', 503)
    state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    now = int(time.time())
    with db() as c:
        c.execute('DELETE FROM flows WHERE expires<?', (now,))
        c.execute('DELETE FROM sessions WHERE expires<?', (now,))
        c.execute('INSERT INTO flows VALUES (?,?,?,?)', (digest(state), digest(binding), verifier, now + 600))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    params = dict(client_id=cfg['client_id'], redirect_uri=CALLBACK, response_type='code', scope=SCOPE, state=state, login_hint=ALLOWED, code_challenge=challenge, code_challenge_method='S256')
    response = RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params), 303)
    response.set_cookie('__Host-findme-flow', binding, max_age=600, secure=True, httponly=True, samesite='lax', path='/')
    return response


@app.get('/api/auth/google/callback')
async def callback(request: Request):
    if PUBLIC_ACCESS:
        return RedirectResponse('/', 303)
    state = request.query_params.get('state', '')
    binding = request.cookies.get('__Host-findme-flow', '')
    now = int(time.time())
    with db() as c:
        # Validate cookie binding before consuming the single-use flow.
        c.execute('BEGIN IMMEDIATE')
        flow = c.execute('SELECT * FROM flows WHERE state=? AND expires>?', (digest(state), now)).fetchone()
        if not flow or not binding or not secrets.compare_digest(flow['binding'], digest(binding)):
            return page('<h1>ลิงก์เข้าสู่ระบบไม่ถูกต้องหรือหมดอายุ</h1><p><a href="/">เริ่มใหม่</a></p>', 400)
        c.execute('DELETE FROM flows WHERE state=?', (digest(state),))
    if request.query_params.get('error') or not request.query_params.get('code'):
        response = page('<h1>ยังไม่ได้เชื่อมต่อ</h1><p>คุณสามารถกลับไปเริ่มใหม่ได้</p><a href="/">กลับหน้าแรก</a>', 400)
        response.delete_cookie('__Host-findme-flow', secure=True, httponly=True, samesite='lax')
        return response
    cfg = credentials()
    if not cfg:
        return page('<h1>การตั้งค่าการเชื่อมต่อไม่พร้อม</h1>', 503)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            result = await client.post('https://oauth2.googleapis.com/token', data={'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'], 'redirect_uri': CALLBACK, 'grant_type': 'authorization_code', 'code': request.query_params['code'], 'code_verifier': flow['verifier']})
            result.raise_for_status()
            tokens = result.json()
            scopes = set(tokens.get('scope', '').split())
            if 'openid' not in scopes or not ({'email', 'https://www.googleapis.com/auth/userinfo.email'} & scopes):
                return page('<h1>ยังไม่ได้อนุญาตการเข้าสู่ระบบ</h1><p><a href="/">เริ่มใหม่</a></p>', 403)
            identity = await client.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization': 'Bearer ' + tokens['access_token']})
            identity.raise_for_status()
            profile = identity.json()
            email = profile['email'].lower()
            if not profile.get('email_verified'):
                return page('<h1>กรุณายืนยันอีเมล Google ก่อนเข้าสู่ระบบ</h1>', 403)
            if email != ALLOWED:
                await client.post('https://oauth2.googleapis.com/revoke', data={'token': tokens.get('refresh_token', tokens['access_token'])})
                return page('<h1>บัญชีนี้ยังไม่ได้เปิดให้ทดสอบ</h1><p>กรุณาใช้บัญชีทดสอบที่กำหนด</p>', 403)
    except (httpx.HTTPError, KeyError, ValueError):
        return page('<h1>เชื่อมต่อ Google ไม่สำเร็จ</h1><p>กรุณาลองใหม่ภายหลัง</p><a href="/">กลับหน้าแรก</a>', 502)
    sid = secrets.token_urlsafe(32)
    tokens['obtained_at'] = now
    with db() as c:
        c.execute('DELETE FROM sessions WHERE sid=?', (digest(request.cookies.get(COOKIE, '')),))
        c.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(sid), email, cipher.encrypt(json.dumps(tokens).encode()), now + 86400))
    response = RedirectResponse('/', 303)
    response.set_cookie(COOKIE, sid, max_age=86400, secure=True, httponly=True, samesite='lax', path='/')
    response.delete_cookie('__Host-findme-flow', secure=True, httponly=True, samesite='lax')
    return response


@app.post('/api/auth/logout')
def logout(request: Request):
    if request.headers.get('origin') != BASE:
        return PlainTextResponse('Forbidden', status_code=403)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE sid=?', (digest(request.cookies.get(COOKIE, '')),))
    response = RedirectResponse('/', 303)
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='lax')
    return response


from . import library
library.install(app, __import__(__name__, fromlist=["app"]))
