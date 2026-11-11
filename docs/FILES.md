# สรุปไฟล์โปรแกรมทั้งหมด

| ไฟล์ | หน้าที่ |
|---|---|
| `app/main.py` | สร้าง FastAPI, หน้าหลัก, security headers/CSP, session แบบไม่ล็อกอิน, API config สำหรับ Analytics และเส้นทาง OAuth เดิมสำหรับโหมด optional |
| `app/library.py` | อ่าน Drive แบบแบ่งหน้าและโฟลเดอร์ย่อย, cache รายการ/ภาพย่อ, ตรวจสิทธิ์และสมาชิกคลัง, สร้าง ZIP/TAR เบื้องหลัง, จำกัดพื้นที่และอายุไฟล์, แยกเจ้าของงาน |
| `app/matching.py` | งานสร้าง/อัปเดตดัชนี, รายงานความคืบหน้า, รับรูปอ้างอิง, จับคู่และแยกรูปที่ไม่แน่ใจ |
| `app/arcface.py` | ตรวจใบหน้าด้วย SCRFD 10G จัดแนวใบหน้า และสร้างเวกเตอร์ ArcFace บน ONNX Runtime |
| `app/matching_core.py` | ตรวจภาพ/EXIF/ขนาด, ตรวจใบหน้าด้วย YuNet, สร้าง embedding ด้วย dlib, เก็บและค้นหาใน SQLite |
| `app/faces.py` | เตรียม preview ย่อจากต้นฉบับ และระบบตรวจตำแหน่งใบหน้าแบบเดิมในหน้าดูรูป |
| `app/static/gallery.html` | หน้าอัปโหลด อัลบั้ม ผลค้นหา ตัวเลือกดาวน์โหลด และหน้าดูภาพใหญ่ |
| `app/static/gallery.js` | เรียก API, อัปโหลด, แบ่งหน้า, เลือกรูปข้ามหน้า, polling งานดัชนี/ดาวน์โหลด, แสดงกรอบใบหน้า |
| `app/static/gallery.css` | รูปแบบหน้าจอ/มือถือ แกลเลอรี และแถบระยะห่างไล่สี |
| `app/static/analytics.js` | อ่าน Analytics ID จาก `/api/config`; โหลด Google tag เฉพาะเมื่อตั้งค่าไว้ |
| `app/models/README.md` | ที่มาและ checksum ของโมเดล YuNet |
| `app/models/YUNET-LICENSE` | ใบอนุญาต MIT ของโมเดล |
| `tests/test_faces.py` | ทดสอบการอ่าน/ย่อภาพ ตัวตรวจภาพว่าง และภาพเสีย |
| `tests/test_library.py` | ทดสอบสิทธิ์, public session, ZIP/TAR, พื้นที่, ป้องกัน path traversal, การแบ่งกลุ่มผลจับคู่, config/default |
| `tests/test_oauth.py` | ทดสอบ OAuth เดิม เช่น PKCE, state, cookie binding, replay, allowed account และ logout |
| `scripts/setup_secrets.py` | สร้าง session key ใหม่ในเครื่องและตั้งสิทธิ์ไฟล์ โดยไม่พิมพ์กุญแจและไม่ทับของเดิม |
| `scripts/download_model.py` | ดาวน์โหลด YuNet จาก upstream และตรวจ SHA-256 ก่อนใช้ |
| `scripts/check_secrets.py` | ตรวจไฟล์เตรียม publish เพื่อหารูปแบบ credential และไฟล์ runtime ที่ไม่ควรขึ้น GitHub |
| `Dockerfile` | สร้าง Python 3.12 image พร้อม compiler/dlib, dependencies และโมเดลที่ตรวจ checksum แล้ว |
| `compose.yaml` | รันแอปแบบ non-root, read-only filesystem, volume สำหรับข้อมูล, localhost port และ healthcheck |
| `compose.https.yaml` | เพิ่ม Caddy HTTPS สำหรับเซิร์ฟเวอร์ใหม่ |
| `compose.existing-proxy.yaml` | เชื่อมแอปเข้ากับ Docker network ของ reverse proxy ที่มีอยู่แล้ว |
| `Caddyfile` | reverse proxy จากโดเมน config ไปยังแอป |
| `.env.example` | ค่า config ตัวอย่าง ไม่มี credential จริง |
| `.gitignore` | กัน config จริง กุญแจ รูป ฐานข้อมูล backup และ runtime ออกจาก Git |
| `.dockerignore` | กันความลับและไฟล์ที่ไม่จำเป็นออกจาก Docker build context |
| `requirements.txt` | dependencies หลักที่ใช้กับแอป |
| `requirements-drive.txt` | Google Auth และ HTTP client ของ Service Account |
| `requirements-arcface.txt` | ONNX Runtime สำหรับ SCRFD 10G + ArcFace |
| `requirements-dev.txt` | dependencies สำหรับทดสอบ |
| `.github/workflows/test.yml` | GitHub Actions สำหรับติดตั้ง ดาวน์โหลดโมเดล ตรวจ secret patterns และทดสอบ |
| `README.md` | ภาพรวม ฟังก์ชัน และทางเข้าคู่มือ |
| `docs/ARCFACE.md` | ตั้งค่าไฟล์โมเดล สร้างดัชนี และสลับกลับไปใช้ YuNet/dlib |
| `docs/INSTALL.md` | ติดตั้ง ตั้งค่า DNS/HTTPS/Drive อัปเดต สำรองและแก้ปัญหา |
| `docs/GITHUB.md` | clone, branch, review, commit, push โดยไม่ส่ง secrets |
| `docs/SECRETS.md` | แยกไฟล์ลับและไฟล์ที่อนุญาตให้อยู่ใน repo |
| `LICENSE` | ใบอนุญาตเดิมของ repository |

