"""Fixed shared-library browser and bounded, private ZIP exports."""
import json
import os
import re
import secrets
import shutil
import threading
import time
import zipfile
import tarfile
import tempfile
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response

ROOT = os.getenv('DRIVE_FOLDER_ID', 'EXAMPLE_DRIVE_FOLDER_ID')
if not re.fullmatch(r'[\w-]+', ROOT):
    raise ValueError('Invalid DRIVE_FOLDER_ID')
MAX_BYTES = 8 * 1024**3
RESERVE = 2 * 1024**3
TTL = 3600
STATIC = Path(__file__).parent / 'static'
refresh_lock = threading.Lock()
scan_lock = threading.Lock()
thumb_slots = threading.Semaphore(4)
preview_slot = threading.Semaphore(1)
executor = ThreadPoolExecutor(max_workers=1)


def safe_name(name, used):
    name = re.sub(r'[\\/\x00-\x1f\x7f:]', '_', name).strip(' .')[:180] or 'photo.jpg'
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while candidate.casefold() in used:
        candidate = f'{stem}_{n}{ext}'
        n += 1
    used.add(candidate.casefold())
    return candidate


@contextmanager
def archive_member(archive, name, size, format, directory):
    if format == 'zip':
        with archive.open(name, 'w', force_zip64=True) as dest:
            yield dest
    else:
        # TAR headers need the exact file length. Spill to persistent storage, not /tmp RAM.
        with tempfile.TemporaryFile(dir=directory) as dest:
            yield dest
            actual = dest.tell()
            if size and actual != size:
                raise HTTPException(502, 'ได้รับไฟล์ไม่ครบ กรุณาสร้างไฟล์ใหม่')
            dest.seek(0)
            info = tarfile.TarInfo(name)
            info.size = actual
            info.mode = 0o600
            archive.addfile(info, dest)


