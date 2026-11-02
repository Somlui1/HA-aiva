import sys
import tinytuya

# ตั้งค่า encoding สำหรับแสดงผลภาษาไทยใน Windows Terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ข้อมูลการเชื่อมต่อ Tuya Gateway
GATEWAY_ID = "ebdfd1403f62ed7eb6ysvu"
GATEWAY_KEY = ":):<n1o1X?{-XoMK"
GATEWAY_IP = "10.10.193.99"

# ข้อมูลอุปกรณ์ Zigbee ตัวลูก (สวิตช์ 3 ช่อง)
SUB_DEVICE_ID = "eb2422f0a31bf12000emah"
SUB_DEVICE_CID = "a4c1387c642f4dbf"  # Node ID / CID ในเครือข่าย Zigbee

print("==========================================")
print("       Tuya Zigbee Gateway Controller      ")
print("==========================================")
print(f"Gateway IP : {GATEWAY_IP}")
print(f"Gateway ID : {GATEWAY_ID}")

# 1. เชื่อมต่อไปยัง Gateway
gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=3.4)
gw.set_socketTimeout(5)
gw.set_socketRetryLimit(3)

# ค้นหาอุปกรณ์ลูกที่ออนไลน์อยู่ใต้ Gateway
print("\n[1] กำลังตรวจสอบสถานะอุปกรณ์ Zigbee ภายใต้ Gateway...")
sub_list = gw.subdev_query()

online_devs = []
offline_devs = []

if sub_list and isinstance(sub_list, dict) and "data" in sub_list:
    online_devs = sub_list["data"].get("online", [])
    offline_devs = sub_list["data"].get("offline", [])
    print(f"  🟢 ออนไลน์ (Online)  : {online_devs}")
    print(f"  🔴 ออฟไลน์ (Offline) : {offline_devs}")
else:
    print("  ⚠️ ไม่สามารถดึงรายการ sub-device ได้โดยตรง (หรือ Gateway ติดการเชื่อมต่ออื่น)")

print(f"\n[2] กำลังตรวจสอบอุปกรณ์เป้าหมาย (CID: {SUB_DEVICE_CID})...")

if SUB_DEVICE_CID in offline_devs:
    print(f"  ❌ แจ้งเตือน: อุปกรณ์ CID '{SUB_DEVICE_CID}' ขณะนี้มีสถานะเป็น OFFLINE")
    print("     -> กรุณาตรวจสอบว่าสวิตช์เปิดเบรกเกอร์/จ่ายไฟอยู่หรือไม่ หรืออยู่ในระยะสัญญาณ Zigbee หรือไม่")
elif SUB_DEVICE_CID in online_devs:
    print(f"  ✅ อุปกรณ์ CID '{SUB_DEVICE_CID}' มีสถานะเป็น ONLINE พร้อมรับคำสั่ง")
else:
    print(f"  ℹ️ อุปกรณ์ CID '{SUB_DEVICE_CID}' ไม่ปรากฏในรายการ (กำลังพยายามเชื่อมต่อโดยตรง...)")

# 2. สร้าง Sub-device object และเชื่อมโยงเข้ากับ Gateway
sub = tinytuya.OutletDevice(SUB_DEVICE_ID, cid=SUB_DEVICE_CID, parent=gw)
sub.set_socketTimeout(5)
status = sub.status()

print("\n[3] ผลลัพธ์สถานะอุปกรณ์ (DPS):")
if status and isinstance(status, dict) and "dps" in status:
    dps = status["dps"]
    print(f"  - สวิตช์ช่องที่ 1: {'เปิด (ON)' if dps.get('1') else 'ปิด (OFF)'}")
    print(f"  - สวิตช์ช่องที่ 2: {'เปิด (ON)' if dps.get('2') else 'ปิด (OFF)'}")
    print(f"  - สวิตช์ช่องที่ 3: {'เปิด (ON)' if dps.get('3') else 'ปิด (OFF)'}")
    print(f"  -> Raw DPS Data: {dps}")

    print("\n[4] กำลังสั่งควบคุมสวิตช์...")
    # ตัวอย่างคำสั่ง: สั่งเปิดช่อง 1, ปิดช่อง 2, ปิดช่อง 3
    print("  - สั่งเปิดช่อง 1 :", sub.turn_on(switch=1))
    print("  - สั่งปิดช่อง 2  :", sub.turn_off(switch=2))
    print("  - สั่งปิดช่อง 3  :", sub.turn_off(switch=3))

    # ตรวจสอบสถานะใหม่อีกครั้ง
    new_status = sub.status()
    if new_status and isinstance(new_status, dict) and "dps" in new_status:
        dps = new_status["dps"]
        print(f"\n  สถานะล่าสุดหลังสั่งงาน -> ช่อง 1: {'ON' if dps.get('1') else 'OFF'} | ช่อง 2: {'ON' if dps.get('2') else 'OFF'} | ช่อง 3: {'ON' if dps.get('3') else 'OFF'}")
else:
    print(f"  ⚠️ ผลลัพธ์: {status}")
    print("  (ไม่สามารถดึงค่า DPS ได้เนื่องจากอุปกรณ์ออฟไลน์ หรือ Gateway ไม่ตอบสนองคำสั่ง sub-device นี้)")

print("\n==========================================")