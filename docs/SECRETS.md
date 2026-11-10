# ไฟล์ลับและการแยก config

## อยู่บนเซิร์ฟเวอร์เท่านั้น

| รายการ | ตำแหน่ง | ใช้ทำอะไร |
|---|---|---|
| Service Account JSON | `secrets/service-account.json` | มี private key สำหรับอ่าน Drive |
| Session encryption key | `secrets/token_key` | เข้ารหัสข้อมูล session ต้องเก็บเดิมเมื่อย้ายเครื่อง |
| OAuth client secret (optional legacy mode) | `secrets/oauth.json` | ไม่ใช้ในโหมด public |
| Config จริง | `.env` | โดเมนและคลังภาพของระบบจริง รวมค่าที่อาจเพิ่มเป็นความลับในอนาคต |
| Runtime data | Docker volume `findme_app_data` | ฐานข้อมูล session, face embeddings, cache และไฟล์ดาวน์โหลดชั่วคราว |
| Backup | พื้นที่สำรองส่วนตัว | อาจมี credential หรือข้อมูลส่วนบุคคล ห้ามขึ้น repo |

## อยู่ใน repo ได้

- Source code, tests และ dependencies
- `.env.example` ที่ใช้โดเมน/อีเมลตัวอย่างและไม่ใส่รหัสจริง
- ชื่อ environment variable และ path ไฟล์ลับ โดยไม่มีค่ากุญแจ
- ค่าปลอมที่ระบุชัดใน tests เช่น `fake-access` หรือ `fake-secret`
- License และ checksum ของโมเดลที่เปิดเผยสาธารณะ

Analytics Measurement ID และ Drive folder ID ไม่ใช่ private key แต่ชุดเผยแพร่นี้ก็นำค่าของระบบต้นทางออก ให้ผู้ติดตั้งใส่เองใน `.env`

## ไม่พิมพ์ secret ระหว่างตรวจระบบ

ใช้ `docker compose config --quiet` เพื่อตรวจรูปแบบ ไม่คัดลอก output ของ `docker compose config` หรือ `docker inspect` ส่วน environment ทั้งหมดไปโพสต์ เพราะอาจมีค่า config ส่วนตัว

สคริปต์ `setup_secrets.py` ไม่แสดง key และไม่เขียนทับของเดิม ส่วน `check_secrets.py` รายงานเฉพาะชื่อไฟล์/ประเภทรูปแบบที่สงสัย ไม่แสดงค่าที่จับได้

ชุดสำหรับ GitHub จัดแยกจากไฟล์ production การนำ source นี้ขึ้น repo ไม่ได้ลบ credential หรือเปลี่ยน config ของเว็บไซต์ที่กำลังทำงาน
