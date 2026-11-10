"""Face positions only: no identity descriptors or matching."""
import threading
import cv2
import numpy as np

cv2.setNumThreads(1)
_lock = threading.Lock()
_model = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
if _model.empty():
    raise RuntimeError('Face detector unavailable')


def detect(raw):
    # Google-generated previews are bounded by the thumbnail endpoint.
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Invalid image')
    h, w = image.shape[:2]
    if w * h > 16000000:
        raise ValueError('Image too large')
    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    with _lock:
        rects = _model.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20))
    boxes = [{'x': int(x), 'y': int(y), 'width': int(a), 'height': int(b)} for x, y, a, b in rects]
    boxes.sort(key=lambda b: (b['y'], b['x']))
    return {'width': w, 'height': h, 'count': len(boxes), 'boxes': boxes}


def prepare_preview(raw):
    import io
    import warnings
    from PIL import Image, ImageOps
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 64000000:
                raise ValueError('Image too large')
            image = ImageOps.exif_transpose(source)
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image = image.convert('RGB')
            out = io.BytesIO()
            image.save(out, 'JPEG', quality=92)
            return out.getvalue()