def install(app, core):
    exports = core.DATA / 'exports'
    thumbs = core.DATA / 'thumbs'
    exports.mkdir(exist_ok=True)
    thumbs.mkdir(exist_ok=True)
    with core.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS library_cache (root TEXT PRIMARY KEY, payload TEXT, updated INTEGER)')
        c.execute('''CREATE TABLE IF NOT EXISTS exports (id TEXT PRIMARY KEY, owner TEXT, status TEXT,
            total INTEGER, done INTEGER, bytes INTEGER, error TEXT, created INTEGER, expires INTEGER)''')
        c.execute('CREATE TABLE IF NOT EXISTS export_formats (id TEXT PRIMARY KEY, format TEXT NOT NULL)')
        c.execute("UPDATE exports SET status='failed',error='เซิร์ฟเวอร์เริ่มใหม่ กรุณาสร้างไฟล์อีกครั้ง' WHERE status IN ('queued','running')")

    def auth(request):
        current = core.session(request)
        if not current:
            raise HTTPException(401, 'เซสชันหมดอายุ กรุณาเชื่อมต่อ Google ใหม่')
        return current

    def origin(request):
        if request.headers.get('origin') != core.BASE:
            raise HTTPException(403, 'Invalid origin')

    service_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')
    service_credentials = None
    if service_file:
        from google.oauth2 import service_account
        service_credentials = service_account.Credentials.from_service_account_file(
            service_file, scopes=['https://www.googleapis.com/auth/drive.readonly'])

    def headers(sid):
        with refresh_lock:
            if service_credentials is not None:
                # Endpoints authenticate browser sessions before requesting data. None is
                # reserved for the server's startup index task, never accepted from HTTP.
                if sid is not None:
                    with core.db() as c:
                        active = c.execute('SELECT 1 FROM sessions WHERE sid=? AND expires>?', (sid, int(time.time()))).fetchone()
                    if not active:
                        raise HTTPException(401, 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่')
                from google.auth.transport.requests import Request as GoogleRequest
                if not service_credentials.valid:
                    service_credentials.refresh(GoogleRequest())
                return {'Authorization': 'Bearer ' + service_credentials.token}
            with core.db() as c:
                row = c.execute('SELECT * FROM sessions WHERE sid=? AND expires>?', (sid, int(time.time()))).fetchone()
            if not row:
                raise HTTPException(401, 'เซสชันหมดอายุ กรุณาเชื่อมต่อ Google ใหม่')
            tokens = json.loads(core.cipher.decrypt(row['tokens']))
            if tokens.get('obtained_at', 0) + tokens.get('expires_in', 3600) < time.time() + 120:
                cfg = core.credentials()
                if not cfg or not tokens.get('refresh_token'):
                    raise HTTPException(401, 'กรุณาเชื่อมต่อ Google ใหม่')
                with httpx.Client(timeout=25) as client:
                    r = client.post('https://oauth2.googleapis.com/token', data={
                        'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'],
                        'refresh_token': tokens['refresh_token'], 'grant_type': 'refresh_token'})
                if r.status_code != 200:
                    raise HTTPException(401, 'สิทธิ์ Google หมดอายุ กรุณาเชื่อมต่อใหม่')
                tokens.update(r.json())
                tokens['obtained_at'] = int(time.time())
                with core.db() as c:
                    c.execute('UPDATE sessions SET tokens=? WHERE sid=?', (core.cipher.encrypt(json.dumps(tokens).encode()), sid))
            return {'Authorization': 'Bearer ' + tokens['access_token']}

    def get_json(sid, path, params=None):
        for attempt in range(3):
            with httpx.Client(timeout=30) as client:
                r = client.get('https://www.googleapis.com/drive/v3/' + path, params=params, headers=headers(sid))
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2**attempt)
                continue
            if r.status_code == 401:
                raise HTTPException(401, 'กรุณาเชื่อมต่อ Google ใหม่')
            raise HTTPException(502, 'Google Drive ไม่พร้อมหรือไม่มีสิทธิ์เข้าถึงไฟล์ กรุณาลองใหม่')

    def library(sid, force=False):
        with scan_lock:
            with core.db() as c:
                old = c.execute('SELECT * FROM library_cache WHERE root=?', (ROOT,)).fetchone()
            if old and not force and old['updated'] > time.time() - 300:
                return json.loads(old['payload'])
            root = get_json(sid, 'files/' + ROOT, {'fields': 'id,name,mimeType,capabilities(canListChildren)', 'supportsAllDrives': 'true'})
            if not root.get('capabilities', {}).get('canListChildren'):
                raise HTTPException(403, 'ไม่สามารถเปิดโฟลเดอร์ที่แชร์ได้')
            folders = [(ROOT, '')]
            seen, files = set(), []
            while folders:
                fid, location = folders.pop(0)
                if fid in seen:
                    continue
                seen.add(fid)
                if len(seen) > 100:
                    raise HTTPException(413, 'จำนวนโฟลเดอร์เกินขนาดที่รองรับในรุ่นนี้')
                token = None
                while True:
                    params = {'q': "'" + fid + "' in parents and trashed=false", 'pageSize': 1000,
                        'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,size,modifiedTime,thumbnailLink,capabilities(canDownload))',
                        'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
                    if token:
                        params['pageToken'] = token
                    data = get_json(sid, 'files', params)
                    if data.get('incompleteSearch'):
                        raise HTTPException(502, 'Google ส่งรายการไม่ครบ กรุณาลองรีเฟรชใหม่')
                    for item in data.get('files', []):
                        if item['mimeType'] == 'application/vnd.google-apps.folder':
                            folders.append((item['id'], location + '/' + item['name']))
                        elif item['mimeType'].startswith('image/'):
                            files.append({**item, 'folder': location.lstrip('/'), 'size': int(item.get('size', 0)),
                                'downloadable': item.get('capabilities', {}).get('canDownload', False)})
                    if len(files) > 10000:
                        raise HTTPException(413, 'จำนวนรูปเกินขนาดที่รองรับในรุ่นนี้')
                    token = data.get('nextPageToken')
                    if not token:
                        break
            files.sort(key=lambda f: (f['folder'].casefold(), f['name'].casefold(), f['id']))
            result = {'name': root['name'], 'root': ROOT, 'files': files, 'updated': int(time.time())}
            with core.db() as c:
                c.execute('INSERT OR REPLACE INTO library_cache VALUES (?,?,?)', (ROOT, json.dumps(result), result['updated']))
            return result

    def item(sid, fid):
        return next((f for f in library(sid)['files'] if f['id'] == fid), None)

    def current_file(sid, fid, listed=False):
        data = get_json(sid, 'files/' + fid, {'fields': 'id,name,size,parents,trashed,mimeType,thumbnailLink,capabilities(canDownload)', 'supportsAllDrives': 'true'})
        if data.get('trashed') or not data.get('mimeType', '').startswith('image/') or not data.get('capabilities', {}).get('canDownload'):
            raise HTTPException(403, 'ไฟล์ถูกลบหรือไม่อนุญาตให้ดาวน์โหลด')
        if listed:
            # The index caller just completed a full root traversal. It cannot be
            # selected from an HTTP query parameter.
            return data
        parents = list(data.get('parents', []))
        if not parents:
            # Drive may hide parents for service-account readers. A fresh full
            # traversal proves membership without trusting a stale cache or URL.
            if any(f['id'] == fid for f in library(sid, force=True)['files']):
                return data
            raise HTTPException(403, 'ไฟล์นี้ไม่ได้อยู่ในคลังรูปที่กำหนดแล้ว')
        seen = set()
        while parents and len(seen) < 100:
            parent = parents.pop()
            if parent == ROOT:
                return data
            if parent in seen:
                continue
            seen.add(parent)
            node = get_json(sid, 'files/' + parent, {'fields': 'parents,trashed', 'supportsAllDrives': 'true'})
            if not node.get('trashed'):
                parents.extend(node.get('parents', []))
        raise HTTPException(403, 'ไฟล์นี้ไม่ได้อยู่ในคลังรูปที่กำหนดแล้ว')

    def cleanup():
        now = int(time.time())
        with core.db() as c:
            expired = c.execute("SELECT id FROM exports WHERE status NOT IN ('queued','running') AND expires<?", (now,)).fetchall()
            for row in expired:
                (exports / (row['id'] + '.zip')).unlink(missing_ok=True)
                (exports / (row['id'] + '.tar')).unlink(missing_ok=True)
                c.execute('DELETE FROM export_formats WHERE id=?', (row['id'],))
                (exports / (row['id'] + '.part')).unlink(missing_ok=True)
                c.execute('DELETE FROM exports WHERE id=?', (row['id'],))
        for p in thumbs.glob('*.img'):
            if p.stat().st_mtime < now - TTL:
                p.unlink(missing_ok=True)
        for p in exports.glob('*.part'):
            if p.stat().st_mtime < now - 86400:
                p.unlink(missing_ok=True)

    def janitor():
        while True:
            try:
                cleanup()
            except Exception:
                pass
            time.sleep(60)

    threading.Thread(target=janitor, daemon=True).start()

    def job_row(jobid, sid):
        with core.db() as c:
            row = c.execute('SELECT * FROM exports WHERE id=? AND owner=? AND expires>?', (jobid, sid, int(time.time()))).fetchone()
        if not row:
            raise HTTPException(404, 'ไม่พบงานหรือไฟล์หมดอายุแล้ว')
        return row

    def progress(jobid, **fields):
        with core.db() as c:
            c.execute('UPDATE exports SET ' + ','.join(key + '=?' for key in fields) + ' WHERE id=?', (*fields.values(), jobid))

    def export_format(jobid):
        with core.db() as c:
            row = c.execute('SELECT format FROM export_formats WHERE id=?', (jobid,)).fetchone()
        return row['format'] if row else 'zip'

    def make_zip(jobid, sid, chosen):
        partial = exports / (jobid + '.part')
        written, used = 0, set()
        format = export_format(jobid)
        try:
            if job_row(jobid, sid)['status'] == 'cancelled':
                raise HTTPException(409, 'ยกเลิกการเตรียมไฟล์แล้ว')
            progress(jobid, status='running')
            archive = zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) if format == 'zip' else tarfile.open(partial, 'w')
            with archive:
                for index, f in enumerate(chosen):
                    if job_row(jobid, sid)['status'] == 'cancelled':
                        raise HTTPException(409, 'ยกเลิกการเตรียมไฟล์แล้ว')
                    meta = current_file(sid, f['id'])
                    expected = int(meta.get('size', 0))
                    if expected > MAX_BYTES - written or shutil.disk_usage(exports).free < expected + RESERVE:
                        raise HTTPException(413, 'พื้นที่ไม่พอ กรุณาเลือกดาวน์โหลดให้น้อยลง')
                    received = 0
                    with httpx.Client(timeout=httpx.Timeout(90, connect=20)) as client:
                        with client.stream('GET', 'https://www.googleapis.com/drive/v3/files/' + f['id'],
                            params={'alt': 'media', 'supportsAllDrives': 'true'}, headers=headers(sid)) as r:
                            if r.status_code != 200:
                                raise HTTPException(502, 'ดาวน์โหลดจาก Google ไม่สำเร็จ กรุณาลองใหม่')
                            with archive_member(archive, safe_name(meta['name'], used), expected, format, exports) as dest:
                                for chunk in r.iter_bytes(1024 * 1024):
                                    if written + len(chunk) > MAX_BYTES or shutil.disk_usage(exports).free < len(chunk) + RESERVE:
                                        raise HTTPException(413, 'ชุดไฟล์ใหญ่เกินขนาดหรือพื้นที่ไม่พอ กรุณาแบ่งดาวน์โหลด')
                                    if job_row(jobid, sid)['status'] == 'cancelled':
                                        raise HTTPException(409, 'ยกเลิกการเตรียมไฟล์แล้ว')
                                    # Stop a background download when its authenticated session is gone.
                                    headers(sid)
                                    dest.write(chunk)
                                    received += len(chunk)
                                    written += len(chunk)
                                    progress(jobid, bytes=written)
                    if expected and received != expected:
                        raise HTTPException(502, 'ได้รับไฟล์ไม่ครบ กรุณาสร้าง ZIP ใหม่')
                    progress(jobid, done=index + 1)
            if job_row(jobid, sid)['status'] == 'cancelled':
                raise HTTPException(409, 'ยกเลิกการเตรียมไฟล์แล้ว')
            os.replace(partial, exports / (jobid + '.' + format))
            progress(jobid, status='ready', expires=int(time.time()) + TTL)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            (exports / (jobid + '.' + format)).unlink(missing_ok=True)
            message = exc.detail if isinstance(exc, HTTPException) else 'เตรียม ZIP ไม่สำเร็จ กรุณาลองใหม่'
            with core.db() as c:
                row = c.execute('SELECT status FROM exports WHERE id=?', (jobid,)).fetchone()
            progress(jobid, status='cancelled' if row and row['status'] == 'cancelled' else 'failed', error=message, expires=int(time.time()) + TTL)

    @app.get('/static/{name}')
    def static(name: str):
        if name not in ('gallery.js', 'gallery.css', 'analytics.js'):
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @app.get('/api/library')
    def list_library(request: Request):
        sid = auth(request)['sid']
        data = library(sid)
        return {**data, 'email': '' if core.PUBLIC_ACCESS else core.ALLOWED, 'files': [{k: f[k] for k in ('id', 'name', 'folder', 'size', 'downloadable')} for f in data['files']]}

    @app.post('/api/library/refresh')
    def refresh(request: Request):
        sid = auth(request)['sid']
        origin(request)
        data = library(sid, force=True)
        return {'count': len(data['files'])}

    @app.get('/api/photos/{fid}/thumbnail')
    def thumbnail(fid: str, request: Request):
        with thumb_slots:
            sid = auth(request)['sid']
            f = item(sid, fid)
            if not f:
                raise HTTPException(404)
            cached = thumbs / (core.digest(fid + f.get('modifiedTime', '')) + '.img')
            if cached.exists() and cached.stat().st_mtime > time.time() - 300:
                raw = cached.read_bytes()
                kind = 'image/png' if raw.startswith(b'\x89PNG') else 'image/webp' if raw.startswith(b'RIFF') else 'image/jpeg'
                return Response(raw, media_type=kind)
            url = f.get('thumbnailLink')
            for attempt in range(2):
                host = urlparse(url or '')
                if host.scheme != 'https' or not host.hostname or not host.hostname.endswith('.googleusercontent.com'):
                    raise HTTPException(404, 'ไม่มีภาพย่อ')
                with httpx.Client(timeout=25) as client:
                    with client.stream('GET', url, headers=headers(sid)) as r:
                        if r.status_code == 200 and r.headers.get('content-type', '').split(';')[0] in ('image/jpeg', 'image/png', 'image/webp'):
                            raw = bytearray()
                            for chunk in r.iter_bytes(65536):
                                raw.extend(chunk)
                                if len(raw) > 5 * 1024**2:
                                    raise HTTPException(413)
                            temp = cached.with_suffix('.' + secrets.token_hex(4) + '.tmp')
                            temp.write_bytes(raw)
                            os.replace(temp, cached)
                            return Response(bytes(raw), media_type=r.headers['content-type'])
                url = get_json(sid, 'files/' + fid, {'fields': 'thumbnailLink', 'supportsAllDrives': 'true'}).get('thumbnailLink')
            raise HTTPException(502, 'โหลดภาพย่อไม่ได้')

    @app.get('/api/photos/{fid}/preview')
    def preview(fid: str, request: Request):
        sid = auth(request)['sid']
        return preview_data(sid, fid)

    def preview_data(sid, fid, indexing=False):
        from .faces import prepare_preview
        f = item(sid, fid)
        if not f:
            raise HTTPException(404)
        with preview_slot:
            cached = thumbs / ('preview-' + core.digest(fid + f.get('modifiedTime', '')) + '.img')
            if cached.exists() and cached.stat().st_mtime > time.time() - 300:
                return Response(cached.read_bytes(), media_type='image/jpeg')
            meta = current_file(sid, fid, listed=indexing)
            if int(meta.get('size', 0)) > 30 * 1024**2:
                raise HTTPException(413, 'ต้นฉบับใหญ่เกิน 30 MB สำหรับภาพตัวอย่าง')
            raw = bytearray()
            with httpx.Client(timeout=60) as client:
                with client.stream('GET', 'https://www.googleapis.com/drive/v3/files/' + fid,
                    params={'alt': 'media', 'supportsAllDrives': 'true'}, headers=headers(sid)) as r:
                    if r.status_code != 200:
                        raise HTTPException(502, 'อ่านต้นฉบับจาก Drive ไม่สำเร็จ')
                    for chunk in r.iter_bytes(65536):
                        raw.extend(chunk)
                        if len(raw) > 30 * 1024**2:
                            raise HTTPException(413, 'ต้นฉบับใหญ่เกินขนาดที่รองรับ')
            try:
                result = prepare_preview(raw)
            except Exception:
                raise HTTPException(422, 'ไม่สามารถเตรียมภาพตัวอย่างนี้ได้')
            temp = cached.with_suffix('.' + secrets.token_hex(4) + '.tmp')
            temp.write_bytes(result)
            os.replace(temp, cached)
            return Response(result, media_type='image/jpeg')

    @app.get('/api/photos/{fid}/faces')
    def face_positions(fid: str, request: Request):
        from .faces import detect
        auth(request)
        response = preview(fid, request)
        try:
            return detect(response.body)
        except ValueError:
            raise HTTPException(422, 'ไม่สามารถตรวจภาพนี้ได้')

    @app.post('/api/exports', status_code=202)
    async def create_export(request: Request):
        sid = auth(request)['sid']
        origin(request)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 100000:
                raise HTTPException(413)
        try:
            payload = json.loads(body)
            ids = payload['ids']
            format = payload.get('format', 'zip')
            if format not in ('zip', 'tar'):
                raise HTTPException(400, 'รองรับไฟล์ ZIP หรือ TAR เท่านั้น')
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'รายการรูปไม่ถูกต้อง')
        if not isinstance(ids, list) or not ids or len(ids) > 1000 or not all(isinstance(v, str) for v in ids) or len(ids) != len(set(ids)):
            raise HTTPException(400, 'เลือกอย่างน้อย 1 รูป และไม่เกิน 1,000 รูปต่อชุด')
        # Move Drive I/O off the async event loop.
        from starlette.concurrency import run_in_threadpool
        data = await run_in_threadpool(library, sid)
        files = {f['id']: f for f in data['files']}
        if any(fid not in files or not files[fid]['downloadable'] for fid in ids):
            raise HTTPException(403, 'มีรูปอยู่นอกคลังหรือไม่อนุญาตดาวน์โหลด')
        chosen = [files[fid] for fid in ids]
        total_size = sum(f['size'] for f in chosen)
        if total_size > MAX_BYTES or shutil.disk_usage(exports).free < total_size + RESERVE:
            raise HTTPException(413, 'ชุดรูปใหญ่เกินพื้นที่ที่รองรับ กรุณาแบ่งดาวน์โหลดเป็นชุดเล็ก')
        cleanup()
        jobid, now = secrets.token_hex(16), int(time.time())
        with core.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT id FROM exports WHERE status IN ('queued','running')").fetchone():
                raise HTTPException(409, 'มีงานเตรียม ZIP อยู่ กรุณารอให้เสร็จก่อน')
            c.execute('INSERT INTO exports VALUES (?,?,?,?,?,?,?,?,?)', (jobid, sid, 'queued', len(chosen), 0, 0, '', now, now + 86400))
            c.execute('INSERT INTO export_formats VALUES (?,?)', (jobid, format))
        executor.submit(make_zip, jobid, sid, chosen)
        return {'id': jobid}

    @app.get('/api/exports/{jobid}')
    def export_status(jobid: str, request: Request):
        row = job_row(jobid, auth(request)['sid'])
        return {**{k: row[k] for k in ('id', 'status', 'total', 'done', 'bytes', 'error', 'expires')}, 'format': export_format(jobid)}

    @app.post('/api/exports/{jobid}/cancel')
    def cancel_export(jobid: str, request: Request):
        sid = auth(request)['sid']
        origin(request)
        row = job_row(jobid, sid)
        if row['status'] in ('queued', 'running'):
            progress(jobid, status='cancelled')
        return {'ok': True}

    @app.get('/api/exports/{jobid}/download')
    def download_export(jobid: str, request: Request):
        row = job_row(jobid, auth(request)['sid'])
        format = export_format(jobid)
        if row['status'] != 'ready' or not (exports / (jobid + '.' + format)).exists():
            raise HTTPException(409, 'ไฟล์ยังไม่พร้อมหรือหมดอายุแล้ว')
        return FileResponse(exports / (jobid + '.' + format), media_type='application/zip' if format == 'zip' else 'application/x-tar', filename='findme-' + jobid[:8] + '.' + format)

    from . import matching
    matching.install(app, core, ROOT, auth, origin, library, lambda sid, fid: preview_data(sid, fid, indexing=True))
    return library
