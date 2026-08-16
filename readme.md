# JobsDB Thailand Scraper
## ติดตั้ง

```bash
pip install -r requirements.txt
```

## ใช้งาน

```bash
python jobsdb_scraper.py --keyword "python developer" --location Bangkok --output jobs_output.csv
```

ไม่ใส่ argument ก็ได้ จะใช้ค่าเริ่มต้นใน `SEARCH_TARGETS` ภายในไฟล์ (แก้ list นี้เพื่อค้นหลายคำ/หลายพื้นที่ในรันเดียว)

## ข้อจำกัดสำคัญ (ตรวจสอบจริงกับ robots.txt แล้ว)

- **ดึงได้แค่หน้าแรกของแต่ละคำค้นหา** — robots.txt ของ th.jobsdb.com มี `Disallow: *?`
  (บล็อก URL ที่มี query string ทั้งหมด) และ pagination ของ JobsDB ใช้ `?page=2`
  เท่านั้น จึงไม่มีฟีเจอร์ไล่หน้าในสคริปต์นี้ — ต้องการข้อมูลมากขึ้นให้เพิ่ม
  keyword/location ใน `SEARCH_TARGETS` แทน
- **ไม่ดึงหน้ารายละเอียดงาน** (`/job/{id}`) — robots.txt สั่ง `Disallow: */job/`
  สคริปต์เก็บ URL ไว้เป็นข้อมูลอ้างอิงในคอลัมน์ `url` เท่านั้น ไม่เคย request หน้านั้น
- โค้ดเช็ค robots.txt เองก่อนทุก request และ fail-closed (ถ้าอ่าน robots.txt
  ไม่ได้ จะไม่ดึงข้อมูลเลย)
- หน่วงเวลาแบบสุ่ม 3–6 วินาทีระหว่าง request, retry พร้อม exponential backoff
  เมื่อเจอ error ชั่วคราว, จัดการ HTTP 429 (Retry-After) ให้อัตโนมัติ
- ใช้เพื่อการเรียนรู้/ส่วนตัวเท่านั้น ห้ามใช้เชิงพาณิชย์หรือ scrape ปริมาณมาก

รายละเอียดทางเทคนิคทั้งหมด (selector ที่ใช้จริง, บั๊กที่พบและวิธีแก้) อยู่ใน
docstring ด้านบนของ [jobsdb_scraper.py](jobsdb_scraper.py)

## Output

ไฟล์ CSV (UTF-8 with BOM เปิดด้วย Excel ได้ปกติ) มีคอลัมน์:
`job_id, title, company, location, work_arrangement, salary, short_description, listed, url`

## แจ้งเตือนงานใหม่อัตโนมัติ (job_alert.py)

ดึงงานตาม `SEARCH_TARGETS` เดิม กรองด้วยเงื่อนไขที่สนใจ (แก้ได้ที่ต้นไฟล์
`job_alert.py`: `INTERESTED_KEYWORDS`, `INTERESTED_WORK_ARRANGEMENTS`,
`EXCLUDED_KEYWORDS`) แล้วแจ้งเตือนผ่าน Discord webhook เฉพาะงาน "ใหม่" ที่
ยังไม่เคยแจ้งมาก่อน (เก็บสถานะไว้ใน `seen_jobs.json`)

ค่าเริ่มต้นตอนนี้: keyword "software developer" / "python developer" @ Bangkok,
กรองเฉพาะงาน **Hybrid**

### ตั้งค่า Discord webhook (ทำครั้งเดียว)

1. ในเซิร์ฟเวอร์ Discord ของคุณ: Server Settings → Integrations → Webhooks →
   New Webhook → เลือกช่องที่ต้องการรับแจ้งเตือน → Copy Webhook URL
2. คัดลอก `config.example.json` เป็น `config.json` แล้วใส่ URL ที่ได้ลงใน
   `discord_webhook_url` (หรือจะตั้ง environment variable `DISCORD_WEBHOOK_URL`
   แทนก็ได้) — ไฟล์ `config.json` อยู่ใน `.gitignore` แล้ว จะไม่ถูก commit

### รันด้วยมือ

```bash
python job_alert.py
```

### รันอัตโนมัติทุก 6 ชม. (ตั้งไว้แล้วผ่าน Windows Task Scheduler)

มี scheduled task ชื่อ **"JobsDB Job Alert"** เรียก `run_job_alert.bat` ทุก 6
ชั่วโมง (log อยู่ที่ `job_alert.log`) — ตรวจสอบ/แก้ไขได้ผ่าน Task Scheduler
(`taskschd.msc`) หรือคำสั่ง:

```powershell
schtasks /query /tn "JobsDB Job Alert" /v /fo list   # ดูสถานะ
schtasks /run /tn "JobsDB Job Alert"                 # สั่งรันทันที (ทดสอบ)
schtasks /delete /tn "JobsDB Job Alert" /f            # ลบ task
```

**หมายเหตุ:** task จะรันได้ก็ต่อเมื่อตั้งค่า Discord webhook ตามขั้นตอนด้านบนแล้ว
ไม่งั้นจะ log error ทุกรอบว่าไม่พบ webhook URL (ไม่กระทบอะไร แค่ไม่แจ้งเตือน)