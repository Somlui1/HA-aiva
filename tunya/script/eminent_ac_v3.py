#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eminent_ac_v3.py - Eminent A06-RM-HS0INT-0506 IR controller + ชุดทดสอบ A/B

ทำไมต้อง v3
  v2 สร้าง frame ได้ "bit ตรง" กับสัญญาณที่จับจากรีโมททุกชุด แต่แอร์ไม่เปลี่ยน fan/mode
  -> ปัญหาอาจไม่อยู่ที่การถอดรหัส ต้องแยกให้ได้ว่าเป็นกรณีไหน:
     (A) ส่งสัญญาณดิบที่ learn มาก็ไม่ได้ผล  -> capture ไม่ครบ / แอร์ต้องการมากกว่า 1 frame / ใช้ RF
     (B) สัญญาณดิบได้ผล แต่ frame ที่สร้างไม่ได้ผล -> encoder หรือ timing ผิด
  คำสั่ง `test` ทำการทดลองนี้ทีละปุ่ม แล้วบันทึกผลลง eminent_test_log.txt

คำสั่ง
  python eminent_ac_v3.py test                 ทดสอบ A/B แบบโต้ตอบ (แนะนำให้รันก่อน)
  python eminent_ac_v3.py raw fan_high         ส่งสัญญาณดิบที่จับจากรีโมท
  python eminent_ac_v3.py raw --list
  python eminent_ac_v3.py set --mode cool --temp 24 --fan high
  python eminent_ac_v3.py set --fan high --frames 2      ส่ง frame ซ้ำ 2 ครั้งในสัญญาณเดียว
  python eminent_ac_v3.py off
  python eminent_ac_v3.py decode <base64>
  python eminent_ac_v3.py selftest
  เพิ่ม --dry-run หน้า subcommand เพื่อดูรหัสโดยไม่ส่ง

Frame (16 nibble, MSB-first) - bit ตรงกับรีโมททุกชุดที่จับได้
  N0=2 | N1: b3 power, b2 sleep | N2: (mode<<2)|fanA | N3: temp-15 | N4-9: 0
  N10 = ~sum(N0..N9) | N11: b0=1, b1=X(?) | N12 turbo | N13 fanB | N14 0 | N15 = -sum(N11..N14)
  mode: fan0 cool1 dry2 ; fanA: auto0 high1 med2 low3 ; fanB: low0 med1 high2 auto7
