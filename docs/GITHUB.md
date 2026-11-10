# เก็บและอัปเดตโค้ดบน GitHub

Repository: https://github.com/rubybox/findmyface

## Clone และเตรียมเครื่อง

```bash
git clone https://github.com/rubybox/findmyface.git
cd findmyface
cp .env.example .env
```

แก้ config จริงใน `.env` และวาง credential ใน `secrets/` เฉพาะเครื่องที่รันแอป ทั้งสองตำแหน่งถูก `.gitignore` กันไว้

## อัปเดตโค้ด

```bash
git switch -c update/photo-search
# แก้ไฟล์โปรแกรมหรือเอกสาร
python3 scripts/check_secrets.py
git add app scripts tests docs README.md Dockerfile compose.yaml compose.https.yaml compose.existing-proxy.yaml Caddyfile .env.example .gitignore .dockerignore requirements.txt requirements-drive.txt requirements-dev.txt .github
git diff --cached --stat
git diff --cached
python3 scripts/check_secrets.py
git commit -m "Update photo search"
git push -u origin update/photo-search
```

จากนั้นเปิด Pull Request บน GitHub ให้ตรวจ diff และรอ workflow ผ่านก่อน merge การ push ใช้ Git credential manager หรือ SSH agent ของเครื่อง ไม่ใส่ token ใน URL เช่น `https://TOKEN@github.com/...`

## ก่อน push ตรวจอะไรบ้าง

- ต้องไม่มี `.env`, `secrets/`, Service Account JSON, private key หรือ session key ในรายการ staged
- ไม่อัปโหลด `data/`, SQLite, face embeddings, รูปผู้ใช้, ZIP/TAR ที่สร้างไว้ หรือ backup
- ใช้ `.env.example` เป็นตัวอย่างและเว้นค่าจริงไว้ในเครื่อง
- โมเดล ONNX ไม่ต้อง commit; build/test ดาวน์โหลดจาก upstream โดยตรวจ checksum

ตรวจรายการ staged ได้ด้วย `git diff --cached --name-only` ตัวตรวจ secret เป็น safeguard สำหรับรูปแบบที่รู้จัก ไม่สามารถแทนการอ่าน diff ได้ทั้งหมด

ถ้า credential เคยหลุดเข้า commit ให้เพิกถอน/เปลี่ยน credential นั้น และจัดการ history ตามขั้นตอนของ GitHub การลบไฟล์ใน commit ใหม่เพียงอย่างเดียวยังเหลือค่าใน history

อ้างอิง: [Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
