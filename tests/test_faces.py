import unittest
from unittest.mock import patch
import cv2
import numpy as np
from app import faces

class FaceDetectionTests(unittest.TestCase):
    def test_blank_and_invalid(self):
        ok, raw=cv2.imencode('.jpg',np.zeros((180,240,3),dtype=np.uint8))
        self.assertTrue(ok)
        self.assertEqual(faces.detect(raw.tobytes()),{'width':240,'height':180,'count':0,'boxes':[]})
        with self.assertRaises(ValueError): faces.detect(b'not an image')
    def test_preview_resizes_without_upscaling(self):
        import io
        from PIL import Image
        buf=io.BytesIO();Image.new('RGB',(2400,1600)).save(buf,'JPEG')
        preview=faces.prepare_preview(buf.getvalue())
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.size,(1600,1067))
        buf=io.BytesIO();Image.new('RGB',(300,200)).save(buf,'JPEG')
        with Image.open(io.BytesIO(faces.prepare_preview(buf.getvalue()))) as image:
            self.assertEqual(image.size,(300,200))
    def test_positions_only(self):
        class Model:
            def detectMultiScale(self,*a,**kw): return [(15,20,30,40)]
        _,raw=cv2.imencode('.jpg',np.zeros((180,240,3),dtype=np.uint8))
        with patch.object(faces,'_model',Model()): result=faces.detect(raw.tobytes())
        self.assertEqual(result['boxes'],[{'x':15,'y':20,'width':30,'height':40}])
        self.assertEqual(set(result),{'width','height','count','boxes'})
if __name__=='__main__':unittest.main()

class MatchingDetectorTests(unittest.TestCase):
    def test_yunet_blank_image(self):
        import io
        from PIL import Image
        from app.matching_core import FaceEngine
        buffer=io.BytesIO();Image.new('RGB',(320,240),'white').save(buffer,'JPEG')
        self.assertEqual(FaceEngine().extract(buffer.getvalue()),[])
    def test_invalid_reference_image(self):
        from app.matching_core import FaceEngine
        with self.assertRaises(ValueError):FaceEngine().extract(b'invalid-image')
