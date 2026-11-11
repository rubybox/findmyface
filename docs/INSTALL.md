# วิธีติดตั้งบน Linux / Hetzner

## 1. เตรียมเครื่อง

ใช้ Docker Engine พร้อม Compose plugin, Git และ Python 3 สำหรับสร้างกุญแจ แนะนำ RAM ประมาณ 4 GB สำหรับเริ่มต้น แอปจำกัด memory ไว้ 1200 MB และใช้ 1 worker

ตั้ง DNS ของโดเมนให้ชี้ไปเซิร์ฟเวอร์ เปิด inbound TCP 80/443 สำหรับ HTTPS และ SSH ตามวิธีดูแลเครื่องของคุณ ห้ามเปิด port 8000 สู่สาธารณะโดยตรง

## 2. ดาวน์โหลด source และสร้าง config

```bash
git clone https://github.com/rubybox/findmyface.git
cd findmyface
cp .env.example .env
chmod 600 .env
```

แก้ `.env`:

| ตัวแปร | ค่าที่ต้องใส่ |
|---|---|
| `APP_BASE_URL` | URL จริง เช่น `https://photos.example.com` ไม่มี path ท้าย URL |
| `APP_DOMAIN` | โดเมนอย่างเดียว เช่น `photos.example.com` |
| `DRIVE_FOLDER_ID` | เฉพาะรหัสท้าย URL `/folders/…` ไม่ใส่ URL ทั้งอัน |
| `PUBLIC_ACCESS` | `true` เพื่อใช้งานทันทีโดยไม่ล็อกอิน |
| `FACE_BACKEND` | `arcface` สำหรับ SCRFD 10G + ArcFace ตาม [คู่มือ ArcFace](ARCFACE.md) หรือ `dlib` สำหรับ YuNet/dlib |
| `FACE_CPU_THREADS` | จำนวน CPU threads สำหรับ ArcFace ค่าเริ่มต้น 1 |
| `AUTO_INDEX` | `true` เพื่ออ่านคลังตอนเริ่มแอป หรือ `false` เพื่อกดอ่านคลังเองและใช้ดัชนีที่เก็บไว้เมื่อรีสตาร์ต |
| `GA_MEASUREMENT_ID` | Measurement ID ของคุณ หรือเว้นว่างเพื่อไม่ติด Analytics |
| `APP_PORT` | localhost port ของแอป ปกติ 8000 |
| `EXTERNAL_PROXY_NETWORK` | ใช้เฉพาะเครื่องที่มี Docker reverse proxy อยู่แล้ว |

`.env` ถูกใช้เติมค่าลง Compose และไม่ต้องอัปขึ้น GitHub

## 3. เชื่อม Google Drive

1. เปิด Google Drive API ใน Google Cloud project ของคุณ
2. สร้าง Service Account และดาวน์โหลด key เป็น JSON เก็บไว้ในเครื่องส่วนตัว
3. แชร์โฟลเดอร์ภาพใน **Google Drive → Share** ให้อีเมล `client_email` ใน JSON เป็น **Viewer** การเพิ่ม IAM role ของ Cloud อย่างเดียวไม่ได้แชร์ไฟล์ Drive
4. สร้าง session key และติดตั้งไฟล์บนเซิร์ฟเวอร์:

```bash
sudo python3 scripts/setup_secrets.py
sudo install -o root -g 10001 -m 640 /path/to/private-service-account.json secrets/service-account.json
```

โฟลเดอร์ `secrets/` ใช้ mode 750 และ GID 10001 ให้ container อ่านได้ ส่วน key ใช้ mode 640 ถ้ามี `token_key` เดิม สคริปต์จะเก็บไว้ ไม่สร้างทับ

โหมด public ไม่ต้องมี `oauth.json` ส่วนกุญแจ JSON และ `token_key` ต้องอยู่บนเซิร์ฟเวอร์เท่านั้น ไม่ใส่ใน `.env.example` หรือ GitHub Secrets หากยังไม่มี workflow ที่จำเป็นต้องใช้

## 4A. เครื่องใหม่ที่ยังไม่มี reverse proxy

```bash
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d --build
docker compose -f compose.yaml -f compose.https.yaml ps
```

Caddy ขอใบรับรอง HTTPS ให้โดเมนที่ตั้งไว้ ต้องมี DNS ชี้มาถูกต้องและ port 80/443 ว่าง

Build ครั้งแรกอาจใช้เวลาหลายนาทีเพราะคอมไพล์ dlib และดาวน์โหลดโมเดล โมเดลจะผ่านการตรวจ SHA-256 ก่อนใช้

## 4B. เครื่องที่มี Caddy / reverse proxy อยู่แล้ว

