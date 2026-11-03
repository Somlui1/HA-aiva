import sys
import os
import json
import base64
import struct
import tinytuya

# ตั้งค่า encoding ภาษาไทยสำหรับ Windows Terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ==============================================================================
# ⚙️ ข้อมูลการเชื่อมต่อ Tuya Gateway (Direct Local Socket - Port 6668)
# ==============================================================================
GATEWAY_ID = "ebdfd1403f62ed7eb6ysvu"
GATEWAY_KEY = ":):<n1o1X?{-XoMK"
GATEWAY_IP = "10.10.193.99"
SUB_NODE_CID = None  # None = ยิงผ่านตัวแม่ (Direct Gateway IR S16)

# ==============================================================================
# 📡 Carrier / Toshiba AC 72-bit (9-byte) Protocol Generator
# ==============================================================================
# Tuya Base64 Pulse Encoding Constants (38kHz)
BIT_1 = b'\x26\x02\x40\x06'   # Mark 550us, Space 1600us
BIT_0 = b'\x26\x02\x26\x02'   # Mark 550us, Space 550us
HDR = b'\x10\x11\x10\x11'     # Header: Mark 4368us, Space 4368us
GAP = b'\x1a\x1d'             # Gap between repeat: 7450us
FOOTER = b'\x26\x02\x30\x75'  # Footer: Mark 550us, Space 30000us

def encode_tuya_packet(bytes_9):
    """แปลงชุดไบต์ 9 ตัวให้เป็น Tuya Base64 IR Packet ที่สมบูรณ์ (Repeat 2 ครั้งตามมาตรฐาน)"""
    raw = b''
    for r in range(2):
        raw += HDR
        for b in bytes_9:
            for bit in range(7, -1, -1):
                raw += BIT_1 if ((b >> bit) & 1) else BIT_0
        if r == 0:
            raw += b'\x26\x02' + GAP
        else:
            raw += FOOTER
    return base64.b64encode(raw).decode('ascii')

def build_carrier_code(temp=25, mode='cool', fan='auto', swing=False, power_off=False):
    """
    สร้างรหัส Base64 ตามโปรโตคอล Toshiba / Carrier 72-bit
    - temp: 17 ถึง 30 °C
    - mode: 'cool', 'auto', 'dry', 'fan'
    - fan: 'auto', 'low', 'med', 'high'
    - swing: True / False
    - power_off: True สำหรับสั่งปิดเครื่อง
    """
    b0 = 0xF2  # Address 1
    b1 = 0x0D  # ~Address 1
    b2 = 0x03  # Length=3 (72-bit), Model=Remote A
    b3 = 0xFC  # ~Byte 2
    b4 = 0x01  # Fixed Header Control

    if power_off:
        b5 = 0x00
        b6 = 0x07  # Mode = 7 (Off)
    else:
        # Byte 5: Temp (High nibble) & Swing (Bit 0)
        t = max(17, min(30, int(temp)))
        t_nibble = (t - 16) & 0x0F
        s_nibble = 0x01 if swing else 0x00
        b5 = (t_nibble << 4) | s_nibble

        # Byte 6: Fan (High 3 bits) & Mode (Low 3 bits)
        mode_map = {'auto': 0, 'cool': 1, 'dry': 2, 'heat': 3, 'fan': 4}
        fan_map = {'auto': 0, 'low': 2, 'med': 3, 'high': 5}
        m_val = mode_map.get(mode.lower(), 1)
        f_val = fan_map.get(fan.lower(), 0)
        b6 = (f_val << 5) | m_val

    b7 = 0x00
    b8 = b0 ^ b1 ^ b2 ^ b3 ^ b4 ^ b5 ^ b6 ^ b7  # XOR Checksum
    return encode_tuya_packet([b0, b1, b2, b3, b4, b5, b6, b7, b8])

