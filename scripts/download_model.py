"""Fetch the upstream MIT-licensed YuNet model and verify its exact checksum."""
import hashlib
import urllib.request
from pathlib import Path

URL = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
SHA256 = '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
DEST = Path(__file__).resolve().parents[1] / 'app/models/face_detection_yunet_2023mar.onnx'

def main():
    if DEST.exists() and hashlib.sha256(DEST.read_bytes()).hexdigest() == SHA256:
        print('YuNet model checksum verified.')
        return
    with urllib.request.urlopen(URL, timeout=90) as response:
        data = response.read(1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError('Model checksum mismatch; refusing to install it.')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEST.with_suffix('.download')
    temporary.write_bytes(data)
    temporary.replace(DEST)
    print('YuNet model downloaded and checksum verified.')

if __name__ == '__main__':
    main()
