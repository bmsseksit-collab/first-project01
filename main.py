import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from pynput import keyboard
import time
import os
import threading
import queue
from PIL import Image, ImageDraw, ImageTk
import pystray
from pystray import MenuItem as item

# --- Config ---
kb_controller = keyboard.Controller()
shortcuts = {}
is_running = True
current_keys = ""
last_type_time = 0
listener = None
app_has_focus = False
task_queue = queue.Queue()
current_mods = set()
current_key = ""
last_triggered_shortcut = ""
last_trigger_time = 0
tray_icon = None
window_icon_image = None
ui_action_queue = queue.Queue()

# --- Load/Save ---
def load_data():
    global shortcuts
    if os.path.exists("autotext_config.json"):
        try:
            with open("autotext_config.json", 'r', encoding='utf-8') as f:
                shortcuts = json.load(f)
            refresh_table()
        except: pass

def save_data():
    try:
        with open("autotext_config.json", 'w', encoding='utf-8') as f:
            json.dump(shortcuts, f, ensure_ascii=False, indent=4)
    except: pass

# --- Parse Hotkey ---
def parse_hotkey(text):
    parts = text.lower().split("+")
    mods = []
    key = ""
    for p in parts:
        p = p.strip()
        if p in ["ctrl", "shift", "alt"]:
            mods.append(p)
        else:
            key = p
    return tuple(mods), key

# --- Background execution ---
def execute_action(shortcut, text):
    try:
        for k in [keyboard.Key.ctrl, keyboard.Key.shift, keyboard.Key.alt]:
            kb_controller.release(k)
        for _ in range(len(shortcut)):
            kb_controller.press(keyboard.Key.backspace)
            kb_controller.release(keyboard.Key.backspace)
            time.sleep(0.01)
        time.sleep(0.05)
        for ch in text:
            if ch == "\n":
                kb_controller.press(keyboard.Key.shift)
                kb_controller.press(keyboard.Key.enter)
                kb_controller.release(keyboard.Key.enter)
                kb_controller.release(keyboard.Key.shift)
            else:
                kb_controller.type(ch)
    except Exception as e:
        print(f"Error: {e}")

def queue_worker():
    while True:
        task = task_queue.get()
        if task is None: break
        shortcut, text = task
        execute_action(shortcut, text)
        task_queue.task_done()

threading.Thread(target=queue_worker, daemon=True).start()

# --- Focus ---
def check_focus_loop():
    global app_has_focus
    try:
        app_has_focus = bool(root.focus_displayof())
    except:
        app_has_focus = False
    root.after(200, check_focus_loop)

# --- Listener ---
def on_press(key):
    global current_keys, last_type_time, current_mods, current_key, last_triggered_shortcut, last_trigger_time
    if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
        current_mods.add("ctrl")
    elif key in [keyboard.Key.shift, keyboard.Key.shift_r]:
        current_mods.add("shift")
    elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]:
        current_mods.add("alt")

    if getattr(key, 'name', '') == 'f12' and "ctrl" in current_mods:
        root.after(0, toggle_status)
        return

    if app_has_focus or not is_running:
        return

    try:
        current_time = time.time()
        if current_time - last_type_time > 1.0:
            current_keys = ""
        last_type_time = current_time

        char = ""
        if hasattr(key, 'char') and key.char is not None:
            raw_char = key.char
            if len(raw_char) == 1 and 1 <= ord(raw_char) <= 26:
                char = chr(ord('a') + ord(raw_char) - 1)
            else:
                char = raw_char.lower()
        elif hasattr(key, 'vk'):
            if 65 <= key.vk <= 90:
                char = chr(key.vk + 32)
            elif 96 <= key.vk <= 105:
                char = str(key.vk - 96)
            elif key.vk == 110:
                char = "."

        if char == "ใ": char = "."

        current_key = char
        
        def can_trigger(shortcut_key):
            nonlocal current_time
            global last_triggered_shortcut, last_trigger_time
            if last_triggered_shortcut == shortcut_key and (current_time - last_trigger_time) < 0.35:
                return False
            last_triggered_shortcut = shortcut_key
            last_trigger_time = current_time
            return True

        for hotkey_text, v in shortcuts.items():
            mods, k = parse_hotkey(hotkey_text)
            if k == current_key and set(mods) == current_mods:
                if can_trigger(hotkey_text):
                    task_queue.put((hotkey_text, v))
                    current_key = ""
                    current_keys = ""
                    return

        if char:
            current_keys += char
            ordered_shortcuts = sorted(shortcuts.items(), key=lambda kv: len(kv[0]), reverse=True)
            for k, v in ordered_shortcuts:
                if current_keys.endswith(k):
                     if can_trigger(k):
                        current_keys = ""
                        task_queue.put((k, v))
                        break
        elif key == keyboard.Key.backspace:
            current_keys = current_keys[:-1]
        elif key in [keyboard.Key.space, keyboard.Key.enter, keyboard.Key.tab]:
            current_keys = ""
    except: pass

