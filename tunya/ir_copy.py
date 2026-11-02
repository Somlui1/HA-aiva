from tinytuya.Contrib import IRRemoteControlDevice
import time

GATEWAY_ID = "ebdfd1403f62ed7eb6ysvu"
GATEWAY_KEY = ":):<n1o1X?{-XoMK"
GATEWAY_IP = "10.10.193.99"

# เชื่อมต่อ Gateway ในโหมด IR Blaster (Local LAN)
ir = IRRemoteControlDevice(
    GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=3.4, control_type=1
)
ir.set_socketTimeout(5)

# --- ขั้นตอนที่ 1: ดูดรหัสปุ่มจากรีโมทจริง (ทำครั้งเดียว) ---
print(">> กรุณากดปุ่มที่รีโมทแอร์จ่อไปที่ Gateway ภายใน 15 วินาที...")
ir_code = ir.receive_button(timeout=15)

if ir_code:
    print(f"\n[สำเร็จ] ได้รหัส IR Code: {ir_code}")

else:
    print("หมดเวลาหรือไม่ได้รับสัญญาณ ลองใหม่อีกครั้งครับ")
