#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ir_studio.py - แอปพลิเคชัน GUI สำหรับกำหนดรายการปุ่มและคัดลอกสัญญาณ IR อัตโนมัติ (Tuya Gateway)
ฟีเจอร์เด่น:
  - กำหนดรายการปุ่มล่วงหน้า (Predefine Slots) เช่น พิมพ์หรือเลือกเทมเพลตแอร์
  - บันทึกเรียงทีละช่องอัตโนมัติ (Step-by-Step Auto Sequence)
  - เซฟลงไฟล์ .txt อัตโนมัติทันทีที่จับได้แต่ละช่อง (ฟอร์แมตเดียวกับ eminent_cool_codes.txt)
  - คัดลอกรหัส Base64 ลง Clipboard อัตโนมัติ
  - ทดสอบยิงสัญญาณจริงไปยังแอร์ได้ทันที (Test Send)
"""

import base64
import json
import os
import struct
import sys
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

try:
    import winsound
except ImportError:
    winsound = None

try:
    import tinytuya
    from tinytuya.Contrib import IRRemoteControlDevice
except ImportError:
    messagebox.showerror(
        "ไม่พบไลบรารี",
        "กรุณารันผ่าน python ใน virtual environment:\n.venv\\Scripts\\python.exe ir_studio.py",
    )
    sys.exit(1)

# ค่า Config Gateway
DEFAULT_GW_ID = os.getenv("TUYA_GW_ID", "ebdfd1403f62ed7eb6ysvu")
DEFAULT_GW_KEY = os.getenv("TUYA_GW_KEY", "-y:NXT'lljVjF<)*")
DEFAULT_GW_IP = os.getenv("TUYA_GW_IP", "10.85.217.151")
DEFAULT_GW_VER = 3.4

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TXT_FILE = os.path.join(HERE, "captured_codes.txt")
DEFAULT_JSON_FILE = os.path.join(HERE, "ir_profile.json")

# เทมเพลตเริ่มต้น
PRESET_TEMPLATES = {
    "Eminent AC (Cool 15-30°C + โหมดครบ)": [
        "power_on",
        "power_off",
        *[f"cool_{t}" for t in range(15, 31)],
        "mode_cool",
        "mode_dry",
        "mode_fan",
        "fan_auto",
        "fan_low",
        "fan_med",
        "fan_high",
        "turbo_on",
        "sleep_on",
        "swing_toggle",
    ],
    "แอร์ทั่วไป (Cool 16-30°C + พัดลม)": [
        "power_on",
        "power_off",
        *[f"cool_{t}" for t in range(16, 31)],
        "fan_auto",
        "fan_low",
        "fan_med",
        "fan_high",
        "mode_cool",
        "mode_dry",
        "mode_fan",
    ],
    "พัดลม / ทีวี (พื้นฐาน)": [
        "power",
        "speed_1",
        "speed_2",
        "speed_3",
        "oscillate",
        "timer",
    ],
}


def b64_to_pulses(code: str):
    """แปลง Base64 กลับเป็นชุด Microsecond Pulses"""
    try:
        raw = base64.b64decode(code.strip() + "=" * (-len(code.strip()) % 4))
        raw = raw[: len(raw) // 2 * 2]
        return list(struct.unpack("<%dH" % (len(raw) // 2), raw))
    except Exception:
        return []


def get_nibbles_str(code: str):
    """ดึงค่า Nibbles สำหรับโปรโตคอล Eminent 64-bit"""
    pulses = b64_to_pulses(code)
    if len(pulses) >= 130 and (7000 < pulses[0] < 11000) and (3500 < pulses[1] < 5500):
        try:
            bits = "".join("1" if pulses[3 + 2 * i] > 1100 else "0" for i in range(64))
            nibbles = [int(bits[i : i + 4], 2) for i in range(0, 64, 4)]
            return "nibbles: " + " ".join(f"{n:X}" for n in nibbles)
        except Exception:
            pass
    return f"pulses: {len(pulses)}"


def analyze_code(code: str):
    """วิเคราะห์และถอดรหัสสัญญาณ"""
    pulses = b64_to_pulses(code)
    if not pulses:
        return "⚠️ รูปแบบ Base64 ไม่ถูกต้อง"

    info = [f"Pulses: {len(pulses)} ค่า", f"Header: Mark {pulses[0]}µs / Space {pulses[1]}µs"]
    if len(pulses) >= 130 and (7000 < pulses[0] < 11000) and (3500 < pulses[1] < 5500):
        try:
            bits = "".join("1" if pulses[3 + 2 * i] > 1100 else "0" for i in range(64))
            nibbles = [int(bits[i : i + 4], 2) for i in range(0, 64, 4)]
            hex_str = " ".join(f"{n:X}" for n in nibbles)
            temp = nibbles[3] + 15 if len(nibbles) > 3 else "?"
            info.append("โปรโตคอล: Eminent 64-bit")
            info.append(f"Nibbles: [{hex_str}] ({temp}°C)")
        except Exception:
            pass
    elif len(pulses) >= 140 and (3800 < pulses[0] < 5000) and (3800 < pulses[1] < 5000):
        info.append("โปรโตคอล: Toshiba / Carrier AC (72-bit)")

    return " | ".join(info)


class IRStudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tuya IR Studio - ตัวช่วยบันทึกสัญญาณ IR ทีละช่องลงไฟล์ .txt")
        self.geometry("980x720")
        self.minsize(820, 580)

        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.ir_device = None
        self.is_learning = False
        self.seq_running = False

        self.txt_path = tk.StringVar(value=DEFAULT_TXT_FILE)
        self.button_slots = []  # list of button_id strings in order
        self.captured_data = {}  # {button_id: {"code": ..., "time": ...}}

        self.auto_copy = tk.BooleanVar(value=True)
        self.auto_save_txt = tk.BooleanVar(value=True)
        self.sound_beep = tk.BooleanVar(value=True)

        self.load_initial_data()
        self.build_ui()
        self.write_txt_file()
        self.connect_gateway_async()

    def load_initial_data(self):
        """โหลดข้อมูลตั้งต้นจาก JSON หรือกำหนดปุ่มเริ่มต้น"""
        # เริ่มด้วยเทมเพลต Eminent
        self.button_slots = list(PRESET_TEMPLATES["Eminent AC (Cool 15-30°C + โหมดครบ)"])

        if os.path.exists(DEFAULT_JSON_FILE):
            try:
                with open(DEFAULT_JSON_FILE, "r", encoding="utf-8") as f:
                    self.captured_data = json.load(f)
            except Exception:
                self.captured_data = {}

        # เติมปุ่มจาก eminent_ac_v3.py ถ้ามี
        v3_path = os.path.join(HERE, "eminent_ac_v3.py")
        if os.path.exists(v3_path):
            try:
                import re

                with open(v3_path, "r", encoding="utf-8") as f:
                    matches = re.findall(r'"([a-zA-Z0-9_]+)":\s*"([A-Za-z0-9+/=]{40,})"', f.read())
                    for k, v in matches:
                        if k not in self.captured_data:
                            self.captured_data[k] = {"code": v, "time": "จาก v3"}
                        if k not in self.button_slots:
                            self.button_slots.append(k)
            except Exception:
                pass

    def save_all_files(self):
        """บันทึกทั้งไฟล์ .json และ .txt ทันที"""
        # 1. บันทึก JSON
        try:
            with open(DEFAULT_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(self.captured_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"JSON save error: {e}")

        # 2. บันทึก TXT ถ้าเปิดใช้งาน
        if self.auto_save_txt.get():
            self.write_txt_file()

    def write_txt_file(self):
        """เขียนไฟล์ .txt ตามฟอร์แมตเดียวกับ eminent_cool_codes.txt"""
        path = self.txt_path.get()
        if not path:
            return

        lines = [
            "# ======================================================================",
            f"# IR CODES PROFILE - อัปเดตล่าสุด: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Gateway: {DEFAULT_GW_IP} ({DEFAULT_GW_ID})",
            "# รูปแบบ: [ชื่อปุ่ม]  nibbles: ...",
            "#          รหัส Tuya Base64",
            "# ======================================================================\n",
        ]

        count_captured = 0
        for btn_id in self.button_slots:
            data = self.captured_data.get(btn_id, {})
            code = data.get("code", "")
            if code:
                count_captured += 1
                nibbles_info = get_nibbles_str(code)
                lines.append(f"[{btn_id}]  {nibbles_info}")
                lines.append(f"{code}\n")
            else:
                lines.append(f"# [{btn_id}]  (ยังไม่มีสัญญาณ)\n")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self.lbl_status.config(
                text=f"💾 อัปเดตไฟล์ .txt อัตโนมัติแล้ว ({count_captured}/{len(self.button_slots)} ปุ่ม)"
            )
        except Exception as e:
            self.lbl_status.config(text=f"⚠️ เขียนไฟล์ .txt ไม่สำเร็จ: {e}")

    def build_ui(self):
        # 1. Top Header Bar
        top_bar = ttk.Frame(self, padding=8)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        self.lbl_gw = ttk.Label(
            top_bar,
            text=f"📡 เกตเวย์: {DEFAULT_GW_IP} ({DEFAULT_GW_ID})",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_gw.pack(side=tk.LEFT)

        self.lbl_conn = ttk.Label(top_bar, text="⏳ กำลังเชื่อมต่อ...", foreground="orange")
        self.lbl_conn.pack(side=tk.LEFT, padx=12)

        btn_reconn = ttk.Button(top_bar, text="🔄 เชื่อมต่อใหม่", command=self.connect_gateway_async)
        btn_reconn.pack(side=tk.RIGHT, padx=4)

        # 2. TXT File Settings Bar
        txt_bar = ttk.Frame(self, padding=(8, 4), style="Card.TFrame")
        txt_bar.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(txt_bar, text="📄 ไฟล์ .txt ปลายทาง:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        ent_txt = ttk.Entry(txt_bar, textvariable=self.txt_path, width=50)
        ent_txt.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        btn_browse = ttk.Button(txt_bar, text="📂 เลือกไฟล์...", command=self.browse_txt_file)
        btn_browse.pack(side=tk.LEFT, padx=4)

        btn_open_txt = ttk.Button(txt_bar, text="👁️ เปิดไฟล์ .txt", command=self.open_current_txt)
        btn_open_txt.pack(side=tk.LEFT, padx=4)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        # 3. Main Paned Window
        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # === Left Frame: Button Slots ===
        left_frame = ttk.Frame(main_paned, width=380)
        main_paned.add(left_frame, weight=1)

        list_header = ttk.Frame(left_frame)
        list_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(list_header, text="📑 ช่องสัญญาณที่กำหนดไว้", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        btn_edit_list = ttk.Button(list_header, text="⚙️ จัดการรายการปุ่ม...", command=self.open_list_editor)
        btn_edit_list.pack(side=tk.RIGHT)

        # Treeview for slots
        tree_scroll = ttk.Scrollbar(left_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(
            left_frame,
            columns=("no", "status", "info"),
            show="headings",
            yscrollcommand=tree_scroll.set,
            selectmode="browse",
        )
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("no", text="#")
        self.tree.heading("status", text="สถานะ")
        self.tree.heading("info", text="ชื่อปุ่มสัญญาณ")
        self.tree.column("no", width=40, anchor=tk.CENTER)
        self.tree.column("status", width=75, anchor=tk.CENTER)
        self.tree.column("info", width=220, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # === Right Frame: Capture & Action ===
        right_frame = ttk.Frame(main_paned, padding=8)
        main_paned.add(right_frame, weight=2)

        # Selected Header
        self.lbl_selected_title = ttk.Label(
            right_frame, text="ช่องที่เลือก: -", font=("Segoe UI", 12, "bold")
        )
        self.lbl_selected_title.pack(anchor=tk.W, pady=(0, 8))

        # Big Sequence Action Frame
        seq_box = ttk.LabelFrame(right_frame, text="🎬 โหมดบันทึกเรียงทีละช่องอัตโนมัติ (Sequential Record)", padding=10)
        seq_box.pack(fill=tk.X, pady=(0, 8))

        seq_btn_frame = ttk.Frame(seq_box)
        seq_btn_frame.pack(fill=tk.X, pady=(0, 6))

        self.btn_start_seq = ttk.Button(
            seq_btn_frame,
            text="▶️ เริ่มบันทึกเรียงช่อง (Auto Sequence)",
            command=self.toggle_sequence_mode,
        )
        self.btn_start_seq.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_learn_one = ttk.Button(
            seq_btn_frame,
            text="📡 จับสัญญาณเฉพาะช่องนี้",
            command=self.start_learning_single,
        )
        self.btn_learn_one.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_test_send = ttk.Button(
            seq_btn_frame,
            text="🚀 ทดสอบยิง (Test Send)",
            command=self.test_send_signal,
        )
        self.btn_test_send.pack(side=tk.LEFT)

        self.lbl_countdown = ttk.Label(
            seq_box,
            text="พร้อมเริ่มบันทึก",
            font=("Segoe UI", 11, "bold"),
            foreground="#0066cc",
        )
        self.lbl_countdown.pack(anchor=tk.W, pady=4)

        # Options
        opt_box = ttk.Frame(right_frame)
        opt_box.pack(fill=tk.X, pady=(0, 6))
        ttk.Checkbutton(opt_box, text="💾 บันทึกลง .txt อัตโนมัติ", variable=self.auto_save_txt).pack(
            side=tk.LEFT, padx=(0, 15)
        )
        ttk.Checkbutton(opt_box, text="📋 คัดลอก Base64 ลง Clipboard", variable=self.auto_copy).pack(
            side=tk.LEFT, padx=(0, 15)
        )
        ttk.Checkbutton(opt_box, text="🔔 เสียงเตือน Beep", variable=self.sound_beep).pack(side=tk.LEFT)

        # Code Box
        code_box = ttk.LabelFrame(right_frame, text="🔑 รหัส Base64 ของช่องนี้", padding=8)
        code_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        code_top = ttk.Frame(code_box)
        code_top.pack(fill=tk.X, pady=(0, 4))
        btn_copy = ttk.Button(code_top, text="📋 คัดลอกรหัส", command=self.copy_current_code)
        btn_copy.pack(side=tk.LEFT)
        btn_clear = ttk.Button(code_top, text="🗑️ ล้างรหัสช่องนี้", command=self.clear_current_code)
        btn_clear.pack(side=tk.LEFT, padx=5)

        self.txt_code = tk.Text(code_box, height=5, wrap=tk.CHAR, font=("Consolas", 10))
        self.txt_code.pack(fill=tk.BOTH, expand=True, pady=4)

        # Analysis Box
        ana_box = ttk.LabelFrame(right_frame, text="🔍 การวิเคราะห์โปรโตคอล (Protocol Breakdown)", padding=6)
        ana_box.pack(fill=tk.X, pady=(0, 6))
        self.lbl_analysis = ttk.Label(ana_box, text="ยังไม่มีข้อมูลสัญญาณ", font=("Segoe UI", 9))
        self.lbl_analysis.pack(anchor=tk.W)

        # 4. Bottom Status Bar
        bottom_bar = ttk.Frame(self, padding=4)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_status = ttk.Label(bottom_bar, text="พร้อมทำงาน", foreground="gray")
        self.lbl_status.pack(side=tk.LEFT)

        btn_export = ttk.Button(bottom_bar, text="📤 ส่งออก Python Dict", command=self.export_python_dict)
        btn_export.pack(side=tk.RIGHT, padx=4)

        self.refresh_tree()

    def connect_gateway_async(self):
        """เชื่อมต่อ Tuya Gateway ใน Background Thread"""
        self.lbl_conn.config(text="⏳ กำลังเชื่อมต่อ...", foreground="orange")

        def _worker():
            try:
                ir = IRRemoteControlDevice(
                    DEFAULT_GW_ID,
                    DEFAULT_GW_IP,
                    DEFAULT_GW_KEY,
                    version=DEFAULT_GW_VER,
                    control_type=1,
                )
                ir.set_socketTimeout(3)
                st = ir.status()
                if isinstance(st, dict) and "Error" in st:
                    err = st.get("Error")
                    self.after(
                        0,
                        lambda: self.lbl_conn.config(
                            text=f"❌ เชื่อมต่อผิดพลาด ({err})", foreground="red"
                        ),
                    )
                    self.ir_device = None
                else:
                    self.ir_device = ir
                    self.after(
                        0,
                        lambda: self.lbl_conn.config(
                            text="🟢 เชื่อมต่อสำเร็จ (พร้อมใช้งาน)", foreground="green"
                        ),
                    )
            except Exception as e:
                self.after(
                    0, lambda: self.lbl_conn.config(text=f"❌ ข้อผิดพลาด: {e}", foreground="red")
                )
                self.ir_device = None

        threading.Thread(target=_worker, daemon=True).start()

    def refresh_tree(self):
        """อัปเดตรายการช่องสัญญาณในตาราง"""
        selected = self.tree.selection()
        cur_id = selected[0] if selected else None

        self.tree.delete(*self.tree.get_children())
        for idx, btn_id in enumerate(self.button_slots, 1):
            has_code = btn_id in self.captured_data and bool(self.captured_data[btn_id].get("code"))
            status = "🟢 มีรหัสแล้ว" if has_code else "⚪ ว่าง (รอจับ)"
            self.tree.insert("", tk.END, iid=btn_id, values=(idx, status, btn_id))

        if cur_id and self.tree.exists(cur_id):
            self.tree.selection_set(cur_id)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])

    def on_tree_select(self, event):
        """เมื่อคลิกเลือกช่องสัญญาณ"""
        selected = self.tree.selection()
        if not selected:
            return
        btn_id = selected[0]
        self.lbl_selected_title.config(text=f"ช่องที่เลือก: [{btn_id}]")

        code = self.captured_data.get(btn_id, {}).get("code", "")
        self.txt_code.delete("1.0", tk.END)
        self.txt_code.insert("1.0", code)

        if code:
            self.lbl_analysis.config(text=analyze_code(code))
        else:
            self.lbl_analysis.config(text="ยังไม่มีข้อมูลสัญญาณในช่องนี้")

    def toggle_sequence_mode(self):
        """เริ่มหรือหยุดโหมดบันทึกเรียงช่องอัตโนมัติ"""
        if self.seq_running:
            self.seq_running = False
            self.btn_start_seq.config(text="▶️ เริ่มบันทึกเรียงช่อง (Auto Sequence)")
            self.lbl_countdown.config(text="⏹️ หยุดการบันทึกต่อเนื่องแล้ว", foreground="black")
            return

        if not self.ir_device:
            messagebox.showerror("ไม่ได้เชื่อมต่อ", "เกตเวย์ยังไม่ได้เชื่อมต่อ กรุณารอสักครู่")
            return

        self.seq_running = True
        self.btn_start_seq.config(text="⏹️ หยุดบันทึกต่อเนื่อง (Stop)")
        threading.Thread(target=self._sequence_worker, daemon=True).start()

    def _sequence_worker(self):
        """Worker วนลูปจับสัญญาณทีละช่อง"""
        slots = list(self.button_slots)
        start_idx = 0

        # ถ้าผู้ใช้เลือกช่องไว้ ให้เริ่มจากช่องนั้น
        selected = self.tree.selection()
        if selected and selected[0] in slots:
            start_idx = slots.index(selected[0])

        for i in range(start_idx, len(slots)):
            if not self.seq_running:
                break

            btn_id = slots[i]
            # ไฮไลต์แถวใน Treeview
            self.after(0, lambda b=btn_id: self.select_and_see(b))

            # แจ้งเตือนนับถอยหลัง
            for s in range(10, 0, -1):
                if not self.seq_running:
                    break
                msg = f"👉 [ช่อง {i+1}/{len(slots)}] กรุณากดปุ่ม [{btn_id}] ที่รีโมทจ่อใส่เกตเวย์ ({s}s)"
                self.after(0, lambda m=msg: self.lbl_countdown.config(text=m, foreground="#0066cc"))
                time.sleep(1)

            if not self.seq_running:
                break

            # ดึงรหัส
            try:
                code = self.ir_device.receive_button(timeout=1)
                if isinstance(code, dict) and "Error" in code:
                    self.after(
                        0,
                        lambda b=btn_id: self.lbl_countdown.config(
                            text=f"⚠️ ข้ามปุ่ม [{b}] (หมดเวลา/ไม่พบสัญญาณ)", foreground="red"
                        ),
                    )
                elif code:
                    self.after(0, lambda b=btn_id, c=code: self.handle_captured_slot(b, c))
                    time.sleep(1.2)  # พักเล็กน้อยก่อนไปช่องถัดไป
            except Exception as e:
                print(f"Receive error on {btn_id}: {e}")

        self.seq_running = False
        self.after(
            0,
            lambda: self.btn_start_seq.config(text="▶️ เริ่มบันทึกเรียงช่อง (Auto Sequence)"),
        )
        self.after(
            0,
            lambda: self.lbl_countdown.config(
                text="🎉 บันทึกครบทุกช่องเรียบร้อยแล้ว!", foreground="green"
            ),
        )

    def select_and_see(self, btn_id):
        if self.tree.exists(btn_id):
            self.tree.selection_set(btn_id)
            self.tree.see(btn_id)

    def start_learning_single(self):
        """จับสัญญาณเฉพาะช่องที่เลือกอยู่ช่องเดียว"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("แจ้งเตือน", "กรุณาเลือกช่องสัญญาณที่ต้องการก่อน")
            return
        if not self.ir_device:
            messagebox.showerror("ไม่ได้เชื่อมต่อ", "เกตเวย์ยังไม่ได้เชื่อมต่อ")
            return

        btn_id = selected[0]
        self.btn_learn_one.config(state=tk.DISABLED)

        def _worker():
            try:
                for s in range(12, 0, -1):
                    self.after(
                        0,
                        lambda sec=s: self.lbl_countdown.config(
                            text=f"👉 กรุณากดปุ่ม [{btn_id}] ที่รีโมท ({sec}s)", foreground="#0066cc"
                        ),
                    )
                    time.sleep(1)

                code = self.ir_device.receive_button(timeout=1)
                if isinstance(code, dict) and "Error" in code:
                    self.after(
                        0,
                        lambda: self.lbl_countdown.config(
                            text=f"⚠️ หมดเวลา ({code.get('Error')})", foreground="red"
                        ),
                    )
                elif code:
                    self.after(0, lambda: self.handle_captured_slot(btn_id, code))
                else:
                    self.after(
                        0,
                        lambda: self.lbl_countdown.config(
                            text="⚠️ ไม่ได้รับสัญญาณ", foreground="red"
                        ),
                    )
            except Exception as e:
                self.after(
                    0, lambda: self.lbl_countdown.config(text=f"❌ เกิดข้อผิดพลาด: {e}", foreground="red")
                )
            finally:
                self.after(0, lambda: self.btn_learn_one.config(state=tk.NORMAL))

        threading.Thread(target=_worker, daemon=True).start()

    def handle_captured_slot(self, btn_id, code):
        """จัดการเมื่อจับสัญญาณได้ในช่องนั้นๆ"""
        if self.sound_beep and winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.captured_data[btn_id] = {
            "code": code,
            "time": now_str,
            "analysis": analyze_code(code),
        }

        # บันทึกทั้งไฟล์ JSON และ .txt ทันที!
        self.save_all_files()

        # อัปเดตช่องแสดงผล
        self.txt_code.delete("1.0", tk.END)
        self.txt_code.insert("1.0", code)
        self.lbl_analysis.config(text=analyze_code(code))

        # Auto Copy
        if self.auto_copy.get():
            self.clipboard_clear()
            self.clipboard_append(code)

        self.lbl_countdown.config(
            text=f"✅ บันทึก [{btn_id}] เรียบร้อยแล้ว!", foreground="green"
        )
        self.refresh_tree()

    def test_send_signal(self):
        """ทดสอบยิงสัญญาณของช่องปัจจุบันไปยังแอร์"""
        code = self.txt_code.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("แจ้งเตือน", "ช่องนี้ยังไม่มีรหัสสัญญาณ ไม่สามารถทดสอบยิงได้")
            return
        if not self.ir_device:
            messagebox.showerror("ไม่ได้เชื่อมต่อ", "เกตเวย์ยังไม่ได้เชื่อมต่อ")
            return

        def _send():
            try:
                self.after(
                    0, lambda: self.lbl_status.config(text="📡 กำลังส่งคำสั่งไปยังเกตเวย์...")
                )
                res = self.ir_device.send_button(code)
                self.after(
                    0,
                    lambda: self.lbl_status.config(
                        text=f"🚀 ส่งสัญญาณเรียบร้อย! (ผลลัพธ์: {res})"
                    ),
                )
            except Exception as e:
                self.after(0, lambda: self.lbl_status.config(text=f"❌ ยิงสัญญาณไม่สำเร็จ: {e}"))

        threading.Thread(target=_send, daemon=True).start()

    def copy_current_code(self):
        code = self.txt_code.get("1.0", tk.END).strip()
        if code:
            self.clipboard_clear()
            self.clipboard_append(code)
            self.lbl_status.config(text="📋 คัดลอกรหัสลง Clipboard เรียบร้อยแล้ว")
        else:
            messagebox.showinfo("แจ้งเตือน", "ไม่มีรหัสให้คัดลอก")

    def clear_current_code(self):
        selected = self.tree.selection()
        if not selected:
            return
        btn_id = selected[0]
        if messagebox.askyesno("ยืนยัน", f"ต้องการลบรหัสในช่อง [{btn_id}] ใช่หรือไม่?"):
            if btn_id in self.captured_data:
                del self.captured_data[btn_id]
                self.save_all_files()
            self.txt_code.delete("1.0", tk.END)
            self.lbl_analysis.config(text="ยังไม่มีข้อมูลสัญญาณ")
            self.refresh_tree()

    def browse_txt_file(self):
        f = filedialog.asksaveasfilename(
            initialdir=HERE,
            initialfile="captured_codes.txt",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if f:
            self.txt_path.set(f)
            self.write_txt_file()

    def open_current_txt(self):
        path = self.txt_path.get()
        if os.path.exists(path):
            os.startfile(path)
        else:
            self.write_txt_file()
            if os.path.exists(path):
                os.startfile(path)

    def open_list_editor(self):
        """หน้าต่างจัดการ / กำหนดรายการปุ่มล่วงหน้า"""
        dialog = tk.Toplevel(self)
        dialog.title("กำหนดรายการปุ่มล่วงหน้า (Predefine Slots)")
        dialog.geometry("480x560")
        dialog.transient(self)
        dialog.grab_set()

        top_f = ttk.Frame(dialog, padding=10)
        top_f.pack(fill=tk.X)

        ttk.Label(top_f, text="เลือกเทมเพลตสำเร็จรูป:").pack(side=tk.LEFT, padx=(0, 5))
        cmb_template = ttk.Combobox(top_f, values=list(PRESET_TEMPLATES.keys()), state="readonly", width=30)
        cmb_template.current(0)
        cmb_template.pack(side=tk.LEFT, padx=5)

        def _apply_template():
            tmpl_name = cmb_template.get()
            if tmpl_name in PRESET_TEMPLATES:
                txt_edit.delete("1.0", tk.END)
                txt_edit.insert("1.0", "\n".join(PRESET_TEMPLATES[tmpl_name]))

        btn_apply_tmpl = ttk.Button(top_f, text="โหลด", command=_apply_template)
        btn_apply_tmpl.pack(side=tk.LEFT)

        mid_f = ttk.Frame(dialog, padding=10)
        mid_f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(mid_f, text="พิมพ์รายชื่อปุ่มที่ต้องการ (บรรทัดละ 1 ปุ่ม):", font=("Segoe UI", 9, "bold")).pack(
            anchor=tk.W, pady=(0, 4)
        )
        txt_edit = tk.Text(mid_f, wrap=tk.NONE, font=("Consolas", 10))
        txt_edit.pack(fill=tk.BOTH, expand=True)
        txt_edit.insert("1.0", "\n".join(self.button_slots))

        bot_f = ttk.Frame(dialog, padding=10)
        bot_f.pack(fill=tk.X)

        def _save_slots():
            raw_text = txt_edit.get("1.0", tk.END).strip()
            new_slots = [line.strip().replace(" ", "_") for line in raw_text.splitlines() if line.strip()]
            if not new_slots:
                messagebox.showerror("ข้อผิดพลาด", "ต้องมีอย่างน้อย 1 ปุ่ม")
                return
            self.button_slots = new_slots
            self.save_all_files()
            self.refresh_tree()
            dialog.destroy()
            messagebox.showinfo("สำเร็จ", f"กำหนดรายการปุ่มล่วงหน้า {len(new_slots)} ช่อง เรียบร้อยแล้ว!")

        ttk.Button(bot_f, text="💾 บันทึกรายการปุ่ม", command=_save_slots).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bot_f, text="ยกเลิก", command=dialog.destroy).pack(side=tk.RIGHT)

    def export_python_dict(self):
        """ส่งออกรหัสเป็น Dictionary สำหรับนำไปแปะใน Python สคริปต์"""
        codes_dict = {k: v.get("code", "") for k, v in self.captured_data.items() if v.get("code")}
        if not codes_dict:
            messagebox.showinfo("แจ้งเตือน", "ยังไม่มีรหัสที่จับได้ในระบบ")
            return

        py_code = "RAW_CODES = {\n"
        for k in self.button_slots:
            if k in codes_dict:
                py_code += f'    "{k}": "{codes_dict[k]}",\n'
        py_code += "}\n"

        self.clipboard_clear()
        self.clipboard_append(py_code)
        messagebox.showinfo(
            "สำเร็จ",
            "คัดลอก Python Dictionary ลงใน Clipboard เรียบร้อยแล้ว! นำไปวางใน eminent_ac.py ได้ทันที",
        )


if __name__ == "__main__":
    app = IRStudioApp()
    app.mainloop()