# ==============================================================================
# 📡 ฐานข้อมูล IR Codes (Tuya Base64) สำหรับ Carrier และ Eminent
# ==============================================================================
# รหัสปิดแอร์ Carrier จากสัญญาณที่ดูดมาได้จริง (F2 0D 03 FC 01 00 07 00 06)
CARRIER_OFF_LEARNED = "EBEQERACPQYQAj0GEAI9BhACPQYQAhACQwIQAhACPQYQAhACEAIQAhACEAIQAhACEAIQAhACPQYQAj0GEAIQAhACPQYQAhACEAIQAhACEAIQAhACEAIQAhACEAJDAj0GEAI9BhACPQYQAj0GEAI9BhACPQYQAj0GEAI9BhACEAIQAhACEAIQAhACEAJDAhACEAIQAhACEAIQAhACEAIQAhACPQYQAhACEAIQAkMCEAIQAhACEAIQAhACEAJDAhACEAIQAhACEAIQAhACEAIQAhACEAIQAhACQwI9BhACPQYQAj0GEAIQAhACEAIQAhACQwIQAkMCEAIQAhACEAIQAkMCEAJDAhACQwIQAhACEAIQAhACQwIQAkMCPQZDAj0GEAIQAkMCGh0QERAREAI9BkMCPQZDAj0GQwI9BkMCEAJDAhACQwI9BkMCEAJDAhACQwIQAkMCEAJDAhACQwI9BkMCPQZDAhACQwI9BkMCEAJDAhACQwIQAkMCEAJDAhACQwIQAkMCPQZDAjDyQwI9BkMCPQZDAj0GQwI9BkMCPQZDAj0GQwIQAkMCEAJDAhACQwIQAkMCEAJDAhACQwIQAkMCEAJDAhACQwI9BkMCEAJDAhACQwIQAkMCEAJDAhACQwIQAkMCEAJDAhACQwIQAkMCEAJDAhACQwIQAkMCEAJDAj0GQwI9BkMCPQZDAhACQwIQAkMCEAJDAhACEAIQAkMCEAJDAhACQwIQAhACEAIQAhACQwIQAkMCEAJDAhACQwI9BhACPQYQAhACEAIwdQ=="

IR_CODES = {
    "carrier": {
        "power_off": build_carrier_code(power_off=True),
        "power_off_learned": CARRIER_OFF_LEARNED,
        "power_on": build_carrier_code(temp=25, mode='cool', fan='auto'),
    },
    "eminent": {
        "power_off": build_carrier_code(power_off=True),
        "power_off_learned": CARRIER_OFF_LEARNED,
        "power_on": build_carrier_code(temp=25, mode='cool', fan='auto'),
        # รหัสเก่าเก็บเป็นตัวเลือกสำรอง
        "cool_25_legacy": "KCN7ESsCKwIrAisCKwJ4BisCKwIrAngGKwIrAisCKwIrAisCKwJ4BisCKwIrAngGKwIrAisCeAYrAisCKwJ4BisCeAYrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCKwIrAisCcQIrAnECKwJxAisCKwIrAnECKwIrAisCKwIrAnECKwJxAisCcQJ4BnECKwJxAisCcQIrAnECKwJxAisCKwIrAisCKwJxAngGKwIrAisCKwIrAisCcQIrAisCeAYrAngGcQJ4BnECKwIrAjB1",
        "power_off_legacy": "QSN7ETMCMwIzAjMCMwKEBjMCMwIzAoQGMwIzAjMCMwIzAjMCMwKEBjMCMwIzAoQGMwIzAjMChAYzAjMCMwIzAjMChAYzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMChAYzAjMCMwIzAjMCMwIzAjMCMwKEBjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAoQGMwIzAjMCMwIzAjMCMwIzAjMChAYzAoQGMwKEBjMCMwIzAjB1"
    }
}

