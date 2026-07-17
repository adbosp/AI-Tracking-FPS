import queue
import threading
import time
import math
import tkinter as tk
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

import mss
import numpy as np
from PIL import Image, ImageTk
from pynput import keyboard
import pystray
from ultralytics import YOLO


@dataclass
class Track:
    center: tuple[float, float]
    last_seen: float
    moving_until: float = 0.0


class PersonTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AI Person Screen Tracker")
        self.icon_path = Path(__file__).with_name("icon.ico")
        if self.icon_path.exists():
            self.root.iconbitmap(default=str(self.icon_path))
        width, height = 440, min(790, self.root.winfo_screenheight() - 24)
        x = self.root.winfo_screenwidth() - width - 12
        self.root.geometry(f"{width}x{height}+{x}+12")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg="#111318")
        self.region = None
        self.running = False
        self.worker = None
        self.frames = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.photo = None
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.fps = tk.IntVar(value=20)
        self.conf = tk.DoubleVar(value=0.45)
        self.move_px = tk.IntVar(value=12)
        self.sound = tk.BooleanVar(value=True)
        self.auto_mouse = tk.BooleanVar(value=False)
        self.auto_move = tk.BooleanVar(value=False)
        self.auto_move_index = 0
        self.last_auto_move_time = 0.0
        self.ignore_injected_until = 0.0
        self.mouse_strength = tk.DoubleVar(value=75)
        self.mouse_strength_text = tk.StringVar(value="75%")
        self.mouse_speed = tk.DoubleVar(value=100)
        self.mouse_speed_text = tk.StringVar(value="NHẢY")
        self.last_mouse_target = None
        self.last_target_time = 0.0
        self.last_pull_time = 0.0
        self.last_cursor_step_time = time.monotonic()
        self.crosshair_enabled = tk.BooleanVar(value=True)
        self.crosshair_style = tk.StringVar(value="Dấu cộng")
        self.language = tk.StringVar(value="Tiếng Việt")
        self.hold_mouse = False
        self.menu_visible = True
        self.key_vars = {
            "menu": tk.StringVar(value="F10"),
            "tracking": tk.StringVar(value="F8"),
            "auto": tk.StringVar(value="F9"),
            "hold": tk.StringVar(value="Left Alt"),
        }
        self.hotkeys = {name: value.get() for name, value in self.key_vars.items()}
        self.keys_down = set()
        self.last_beep = 0.0
        self.overlay = None
        self.overlay_canvas = None
        self.crosshair_window = None
        self.crosshair_canvas = None
        self._build_ui()
        self.language.trace_add("write", lambda *_: self._change_language())
        for name, variable in self.key_vars.items():
            variable.trace_add("write", lambda *_args, n=name: self._update_hotkey(n))
        self.crosshair_enabled.trace_add("write", lambda *_: self._refresh_crosshair())
        self.crosshair_style.trace_add("write", lambda *_: self._refresh_crosshair())
        self.mouse_strength.trace_add("write", lambda *_: self._update_strength_label())
        self.mouse_speed.trace_add("write", lambda *_: self._update_speed_label())
        self.key_listener = keyboard.Listener(on_press=self._key_pressed, on_release=self._key_released)
        self.key_listener.start()
        self._create_tray_icon()
        self.root.after(100, self._refresh_crosshair)
        self.root.after(30, self._show_frame)
        self.root.after(2, self._cursor_lock_tick)
        self.root.after(100, self._auto_move_tick)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        if hasattr(self, "ui_root") and self.ui_root.winfo_exists():
            self.ui_root.destroy()
        t = self._t
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("IOS.TLabel", background="#1C1F26", foreground="#F5F5F7", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#111318", foreground="#98989F", font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background="#1C1F26", foreground="#FFFFFF", font=("Segoe UI Semibold", 11))
        style.configure("Status.TLabel", background="#1C1F26", foreground="#0A84FF", font=("Segoe UI Semibold", 10))
        style.configure("Primary.TButton", background="#007AFF", foreground="white", borderwidth=0, padding=(12, 10), font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", "#006EE6"), ("disabled", "#B7D8FF")])
        style.configure("Secondary.TButton", background="#2C2F38", foreground="#F5F5F7", borderwidth=0, padding=(12, 10), font=("Segoe UI Semibold", 10))
        style.map("Secondary.TButton", background=[("active", "#3A3D47")])
        style.configure("IOS.TCheckbutton", background="#1C1F26", foreground="#F5F5F7", font=("Segoe UI", 10), padding=2)
        style.map("IOS.TCheckbutton", background=[("active", "#1C1F26")])
        style.configure("IOS.TCombobox", fieldbackground="#2C2F38", foreground="#FFFFFF", background="#343842", bordercolor="#484B55", lightcolor="#484B55", darkcolor="#484B55", arrowcolor="#FFFFFF", padding=5)
        style.map("IOS.TCombobox", fieldbackground=[("readonly", "#2C2F38")], foreground=[("readonly", "#FFFFFF")])
        style.configure("IOS.TSpinbox", fieldbackground="#2C2F38", foreground="#FFFFFF", background="#343842", arrowcolor="#FFFFFF", bordercolor="#484B55", padding=5)
        style.configure("IOS.Horizontal.TScale", background="#1C1F26", troughcolor="#343842", sliderlength=18, borderwidth=0)

        outer = tk.Frame(self.root, bg="#111318", padx=18, pady=14)
        self.ui_root = outer
        outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg="#111318", cursor="fleur")
        header.pack(fill="x", pady=(0, 10))
        header.bind("<Button-1>", self._start_drag)
        header.bind("<B1-Motion>", self._drag_window)
        tk.Label(header, text="◎", bg="#007AFF", fg="white", font=("Segoe UI", 14, "bold"), width=2, height=1).pack(side="left", padx=(0, 10))
        header_text = tk.Frame(header, bg="#111318"); header_text.pack(side="left")
        header_text.bind("<Button-1>", self._start_drag); header_text.bind("<B1-Motion>", self._drag_window)
        tk.Label(header_text, text="AI Person Tracker", bg="#111318", fg="#FFFFFF", font=("Segoe UI Semibold", 16)).pack(anchor="w")
        ttk.Label(header_text, text="Screen tracking controller", style="Muted.TLabel").pack(anchor="w")
        ttk.Combobox(header, values=["Tiếng Việt", "English"], textvariable=self.language, width=10, state="readonly", style="IOS.TCombobox").pack(side="right", pady=4)

        controls = tk.Frame(outer, bg="#111318")
        controls.pack(fill="x", pady=(0, 8))
        self.select_btn = ttk.Button(controls, text=t("select"), command=self.select_region, state="disabled" if self.running else "normal", style="Secondary.TButton")
        self.select_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.start_btn = ttk.Button(controls, text=t("stop") if self.running else t("start"), command=self.toggle, state="normal" if self.region else "disabled", style="Primary.TButton")
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        status_card = tk.Frame(outer, bg="#1C1F26", highlightbackground="#30333B", highlightthickness=1, padx=12, pady=8)
        status_card.pack(fill="x", pady=(4, 6))
        region_value = f"X={self.region['left']}, Y={self.region['top']}, {self.region['width']} × {self.region['height']}px" if self.region else None
        self.region_text = ttk.Label(status_card, text=f"{t('region')}: {region_value}" if region_value else t("no_region"), style="IOS.TLabel")
        self.region_text.pack(anchor="w")
        self.status = ttk.Label(status_card, text=f"● {t('tracking')}" if self.running else f"● {t('ready')}", style="Status.TLabel")
        self.status.pack(anchor="w", pady=(3, 0))

        settings = self._card(outer, t("controls"))
        self._setting_row(settings, t("processing"), self.fps, 5, 60, 1, "FPS")
        self._setting_row(settings, t("confidence"), self.conf, 0.1, 0.95, 0.05)
        self._setting_row(settings, t("movement"), self.move_px, 2, 200, 1, "px")
        ttk.Separator(settings).pack(fill="x", pady=7)
        ttk.Checkbutton(settings, text=t("sound"), variable=self.sound, style="IOS.TCheckbutton").pack(anchor="w", pady=2)
        ttk.Checkbutton(settings, text=t("auto_mouse"), variable=self.auto_mouse, style="IOS.TCheckbutton").pack(anchor="w", pady=2)
        ttk.Checkbutton(settings, text=t("auto_move"), variable=self.auto_move, style="IOS.TCheckbutton").pack(anchor="w", pady=2)
        strength_row = tk.Frame(settings, bg="#1C1F26"); strength_row.pack(fill="x", pady=(5, 2))
        ttk.Label(strength_row, text=t("lock_strength"), style="IOS.TLabel").pack(side="left")
        ttk.Label(strength_row, textvariable=self.mouse_strength_text, width=5, anchor="e", style="IOS.TLabel").pack(side="right")
        ttk.Scale(strength_row, from_=1, to=100, variable=self.mouse_strength, orient="horizontal", length=150, style="IOS.Horizontal.TScale").pack(side="right", padx=8)
        speed_row = tk.Frame(settings, bg="#1C1F26"); speed_row.pack(fill="x", pady=(3, 2))
        ttk.Label(speed_row, text=t("cursor_speed"), style="IOS.TLabel").pack(side="left")
        ttk.Label(speed_row, textvariable=self.mouse_speed_text, width=5, anchor="e", style="IOS.TLabel").pack(side="right")
        ttk.Scale(speed_row, from_=1, to=100, variable=self.mouse_speed, orient="horizontal", length=150, style="IOS.Horizontal.TScale").pack(side="right", padx=8)
        ttk.Checkbutton(settings, text=t("show_crosshair"), variable=self.crosshair_enabled, style="IOS.TCheckbutton").pack(anchor="w", pady=2)
        crosshair_row = tk.Frame(settings, bg="#1C1F26"); crosshair_row.pack(fill="x", pady=(3, 0))
        ttk.Label(crosshair_row, text=t("crosshair_style"), style="IOS.TLabel").pack(side="left")
        crosshair_values = ["Classic", "Center Dot", "Circle", "X Shape"] if self.language.get() == "English" else ["Dấu cộng", "Chấm tâm", "Vòng tròn", "Chữ X"]
        ttk.Combobox(crosshair_row, values=crosshair_values, textvariable=self.crosshair_style, width=12, state="readonly", style="IOS.TCombobox").pack(side="right")

        keys = self._card(outer, t("hotkeys"))
        key_choices = [
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
            "Left Alt", "Right Alt", "Left Ctrl", "Right Ctrl", "Left Shift", "Right Shift",
            "Space", "Tab", "Caps Lock", "Enter", "Esc", "Up", "Down", "Left", "Right",
        ] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + list("0123456789")
        for name, label in [("menu", t("toggle_menu")), ("tracking", t("start_pause")), ("auto", t("auto_toggle")), ("hold", t("hold_auto"))]:
            row = tk.Frame(keys, bg="#1C1F26"); row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, style="IOS.TLabel").pack(side="left")
            ttk.Combobox(row, values=key_choices, textvariable=self.key_vars[name], width=11, state="normal", style="IOS.TCombobox").pack(side="right")

    def _t(self, key):
        vi = {
            "select": "Chọn vùng", "start": "Bắt đầu", "stop": "Dừng", "region": "Vùng",
            "no_region": "Chưa chọn vùng theo dõi", "ready": "Sẵn sàng", "tracking": "Đang theo dõi",
            "controls": "Điều khiển", "processing": "Tốc độ xử lý", "confidence": "Độ tin cậy",
            "movement": "Ngưỡng di chuyển", "sound": "Phát âm thanh cảnh báo",
            "auto_mouse": "Tự động kéo con trỏ", "auto_move": "Auto Move  •  W A S D mỗi 2 giây",
            "lock_strength": "Lực khóa chuột", "cursor_speed": "Tốc độ di chuyển",
            "show_crosshair": "Hiển thị Crosshair", "crosshair_style": "Giao diện Crosshair",
            "hotkeys": "Phím tắt", "toggle_menu": "Ẩn/hiện menu", "start_pause": "Bắt đầu/Pause",
            "auto_toggle": "Auto Mouse On/Off", "hold_auto": "Giữ để Auto Mouse",
        }
        en = {
            "select": "Select Region", "start": "Start", "stop": "Stop", "region": "Region",
            "no_region": "No tracking region selected", "ready": "Ready", "tracking": "Tracking active",
            "controls": "Controls", "processing": "Processing rate", "confidence": "Confidence",
            "movement": "Movement threshold", "sound": "Play alert sound",
            "auto_mouse": "Auto Mouse", "auto_move": "Auto Move  •  W A S D every 2 seconds",
            "lock_strength": "Mouse lock strength", "cursor_speed": "Cursor movement speed",
            "show_crosshair": "Show Crosshair", "crosshair_style": "Crosshair style",
            "hotkeys": "Global Hotkeys", "toggle_menu": "Show/hide menu", "start_pause": "Start/Pause",
            "auto_toggle": "Auto Mouse On/Off", "hold_auto": "Hold for Auto Mouse",
        }
        return (en if self.language.get() == "English" else vi)[key]

    def _change_language(self):
        pairs = {"Dấu cộng": "Classic", "Chấm tâm": "Center Dot", "Vòng tròn": "Circle", "Chữ X": "X Shape"}
        current = self.crosshair_style.get()
        if self.language.get() == "English":
            self.crosshair_style.set(pairs.get(current, current))
        else:
            reverse = {value: key for key, value in pairs.items()}
            self.crosshair_style.set(reverse.get(current, current))
        self._build_ui()

    def _start_drag(self, event):
        self._drag_x, self._drag_y = event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y()

    def _drag_window(self, event):
        self.root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    @staticmethod
    def _card(parent, title):
        card = tk.Frame(parent, bg="#1C1F26", highlightbackground="#30333B", highlightthickness=1, padx=12, pady=8)
        card.pack(fill="x", pady=6)
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 7))
        return card

    @staticmethod
    def _setting_row(parent, label, variable, minimum, maximum, increment, suffix=None):
        row = tk.Frame(parent, bg="#1C1F26"); row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="IOS.TLabel").pack(side="left")
        ttk.Label(row, text=suffix or "", width=4, anchor="w", style="IOS.TLabel").pack(side="right", padx=(5, 0))
        control = ttk.Spinbox(
            row, from_=minimum, to=maximum, increment=increment,
            width=8, textvariable=variable, style="IOS.TSpinbox",
        )
        control.pack(side="right")

    def _update_hotkey(self, name):
        value = self.key_vars[name].get().strip()
        aliases = {"ESCAPE": "Esc", "RETURN": "Enter", "SPACEBAR": "Space", "CAPSLOCK": "Caps Lock"}
        self.hotkeys[name] = aliases.get(value.upper(), value.upper() if len(value) == 1 or value.upper().startswith("F") else value.title())

    @staticmethod
    def _key_name(key):
        mapping = {
            keyboard.Key.alt_l: "Left Alt", keyboard.Key.alt_r: "Right Alt",
            keyboard.Key.ctrl_l: "Left Ctrl", keyboard.Key.ctrl_r: "Right Ctrl",
            keyboard.Key.shift_l: "Left Shift", keyboard.Key.shift_r: "Right Shift",
            keyboard.Key.space: "Space", keyboard.Key.tab: "Tab", keyboard.Key.caps_lock: "Caps Lock",
            keyboard.Key.enter: "Enter", keyboard.Key.esc: "Esc", keyboard.Key.up: "Up",
            keyboard.Key.down: "Down", keyboard.Key.left: "Left", keyboard.Key.right: "Right",
        }
        if key in mapping:
            return mapping[key]
        name = getattr(key, "name", "")
        if name.startswith("f") and name[1:].isdigit():
            return name.upper()
        char = getattr(key, "char", None)
        return char.upper() if char else ""

    def _key_pressed(self, key):
        name = self._key_name(key)
        if time.monotonic() < self.ignore_injected_until and name in {"W", "A", "S", "D"}:
            return
        if not name or name in self.keys_down:
            return
        self.keys_down.add(name)
        if name == self.hotkeys["menu"]:
            self.root.after(0, self.toggle_menu)
        elif name == self.hotkeys["tracking"]:
            self.root.after(0, self.toggle)
        elif name == self.hotkeys["auto"]:
            self.root.after(0, lambda: self.auto_mouse.set(not self.auto_mouse.get()))
        if name == self.hotkeys["hold"]:
            self.root.after(0, self._hold_mouse_on)

    def _key_released(self, key):
        name = self._key_name(key)
        if time.monotonic() < self.ignore_injected_until and name in {"W", "A", "S", "D"}:
            return
        self.keys_down.discard(name)
        if name == self.hotkeys["hold"]:
            self.root.after(0, self._hold_mouse_off)

    def _hold_mouse_on(self):
        self.hold_mouse = True

    def _hold_mouse_off(self):
        self.hold_mouse = False

    def toggle_menu(self):
        is_hidden = self.root.state() == "withdrawn"
        if is_hidden:
            self.menu_visible = True
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.menu_visible = False
            self.root.withdraw()

    def _create_tray_icon(self):
        tray_image = Image.open(self.icon_path).convert("RGBA")
        menu = pystray.Menu(
            pystray.MenuItem("Mở menu", lambda *_: self.root.after(0, self.show_menu), default=True),
            pystray.MenuItem("Bắt đầu / Pause", lambda *_: self.root.after(0, self.toggle)),
            pystray.MenuItem("Bật / Tắt Auto Mouse", lambda *_: self.root.after(0, self.toggle_auto_mouse)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Thoát", lambda *_: self.root.after(0, self.close)),
        )
        self.tray_icon = pystray.Icon("AI Person Tracker", tray_image, "AI Person Screen Tracker", menu)
        self.tray_icon.run_detached()

    def show_menu(self):
        self.menu_visible = True
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def toggle_auto_mouse(self):
        self.auto_mouse.set(not self.auto_mouse.get())

    def select_region(self):
        self.stop()
        self.root.withdraw()
        time.sleep(.15)
        with mss.mss() as capture:
            virtual = capture.monitors[0]
            shot = capture.grab(virtual)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{virtual['width']}x{virtual['height']}+{virtual['left']}+{virtual['top']}")
        canvas = tk.Canvas(overlay, cursor="cross", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        bg = ImageTk.PhotoImage(image)
        canvas.create_image(0, 0, image=bg, anchor="nw")
        canvas.create_text(virtual["width"] // 2, 35, text="Kéo chuột chọn vùng có người • Esc để hủy", fill="white", font=("Segoe UI", 16, "bold"))
        state = {"start": None, "rect": None}

        def down(event):
            state["start"] = (event.x, event.y)
            state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#00d4ff", width=3)

        def drag(event):
            if state["start"]:
                canvas.coords(state["rect"], *state["start"], event.x, event.y)

        def up(event):
            if not state["start"]:
                return
            x1, y1 = state["start"]
            x, y = min(x1, event.x), min(y1, event.y)
            w, h = abs(event.x - x1), abs(event.y - y1)
            if w >= 32 and h >= 32:
                self.region = {"left": x + virtual["left"], "top": y + virtual["top"], "width": w, "height": h}
            overlay.destroy()

        canvas.bind("<Button-1>", down)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", up)
        overlay.bind("<Escape>", lambda _: overlay.destroy())
        overlay.focus_force()
        self.root.wait_window(overlay)
        self.root.deiconify()
        self.root.lift()
        if self.region:
            r = self.region
            self.region_text.config(text=f"{self._t('region')}: X={r['left']}, Y={r['top']}, {r['width']} × {r['height']}px")
            self.start_btn.config(state="normal")

    def toggle(self):
        if self.running:
            self.stop()
        else:
            if not self.region:
                self.status.config(text="Select a region before starting" if self.language.get() == "English" else "Hãy chọn vùng trước khi bắt đầu")
                return
            self.running = True
            self.stop_event.clear()
            self.start_btn.config(text=self._t("stop"))
            self.select_btn.config(state="disabled")
            self.status.config(text="Loading AI…" if self.language.get() == "English" else "Đang tải AI…")
            self._create_overlay()
            self.worker = threading.Thread(target=self._capture_loop, daemon=True)
            self.worker.start()

    def stop(self):
        self.running = False
        self.stop_event.set()
        self.start_btn.config(text=self._t("start"))
        self.select_btn.config(state="normal")
        self.tracks.clear()
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
            self.overlay_canvas = None

    def _create_overlay(self):
        if self.overlay is not None or not self.region:
            return
        r = self.region
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-transparentcolor", "#ff00ff")
        self.overlay.configure(bg="#ff00ff")
        self.overlay.geometry(f"{r['width']}x{r['height']}+{r['left']}+{r['top']}")
        self.overlay_canvas = tk.Canvas(self.overlay, bg="#ff00ff", highlightthickness=0)
        self.overlay_canvas.pack(fill="both", expand=True)
        self.overlay.update_idletasks()
        hwnd = self.overlay.winfo_id()
        get_style = ctypes.windll.user32.GetWindowLongW
        set_style = ctypes.windll.user32.SetWindowLongW
        ex_style = get_style(hwnd, -20)
        set_style(hwnd, -20, ex_style | 0x00000020 | 0x00000080 | 0x08000000)

    def _draw_overlay(self, assignments):
        if self.overlay_canvas is None:
            return
        self.overlay_canvas.delete("all")
        for track_id, moving, x1, y1, x2, y2, score in assignments:
            color = "#ff3030" if moving else "#35e06f"
            self.overlay_canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3)
            label = f"Person #{track_id} {'MOVING' if moving else 'STILL'} {score:.0%}"
            text_id = self.overlay_canvas.create_text(x1 + 5, max(12, y1 - 11), text=label, fill="white", anchor="w", font=("Segoe UI", 10, "bold"))
            bounds = self.overlay_canvas.bbox(text_id)
            if bounds:
                bg = self.overlay_canvas.create_rectangle(bounds[0] - 4, bounds[1] - 2, bounds[2] + 4, bounds[3] + 2, fill=color, outline=color)
                self.overlay_canvas.tag_raise(text_id, bg)

    def _refresh_crosshair(self):
        if not self.crosshair_enabled.get():
            if self.crosshair_window is not None:
                self.crosshair_window.withdraw()
            return
        if self.crosshair_window is None:
            size = 100
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            self.crosshair_window = tk.Toplevel(self.root)
            self.crosshair_window.overrideredirect(True)
            self.crosshair_window.attributes("-topmost", True)
            self.crosshair_window.attributes("-transparentcolor", "#ff00ff")
            self.crosshair_window.configure(bg="#ff00ff")
            self.crosshair_window.geometry(f"{size}x{size}+{(screen_w-size)//2}+{(screen_h-size)//2}")
            self.crosshair_canvas = tk.Canvas(self.crosshair_window, width=size, height=size, bg="#ff00ff", highlightthickness=0)
            self.crosshair_canvas.pack(fill="both", expand=True)
            self.crosshair_window.update_idletasks()
            hwnd = self.crosshair_window.winfo_id()
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style | 0x00000020 | 0x00000080 | 0x08000000)
        else:
            self.crosshair_window.deiconify()
            self.crosshair_window.lift()
        self._draw_fps_crosshair()

    def _draw_fps_crosshair(self):
        canvas = self.crosshair_canvas
        if canvas is None:
            return
        canvas.delete("all")
        cx = cy = 50
        cyan, shadow = "#00F5FF", "#071014"
        style = self.crosshair_style.get()

        def line(x1, y1, x2, y2, width=2):
            canvas.create_line(x1, y1, x2, y2, fill=shadow, width=width + 3, capstyle="round")
            canvas.create_line(x1, y1, x2, y2, fill=cyan, width=width, capstyle="round")

        if style in ("Dấu cộng", "Classic"):
            for coords in [(25, 50, 43, 50), (57, 50, 75, 50), (50, 25, 50, 43), (50, 57, 50, 75)]:
                line(*coords, width=3)
            canvas.create_oval(47, 47, 53, 53, fill="#FFFFFF", outline=shadow, width=2)
        elif style in ("Chấm tâm", "Center Dot"):
            canvas.create_oval(43, 43, 57, 57, fill=shadow, outline=shadow)
            canvas.create_oval(46, 46, 54, 54, fill=cyan, outline="#FFFFFF", width=1)
        elif style in ("Vòng tròn", "Circle"):
            canvas.create_oval(34, 34, 66, 66, outline=shadow, width=6)
            canvas.create_oval(34, 34, 66, 66, outline=cyan, width=3)
            canvas.create_oval(48, 48, 52, 52, fill="#FFFFFF", outline="#FFFFFF")
        elif style in ("Chữ X", "X Shape"):
            for coords in [(29, 29, 43, 43), (57, 57, 71, 71), (71, 29, 57, 43), (43, 57, 29, 71)]:
                line(*coords, width=3)

    def _capture_loop(self):
        try:
            model_path = Path(__file__).with_name("yolo11n.pt")
            model = YOLO(str(model_path))
            with mss.mss() as capture:
                while not self.stop_event.is_set():
                    started = time.perf_counter()
                    shot = capture.grab(self.region)
                    frame = np.asarray(shot)[:, :, :3].copy()
                    result = model.predict(frame, classes=[0], conf=float(self.conf.get()), imgsz=640, verbose=False)[0]
                    boxes = []
                    if result.boxes is not None:
                        for xyxy, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                            boxes.append((*map(int, xyxy), float(score)))
                    annotated, moving, assignments = self._track_and_draw(frame, boxes)
                    rgb = annotated[:, :, ::-1]
                    try:
                        self.frames.put_nowait((rgb, len(boxes), moving, assignments))
                    except queue.Full:
                        try: self.frames.get_nowait()
                        except queue.Empty: pass
                    delay = max(0, 1 / max(1, self.fps.get()) - (time.perf_counter() - started))
                    self.stop_event.wait(delay)
        except Exception as exc:
            self.frames.put((None, -1, str(exc), []))

    def _track_and_draw(self, frame, boxes):
        import cv2
        now = time.monotonic()
        unmatched = set(self.tracks)
        assignments = []
        for x1, y1, x2, y2, score in boxes:
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            candidates = [(np.hypot(center[0] - self.tracks[i].center[0], center[1] - self.tracks[i].center[1]), i) for i in unmatched]
            distance, track_id = min(candidates, default=(9999, -1))
            max_match = max(60, (y2 - y1) * .7)
            if distance > max_match:
                track_id = self.next_id; self.next_id += 1
                self.tracks[track_id] = Track(center, now)
                distance = 0
            else:
                unmatched.discard(track_id)
            track = self.tracks[track_id]
            if distance >= self.move_px.get(): track.moving_until = now + .35
            track.center, track.last_seen = center, now
            assignments.append((track_id, track.moving_until > now, x1, y1, x2, y2, score))
        self.tracks = {i: t for i, t in self.tracks.items() if now - t.last_seen < 1.2}
        moving_count = 0
        for track_id, moving, x1, y1, x2, y2, score in assignments:
            color = (40, 40, 240) if moving else (70, 210, 80)
            if moving: moving_count += 1
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            cv2.putText(frame, f"Person #{track_id} {'MOVING' if moving else 'STILL'} {score:.0%}", (x1, max(25, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, .65, color, 2)
        return frame, moving_count, assignments

    def _show_frame(self):
        try:
            rgb, people, moving, assignments = self.frames.get_nowait()
            if rgb is None:
                self.status.config(text=f"{'Error' if self.language.get() == 'English' else 'Lỗi'}: {moving}")
                self.stop()
            else:
                self._draw_overlay(assignments)
                text = (f"Detected {people} people • {moving} moving" if self.language.get() == "English"
                        else f"Phát hiện {people} người • {moving} người đang di chuyển")
                self.status.config(text=text)
                if (self.auto_mouse.get() or self.hold_mouse) and assignments:
                    moving_people = [item for item in assignments if item[1]]
                    targets = moving_people or assignments
                    target = max(targets, key=lambda item: item[6])
                    _, _, x1, y1, x2, y2, _ = target
                    target_x = self.region["left"] + (x1 + x2) // 2
                    target_y = self.region["top"] + (y1 + y2) // 2
                    self._pull_cursor(target_x, target_y)
                if moving and self.sound.get() and time.monotonic() - self.last_beep > .7:
                    self.root.bell(); self.last_beep = time.monotonic()
        except queue.Empty:
            pass
        self.root.after(30, self._show_frame)

    def _pull_cursor(self, target_x, target_y):
        strength = max(1, min(100, int(self.mouse_strength.get())))
        now = time.monotonic()
        self.last_mouse_target = (target_x, target_y)
        self.last_target_time = now
        # Lực thấp thay đổi tần suất bắt lại, không làm con trỏ trượt chậm.
        interval = max(0.0, (75 - strength) / 100.0)
        if now - self.last_pull_time >= interval:
            self._move_cursor_toward(target_x, target_y)
            self.last_pull_time = now

    def _cursor_lock_tick(self):
        strength = max(1, min(100, int(self.mouse_strength.get())))
        active = self.running and (self.auto_mouse.get() or self.hold_mouse)
        target_fresh = time.monotonic() - self.last_target_time < 0.35
        if active and strength > 75 and target_fresh and self.last_mouse_target:
            self._move_cursor_toward(*self.last_mouse_target)
        # Trên 75% khóa giữa các frame; 100% lặp gần như liên tục.
        if strength <= 75:
            delay = 16
        else:
            delay = max(1, round(18 - (strength - 75) * 17 / 25))
        self.root.after(delay, self._cursor_lock_tick)

    def _update_strength_label(self):
        strength = int(self.mouse_strength.get())
        lock_text = "LOCK" if self.language.get() == "English" else "KHÓA"
        self.mouse_strength_text.set(lock_text if strength >= 100 else f"{strength}%")

    def _update_speed_label(self):
        speed = int(self.mouse_speed.get())
        snap_text = "SNAP" if self.language.get() == "English" else "NHẢY"
        self.mouse_speed_text.set(snap_text if speed >= 100 else f"{speed}%")

    def _auto_move_tick(self):
        now = time.monotonic()
        if self.auto_move.get() and now - self.last_auto_move_time >= 2.0:
            keys = [("W", 0x57), ("A", 0x41), ("S", 0x53), ("D", 0x44)]
            _, virtual_key = keys[self.auto_move_index]
            self.auto_move_index = (self.auto_move_index + 1) % len(keys)
            self.last_auto_move_time = now
            self.ignore_injected_until = now + 0.25
            ctypes.windll.user32.keybd_event(virtual_key, 0, 0, 0)
            self.root.after(80, lambda vk=virtual_key: ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0))
        elif not self.auto_move.get():
            self.last_auto_move_time = 0.0
            self.auto_move_index = 0
        self.root.after(100, self._auto_move_tick)

    def _move_cursor_toward(self, target_x, target_y):
        speed = max(1, min(100, int(self.mouse_speed.get())))
        now = time.monotonic()
        elapsed = max(0.001, min(0.1, now - self.last_cursor_step_time))
        self.last_cursor_step_time = now
        if speed >= 100:
            ctypes.windll.user32.SetCursorPos(target_x, target_y)
            return
        point = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return
        # Nội suy theo thời gian để tốc độ không phụ thuộc FPS hay tần suất khóa.
        rate = 0.7 + 24.0 * (speed / 100.0) ** 2
        factor = 1.0 - math.exp(-rate * elapsed)
        next_x = round(point.x + (target_x - point.x) * factor)
        next_y = round(point.y + (target_y - point.y) * factor)
        ctypes.windll.user32.SetCursorPos(next_x, next_y)

    def close(self):
        self.stop()
        for virtual_key in (0x57, 0x41, 0x53, 0x44):
            ctypes.windll.user32.keybd_event(virtual_key, 0, 0x0002, 0)
        self.key_listener.stop()
        self.tray_icon.stop()
        if self.crosshair_window is not None:
            self.crosshair_window.destroy()
        self.root.destroy()


if __name__ == "__main__":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HYVN.AIPersonScreenTracker.1")
    root = tk.Tk()
    PersonTrackerApp(root)
    root.mainloop()
