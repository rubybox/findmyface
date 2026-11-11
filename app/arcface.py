"""CPU inference for the SCRFD-10G and ArcFace ResNet50 ONNX exports."""
import hashlib
from pathlib import Path

import cv2
import numpy as np

from .matching_core import read_rgb

# The five landmarks are ordered as in the SCRFD output (image-left first).
_ARCFACE_TEMPLATE = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041],
], dtype=np.float64)
_MODEL_HASHES = {
    'det_10g.onnx': '5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91',
    'w600k_r50.onnx': '4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43',
}


def align_face(bgr, landmarks):
    """Fit a similarity transform using all five landmarks."""
    source_mean = landmarks.mean(axis=0)
    target_mean = _ARCFACE_TEMPLATE.mean(axis=0)
    source = landmarks - source_mean
    target = _ARCFACE_TEMPLATE - target_mean
    variance = np.square(source).sum()
    if not np.isfinite(variance) or variance < 1e-6:
        return None
    u, singular_values, vt = np.linalg.svd(target.T @ source)
    signs = np.ones(2)
    if np.linalg.det(u @ vt) < 0:
        signs[-1] = -1
    rotation = (u * signs) @ vt
    scale = (singular_values @ signs) / variance
    transform = np.column_stack((rotation * scale, target_mean - scale * rotation @ source_mean))
    return cv2.warpAffine(bgr, transform, (112, 112))


class ArcFaceEngine:
    metric = 'cosine'

    def __init__(self, model_dir, threads=1):
        import onnxruntime as ort

        ort.disable_telemetry_events()
        if not 1 <= threads <= 4:
            raise ValueError('FACE_CPU_THREADS must be between 1 and 4')
        self.size = 640
        # A new input size or preprocessing revision needs its own index.
        self.model_id = 'scrfd10g-640-arcface-w600k-r50-v1'
        paths = {}
        for name, expected in _MODEL_HASHES.items():
            path = Path(model_dir) / name
            if not path.is_file():
                raise FileNotFoundError(f'Missing ArcFace model: {path}')
            with path.open('rb') as model:
                if hashlib.file_digest(model, 'sha256').hexdigest() != expected:
                    raise ValueError(f'Unexpected model checksum: {name}')
            paths[name] = path

        options = ort.SessionOptions()
        options.enable_cpu_mem_arena = False
        options.intra_op_num_threads = threads
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        self.detector = ort.InferenceSession(str(paths['det_10g.onnx']), options,
                                             providers=['CPUExecutionProvider'])
        self.recognizer = ort.InferenceSession(str(paths['w600k_r50.onnx']), options,
                                               providers=['CPUExecutionProvider'])
        self.anchors = []
        for stride in (8, 16, 32):
            axis = np.arange(self.size // stride, dtype=np.float32) * stride
            x, y = np.meshgrid(axis, axis)
            self.anchors.append(np.repeat(np.column_stack((x.ravel(), y.ravel())), 2, axis=0))

    def detect(self, bgr):
        height, width = bgr.shape[:2]
        factor = self.size / max(height, width)
        new_width = max(1, round(width * factor))
        new_height = max(1, round(height * factor))
        canvas = np.zeros((self.size, self.size, 3), dtype=np.uint8)
        canvas[:new_height, :new_width] = cv2.resize(bgr, (new_width, new_height))
        blob = cv2.dnn.blobFromImage(canvas, 1 / 128, mean=(127.5,) * 3, swapRB=True)
        scores, boxes, points = [], [], []
        outputs = self.detector.run(None, {self.detector.get_inputs()[0].name: blob})
        for i, (stride, anchors) in enumerate(zip((8, 16, 32), self.anchors)):
            confidence = outputs[i].reshape(-1)
            selected = np.flatnonzero(confidence >= 0.5)
            center = anchors[selected]
            offsets = outputs[i + 3].reshape(-1, 4)[selected] * stride
            box = np.column_stack((center - offsets[:, :2], center + offsets[:, 2:]))
            keypoints = outputs[i + 6].reshape(-1, 5, 2)[selected] * stride + center[:, None, :]
            scale = np.array([width / new_width, height / new_height])
            box = (box.reshape(-1, 2, 2) * scale).reshape(-1, 4)
            box[:, ::2] = np.clip(box[:, ::2], 0, width)
            box[:, 1::2] = np.clip(box[:, 1::2], 0, height)
            valid = np.all(box[:, 2:] - box[:, :2] >= 24, axis=1)
            boxes.extend(box[valid])
            points.extend(keypoints[valid] * scale)
            scores.extend(confidence[selected][valid])
        if not boxes:
            return []
        # OpenCV NMS expects x, y, width, height rather than corner coordinates.
        rectangles = [[l, t, r - l, b - t] for l, t, r, b in boxes]
        indices = cv2.dnn.NMSBoxes(rectangles, [float(s) for s in scores], 0.49, 0.4)
        return [(boxes[i], points[i]) for i in np.asarray(indices).reshape(-1)]

    def extract(self, data):
        pixels, width, height = read_rgb(data)
        bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        sx, sy = width / bgr.shape[1], height / bgr.shape[0]
        faces = []
        for (left, top, right, bottom), landmarks in self.detect(bgr):
            aligned = align_face(bgr, landmarks)
            if aligned is None:
                continue
            blob = cv2.dnn.blobFromImage(aligned, 1 / 127.5, mean=(127.5,) * 3, swapRB=True)
            vector = self.recognizer.run(None, {self.recognizer.get_inputs()[0].name: blob})[0].reshape(-1)
            norm = np.linalg.norm(vector)
            if not np.isfinite(norm) or norm == 0 or vector.size != 512:
                raise ValueError('Invalid ArcFace embedding')
            box = {'top': round(top * sy), 'right': round(right * sx),
                   'bottom': round(bottom * sy), 'left': round(left * sx)}
            faces.append((box, vector / norm))
        return faces