ใช้วิธีนี้แทน 4A เพื่อไม่เปิด Caddy อีกตัวทับ port เดิม

ตั้ง `EXTERNAL_PROXY_NETWORK` เป็นชื่อ network ของ reverse proxy จริง แล้วรัน:

```bash
docker compose -f compose.yaml -f compose.existing-proxy.yaml config --quiet
docker compose -f compose.yaml -f compose.existing-proxy.yaml up -d --build
```

เพิ่ม block นี้ใน Caddy เดิม โดยเปลี่ยนโดเมน:

```caddy
photos.example.com {
    encode gzip
    header -Server
    reverse_proxy findme-app:8000
}
```

ตรวจ config ของ Caddy ก่อน reload ตามวิธีติดตั้ง Caddy เดิมของคุณ แอปใช้ alias `findme-app` บน external network และไม่ต้องเปิด port 8000 เพิ่ม

## 5. ใช้งาน

เปิด `APP_BASE_URL` ผ่าน HTTPS โดยไม่ต้องล็อกอิน ถ้าใช้ `AUTO_INDEX=false` ให้กด **อ่านคลังรูปจาก Drive** เพื่อสร้างดัชนีครั้งแรก รอให้เสร็จ จากนั้นเลือกรูปอ้างอิงที่มีใบหน้าเดียว แล้วกดค้นหา

- รูปผ่านเกณฑ์เรียงจากใกล้ที่สุด โดย ArcFace ใช้เกณฑ์เริ่มต้น 0.50 และ YuNet/dlib ใช้ 0.46
- รูปไม่แน่ใจอยู่หน้าสุดท้ายเมื่อมีรูปผ่านเกณฑ์มากกว่า 20 รูป
- เลือกรูปข้ามหน้าและดาวน์โหลด ZIP/TAR ได้ งานดาวน์โหลดผูกกับ cookie ของ browser นั้น มีอายุ 1 ชั่วโมง
- เมื่อเพิ่มรูปใน Drive กด **อ่านคลังรูปจาก Drive** ดัชนีจะข้ามรูปที่ไม่เปลี่ยน

รูปอ้างอิงต้องไม่เกิน 15 MB; ต้นฉบับสำหรับ preview/index ไม่เกิน 30 MB และ 64 ล้านพิกเซล HEIC ยังไม่เปิดรองรับในชุดนี้

## อัปเดตรุ่น

สำรอง persistent volume และกุญแจก่อนอัปเดต จากนั้นใช้ชุดคำสั่ง Compose เดียวกับตอนติดตั้ง เช่นเครื่องที่ใช้ external proxy:

```bash
git pull --ff-only
docker compose -f compose.yaml -f compose.existing-proxy.yaml build app
docker compose -f compose.yaml -f compose.existing-proxy.yaml up -d --no-build --no-deps app
```

อย่ารัน `docker compose down -v` ถ้าต้องการเก็บข้อมูลเดิม เพราะ volume มีดัชนีและข้อมูล session ให้เก็บ `name: findme` และชื่อ volume เดิมเมื่อย้าย source directory เพื่อไม่เผลอสร้างฐานข้อมูลใหม่คนละชุด

การแก้ `.env` ต้อง recreate container ด้วย `up -d` เพื่อโหลดค่าใหม่ การแชร์สิทธิ์ใน Drive ไม่ต้อง rebuild image

## ตรวจและแก้ปัญหา

```bash
docker compose ps
docker compose logs --tail 80 app
curl http://127.0.0.1:8000/healthz
```

- **Drive 404/403:** ตรวจ folder ID และแชร์ให้ Service Account ที่ใช้จริง
- **Permission denied `/run/secrets`:** ตรวจ GID 10001 และ mode ของ folder/file
- **สร้างงานแล้วไม่พบงาน:** ใช้ HTTPS และ cookie ของ browser เดิม ตรวจ `APP_BASE_URL` ให้ตรงโดเมน
- **Invalid origin:** URL ใน `.env` ต้องตรงกับ origin ของหน้าเว็บ
- **ไม่พบใบหน้า:** ใช้รูปชัด ใบหน้าใหญ่พอ มีเพียงคนเดียว แว่น/หมวก/หน้าหันข้างอาจมีผล
- **ภาพ resolution สูง:** แอปรองรับไม่เกิน 64 ล้านพิกเซล และย่อก่อนตรวจหน้า
- **Analytics ไม่ทำงาน:** ตรวจ `GA_MEASUREMENT_ID`, recreate container, browser/ad blocker และรายงาน Realtime ของ property คุณ

อ้างอิง: [Docker Compose environment variables](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation), [Google Drive sharing](https://developers.google.com/workspace/drive/api/guides/manage-sharing)
