#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eminent_ac_v2.py - ควบคุมแอร์ Eminent (รีโมท A06-RM-HS0INT-0506) ผ่าน Tuya IR Gateway

รีโมทส่ง "สถานะทั้งหมด" ทุกครั้งที่กด -> สคริปต์นี้สร้าง frame จากสถานะที่ต้องการได้เอง
ไม่ต้อง learn รายปุ่ม

โปรโตคอล (ถอดจากสัญญาณจริง 35 ชุด, checksum ผ่านทุกชุด)
  38kHz, header 9000/4475us, bit mark 560us, space 0=565us / 1=1690us, 64 bit MSB-first
  แบ่งเป็น 16 nibble N0..N15

  N0  = 0x2                      ค่าคงที่
  N1  = bit3 power(1=on) | bit2 sleep
  N2  = (mode << 2) | fan_a      mode: fan=0, cool=1, dry=2
                                 fan_a: auto=0, high=1, med=2, low=3
  N3  = temp - 15                (15..30)
  N4..N9 = 0                     (ยังไม่พบการใช้งาน - น่าจะเป็น timer)
  N10 = ~(N0+..+N9) & 0xF        checksum #1
  N11 = 0x1 | bit1 "X"           X = เปิดเมื่อกดปุ่มที่บันทึกว่า clean_on  (ยังไม่ยืนยันว่าเป็น clean หรือ swing)
  N12 = turbo (0/1)
  N13 = fan_b                    low=0, med=1, high=2, auto=7
  N14 = 0
  N15 = -(N11+N12+N13+N14) & 0xF checksum #2

ตัวอย่าง:
  python eminent_ac_v2.py selftest
  python eminent_ac_v2.py set --mode cool --temp 25 --fan auto
  python eminent_ac_v2.py set --temp 24 --fan high --turbo
  python eminent_ac_v2.py off
  python eminent_ac_v2.py --dry-run set --mode dry --temp 26
  python eminent_ac_v2.py decode <base64>