# เติมรหัส 17 - 30 °C ที่คำนวณจากโปรโตคอลจริงให้ทั้ง Carrier และ Eminent
for temp in range(17, 31):
    code_cool = build_carrier_code(temp=temp, mode='cool', fan='auto')
    code_auto = build_carrier_code(temp=temp, mode='auto', fan='auto')

    IR_CODES["carrier"][f"cool_{temp}"] = code_cool
    IR_CODES["carrier"][f"auto_{temp}"] = code_auto
    IR_CODES["carrier"][f"temp_{temp}"] = code_cool

    IR_CODES["eminent"][f"cool_{temp}"] = code_cool
    IR_CODES["eminent"][f"auto_{temp}"] = code_auto
    IR_CODES["eminent"][f"temp_{temp}"] = code_cool

# ==============================================================================
# 🚀 ฟังก์ชันส่งสัญญาณ IR ไปยัง Tuya Gateway โดยตรง (Direct Local Socket)
# ==============================================================================
def send_ir_direct(ir_code: str, label: str = "") -> bool:
    """
    ส่งสัญญาณ IR Base64 ตรงไปยัง Tuya S16 Gateway ผ่านพอร์ต 6668 โดยไม่ผ่าน Home Assistant
    """
    if not ir_code or not isinstance(ir_code, str):
        print("❌ รหัส IR ไม่ถูกต้อง")
        return False

    print(f"\n📡 [Direct IR] กำลังเชื่อมต่อ Tuya Gateway: {GATEWAY_IP}")
    if label:
        print(f"🎯 คำสั่ง: {label}")
    print(f"📦 รหัส Base64 ({len(ir_code)} ตัวอักษร): {ir_code[:30]}...{ir_code[-15:]}")

    try:
        gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=3.4)
        target = tinytuya.Device(SUB_NODE_CID, cid=SUB_NODE_CID, parent=gw) if SUB_NODE_CID else gw

        # Tuya IR DP 201 ใช้ nowait=True เพราะคำสั่ง send_ir ไม่ส่ง ACK กลับ
        payload = json.dumps({
            "control": "send_ir",
            "type": 0,
            "head": "",
            "key1": "1" + ir_code
        })

        target.set_value(201, payload, nowait=True)
        print("✅ ยิงสัญญาณ IR ตรงผ่าน Tuya Gateway สำเร็จเรียบร้อย!")
        return True

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่งสัญญาณตรง: {e}")
        print("\n💡 คำแนะนำ:")
        print("  1. ตรวจสอบว่า Home Assistant ใน Docker หรือ Tuya Smart App เปิดค้างอยู่หรือไม่")
        print("     (Tuya Gateway รองรับเพียง 1 connection พร้อมกันบน Port 6668)")
        print(f"  2. ตรวจสอบว่าคอมพิวเตอร์สามารถ ping ไปยัง {GATEWAY_IP} ได้ปกติ")
        return False

