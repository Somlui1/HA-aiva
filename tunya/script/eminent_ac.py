#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eminent_ac.py - ควบคุมแอร์ Eminent (รีโมท A06-RM-HS0INT-0506) ผ่าน Tuya IR Gateway (tinytuya)

โปรโตคอลที่ถอดได้จากสัญญาณจริง 16 ชุด (15-30°C):
  - Carrier 38 kHz, Header 9000us mark / 4475us space
  - Bit mark ~560us, '0' space ~565us, '1' space ~1690us, ปิดท้ายด้วย mark + gap
  - 64 bit, ส่ง MSB-first, มองเป็น 16 nibble:  N0..N15
        idx :  0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
        @25 :  2 8 7 A 0 0 0 0 0 0  4  3  0  0  0  D
  - N3  = อุณหภูมิ - 15     (15°C=0x0 ... 30°C=0xF)   [ยืนยันแล้ว 16/16]
  - N10 = checksum = (~ ผลรวม nibble อื่นทั้งหมด) & 0xF  [ยืนยันแล้ว 16/16]
  - nibble อื่น (N0-N2, N4-N9, N11-N15) = mode / fan / swing / power / function
    ยังไม่ทราบความหมาย -> ใช้คำสั่ง learn + analyze เพื่อหาเพิ่ม

คำสั่ง:
  python tunya\script\eminent_ac.py selftest                 ตรวจว่า encoder สร้างรหัสตรงกับที่จับได้ทั้ง 16 ชุด
  python tunya\script\eminent_ac.py temp 25                  ส่งคำสั่งตั้งอุณหภูมิ (สร้างรหัสเอง ไม่ต้อง learn)
  python tunya\script\eminent_ac.py temp 25 --base cool_low  ตั้งอุณหภูมิโดยใช้ state จากปุ่มที่ learn ไว้ (คง mode/fan เดิม)
  python tunya\script\eminent_ac.py learn power_on           จับสัญญาณปุ่มจริงแล้วบันทึกเข้า eminent_codes.json
  python tunya\script\eminent_ac.py send power_on            ส่งรหัสที่ learn ไว้
  python tunya\script\eminent_ac.py list                     แสดงรหัสที่บันทึกไว้ทั้งหมด (พร้อม nibble)
  python tunya\script\eminent_ac.py decode <base64>          ถอดรหัส base64 ของ Tuya
  python tunya\script\eminent_ac.py analyze                  เทียบ nibble ของทุกปุ่มกับ frame อ้างอิง เพื่อหาตำแหน่ง mode/fan/...
  python tunya\script\eminent_ac.py --dry-run temp 25        สร้างรหัสโดยไม่ส่งจริง