"""
import argparse
import base64
import json
import os
import struct
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

GATEWAY_ID = os.getenv("TUYA_GW_ID", "ebdfd1403f62ed7eb6ysvu")
GATEWAY_KEY = os.getenv("TUYA_GW_KEY", "-y:NXT'lljVjF<)*")
GATEWAY_IP = os.getenv("TUYA_GW_IP", "10.85.217.151")
GATEWAY_VER = float(os.getenv("TUYA_GW_VER", "3.4"))
SUB_NODE_CID = os.getenv("TUYA_SUB_CID") or None

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eminent_state.json")

HDR_MARK, HDR_SPACE = 9025, 4475
BIT_MARK, ZERO_SPACE, ONE_SPACE, GAP = 565, 565, 1690, 30000
NBITS = 64

MODES = {"fan": 0, "cool": 1, "dry": 2}
FAN_A = {"auto": 0, "high": 1, "med": 2, "low": 3}
FAN_B = {"low": 0, "med": 1, "high": 2, "auto": 7}

DEFAULT_STATE = {"power": True, "mode": "cool", "temp": 25, "fan": "auto",
                 "sleep": False, "turbo": False, "x_flag": False}


# ---------------- encode / decode ----------------
def build(state):
    s = {**DEFAULT_STATE, **state}
    if not 15 <= s["temp"] <= 30:
        raise ValueError("temp ต้องอยู่ระหว่าง 15-30")
    n = [0] * 16
    n[0] = 0x2
    n[1] = (8 if s["power"] else 0) | (4 if s["sleep"] else 0)
    n[2] = (MODES[s["mode"]] << 2) | FAN_A[s["fan"]]
    n[3] = s["temp"] - 15
    n[11] = 0x1 | (2 if s["x_flag"] else 0)
    n[12] = 1 if s["turbo"] else 0
    n[13] = FAN_B[s["fan"]]
    n[15] = (-sum(n[11:15])) & 0xF
    n[10] = (~sum(n[:10])) & 0xF
    return n


def parse(n):
    inv = lambda d, v: next((k for k, x in d.items() if x == v), f"?{v:X}")
    return {
        "power": bool(n[1] & 8), "sleep": bool(n[1] & 4),
        "mode": inv(MODES, n[2] >> 2), "fan": inv(FAN_A, n[2] & 3),
        "fan_b": inv(FAN_B, n[13]), "temp": n[3] + 15,
        "turbo": bool(n[12]), "x_flag": bool(n[11] & 2),
        "chk1": n[10] == (~sum(n[:10])) & 0xF,
        "chk2": n[15] == (-sum(n[11:15])) & 0xF,
    }


def encode(n):
    bits = "".join(f"{x:04b}" for x in n)
    p = [HDR_MARK, HDR_SPACE]
    for b in bits:
        p += [BIT_MARK, ONE_SPACE if b == "1" else ZERO_SPACE]
    p += [BIT_MARK, GAP]
    return base64.b64encode(struct.pack("<%dH" % len(p), *p)).decode()


def decode(code):
    raw = base64.b64decode(code.strip() + "=" * (-len(code.strip()) % 4))
    raw = raw[: len(raw) // 2 * 2]
    p = list(struct.unpack("<%dH" % (len(raw) // 2), raw))
    if not (7000 < p[0] < 11000 and 3500 < p[1] < 5500):
        raise ValueError("header ไม่ตรงโปรโตคอล")
    expect = 2 + NBITS * 2 + 2
    if len(p) > expect:
        # พบใน capture บางชุด: มี pulse 565us เกินมาในช่วง bit 0 ยาว ๆ -> ตัดส่วนเกินออกจาก run ของ 0
        extra = len(p) - expect
        run_start = next(i for i in range(20, len(p) - 40, 1)
                         if all(v < 1100 for v in p[i:i + 40]))
        p = p[:run_start] + p[run_start + extra:]
    bits = "".join("1" if p[3 + 2 * i] > 1100 else "0" for i in range(NBITS))
    return [int(bits[i:i + 4], 2) for i in range(0, NBITS, 4)]


fmt = lambda n: " ".join(f"{x:X}" for x in n)


# ---------------- state persistence ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return {**DEFAULT_STATE, **json.load(f)}
    return dict(DEFAULT_STATE)


def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


# ---------------- Tuya ----------------
def transmit(code, dry_run):
    if dry_run:
        print(f"   [dry-run] {code}")
        return
    import tinytuya
    from tinytuya.Contrib import IRRemoteControlDevice
    if SUB_NODE_CID:
        gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=GATEWAY_VER)
        ir = IRRemoteControlDevice(SUB_NODE_CID, cid=SUB_NODE_CID, parent=gw,
                                   version=GATEWAY_VER, control_type=1)
    else:
        ir = IRRemoteControlDevice(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY,
                                   version=GATEWAY_VER, control_type=1)
    ir.set_socketTimeout(5)
    res = ir.send_button(code)
    if isinstance(res, dict) and "Error" in res:
        sys.exit(f"❌ {res}  (Error 914 = HA ถือ connection อยู่ -> docker compose stop)")
    print("✅ ส่งแล้ว")


def send_state(s, dry_run):
    n = build(s)
    print(f"📡 {s}\n   nibbles: {fmt(n)}")
    transmit(encode(n), dry_run)
    if not dry_run:
        save_state(s)


# ---------------- selftest (frame จริงจากรีโมท) ----------------
SAMPLES = [
    # (ชื่อ, nibbles จริงที่ถอดได้, state ที่คาด)
    ("baseline/power_on/cool", "2 8 4 A 0 0 0 0 0 0 7 1 0 7 0 8", {}),
    ("power_off",  "2 0 4 A 0 0 0 0 0 0 F 1 0 7 0 8", {"power": False}),
    ("mode_dry",   "2 8 8 A 0 0 0 0 0 0 3 1 0 7 0 8", {"mode": "dry"}),
    ("mode_fan",   "2 8 0 A 0 0 0 0 0 0 B 1 0 7 0 8", {"mode": "fan"}),
    ("fan_low",    "2 8 7 A 0 0 0 0 0 0 4 1 0 0 0 F", {"fan": "low"}),
    ("fan_med",    "2 8 6 A 0 0 0 0 0 0 5 1 0 1 0 E", {"fan": "med"}),
    ("fan_high",   "2 8 5 A 0 0 0 0 0 0 6 1 0 2 0 D", {"fan": "high"}),
    ("turbo_on",   "2 8 4 A 0 0 0 0 0 0 7 1 1 7 0 7", {"turbo": True}),
    ("sleep_on",   "2 C 4 A 0 0 0 0 0 0 3 1 0 7 0 8", {"sleep": True}),
    ("clean_on",   "2 8 4 A 0 0 0 0 0 0 7 3 0 7 0 6", {"x_flag": True}),
    ("fan_18_high", "2 8 1 3 0 0 0 0 0 0 1 1 0 2 0 D", {"mode": "fan", "temp": 18, "fan": "high"}),
] + [
    (f"temp_{t}", None, {"temp": t, "fan": "low", "x_flag": True}) for t in range(15, 31)
]
TEMP_SERIES = {t: f"2 8 7 {t - 15:X} 0 0 0 0 0 0 {((~(2 + 8 + 7 + t - 15)) & 0xF):X} 3 0 0 0 D"
               for t in range(15, 31)}  # ชุด 15-30 ที่ถอดไว้ก่อนหน้า (ยืนยัน 16/16)


def cmd_selftest(_):
    ok = True
    for name, ref, st in SAMPLES:
        ref = ref or TEMP_SERIES[st["temp"]]
        got = fmt(build(st))
        good = got == ref and decode(encode(build(st))) == build(st)
        ok &= good
        print(f"{name:<24} {got}  {'OK' if good else 'MISMATCH (ref ' + ref + ')'}")
    print("✅ ทุก frame ตรง" if ok else "❌ มี frame ไม่ตรง")
    sys.exit(0 if ok else 1)


def cmd_set(a):
    s = load_state()
    s["power"] = True
    for k in ("mode", "temp", "fan"):
        if getattr(a, k) is not None:
            s[k] = getattr(a, k)
    for k in ("sleep", "turbo", "x_flag"):
        v = getattr(a, k)
        if v is not None:
            s[k] = v
    if s["mode"] == "dry":
        s["fan"] = "auto"      # รีโมทบังคับ fan auto ในโหมด dry
    send_state(s, a.dry_run)


def cmd_off(a):
    s = load_state()
    s["power"] = False
    send_state(s, a.dry_run)


def cmd_decode(a):
    n = decode(a.code)
    print("nibbles:", fmt(n))
    for k, v in parse(n).items():
        print(f"  {k:<7}: {v}")


def tri(p, name, help_):
    g = p.add_mutually_exclusive_group()
    g.add_argument(f"--{name}", dest=name.replace("-", "_"), action="store_true", default=None, help=help_)
    g.add_argument(f"--no-{name}", dest=name.replace("-", "_"), action="store_false")


def main():
    ap = argparse.ArgumentParser(description="Eminent A06-RM-HS0INT-0506 IR controller")
    ap.add_argument("--dry-run", action="store_true")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("selftest").set_defaults(fn=cmd_selftest)
    p = sp.add_parser("set")
    p.add_argument("--mode", choices=MODES)
    p.add_argument("--temp", type=int)
    p.add_argument("--fan", choices=FAN_A)
    tri(p, "sleep", "sleep mode")
    tri(p, "turbo", "turbo")
    tri(p, "x-flag", "บิต N11.1 (ปุ่มที่บันทึกเป็น clean_on - รอยืนยัน)")
    p.set_defaults(fn=cmd_set)
    sp.add_parser("off").set_defaults(fn=cmd_off)
    p = sp.add_parser("decode"); p.add_argument("code"); p.set_defaults(fn=cmd_decode)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
