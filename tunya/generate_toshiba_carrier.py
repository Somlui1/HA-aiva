import base64
import json

# ==============================================================================
# Protocol: Toshiba / Carrier AC 72-bit (9-byte) Protocol Generator
# Manufacturer: Toshiba Carrier Corporation (TCTC)
# Reference: IRremoteESP8266 (ir_Toshiba.cpp / ir_Carrier.cpp)
# ==============================================================================

# Tuya Base64 Pulse Encoding Constants (38kHz)
BIT_1 = b'\x26\x02\x40\x06'   # Mark 550us, Space 1600us
BIT_0 = b'\x26\x02\x26\x02'   # Mark 550us, Space 550us
HDR = b'\x10\x11\x10\x11'     # Header: Mark 4368us, Space 4368us
GAP = b'\x1a\x1d'             # Gap between repeat: 7450us
FOOTER = b'\x26\x02\x30\x75'  # Footer: Mark 550us, Space 30000us

def encode_tuya_packet(bytes_9):
    """แปลงชุดไบต์ 9 ตัวให้กลายเป็น Tuya Base64 IR Packet ที่สมบูรณ์"""
    raw = b''
    # ส่ง 2 รอบ (Normal + Repeat) ตามข้อกำหนดของโปรโตคอล Toshiba/Carrier
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

def build_command(temp=25, mode='cool', fan='auto', swing=False, power_off=False):
    """
    สร้างไบต์ 9 ตัวตามโปรโตคอล Toshiba / Carrier
    - temp: 17 ถึง 30 องศาเซลเซียส
    - mode: 'cool', 'dry', 'fan', 'auto'
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

    b7 = 0x00  # Timer / Option flags
    b8 = b0 ^ b1 ^ b2 ^ b3 ^ b4 ^ b5 ^ b6 ^ b7  # XOR Checksum

    return [b0, b1, b2, b3, b4, b5, b6, b7, b8]

def get_base64_command(**kwargs):
    bytes_data = build_command(**kwargs)
    return encode_tuya_packet(bytes_data)

if __name__ == "__main__":
    print("==========================================")
    print("  Toshiba / Carrier 72-bit IR Code Generator")
    print("==========================================")
    
    # 1. แสดงตัวอย่างรหัสปิดแอร์ (ตรงกับที่ผู้ใช้ดูดมา)
    off_code = get_base64_command(power_off=True)
    print("\n[คำสั่งปิดเครื่อง (Power Off)]:")
    print(off_code)

    # 2. สร้างรหัสทำความเย็น 17 - 30 องศา
    print("\n[คำสั่งทำความเย็น 17 - 30 องศา]:")
    for t in range(17, 31):
        code = get_base64_command(temp=t, mode='cool', fan='auto')
        print(f"cool_{t} = \"{code}\"")