# ==============================================================================
# 🎮 ส่วนควบคุมหลักและ CLI Interface
# ==============================================================================
def control_ac(brand_or_cmd: str, action: str = None, mode: str = "cool", fan: str = "auto"):
    """
    ฟังก์ชันหลักสำหรับสั่งงานแอร์แบบยิงตรง
    - brand_or_cmd: 'carrier', 'eminent', หรือ 'direct' (สำหรับยิง base64 ตรง)
    - action: อุณหภูมิ (17-30), 'off', 'on', 'cool_25', หรือ raw base64 string
    """
    brand_or_cmd = brand_or_cmd.lower().strip()

    # กรณีที่ 1: ยิงรหัส Base64 ตรงๆ
    if brand_or_cmd in ["direct", "raw", "test"]:
        code_to_send = action if action else brand_or_cmd
        send_ir_direct(code_to_send, label="Raw Base64 Code")
        return

    # กรณีที่ 2: สั่งงานตามยี่ห้อ (carrier / eminent)
    if brand_or_cmd not in ["carrier", "eminent"]:
        print(f"❌ ยี่ห้อ '{brand_or_cmd}' ไม่ถูกต้อง (รองรับ: carrier, eminent, หรือ direct <code_base64>)")
        return

    if action is None:
        print("❌ กรุณาระบุคำสั่ง เช่น 25, off, on")
        return

    action_str = str(action).lower().strip()

    # ตรวจสอบคำสั่งปิดเครื่อง
    if action_str in ["off", "power_off", "poweroff"]:
        code = IR_CODES[brand_or_cmd].get("power_off")
        label = f"{brand_or_cmd.upper()} -> ปิดเครื่อง (Power Off)"
        send_ir_direct(code, label=label)
        return

    # ตรวจสอบคำสั่งเปิดเครื่อง
    if action_str in ["on", "power_on", "poweron"]:
        code = IR_CODES[brand_or_cmd].get("power_on")
        label = f"{brand_or_cmd.upper()} -> เปิดเครื่อง (Power On)"
        send_ir_direct(code, label=label)
        return

    # ตรวจสอบอุณหภูมิ (ตัวเลข 17 - 30)
    if action_str.isdigit():
        temp = int(action_str)
        if 17 <= temp <= 30:
            code = build_carrier_code(temp=temp, mode=mode, fan=fan)
            label = f"{brand_or_cmd.upper()} -> อุณหภูมิ {temp}°C (โหมด: {mode}, พัดลม: {fan})"
            send_ir_direct(code, label=label)
        else:
            print(f"❌ รองรับอุณหภูมิ 17 - 30°C (ระบุมา: {temp})")
        return

    # ตรวจสอบคำสั่งตามชื่อคีย์ในตาราง (เช่น cool_25, auto_24)
    if action_str in IR_CODES[brand_or_cmd]:
        code = IR_CODES[brand_or_cmd][action_str]
        label = f"{brand_or_cmd.upper()} -> {action_str}"
        send_ir_direct(code, label=label)
        return

    print(f"❌ ไม่พบคำสั่ง '{action_str}' สำหรับ {brand_or_cmd}")

if __name__ == "__main__":
    print("==========================================================")
    print(" 📡 Tuya Direct IR AC Controller (Standalone / No HA)")
    print("==========================================================")
    
    args = sys.argv[1:]
    if len(args) == 0:
        print("ตัวอย่างการสั่งงานตรง (Direct Local Socket):")
        print("  python tunya/control_ac.py carrier 24         # สั่ง Carrier 24°C โหมด Cool")
        print("  python tunya/control_ac.py carrier 25 auto    # สั่ง Carrier 25°C โหมด Auto")
        print("  python tunya/control_ac.py carrier off        # สั่งปิด Carrier")
        print("  python tunya/control_ac.py carrier on         # สั่งเปิด Carrier (25°C)")
        print("  python tunya/control_ac.py eminent 25         # สั่ง Eminent 25°C")
        print("  python tunya/control_ac.py eminent off        # สั่งปิด Eminent")
        print("  python tunya/control_ac.py direct <BASE64>    # ยิงรหัส Base64 ใดๆ ทดสอบทันที")
        print("==========================================================")
        # รันยิงทดสอบ Carrier 24°C ตรงๆ ทันที
        print("\n🚀 กำลังยิงทดสอบ Carrier 24°C ตรงๆ ทันที...")
        control_ac("carrier", 24)
    elif len(args) == 1:
        # ถ้าระบุแค่อุณหภูมิหรือคำสั่ง เช่น '24' หรือ 'off' ให้ default เป็น carrier
        if args[0].isdigit() or args[0] in ["off", "on"]:
            control_ac("carrier", args[0])
        else:
            control_ac(args[0])
    elif len(args) == 2:
        control_ac(args[0], args[1])
    elif len(args) >= 3:
        control_ac(args[0], args[1], mode=args[2], fan=args[3] if len(args) > 3 else "auto")
