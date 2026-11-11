"""Persistent face index for the configured Drive library."""
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException, Request
from .matching_core import Store, FaceEngine

MAX_IMAGE = 30 * 1024**2


def install(app, core, root, auth, origin, library, preview):
    backend = os.getenv('FACE_BACKEND', 'dlib')
    if backend == 'arcface':
        from .arcface import ArcFaceEngine
        engine = ArcFaceEngine(os.getenv('ARCFACE_MODEL_DIR', '/run/secrets/arcface-models'),
                               int(os.getenv('FACE_CPU_THREADS', '1')))
        filename = f'faces-{engine.model_id}-{root}.sqlite3'
        threshold_min, threshold_max, default_threshold = 0.05, 1.0, 0.50
    elif backend == 'dlib':
        engine = FaceEngine()
        filename = f'faces-yunet-{root}.sqlite3'
        threshold_min, threshold_max, default_threshold = 0.30, 0.65, 0.46
    else:
        raise ValueError('FACE_BACKEND must be dlib or arcface')
    metric = getattr(engine, 'metric', 'euclidean')
    threshold_config = {'min': threshold_min, 'max': threshold_max, 'default': default_threshold}
    store = Store(core.DATA / filename)
    inference = threading.Lock()
    state_lock = threading.Lock()
    worker = ThreadPoolExecutor(max_workers=1)
    state = {'status': 'idle', 'processed': 0, 'skipped': 0, 'failed': 0, 'total': 0}

    def extract(raw):
        with inference:
            return engine.extract(raw)

    def run(sid):
        seen = set()
        try:
            data = library(sid, force=True)
            with state_lock:
                state['total'] = len(data['files'])
            for f in data['files']:
                seen.add(f['id'])
                meta = {'id': f['id'], 'name': f['name'], 'modifiedTime': f.get('modifiedTime', ''),
                        'webViewLink': 'https://drive.google.com/file/d/' + f['id'] + '/view'}
                if store.unchanged(meta, engine.model_id):
                    with state_lock:
                        state['skipped'] += 1
                    continue
                try:
                    response = preview(sid, f['id'])
                    faces = extract(response.body)
                    store.replace(meta, faces, engine.model_id)
                    with state_lock:
                        state['processed'] += 1
                except Exception:
                    if state['failed'] < 3:
                        import logging
                        logging.getLogger(__name__).exception('Could not index Drive photo')
                    store.remove(f['id'])
                    with state_lock:
                        state['failed'] += 1
            store.prune(seen)
            with state_lock:
                state['status'] = 'completed_with_errors' if state['failed'] else 'completed'
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Face indexing failed')
            with state_lock:
                state['status'] = 'failed'
        finally:
            with state_lock:
                state['finished_at'] = int(time.time())

    @app.get('/api/faces/index')
    def index_status(request: Request):
        auth(request)
        with state_lock:
            snapshot = dict(state)
        return {**snapshot, **store.stats(), 'backend': backend, 'metric': metric,
                'threshold_config': threshold_config}

    @app.post('/api/faces/index', status_code=202)
    def start_index(request: Request):
        current = auth(request)
        origin(request)
        with state_lock:
            if state['status'] == 'running':
                raise HTTPException(409, 'กำลังอ่านคลังรูปอยู่ กรุณารอสักครู่')
            state.update(status='running', processed=0, skipped=0, failed=0, total=0)
            worker.submit(run, current['sid'])
        return {'status': 'running'}

    @app.post('/api/faces/search')
    async def search(request: Request):
        current = auth(request)
        origin(request)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 15 * 1024**2:
                raise HTTPException(413, 'รูปอ้างอิงต้องไม่เกิน 15 MB')
        from starlette.concurrency import run_in_threadpool
        try:
            threshold = float(request.query_params.get('threshold', str(default_threshold)))
            if not threshold_min <= threshold <= threshold_max:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'เกณฑ์จับคู่ไม่ถูกต้อง')
        try:
            faces = await run_in_threadpool(extract, bytes(raw))
        except ValueError:
            raise HTTPException(422, 'ไม่สามารถอ่านรูปอ้างอิงนี้ได้')
        if len(faces) != 1:
            raise HTTPException(422, 'กรุณาใช้รูปอ้างอิงที่เห็นใบหน้าชัดเจนเพียง 1 คน')
        # Recheck membership against the current configured library before returning matches.
        data = await run_in_threadpool(library, current['sid'])
        allowed = {f['id'] for f in data['files']}
        candidates = await run_in_threadpool(store.search, faces[0][1], threshold + .1, None, engine.model_id, metric)
        candidates = [r for r in candidates if r['file_id'] in allowed]
        matches = [r for r in candidates if r['distance'] <= threshold]
        reviews = [r for r in candidates if r['distance'] > threshold]
        return {'backend': backend, 'metric': metric, 'matches': matches, 'review': reviews if len(matches) > 20 else [],
                'threshold': threshold, 'review_threshold': threshold + .1,
                'review_total': len(reviews) if len(matches) > 20 else 0}

    if os.getenv('AUTO_INDEX', '').lower() == 'true' and os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        # Run once on each process start; unchanged files are skipped using the persistent index.
        state['status'] = 'running'
        worker.submit(run, None)

    return store
