# FindMyFace

ค้นหารูปใน Google Drive ด้วยรูปใบหน้าอ้างอิง แล้วเลือกรูปเพื่อดาวน์โหลดต้นฉบับเป็น ZIP หรือ TAR

## ทำอะไรได้บ้าง

- เปิดใช้งานได้โดยไม่ต้องล็อกอิน เมื่อ `PUBLIC_ACCESS=true`
- อ่านคลังภาพและโฟลเดอร์ย่อยผ่าน Service Account แบบอ่านอย่างเดียว
- ใช้ YuNet ตรวจใบหน้า และ dlib สร้างค่าลักษณะใบหน้า เก็บดัชนีใน SQLite
- รับรูปอ้างอิงที่มีใบหน้าเดียว แสดงผลรูปที่ผ่านเกณฑ์เรียงตามระยะห่าง เริ่มต้นที่ **0.46**
- แถบระยะห่างไล่สีค่าน้อยเข้ม → ค่ามากอ่อน
- รูปผ่านเกณฑ์แสดงหน้าละ 20 รูป ถ้ามีมากกว่า 20 รูป จะรวมรูปที่ไม่แน่ใจไว้หน้าสุดท้าย
- เลือกรูปข้ามหน้า ดาวน์โหลด ZIP/TAR มีสถานะและยกเลิกงานได้
- ตั้งค่า Google Analytics ผ่าน `.env` ได้ หรือเว้นว่างเพื่อปิด

รูปที่ไม่แน่ใจใช้ช่วงระยะห่าง `(threshold, threshold + 0.10]` ระยะห่างไม่ใช่เปอร์เซ็นต์ความมั่นใจ ควรตรวจผลด้วยสายตา โดยเฉพาะใบหน้าเล็ก หมวก แว่น และใบหน้าที่ถูกบัง

## เอกสาร

- [สรุปไฟล์และการทำงานทั้งหมด](docs/FILES.md)
- [ติดตั้งบน Linux/Hetzner ด้วย Docker และ HTTPS](docs/INSTALL.md)
- [ตั้งค่า GitHub และอัปเดตโค้ด](docs/GITHUB.md)
- [ไฟล์ที่เป็นความลับและการสำรองข้อมูล](docs/SECRETS.md)
- [ตัวอย่าง config ที่ไม่มีรหัสจริง](.env.example)

## เริ่มติดตั้ง

เตรียม Linux server, Docker Engine พร้อม Compose plugin, โดเมนที่ชี้มายังเซิร์ฟเวอร์ และ Service Account ที่มีสิทธิ์ Viewer ในโฟลเดอร์ภาพ

```bash
git clone https://github.com/rubybox/findmyface.git
cd findmyface
cp .env.example .env
```

แก้ `.env` เป็นโดเมนและรหัสโฟลเดอร์ของคุณ จากนั้นสร้างกุญแจและติดตั้ง Service Account บนเซิร์ฟเวอร์:

```bash
sudo python3 scripts/setup_secrets.py
sudo install -o root -g 10001 -m 640 /path/to/private-service-account.json secrets/service-account.json
```

ถ้าเป็นเซิร์ฟเวอร์ใหม่ที่ยังไม่มี reverse proxy:

```bash
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d --build
```

ถ้ามี Caddy อยู่แล้ว ให้ใช้วิธีใน [INSTALL.md](docs/INSTALL.md) แทน เพื่อไม่เปิดบริการใหม่ทับพอร์ต 80/443

เปิดเว็บไซต์ผ่าน HTTPS ดูความคืบหน้าดัชนี แล้วเลือกรูปอ้างอิงเพื่อค้นหา ปุ่ม **อ่านคลังรูปจาก Drive** ใช้อัปเดตเมื่อมีรูปเพิ่ม

## ความลับไม่อยู่ใน repo

ชุดนี้ไม่มี API key, Service Account JSON, private key, OAuth client secret, session key, `.env` จริง, รูปผู้ใช้, ฐานข้อมูลใบหน้า หรือ backup

ค่าโดเมน โฟลเดอร์ อีเมล และ Analytics ID ของระบบต้นทางถูกนำออกจาก source และเปลี่ยนเป็น config ตัวอย่าง

```bash
python3 scripts/check_secrets.py
```

ตัวตรวจเป็นการตรวจรูปแบบที่พบบ่อย ควรตรวจ `git diff --cached` ก่อน commit ด้วย ห้ามส่งไฟล์ทั้งโฟลเดอร์เซิร์ฟเวอร์ขึ้น GitHub

## ทดสอบ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/download_model.py
python scripts/check_secrets.py
python -m pytest -q
```

dlib ต้องมี CMake และ compiler; Ubuntu ใช้ `sudo apt-get install build-essential cmake python3-dev` ชุดทดสอบสร้างกุญแจและข้อมูลจำลองในพื้นที่ชั่วคราว ไม่ต้องใช้ Service Account จริง

โมเดล YuNet ดาวน์โหลดจาก OpenCV Zoo และตรวจ SHA-256 ระหว่าง build; repo เก็บที่มาและใบอนุญาตของโมเดลไว้ใน `app/models/`

## ข้อจำกัดของรุ่นนี้

ใช้ 1 worker/1 instance และ SQLite เหมาะกับการเริ่มต้นขนาดเล็ก ตั้ง memory limit ของแอปไว้ 1200 MB และแนะนำเซิร์ฟเวอร์ประมาณ 4 GB เมื่อใช้ร่วมกับบริการอื่น งานสร้างดัชนีและดาวน์โหลดเป็นงานเบื้องหลังในโปรเซส รีสตาร์ตอาจต้องเริ่มงานดาวน์โหลดใหม่ ส่วนดัชนีที่บันทึกแล้วอยู่ใน volume

ดาวน์โหลดได้ไม่เกิน 1,000 รูป/8 GB ต่อชุด ไฟล์รวมมีอายุ 1 ชั่วโมง และแยกเจ้าของงานด้วย cookie ชั่วคราว ในโหมด public ทุกคนที่เปิดเว็บไซต์สามารถค้นหาและเลือกรูปจากคลังที่ตั้งไว้ได้

## License

คงไฟล์ [LICENSE](LICENSE) ที่เจ้าของ repository กำหนดไว้ โมเดล YuNet มีใบอนุญาต MIT แยกตาม [YUNET-LICENSE](app/models/YUNET-LICENSE)