## เส้นทางข้อมูล

1. เซิร์ฟเวอร์อ่านโฟลเดอร์ Drive ด้วย Service Account และสร้างรายการไฟล์
2. งาน index ดาวน์โหลดภาพเพื่อย่อและตรวจใบหน้า แล้วเก็บ embedding/metadata ใน SQLite ตามโฟลเดอร์
3. ผู้ใช้ส่งรูปอ้างอิง 1 ใบหน้า แอปสร้าง embedding แล้วเทียบระยะห่างกับดัชนี
4. ส่งผลรูปผ่านเกณฑ์ก่อน และรูปไม่แน่ใจท้ายสุดตามเงื่อนไข
5. รูปที่เลือกถูกดาวน์โหลดต้นฉบับจาก Drive มารวมเป็น ZIP/TAR บนเซิร์ฟเวอร์ และลบเมื่อหมดอายุ

## API หลัก

| Method | Path | ใช้ทำอะไร |
|---|---|---|
| GET | `/` | หน้าเว็บ |
| GET | `/healthz` | healthcheck |
| GET | `/api/config` | config สาธารณะของ Analytics เท่านั้น |
| GET | `/api/library` | รายการรูป |
| POST | `/api/library/refresh` | อัปเดตรายการรูป |
| GET/POST | `/api/faces/index` | ดูสถานะ/เริ่มสร้างดัชนี |
| POST | `/api/faces/search` | ส่ง body เป็น bytes ของรูปอ้างอิง และระบุ `?threshold=0.50` ได้ |
| GET | `/api/photos/{id}/thumbnail` | ภาพย่อ |
| GET | `/api/photos/{id}/preview` | ภาพตัวอย่างย่อจากต้นฉบับ |
| GET | `/api/photos/{id}/faces` | ตำแหน่งใบหน้าใน preview |
| POST | `/api/exports` | สร้างงาน `{"ids":["file-id"],"format":"zip"}` หรือ `tar` |
| GET | `/api/exports/{job}` | สถานะงาน |
| POST | `/api/exports/{job}/cancel` | ยกเลิก |
| GET | `/api/exports/{job}/download` | ดาวน์โหลดไฟล์ของ session เจ้าของงาน |

คำขอ POST ต้องมี `Origin` ตรงกับ `APP_BASE_URL` และการติดตามงานต้องเก็บ cookie ของ browser/client เดิม