หมายเหตุ: Tuya Gateway รับได้ 1 connection -> ถ้า Home Assistant ต่ออยู่ ให้หยุดก่อน (docker compose stop)
"""
import argparse
import base64
import json
import os
import struct
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------- Gateway config (ค่าเดียวกับ ir_copy.py; override ด้วย env ได้) ----------------
GATEWAY_ID = os.getenv("TUYA_GW_ID", "ebdfd1403f62ed7eb6ysvu")
GATEWAY_KEY = os.getenv("TUYA_GW_KEY", "-y:NXT'lljVjF<)*")
GATEWAY_IP = os.getenv("TUYA_GW_IP", "10.85.217.151")
GATEWAY_VER = float(os.getenv("TUYA_GW_VER", "3.4"))
SUB_NODE_CID = os.getenv("TUYA_SUB_CID") or None

CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eminent_codes.json")

# ---------------- Protocol ----------------
HDR_MARK, HDR_SPACE = 9050, 4475
BIT_MARK, ZERO_SPACE, ONE_SPACE = 560, 565, 1690
GAP = 30000
NBITS = 64
TEMP_MIN, TEMP_MAX = 15, 30
TEMP_NIB, CHK_NIB = 3, 10

# frame อ้างอิงที่ถอดจากรีโมทจริง (ที่ 15°C) - nibble อื่นคือ state ตอนที่จับสัญญาณ
BASE_FRAME = [0x2, 0x8, 0x7, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0xE, 0x3, 0x0, 0x0, 0x0, 0xD]

# รหัสต้นฉบับที่จับได้ (ใช้ selftest)
CAPTURED = {
    15: "WiNiETQCNAI0AjQCNAKUBjQCNAI0ApQGNAI0AjQCNAI0AjQCNAI0AjQClAY0ApQGNAKUBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0ApQGNAKUBjQClAY0AjQCNAI0AjQCNAI0ApQGNAKUBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQClAY0ApQGNAI0AjQClAY0AjB1",
    20: "cyNiETQCNAI0AjQCNAKVBjQCNAI0ApUGNAI0AjQCNAI0AjQCNAI0AjQClQY0ApUGNAKVBjQCNAI0ApUGNAI0AjQClQY0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0ApUGNAI0AjQCNAI0ApUGNAI0AjQCNAI0ApUGNAKVBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQClQY0ApUGNAI0AjQClQY0AjB1",
    25: "WiN7EU8CFgJPAhYCTwKHBk8CTwJPAocGTwIWAk8CFgJPAk8CFgJPAhYChwYWAocGFgKHBhYChwYWAk8CFgKHBk8CTwJPAhYCFgJPAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwKHBk8CFgJPAhYCTwIWAk8CFgJPAocGTwKHBk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8ChwZPAocGTwIWAk8ChwZPAjB1",
    30: "WiN7ETUCNQI1AjUCNQKNBjUCNQI1Ao0GNQI1AjUCNQI1AjUCNQI1AjUCjQY1Ao0GNQKNBjUCjQY1Ao0GNQKNBjUCjQY1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1Ao0GNQKNBjUCjQY1Ao0GNQI1AjUCNQI1Ao0GNQKNBjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCjQY1Ao0GNQI1AjUCjQY1AjB1",
}


def b64_to_pulses(code: str):
    raw = base64.b64decode(code.strip() + "=" * (-len(code.strip()) % 4))
    raw = raw[: len(raw) // 2 * 2]
    return list(struct.unpack("<%dH" % (len(raw) // 2), raw))


def pulses_to_b64(pulses):
    return base64.b64encode(struct.pack("<%dH" % len(pulses), *pulses)).decode()


def checksum(nibbles):
    return (~sum(n for i, n in enumerate(nibbles) if i != CHK_NIB)) & 0xF


def decode(code: str):
    """base64 -> list ของ 16 nibble (raise ValueError ถ้าไม่ใช่โปรโตคอลนี้)"""
    p = b64_to_pulses(code)
    if len(p) < 2 + NBITS * 2 or not (7000 < p[0] < 11000 and 3500 < p[1] < 5500):
        raise ValueError(f"ไม่ใช่โปรโตคอล Eminent 64-bit (pulses={len(p)}, header={p[:2]})")
    bits = "".join("1" if p[3 + 2 * i] > 1100 else "0" for i in range(NBITS))
    return [int(bits[i:i + 4], 2) for i in range(0, NBITS, 4)]


def encode(nibbles):
    """list ของ 16 nibble -> base64 (คำนวณ checksum ใหม่ให้อัตโนมัติ)"""
    n = list(nibbles)
    n[CHK_NIB] = checksum(n)
    bits = "".join(f"{x:04b}" for x in n)
    pulses = [HDR_MARK, HDR_SPACE]
    for b in bits:
        pulses += [BIT_MARK, ONE_SPACE if b == "1" else ZERO_SPACE]
    pulses += [BIT_MARK, GAP]
    return pulses_to_b64(pulses)


def fmt(n):
    return " ".join(f"{x:X}" for x in n)


def set_temp(nibbles, temp: int):
    if not TEMP_MIN <= temp <= TEMP_MAX:
        raise ValueError(f"อุณหภูมิต้องอยู่ระหว่าง {TEMP_MIN}-{TEMP_MAX}")
    n = list(nibbles)
    n[TEMP_NIB] = temp - TEMP_MIN
    n[CHK_NIB] = checksum(n)
    return n


# ---------------- Code library ----------------
def load_codes():
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_codes(codes):
    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)


# ---------------- Tuya IR ----------------
def get_ir():
    import tinytuya
    from tinytuya.Contrib import IRRemoteControlDevice

    if SUB_NODE_CID:
        gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=GATEWAY_VER)
        gw.set_socketTimeout(5)
        ir = IRRemoteControlDevice(SUB_NODE_CID, cid=SUB_NODE_CID, parent=gw,
                                   version=GATEWAY_VER, control_type=1)
    else:
        ir = IRRemoteControlDevice(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY,
                                   version=GATEWAY_VER, control_type=1)
    ir.set_socketTimeout(5)
    return ir


def transmit(code: str, dry_run=False, repeat=1):
    print(f"   nibbles: {fmt(decode(code))}")
    if dry_run:
        print(f"   [dry-run] base64: {code}")
        return
    ir = get_ir()
    for i in range(repeat):
        res = ir.send_button(code)
        if isinstance(res, dict) and "Error" in res:
            print(f"❌ ส่งไม่สำเร็จ: {res}")
            print("   ถ้าเป็น Error 914: Home Assistant ถือ connection อยู่ -> docker compose stop ก่อน")
            sys.exit(1)
        if i + 1 < repeat:
            time.sleep(0.3)
    print("✅ ส่งแล้ว")


# ---------------- Commands ----------------
def cmd_selftest(_a):
    ok = True
    for t, code in sorted(CAPTURED.items()):
        got = decode(encode(set_temp(BASE_FRAME, t)))
        ref = decode(code)
        same = got == ref
        ok &= same
        print(f"{t}°C  ref={fmt(ref)}  gen={fmt(got)}  {'OK' if same else 'MISMATCH'}")
    print("✅ selftest ผ่าน" if ok else "❌ selftest ไม่ผ่าน")
    sys.exit(0 if ok else 1)


def cmd_temp(a):
    base = BASE_FRAME
    if a.base:
        codes = load_codes()
        if a.base not in codes:
            sys.exit(f"ไม่พบ '{a.base}' ใน {CODES_FILE} (ใช้ learn ก่อน)")
        base = decode(codes[a.base])
    n = set_temp(base, a.value)
    print(f"🌡  ตั้งอุณหภูมิ {a.value}°C" + (f" (state จาก '{a.base}')" if a.base else ""))
    transmit(encode(n), a.dry_run, a.repeat)


def cmd_learn(a):
    ir = get_ir()
    print(f">> กดปุ่ม '{a.name}' บนรีโมทจ่อ IR gateway ภายใน {a.timeout} วินาที...")
    code = ir.receive_button(timeout=a.timeout)
    if not code or (isinstance(code, dict) and "Error" in code):
        sys.exit(f"❌ ไม่ได้รับสัญญาณ: {code}")
    code = str(code).strip()
    try:
        n = decode(code)
        valid = checksum(n) == n[CHK_NIB]
        print(f"   nibbles: {fmt(n)}   temp={n[TEMP_NIB] + TEMP_MIN}°C   checksum={'OK' if valid else 'ผิด!'}")
    except ValueError as e:
        print(f"⚠️  {e} -> บันทึกเป็น raw (ส่งซ้ำได้ แต่ถอดความหมายไม่ได้)")
    codes = load_codes()
    codes[a.name] = code
    save_codes(codes)
    print(f"💾 บันทึก '{a.name}' แล้ว -> {CODES_FILE}")


def cmd_send(a):
    codes = load_codes()
    if a.name not in codes:
        sys.exit(f"ไม่พบ '{a.name}' ใช้ list ดูรายการ")
    print(f"📡 ส่ง '{a.name}'")
    transmit(codes[a.name], a.dry_run, a.repeat)


def cmd_list(_a):
    codes = load_codes()
    if not codes:
        print("(ยังไม่มีรหัสที่ learn ไว้)")
    for k, v in codes.items():
        try:
            n = decode(v)
            print(f"{k:<20} {fmt(n)}   temp={n[TEMP_NIB] + TEMP_MIN}")
        except ValueError:
            print(f"{k:<20} (raw / ถอดไม่ได้)")


def cmd_decode(a):
    n = decode(a.code)
    print(f"nibbles : {fmt(n)}")
    print(f"temp    : {n[TEMP_NIB] + TEMP_MIN}°C")
    print(f"checksum: {'OK' if checksum(n) == n[CHK_NIB] else 'ผิด'} (คาดว่า {checksum(n):X})")


def cmd_analyze(a):
    codes = load_codes()
    ref = decode(codes[a.ref]) if a.ref else BASE_FRAME
    print(f"อ้างอิง: {a.ref or 'BASE_FRAME'}  ->  {fmt(ref)}")
    print("idx                  " + " ".join(f"{i:X}" for i in range(16)))
    for k, v in codes.items():
        try:
            n = decode(v)
        except ValueError:
            continue
        diff = [i for i in range(16) if n[i] != ref[i] and i not in (TEMP_NIB, CHK_NIB)]
        mark = " ".join(f"{x:X}" if i in diff else "." for i, x in enumerate(n))
        print(f"{k:<20} {mark}   ต่างที่ nibble {diff or '-'}")
    print("\n'.' = เหมือน frame อ้างอิง (ไม่นับ temp/checksum)")


def main():
    ap = argparse.ArgumentParser(description="Eminent A06-RM-HS0INT-0506 IR controller")
    ap.add_argument("--dry-run", action="store_true", help="ไม่ส่งจริง แค่แสดงรหัส")
    ap.add_argument("--repeat", type=int, default=1, help="จำนวนครั้งที่ส่งซ้ำ")
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("selftest").set_defaults(fn=cmd_selftest)
    p = sp.add_parser("temp"); p.add_argument("value", type=int); p.add_argument("--base")
    p.set_defaults(fn=cmd_temp)
    p = sp.add_parser("learn"); p.add_argument("name"); p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(fn=cmd_learn)
    p = sp.add_parser("send"); p.add_argument("name"); p.set_defaults(fn=cmd_send)
    sp.add_parser("list").set_defaults(fn=cmd_list)
    p = sp.add_parser("decode"); p.add_argument("code"); p.set_defaults(fn=cmd_decode)
    p = sp.add_parser("analyze"); p.add_argument("--ref"); p.set_defaults(fn=cmd_analyze)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
