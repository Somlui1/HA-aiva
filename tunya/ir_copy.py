import sys
import time
import os
import tinytuya
from tinytuya.Contrib import IRRemoteControlDevice

# ตั้งค่า encoding สำหรับภาษาไทย
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ข้อมูล Gateway
GATEWAY_ID = "ebdfd1403f62ed7eb6ysvu"
GATEWAY_KEY = "za{uf`wXm`I:e[Q3"
GATEWAY_IP = "10.85.217.151"

# Sub-node CID (เช่น ZS05 Zigbee IR: "bc8d7efffe78a16b")
# หากต้องการจับสัญญาณที่ตัว Gateway โดยตรง ให้ใส่เป็น None
SUB_NODE_CID = None

print("==========================================")
print("       IR Code Learning (Direct Gateway)  ")
print("==========================================")
print("💡 หมายเหตุ: หาก Home Assistant รันอยู่ แนะนำให้ใช้:")
print("   python tunya/learn_ir_ha.py <brand> <cmd>")
print("   (ไม่ต้องปิด Docker Home Assistant)")
print("==========================================")

# 1. เชื่อมต่อ Gateway
gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=3.4)
gw.set_socketTimeout(5)

# 2. ตั้งค่า IR Device (รองรับทั้ง Sub-node และ Gateway)
if SUB_NODE_CID:
    print(f"📡 โหมด: Sub-node CID -> {SUB_NODE_CID}")
    ir = IRRemoteControlDevice(
        SUB_NODE_CID, cid=SUB_NODE_CID, parent=gw, version=3.4, control_type=1
    )
else:
    print("📡 โหมด: Gateway IR Blaster โดยตรง")
    ir = IRRemoteControlDevice(
        GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=3.4, control_type=1
    )

ir.set_socketTimeout(5)

# 3. เริ่มดูดรหัส
print(">> กรุณากดปุ่มที่รีโมทแอร์จ่อไปที่ตัวรับสัญญาณภายใน 15 วินาที...")
ir_code = ir.receive_button(timeout=15)

if isinstance(ir_code, dict) and "Error" in ir_code:
    print(f"\n❌ เกิดข้อผิดพลาดจากอุปกรณ์: {ir_code}")
    print("\n💡 หากเจอ Error 914 (Check device key or version):")
    print("   สาเหตุเกิดจาก Container Home Assistant กำลังเชื่อมต่อ Gateway อยู่")
    print("   Tuya Gateway อนุญาตให้มีเพียง 1 Connection เท่านั้น")
    print("   วิธีแก้: รันคำสั่ง 'docker compose stop' ในอีกหน้าต่างก่อน แล้วลองใหม่")
elif ir_code:
    # บันทึกรหัสลงไฟล์อัตโนมัติ เพื่อป้องกัน Terminal ตัดคำหรือจัดหน้าเบี้ยว
    last_file = os.path.join(os.path.dirname(__file__), "last_captured.txt")
    with open(last_file, "w", encoding="utf-8") as f:
        f.write(str(ir_code).strip())

    history_file = os.path.join(os.path.dirname(__file__), "captured_history.txt")
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {str(ir_code).strip()}\n")

    print(f"\n🎉 [สำเร็จ] ได้รหัส IR Code (ความยาว {len(ir_code)} ตัวอักษร):")
    print(f"{ir_code}")
    print(f"\n💾 บันทึกลงไฟล์แล้วที่: tunya/last_captured.txt")
else:
    print("หมดเวลาหรือไม่ได้รับสัญญาณ ลองใหม่อีกครั้งครับ")