"""
import argparse, base64, json, os, struct, sys, time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

GATEWAY_ID = os.getenv("TUYA_GW_ID", "ebdfd1403f62ed7eb6ysvu")
GATEWAY_KEY = os.getenv("TUYA_GW_KEY", "-y:NXT'lljVjF<)*")
GATEWAY_IP = os.getenv("TUYA_GW_IP", "10.85.217.151")
GATEWAY_VER = float(os.getenv("TUYA_GW_VER", "3.4"))
SUB_NODE_CID = os.getenv("TUYA_SUB_CID") or None

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "eminent_state.json")
LOG_FILE = os.path.join(HERE, "eminent_test_log.txt")

RAW = {
"cool_25_auto": "QSOUETQCNAI0AjQCNAKMBjQCNAI0AowGNAI0AjQCNAI0AjQCNAI0AjQCjAY0AjQCNAI0AjQCjAY0AjQCNAKMBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAKMBjQCjAY0AowGNAI0AjQCNAI0AjQCNAKMBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAKMBjQCjAY0AowGNAI0AjQCNAI0AjQCNAI0AjQCjAY0AjQCNAI0AjQCNAI0AjB1",
"power_off": "KCOtETUCNQI1AjUCNQKFBjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUChQY1AjUCNQI1AjUChQY1AjUCNQKFBjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AoUGNQKFBjUChQY1AoUGNQI1AjUCNQI1AjUCNQKFBjUCNQI1AjUCNQI1AjUCNQI1AjUCNQKFBjUChQY1AoUGNQI1AjUCNQI1AjUCNQI1AjUChQY1AjUCNQI1AjUCNQI1AjB1",
"power_on": "QSOUETUCNQI1AjUCNQKJBjUCNQI1AokGNQI1AjUCNQI1AjUCNQI1AjUCiQY1AjUCNQI1AjUCiQY1AjUCNQKJBjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQI1AjUCNQKJBjUCiQY1AokGNQI1AjUCNQI1AjUCNQKJBjUCNQI1AjUCNQI1AjUCNQI1AjUCNQKJBjUCiQY1AokGNQI1AjUCNQI1AjUCNQI1AjUCiQY1AjUCNQI1AjUCNQI1AjB1",
"mode_dry": "QSOUETQCNAI0AjQCNAKRBjQCNAI0ApEGNAI0AjQCNAI0AjQCNAKRBjQCNAI0AjQCNAI0AjQCkQY0AjQCNAKRBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCkQY0ApEGNAI0AjQCNAI0AjQCNAKRBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAKRBjQCkQY0ApEGNAI0AjQCNAI0AjQCNAI0AjQCkQY0AjQCNAI0AjQCNAI0AjB1",
"mode_fan": "KCOtETMCMwJxAjMCMwJpBnECMwIzAmkGcQIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCaQYzAjMCcQJpBjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwJxAmkGMwIzAnECaQYzAmkGMwIzAnECMwIzAjMCMwJpBjMCMwIzAjMCMwIzAjMCMwIzAjMCMwJpBjMCaQYzAmkGMwIzAnECMwJxAjMCMwIzAjMCaQYzAjMCMwIzAjMCMwIzAjB1",
"fan_low": "KCOUETYCNgI2AjYCNgJ7BjYCNgI2AnsGNgI2AjYCNgI2AjYCNgI2AjYCewY2AnsGNgJ7BjYCewY2AjYCNgJ7BjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgJ7BjYCNgI2AjYCNgI2AjYCNgI2AjYCNgJ7BjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCewY2AnsGNgJ7BjYCewY2AjB1",
"fan_med": "KCOUETcCNwI3AjcCNwJ3BjcCNwI3AncGNwI3AjcCNwI3AjcCNwI3AjcCdwY3AncGNwI3AjcCdwY3AjcCNwJ3BjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwJ3BjcCNwI3AncGNwI3AjcCNwI3AjcCNwJ3BjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AjcCNwI3AncGNwI3AjcCNwI3AjcCNwI3AjcCdwY3AncGNwJ3BjcCNwI3AjB1",
"fan_high": "QSOUETMCMwIzAjMCMwJzBjMCMwIzAnMGMwIzAjMCMwIzAjMCcQIzAnECcwZxAjMCMwJzBnECcwZxAjMCcQJzBnECMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCMwJzBjMCcwYzAjMCMwIzAjMCMwIzAjMCMwJzBjMCMwIzAjMCMwIzAjMCMwIzAjMCMwIzAjMCcwYzAjMCMwIzAjMCMwIzAjMCMwIzAjMCcwYzAnMGMwIzAjMCcwYzAjB1",
"turbo_on": "KCOtETYCNgI2AjYCNgKDBjYCNgI2AoMGNgI2AjYCNgI2AjYCNgI2AjYCgwY2AjYCNgI2AjYCgwY2AjYCNgKDBjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgI2AjYCNgKDBjYCgwY2AoMGNgI2AjYCNgI2AjYCNgKDBjYCNgI2AjYCNgI2AjYCgwY2AjYCNgKDBjYCgwY2AoMGNgI2AjYCNgI2AjYCNgI2AjYCNgI2AoMGNgKDBjYCgwY2AjB1",
"sleep_on": "KCOtETQCNAI0AjQCNAKOBjQCNAI0Ao4GNAKOBjQCNAI0AjQCNAI0AjQCjgY0AjQCNAI0AjQCjgY0AjQCNAKOBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCjgY0Ao4GNAI0AjQCNAI0AjQCNAKOBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAKOBjQCjgY0Ao4GNAI0AjQCNAI0AjQCNAI0AjQCjgY0AjQCNAI0AjQCNAI0AjB1",
"clean_on": "KCOUEXECMgIyAjICMgJwBjICMgJxAnAGMgIyAjICMgJxAjICMgIyAjICcAYyAjICMgIyAjICcAYyAjICMgJwBjICMgJxAjICcQIyAjICMgIyAjICMgIyAjICMgIyAjICMgIyAjICMgIyAjICMgIyAnECMgJxAjICMgIyAjICMgIyAjICMgIyAjICMgIyAjICMgIyAnECMgJxAjICMgIyAjICMgIyAjICMgJwBjICcAYyAnAGMgIyAjICMgIyAnAGMgJwBjICMgIyAjICMgIyAjICMgIyAjICMgJwBjICcAYyAnAGcQIyAjICMgIyAjICMgIyAjICMgIyAnAGcQJwBjICMgJxAjB1",
"fanmode_18_high": "QSOUETQCNAI0AjQCNAKIBjQCNAI0AogGNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAKIBjQCNAI0AjQCNAKIBjQCiAY0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AjQCNAI0AogGNAI0AjQCNAI0AjQCNAKIBjQCNAI0AjQCNAI0AjQCNAI0AjQCNAJxAjQCiAY0AjQCNAI0AjQCNAI0AjQCNAI0AjQCiAY0AogGNAI0AjQCiAY0AjB1",
"low_25_x": "WiN7EU8CFgJPAhYCTwKHBk8CTwJPAocGTwIWAk8CFgJPAk8CFgJPAhYChwYWAocGFgKHBhYChwYWAk8CFgKHBk8CTwJPAhYCFgJPAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwKHBk8CFgJPAhYCTwIWAk8CFgJPAocGTwKHBk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8CFgJPAhYCTwIWAk8ChwZPAocGTwIWAk8ChwZPAjB1",
}

# frame ที่ถอดได้ของแต่ละ raw (ใช้อ้างอิง/selftest)
RAW_STATE = {
    "cool_25_auto": {},
    "power_off": {"power": False},
    "power_on": {},
    "mode_dry": {"mode": "dry"},
    "mode_fan": {"mode": "fan"},
    "fan_low": {"fan": "low"},
    "fan_med": {"fan": "med"},
    "fan_high": {"fan": "high"},
    "turbo_on": {"turbo": True},
    "sleep_on": {"sleep": True},
    "clean_on": {"x_flag": True},
    "fanmode_18_high": {"mode": "fan", "temp": 18, "fan": "high"},
    "low_25_x": {"fan": "low", "x_flag": True},
}

HDR_MARK, HDR_SPACE = 9025, 4500
BIT_MARK, ZERO_SPACE, ONE_SPACE, GAP = 565, 565, 1670, 30000
MODES = {"fan": 0, "cool": 1, "dry": 2}
FAN_A = {"auto": 0, "high": 1, "med": 2, "low": 3}
FAN_B = {"low": 0, "med": 1, "high": 2, "auto": 7}
DEFAULT = {"power": True, "mode": "cool", "temp": 25, "fan": "auto",
           "sleep": False, "turbo": False, "x_flag": False}


def build(state):
    s = {**DEFAULT, **state}
    if not 15 <= s["temp"] <= 30:
        raise ValueError("temp 15-30")
    n = [0] * 16
    n[0] = 2
    n[1] = (8 if s["power"] else 0) | (4 if s["sleep"] else 0)
    n[2] = (MODES[s["mode"]] << 2) | FAN_A[s["fan"]]
    n[3] = s["temp"] - 15
    n[11] = 1 | (2 if s["x_flag"] else 0)
    n[12] = 1 if s["turbo"] else 0
    n[13] = FAN_B[s["fan"]]
    n[15] = (-sum(n[11:15])) & 0xF
    n[10] = (~sum(n[:10])) & 0xF
    return n


def frame_pulses(n):
    p = [HDR_MARK, HDR_SPACE]
    for b in "".join(f"{x:04b}" for x in n):
        p += [BIT_MARK, ONE_SPACE if b == "1" else ZERO_SPACE]
    return p + [BIT_MARK, GAP]


def encode(n, frames=1):
    p = frame_pulses(n) * frames
    return base64.b64encode(struct.pack("<%dH" % len(p), *p)).decode()


def pulses(code):
    raw = base64.b64decode(code.strip() + "=" * (-len(code.strip()) % 4))
    raw = raw[: len(raw) // 2 * 2]
    return list(struct.unpack("<%dH" % (len(raw) // 2), raw))


def clean_pulses(p):
    """แก้ capture ที่มี pulse เกิน (พบใน power_on/off: 135 แทน 132) โดยตัดออกจากช่วง bit 0 ยาว"""
    want = 132
    if len(p) > want:
        extra = len(p) - want
        start = next(i for i in range(3, len(p) - 40) if i % 2 == 1 and all(v < 1100 for v in p[i:i + 40]))
        p = p[:start + 10] + p[start + 10 + extra:]
    return p


def decode(code):
    p = clean_pulses(pulses(code))
    if not (7000 < p[0] < 11000 and 3500 < p[1] < 5500):
        raise ValueError("header ไม่ตรง")
    bits = "".join("1" if p[3 + 2 * i] > 1100 else "0" for i in range(64))
    return [int(bits[i:i + 4], 2) for i in range(0, 64, 4)]


fmt = lambda n: " ".join(f"{x:X}" for x in n)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return {**DEFAULT, **json.load(f)}
    return dict(DEFAULT)


def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


_IR = None
def ir():
    global _IR
    if _IR is None:
        import tinytuya
        from tinytuya.Contrib import IRRemoteControlDevice
        if SUB_NODE_CID:
            gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=GATEWAY_VER)
            _IR = IRRemoteControlDevice(SUB_NODE_CID, cid=SUB_NODE_CID, parent=gw,
                                        version=GATEWAY_VER, control_type=1)
        else:
            _IR = IRRemoteControlDevice(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY,
                                        version=GATEWAY_VER, control_type=1)
        _IR.set_socketTimeout(5)
    return _IR


def transmit(code, dry):
    if dry:
        print(f"   [dry-run] {code[:60]}...")
        return
    res = ir().send_button(code)
    if isinstance(res, dict) and "Error" in res:
        sys.exit(f"❌ {res}  (Error 914 = HA ถือ connection -> docker compose stop)")
    print("   ✅ ส่งแล้ว")


# ---------------- commands ----------------
def cmd_selftest(_):
    ok = True
    for k, st in RAW_STATE.items():
        got, ref = build(st), decode(RAW[k])
        same = got == ref and decode(encode(got)) == got
        ok &= same
        print(f"{k:<16} raw={fmt(ref)}  gen={fmt(got)}  {'OK' if same else 'MISMATCH'}")
    print("✅ encoder ตรงกับรีโมททุกชุด" if ok else "❌ มีชุดไม่ตรง")
    sys.exit(0 if ok else 1)


def cmd_raw(a):
    if a.list or not a.name:
        for k in RAW:
            print(f"{k:<16} {fmt(decode(RAW[k]))}")
        return
    print(f"📡 raw '{a.name}'  {fmt(decode(RAW[a.name]))}")
    transmit(RAW[a.name], a.dry_run)


def cmd_set(a):
    s = load_state()
    s["power"] = True
    for k in ("mode", "temp", "fan", "sleep", "turbo", "x_flag"):
        v = getattr(a, k)
        if v is not None:
            s[k] = v
    if s["mode"] == "dry":
        s["fan"] = "auto"
    n = build(s)
    print(f"📡 {s}\n   nibbles: {fmt(n)}  frames={a.frames}")
    transmit(encode(n, a.frames), a.dry_run)
    if not a.dry_run:
        save_state(s)


def cmd_off(a):
    s = load_state(); s["power"] = False
    print(f"📡 OFF  {fmt(build(s))}")
    transmit(encode(build(s), a.frames), a.dry_run)
    if not a.dry_run:
        save_state(s)


def cmd_decode(a):
    p = pulses(a.code)
    n = decode(a.code)
    print(f"pulses={len(p)}  nibbles: {fmt(n)}")
    print(f"chk1={'OK' if n[10] == (~sum(n[:10])) & 0xF else 'BAD'}  chk2={'OK' if n[15] == (-sum(n[11:15])) & 0xF else 'BAD'}")


TESTS = [
    # (ชื่อ, คำอธิบาย, วิธีเตรียมแอร์ก่อนส่ง)
    ("fan_high", "พัดลม HIGH", "เปิดแอร์ COOL พัดลม LOW ด้วยรีโมทจริง"),
    ("fan_low", "พัดลม LOW", "ตั้งพัดลม HIGH ด้วยรีโมทจริง"),
    ("fan_med", "พัดลม MED", "ตั้งพัดลม LOW ด้วยรีโมทจริง"),
    ("mode_fan", "โหมด FAN", "ตั้งโหมด COOL ด้วยรีโมทจริง"),
    ("mode_dry", "โหมด DRY", "ตั้งโหมด COOL ด้วยรีโมทจริง"),
    ("turbo_on", "TURBO เปิด", "ปิด turbo ด้วยรีโมทจริง"),
]
VARIANTS = [("RAW (ดิบจากรีโมท)", lambda k: RAW[k]),
            ("GEN x1 frame", lambda k: encode(build(RAW_STATE[k]), 1)),
            ("GEN x2 frame", lambda k: encode(build(RAW_STATE[k]), 2))]


def cmd_test(a):
    log = [f"=== Eminent A/B test {time.strftime('%Y-%m-%d %H:%M:%S')} ==="]
    print("ตอบ y = แอร์เปลี่ยนตามที่คาด, n = ไม่เปลี่ยน, b = ได้ยินเสียง beep แต่ไม่เปลี่ยน, s = ข้าม\n")
    for key, desc, prep in TESTS:
        for vname, mk in VARIANTS:
            input(f"\n[{desc}] {vname}\n  เตรียม: {prep}  แล้วกด Enter เพื่อส่ง...")
            transmit(mk(key), a.dry_run)
            ans = input("  ผล (y/n/b/s) + หมายเหตุ: ").strip()
            log.append(f"{key:<10} | {vname:<18} | {ans}")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n\n")
    print("\n" + "\n".join(log))
    print(f"\n💾 บันทึกแล้ว -> {LOG_FILE}  (copy ผลนี้ส่งกลับมา)")


def tri(p, name):
    d = name.replace("-", "_")
    g = p.add_mutually_exclusive_group()
    g.add_argument(f"--{name}", dest=d, action="store_true", default=None)
    g.add_argument(f"--no-{name}", dest=d, action="store_false")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--frames", type=int, default=1, choices=[1, 2, 3])
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("selftest").set_defaults(fn=cmd_selftest)
    sp.add_parser("test").set_defaults(fn=cmd_test)
    p = sp.add_parser("raw"); p.add_argument("name", nargs="?", choices=list(RAW))
    p.add_argument("--list", action="store_true"); p.set_defaults(fn=cmd_raw)
    p = sp.add_parser("set")
    p.add_argument("--mode", choices=MODES); p.add_argument("--temp", type=int)
    p.add_argument("--fan", choices=FAN_A)
    p.add_argument("--frames", type=int, choices=[1, 2, 3], default=1)
    for t in ("sleep", "turbo", "x-flag"):
        tri(p, t)
    p.set_defaults(fn=cmd_set)
    p = sp.add_parser("off"); p.add_argument("--frames", type=int, choices=[1, 2, 3], default=1)
    p.set_defaults(fn=cmd_off)
    p = sp.add_parser("decode"); p.add_argument("code"); p.set_defaults(fn=cmd_decode)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
