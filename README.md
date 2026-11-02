# Home Assistant Infrastructure & Configuration

ระบบจัดการ Home Assistant พร้อม Docker Compose, Tuya Local IR Blaster, HACS, และ MCP Server (Model Context Protocol)

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
├── config/                     # โฟลเดอร์ Configuration ของ Home Assistant
│   ├── configuration.yaml      # การตั้งค่าหลัก (Climate Templates, Helpers)
│   ├── automations.yaml        # Automations
│   ├── scripts.yaml            # Scripts
│   ├── custom_components/      # HACS, Tuya Local, SmartIR
│   └── .storage/               # Entity registry, Device registry, Tuya IR codes
├── tunya/                      # สคริปต์ Python สำหรับทดสอบ Tuya Gateway / Zigbee
├── docker-compose.yml          # ไฟล์รัน Home Assistant Container
├── mcp_config.example.json     # ตัวอย่างการตั้งค่า MCP Server สำหรับ AI Client
├── .gitignore                  # Git Ignore กรอง Database, Logs, Auth tokens
└── README.md
```

---

## 🚀 การเริ่มต้นใช้งาน (Getting Started)

1. **รัน Home Assistant ผ่าน Docker Compose:**
   ```bash
   docker compose up -d
   ```
2. **เข้าใช้งาน Web UI:**
   * URL: `http://localhost:8123` (หรือตาม IP เครื่อง เช่น `http://10.10.193.99:8123`)

---

## ❄️ อุปกรณ์ในห้อง Meeting Room 1

* **IR Blaster:** `remote.tunya_gateway_ir` (Avatto S16 via Tuya Local)
* **Carrier AC:** `climate.carrier_ac`
* **Eminent AC:** `climate.eminent_ac`
  * โหมด: `input_select.eminent_ac_mode`
  * ปรับอุณหภูมิ: `input_number.eminent_ac_temp`

---

## 🤖 การเชื่อมต่อ Model Context Protocol (MCP)

Home Assistant ตัวนี้เปิดใช้งาน **Native MCP Server (`mcp_server`)** ไว้เรียบร้อยแล้ว:

1. **สร้าง Long-Lived Access Token:**
   * ไปที่ Home Assistant Web UI > คลิกที่รูปโปรไฟล์มุมซ้ายล่าง
   * เลื่อนลงมาที่หัวข้อ **Long-Lived Access Tokens (โทเค็นการเข้าถึงแบบใช้งานได้นาน)**
   * กดสร้าง Token แล้วคัดลอกค่า Token เก็บไว้
2. **นำไปใส่ใน MCP Client (เช่น Claude Desktop, Antigravity IDE, Cursor):**
   * ดูตัวอย่างในไฟล์ [`mcp_config.example.json`](./mcp_config.example.json)
   * รองรับทั้ง **SSE** (`/mcp_server/sse`) และ **Streamable HTTP** (`/api/mcp`)
   * Entities ทั้งหมดใน Meeting Room 1 ได้ถูกเปิดค่า `should_expose: true` ให้ AI มองเห็นและสั่งการได้ทันที

---

## 📦 การนำไปรันบน Git Server

1. **เพิ่ม Remote และ Push ขึ้น Git Server:**
   ```bash
   git remote add origin <URL_GIT_SERVER>
   git push -u origin master
   ```
2. **บนเครื่อง Server ปลายทาง:**
   ```bash
   git clone <URL_GIT_SERVER> home-assistant
   cd home-assistant
   docker compose up -d
   ```