def on_release(key):
    global current_mods
    if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
        current_mods.discard("ctrl")
    elif key in [keyboard.Key.shift, keyboard.Key.shift_r]:
        current_mods.discard("shift")
    elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]:
        current_mods.discard("alt")

# --- UI Functions ---
def toggle_status():
    global is_running
    is_running = not is_running
    btn_toggle.config(text="●  ระบบทำงาน (ON)" if is_running else "○  ปิดระบบ (OFF)",
                      bg="#2ECC71" if is_running else "#E74C3C")

def cmd_add():
    k = entry_kw.get().strip(); p = entry_ph.get().strip()
    if not k or not p: return
    mods = []
    if var_ctrl.get(): mods.append("Ctrl")
    if var_alt.get(): mods.append("Alt")
    if var_shift.get(): mods.append("Shift")
    k_full = "+".join(mods + [k.upper()]) if mods else k
    shortcuts[k_full] = p
    save_data()
    refresh_table()
    entry_kw.delete(0, tk.END)
    entry_ph.delete(0, tk.END)
    var_ctrl.set(False); var_alt.set(False); var_shift.set(False)

def cmd_delete():
    to_del = [tree.item(i, 'values')[1] for i in tree.get_children() if tree.item(i, 'values')[0]=="☑"]
    if not to_del:
        messagebox.showwarning("แจ้งเตือน", "กรุณาติ๊ก ☑ เลือกรายการก่อน")
        return
    for k in to_del:
        shortcuts.pop(k, None)
    save_data()
    refresh_table()

def cmd_export():
    f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
    if f:
        with open(f,'w',encoding='utf-8') as file:
            json.dump(shortcuts, file, ensure_ascii=False, indent=4)

def cmd_import():
    f = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
    if f:
        with open(f,'r',encoding='utf-8-sig') as file:
            shortcuts.update(json.load(file))
        save_data()
        refresh_table()

def refresh_table():
    for i in tree.get_children():
        tree.delete(i)
    for k,v in shortcuts.items():
        tree.insert("",tk.END,values=("☐",k,v))

def on_tree_select(event):
    sel = tree.selection()
    if sel:
        item = tree.item(sel[0], 'values')
        entry_kw.delete(0, tk.END)
        entry_kw.insert(0, item[1].split('+')[-1])  # แก้ไข Key ให้ไม่ซ้ำ modifier
        entry_ph.delete(0, tk.END)
        entry_ph.insert(0, item[2])
        mods, key = parse_hotkey(item[1])
        var_ctrl.set("ctrl" in mods)
        var_alt.set("alt" in mods)
        var_shift.set("shift" in mods)

def toggle_check(row):
    v = tree.item(row,'values')
    tree.item(row, values=("☑" if v[0]=="☐" else "☐", v[1], v[2]))

def api_paste(event=None):
    widget = root.focus_get()
    if isinstance(widget, tk.Entry):
        try:
            content = root.clipboard_get()
            if widget.selection_present():
                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            widget.insert(tk.INSERT, content)
            return "break"
        except:
            widget.event_generate("<<Paste>>")
            return "break"
    return None

def api_copy(event=None):
    widget = root.focus_get()
    if isinstance(widget, tk.Entry):
        try:
            widget.event_generate("<<Copy>>")
            return "break"
        except:
            return None
    return None

def direct_select_all(event=None):
    widget = root.focus_get()
    if isinstance(widget, tk.Entry):
        widget.select_range(0, tk.END)
        widget.icursor(tk.END)
    return "break"

def show_context_menu(event, widget):
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="วาง (Paste)", command=api_paste)
    menu.add_command(label="คัดลอก (Copy)", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="เลือกทั้งหมด (Select All)", command=direct_select_all)
    menu.tk_popup(event.x_root, event.y_root)


