import sys, json, os
import tinytuya
if sys.platform == "win32": sys.stdout.reconfigure(encoding="utf-8")
GATEWAY_ID = "a310acce1e30a9ca83yznt"
GATEWAY_KEY = "-y:NXT'lljVjF<)*"
GATEWAY_IP = "10.85.217.151"
print("==========================================\n       Tuya Zigbee Gateway Controller      \n==========================================")
print(f"Gateway IP : {GATEWAY_IP}\nGateway ID : {GATEWAY_ID}")
# โหลดชื่ออุปกรณ์จาก devices.json (ถ้ามี) map ด้วย node_id/cid
meta = {}
devices_path = os.path.join(os.path.dirname(__file__), "devices.json") if os.path.exists(os.path.join(os.path.dirname(__file__), "devices.json")) else "devices.json"
if os.path.exists(devices_path):
    with open(devices_path, encoding="utf-8") as f:
        for d in json.load(f):
            for k in (d.get("node_id"), d.get("cid"), d.get("id")):
                if k: meta[k] = d
# เชื่อมต่อ gateway ลอง version 3.4 → 3.5 → 3.3
gw, sub_list = None, None
for ver in (3.4, 3.5, 3.3):
    gw = tinytuya.Device(GATEWAY_ID, GATEWAY_IP, GATEWAY_KEY, version=ver)
    gw.set_socketTimeout(5); gw.set_socketRetryLimit(3)
    print(f"\n[1] กำลังตรวจสอบอุปกรณ์ Zigbee (protocol {ver})...")
    sub_list = gw.subdev_query()
    if isinstance(sub_list, dict) and "Error" not in sub_list: break
    print(f"    ✗ ล้มเหลว: {sub_list}")
else:
    sys.exit("ไม่สามารถเชื่อมต่อ Gateway ได้ ตรวจสอบ IP / Local Key / version")
data = sub_list.get("data", sub_list)
online, offline = data.get("online", []) or [], data.get("offline", []) or []
print(f"\n[2] พบอุปกรณ์ทั้งหมด {len(online)+len(offline)} ตัว (online {len(online)} / offline {len(offline)})")
print(f"{'#':<3} {'สถานะ':<8} {'CID':<20} {'ชื่อ':<28} {'Product/Model':<25} Device ID")
print("-"*110)
for i, (cid, st) in enumerate([(c, "ONLINE") for c in online] + [(c, "OFFLINE") for c in offline], 1):
    m = meta.get(cid, {})
    print(f"{i:<3} {st:<8} {cid:<20} {m.get('name','-')[:27]:<28} {(m.get('product_name') or m.get('model') or '-')[:24]:<25} {m.get('id','-')}")
# อ่านสถานะ DPS ของอุปกรณ์ที่ online
print("\n[3] สถานะ DPS ของอุปกรณ์ที่ online")
for cid in online:
    try:
        sub = tinytuya.Device(cid, cid=cid, parent=gw)
        st = sub.status()
        if isinstance(st, dict):
            print(f"  {meta.get(cid,{}).get('name',cid)}: {st.get('dps', st)}")
        else:
            print(f"  {meta.get(cid,{}).get('name',cid)}: ไม่สามารถอ่านค่า DPS ได้โดยตรง (status: {st})")
    except Exception as e:
        print(f"  {cid}: อ่านสถานะไม่ได้ ({e})")
if not meta: print("\n※ ไม่พบ devices.json จึงแสดงได้เฉพาะ CID ให้รัน 'python -m tinytuya wizard' เพื่อดึงชื่ออุปกรณ์")

#bc8d7efffe78a16b