import io
import json
import sqlite3
import warnings
from pathlib import Path
from contextlib import contextmanager

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


class FaceEngine:
    # Change this ID when changing models or preprocessing; old vectors must be rebuilt.
    model_id = 'yunet2023-score085-dlib-resnet-v2'

    def extract(self, data: bytes):
        import face_recognition
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as raw:
                    if raw.width * raw.height > 64_000_000:
                        raise ValueError('Image exceeds 64 megapixels')
                    image = ImageOps.exif_transpose(raw).convert('RGB')
                    width, height = image.size
                    image.thumbnail((1600, 1600))
                    pixels = np.array(image)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as exc:
            raise ValueError('Invalid or oversized image') from exc
        import cv2
        detector = getattr(self, '_detector', None)
        if detector is None:
            detector = cv2.FaceDetectorYN.create(
                str(Path(__file__).parent / 'models/face_detection_yunet_2023mar.onnx'),
                '', (pixels.shape[1], pixels.shape[0]), 0.85, 0.3, 5000)
            self._detector = detector
        detector.setInputSize((pixels.shape[1], pixels.shape[0]))
        _, detections = detector.detect(cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
        locations = []
        for detection in detections if detections is not None else []:
            x, y, w, h = detection[:4]
            if min(w, h) < 24:
                continue
            top, left = max(0, int(y)), max(0, int(x))
            bottom, right = min(pixels.shape[0], int(y+h)), min(pixels.shape[1], int(x+w))
            if bottom > top and right > left:
                locations.append((top, right, bottom, left))
        vectors = face_recognition.face_encodings(pixels, locations)
        sx, sy = width / image.width, height / image.height
        return [({'top': round(t * sy), 'right': round(r * sx),
                  'bottom': round(b * sy), 'left': round(l * sx)}, vector)
                for (t, r, b, l), vector in zip(locations, vectors)]


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY, modified TEXT NOT NULL,
                    name TEXT NOT NULL, url TEXT NOT NULL, model TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS faces (
                    photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
                    box TEXT NOT NULL, vector BLOB NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def unchanged(self, photo, model):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM photos WHERE id=? AND modified=? AND model=?',
                              (photo['id'], photo['modifiedTime'], model)).fetchone() is not None

    def replace(self, photo, faces, model):
        with self.connect() as db:
            db.execute('DELETE FROM photos WHERE id=?', (photo['id'],))
            db.execute('INSERT INTO photos VALUES (?,?,?,?,?)',
                       (photo['id'], photo['modifiedTime'], photo['name'],
                        photo.get('webViewLink', ''), model))
            db.executemany('INSERT INTO faces VALUES (?,?,?)',
                           [(photo['id'], json.dumps(box), np.asarray(vec, dtype='<f8').tobytes())
                            for box, vec in faces])

    def remove(self, photo_id):
        with self.connect() as db:
            db.execute('DELETE FROM photos WHERE id=?', (photo_id,))

    def prune(self, seen):
        with self.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM photos')]
            db.executemany('DELETE FROM photos WHERE id=?', [(i,) for i in ids if i not in seen])

    def get_photo(self, photo_id):
        with self.connect() as db:
            row = db.execute('SELECT id,name FROM photos WHERE id=?', (photo_id,)).fetchone()
            return dict(row) if row else None

    def stats(self):
        with self.connect() as db:
            return {'photos': db.execute('SELECT count(*) FROM photos').fetchone()[0],
                    'faces': db.execute('SELECT count(*) FROM faces').fetchone()[0]}

    def search(self, reference, threshold, limit, model):
        matches = {}
        with self.connect() as db:
            rows = db.execute('''SELECT p.id,p.name,p.url,f.box,f.vector FROM faces f
                                 JOIN photos p ON p.id=f.photo_id WHERE p.model=?''', (model,))
            for row in rows:
                distance = float(np.linalg.norm(np.frombuffer(row['vector'], dtype='<f8') - reference))
                if distance <= threshold:
                    result = matches.setdefault(row['id'], {
                        'file_id': row['id'], 'name': row['name'], 'drive_url': row['url'],
                        'distance': distance, 'faces': []})
                    result['distance'] = min(result['distance'], distance)
                    result['faces'].append({'box': json.loads(row['box']), 'distance': distance})
        results = sorted(matches.values(), key=lambda item: item['distance'])
        return results if limit is None else results[:limit]