def create_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 12, 56, 60), fill="#f4b183", outline="#6b3e26", width=2)
    draw.polygon([(18, 16), (26, 4), (30, 20)], fill="#f4b183", outline="#6b3e26")
    draw.polygon([(46, 16), (38, 4), (34, 20)], fill="#f4b183", outline="#6b3e26")
    draw.ellipse((22, 30, 28, 36), fill="#2b2b2b")
    draw.ellipse((36, 30, 42, 36), fill="#2b2b2b")
    draw.polygon([(32, 40), (28, 45), (36, 45)], fill="#d95f5f")
    return img

def show_window_from_tray(icon=None, item=None):
    ui_action_queue.put("restore")

def _restore_window():
    global tray_icon
    root.deiconify()
    if tray_icon is not None:
        try:
            tray_icon.stop()
        except:
            pass
        tray_icon = None
    root.after(50, root.lift)
    root.after(60, lambda: root.attributes("-topmost", True))
    root.after(120, lambda: root.attributes("-topmost", False))

def hide_to_tray(event=None):
    root.withdraw()
    setup_tray_icon()

def quit_app(icon=None, item=None):
    ui_action_queue.put("quit")

def setup_tray_icon():
    global tray_icon
    if tray_icon is not None:
        return
    menu = (
        item("เปิดโปรแกรม", show_window_from_tray),
        item("ออกจากโปรแกรม", quit_app),
    )
    tray_icon = pystray.Icon("bms_program", create_tray_image(), "BMS Program", menu)

    def run_icon():
        try:
            tray_icon.run()
        finally:
            pass

    threading.Thread(target=run_icon, daemon=True).start()

def process_ui_actions():
    try:
        while True:
            action = ui_action_queue.get_nowait()
            if action == "restore":
                _restore_window()
            elif action == "quit":
                try:
                    if tray_icon:
                        tray_icon.stop()
                except:
                    pass
                root.destroy()
    except queue.Empty:
        pass
    root.after(100, process_ui_actions)

def on_window_state_change(event=None):
    if root.state() == "iconic":
        hide_to_tray()

# --- UI Setup ---
root = tk.Tk()
root.title("BMS Program")
root.configure(bg="#eef2f7")
root.geometry("1080x720")
root.minsize(900, 620)
window_icon_image = ImageTk.PhotoImage(create_tray_image())
root.iconphoto(True, window_icon_image)

# --- Bind Clipboard ---
root.bind_class("Entry","<Control-v>", api_paste)
root.bind_class("Entry","<Control-V>", api_paste)
root.bind_class("Entry","<Control-a>", direct_select_all)
root.bind_class("Entry","<Control-A>", direct_select_all)
root.bind_class("Entry","<Control-c>", api_copy)
root.bind_class("Entry","<Control-C>", api_copy)

title_frame = tk.Frame(root, bg="#eef2f7")
title_frame.pack(fill="x", padx=20, pady=(16,6))
tk.Label(title_frame, text="BMS Program", font=("Segoe UI", 22, "bold"), fg="#1f2937").pack(side="left", anchor="w")
cat_track = tk.Canvas(title_frame, width=420, height=32, bg="#f5f7fb", highlightthickness=0)
cat_track.pack(side="left", padx=20, fill="x", expand=True)
cat_sprite = cat_track.create_text(12, 16, text="🐈", font=("Segoe UI Emoji", 18))
btn_toggle = tk.Button(title_frame, text="●  ระบบทำงาน (ON)", command=toggle_status, bg="#16a34a", fg="white", activebackground="#15803d", relief="flat", width=20)
btn_toggle.pack(side="right")

# --- Input Frame พร้อมปุ่ม วาง และ คลุมดำ ---
input_frame = tk.LabelFrame(root,text="จัดการคำสั่ง", padx=15, pady=22, bg="#f8fafc", fg="#1f2937")
input_frame.pack(fill="x", padx=20, pady=10)
input_frame.grid_columnconfigure(2, weight=1)
input_frame.grid_columnconfigure(4, weight=5)
input_frame.grid_columnconfigure(7, weight=0)
tk.Label(input_frame,text="Hotkey:").grid(row=0,column=0)
modifier_frame = tk.Frame(input_frame); modifier_frame.grid(row=0,column=1,sticky="w", padx=5)

