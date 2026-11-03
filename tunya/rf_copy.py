import sys
import time
import os
import tinytuya
from tinytuya.Contrib.RFRemoteControlDevice import RFRemoteControlDevice

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

GATEWAY_ID = "ebdfd1403f62ed7eb6ysvu"
GATEWAY_KEY = ":):<n1o1X?{-XoMK"
GATEWAY_IP = "10.10.193.99"

print("==========================================")
print("       RF Code Learning (Direct Gateway)  ")
print("==========================================")

rf = RFRemoteControlDevice(
    GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=3.4, control_type=1
)
rf.set_socketTimeout(5)

# freq=0 หมายถึง Auto-detect คลื่นความถี่ (หรือระบุเป็น '433.92' หรือ '315')
print(">> กรุณากดปุ่มที่รีโมท RF ค้างไว้หรือกดซ้ำๆ ใกล้ตัว Gateway ภายใน 15 วินาที...")
rf_code = rf.rf_receive_button(freq=0, timeout=15)

if isinstance(rf_code, dict) and "Error" in rf_code:
    print(f"\n❌ เกิดข้อผิดพลาดจากอุปกรณ์: {rf_code}")
    print("\n💡 หากเจอ Error 914 (Check device key or version):")
    print("   สาเหตุเกิดจาก Container Home Assistant กำลังเชื่อมต่อ Gateway อยู่")
    print("   Tuya Gateway อนุญาตให้มีเพียง 1 Connection เท่านั้น")
    print("   วิธีแก้: รันคำสั่ง 'docker compose stop' ในอีกหน้าต่างก่อน แล้วลองใหม่")
elif rf_code:
    # บันทึกรหัสลงไฟล์อัตโนมัติ เพื่อป้องกัน Terminal ตัดคำ
    last_file = os.path.join(os.path.dirname(__file__), "last_captured_rf.txt")
    with open(last_file, "w", encoding="utf-8") as f:
        f.write(str(rf_code).strip())

    history_file = os.path.join(os.path.dirname(__file__), "captured_rf_history.txt")
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {str(rf_code).strip()}\n")

    print(f"\n🎉 [สำเร็จ] ได้รหัส RF Code:")
    print(f"{rf_code}")
    print(f"\n💾 บันทึกลงไฟล์แล้วที่: tunya/last_captured_rf.txt")
    print("\n💡 ตัวอย่างการนำไปส่งสัญญาณ:")
    print("   rf.rf_send_button(rf_code)")
else:
    print("หมดเวลาหรือไม่ได้รับสัญญาณ RF ลองกดใหม่อีกครั้งครับ")
