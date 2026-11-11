# ตั้งค่า SCRFD 10G + ArcFace บน CPU

โหมด `arcface` ใช้ SCRFD 10G ที่อินพุต 640 × 640 ตรวจกรอบและจุดใบหน้า 5 จุด แล้วใช้ ArcFace ResNet50 (`w600k_r50`) สร้างเวกเตอร์ 512 ค่า ทั้งตอนทำดัชนีและตอนอ่านรูปอ้างอิงใช้โมเดลและการจัดแนวชุดเดียวกัน

## เตรียมโมเดล

ใช้ไฟล์ ONNX ที่มีสิทธิ์สำหรับงานที่จะรัน ระบบรองรับไฟล์สองตัวจากชุด `buffalo_l` และตรวจ SHA-256 ตอนเริ่มแอป

- `secrets/arcface-models/det_10g.onnx`
- `secrets/arcface-models/w600k_r50.onnx`

ไฟล์จาก Model Zoo ของ InsightFace มีข้อกำหนดสำหรับงานวิจัยที่ไม่ใช่เชิงพาณิชย์ ตรวจสิทธิ์ก่อนนำไปเปิดบริการจริง ไฟล์โมเดลเก็บอยู่บนเครื่องที่รันระบบ [InsightFace Model Zoo](https://github.com/deepinsight/insightface/blob/master/model_zoo/README.md)

บน Linux ที่ใช้ Docker ให้ UID/GID 10001 อ่านไฟล์และเข้าโฟลเดอร์ดังกล่าวได้ เช่น ตั้งโฟลเดอร์เป็น root:10001 mode 750 และไฟล์เป็น root:10001 mode 640

## เปิดใช้งาน

ตั้งค่าใน `.env` ของเซิร์ฟเวอร์

```dotenv
FACE_BACKEND=arcface
FACE_CPU_THREADS=1
AUTO_INDEX=false
```

Compose จะติดตั้ง ONNX Runtime จาก `requirements-arcface.txt` ระหว่าง build ใช้ชุด Compose ให้ตรงกับการติดตั้งของคุณ ตัวอย่างนี้ใช้กับเครื่องที่มี reverse proxy อยู่แล้ว

```sh
docker compose -f compose.yaml -f compose.existing-proxy.yaml up -d --build app
```

เปิดหน้าเว็บแล้วกด **อ่านคลังรูปจาก Drive** หนึ่งครั้ง รอให้สร้างดัชนีเสร็จก่อนทดสอบค้นหาทั้งคลัง หลังจากนั้นแอปจะอ่านดัชนีที่เก็บใน volume เดิมและประมวลผลเฉพาะรูปอ้างอิงใหม่ ดัชนี ArcFace อยู่ใน SQLite คนละไฟล์กับ dlib

โหมดนี้แสดง **cosine distance = 1 − cosine similarity** ค่ายิ่งต่ำยิ่งคล้าย ค่าเริ่มต้น **0.50** ปรับได้บนแถบความเข้มงวด ด้านค่าต่ำมีไอคอนรูปภาพ 1 รูป และด้านค่าสูงมี 4 รูป

ดูค่า `backend`, `metric` และช่วงเกณฑ์ได้จาก `GET /api/faces/index` หากจะกลับไปใช้ YuNet/dlib ให้ตั้ง `FACE_BACKEND=dlib` และสร้าง container ใหม่ ดัชนีเดิมจะใช้ต่อได้เมื่อเก็บ volume เดิมไว้