entry_kw = tk.Entry(input_frame,width=8); entry_kw.grid(row=0,column=2,padx=5, sticky="ew")
var_ctrl = tk.BooleanVar(); var_alt = tk.BooleanVar(); var_shift = tk.BooleanVar()
tk.Checkbutton(modifier_frame,text="Ctrl",variable=var_ctrl).pack(side="left")
tk.Checkbutton(modifier_frame,text="Alt",variable=var_alt).pack(side="left")
tk.Checkbutton(modifier_frame,text="Shift",variable=var_shift).pack(side="left")

tk.Label(input_frame,text="Keyword:").grid(row=0,column=3)
entry_ph = tk.Entry(input_frame,width=50); entry_ph.grid(row=0,column=4,padx=5, sticky="ew")
for ent in (entry_kw, entry_ph):
    ent.bind("<Control-v>", api_paste)
    ent.bind("<Control-V>", api_paste)
    ent.bind("<Control-a>", direct_select_all)
    ent.bind("<Control-A>", direct_select_all)
    ent.bind("<Control-c>", api_copy)
    ent.bind("<Control-C>", api_copy)
tk.Button(input_frame,text="วาง", command=api_paste,bg="#2563eb",fg="white",activebackground="#1d4ed8",relief="flat",width=6).grid(row=0,column=5,padx=2)
tk.Button(input_frame,text="คลุมดำ", command=direct_select_all,bg="#7c3aed",fg="white",activebackground="#6d28d9",relief="flat",width=6).grid(row=0,column=6,padx=2)
tk.Button(input_frame,text="บันทึก",command=cmd_add,bg="#059669",fg="white",activebackground="#047857",relief="flat",width=8).grid(row=0,column=7,padx=5)

# --- Treeview + Action Buttons ---
tree_frame = tk.Frame(root); tree_frame.pack(fill="both",expand=True,padx=20)
tree = ttk.Treeview(tree_frame,columns=("check","kw","ph"),show="headings", height=16)
tree.heading("check",text="เลือก"); tree.heading("kw",text="Hotkey"); tree.heading("ph",text="Keyword")
tree.column("check",width=50,anchor="center", stretch=False); tree.column("kw",width=180, stretch=True); tree.column("ph",width=720, stretch=True)
sb = ttk.Scrollbar(tree_frame,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=sb.set)
tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y") 
tree.bind('<<TreeviewSelect>>',on_tree_select)
tree.bind('<Button-1>', lambda e: root.after(10, lambda: toggle_check(tree.identify_row(e.y))))

select_frame = tk.Frame(root,pady=5); select_frame.pack(fill="x", padx=20)
tk.Button(select_frame,text="เลือกทั้งหมด",command=lambda:[tree.item(i,values=("☑",tree.item(i,'values')[1],tree.item(i,'values')[2])) for i in tree.get_children()]).pack(side="left",padx=2)
tk.Button(select_frame,text="ยกเลิกการเลือก",command=lambda:[tree.item(i,values=("☐",tree.item(i,'values')[1],tree.item(i,'values')[2])) for i in tree.get_children()]).pack(side="left",padx=2)

status_frame = tk.Frame(root,pady=5); status_frame.pack(fill="x", padx=20)
tk.Label(status_frame, text="(Ctrl+F12 = เปิด/ปิดด่วน)").pack(side="left")

action_frame = tk.Frame(root,pady=10); action_frame.pack(fill="x", padx=20)
tk.Button(action_frame,text="ลบรายการ",command=cmd_delete,bg="#f44336",fg="white",width=12).pack(side="left")
tk.Label(action_frame,text=" | สำรองข้อมูล: ").pack(side="left", padx=5)
tk.Button(action_frame,text="ส่งออก (Export)",command=cmd_export,bg="#2196F3",fg="white").pack(side="left", padx=2)
tk.Button(action_frame,text="นำเข้า (Import)",command=cmd_import,bg="#FF9800",fg="white").pack(side="left", padx=2)

def animate_cat(direction=1):
    x, y = cat_track.coords(cat_sprite)
    width = max(cat_track.winfo_width(), 50)
    step = 4 * direction
    if x >= width - 12:
        direction = -1
        step = -4
    elif x <= 12:
        direction = 1
        step = 4
    cat_track.move(cat_sprite, step, 0)
    root.after(40, lambda: animate_cat(direction))

root.bind("<Unmap>", on_window_state_change)
root.protocol("WM_DELETE_WINDOW", hide_to_tray)

process_ui_actions()
animate_cat()

# --- Start ---
load_data()
check_focus_loop()
listener = keyboard.Listener(on_press=on_press,on_release=on_release)
listener.start()
root.mainloop()