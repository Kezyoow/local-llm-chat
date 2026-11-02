#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3 本地助手 —— 圆润玻璃风格（iOS / ins 风）

特性：
    · 圆角卡片 + 磨砂背景 + 柔和阴影
    · 气泡式对话（用户右侧蓝泡，助手左侧白泡）
    · 附件：PDF/Word/Excel/PPT/文本/代码；图片自动切视觉模型 Qwen3-VL
    · 流式、停止、多轮、历史会话、实时 tok/s、测速面板

数据：E:\\QwenChat\\   （sessions / settings.json / _uploads / assets）
后端：http://127.0.0.1:11434
"""

import base64
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import urllib.request
import uuid
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageTk

import extract
import providers

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(APP_DIR, "sessions")
UPLOAD_DIR = os.path.join(APP_DIR, "_uploads")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
def _asset(*names):
    """按顺序找第一个存在的素材；都没有就用仓库自带的 default_*。"""
    for n in names:
        p = os.path.join(APP_DIR, "assets", n)
        if os.path.isfile(p):
            return p
    return os.path.join(APP_DIR, "assets", names[-1])


# 用户自己的图优先，其次是仓库自带的中性默认图
BG_IMAGE = _asset("background.jpg", "default_bg.jpg")
SIDE_IMAGE = _asset("side_card.jpg", "default_side.jpg")

# ---------------------------------------------------------------- 色板
LIGHT = {
    "INK": "#232830", "INK_SOFT": "#5B6572", "MUTED": "#98A1AE",
    "LINE": "#E9EDF3", "CARD": "#FCFCFD", "ACCENT": "#5B8DEF",
    "ACCENT_DK": "#4A7BE0", "ACCENT_SOFT": "#EAF1FF", "PINK": "#F0A6B8",
    "BUBBLE_ASST": "#F5F7FB", "BUBBLE_USER": "#5B8DEF", "THINK_BG": "#F4F6F9",
    "OK": "#33C27F", "BAD": "#F0605D",
    "FIELD_BG": "#EDF1F7", "FIELD_LINE": "#DEE5EF", "ROOT_BG": "#E8EDF5",
    "DIALOG_BG": "#F7F9FC", "ENTRY_BG": "#FFFFFF",
}
DARK = {
    "INK": "#E7ECF4", "INK_SOFT": "#A7B1C2", "MUTED": "#79839A",
    "LINE": "#2F3847", "CARD": "#1A1F28", "ACCENT": "#6C9BFF",
    "ACCENT_DK": "#5A89EE", "ACCENT_SOFT": "#233149", "PINK": "#E48FA6",
    "BUBBLE_ASST": "#232B36", "BUBBLE_USER": "#4A7BE0", "THINK_BG": "#1E242E",
    "OK": "#3DDC84", "BAD": "#FF6B6B",
    "FIELD_BG": "#232B36", "FIELD_LINE": "#333C4D", "ROOT_BG": "#0D1015",
    "DIALOG_BG": "#171C24", "ENTRY_BG": "#232B36",
}

FONT_FAMILY = "Microsoft YaHei UI"

# 下面这些是全局当前值，由 apply_theme() 填充
THEME = "light"
INK = INK_SOFT = MUTED = LINE = CARD = ACCENT = ACCENT_DK = ""
ACCENT_SOFT = PINK = BUBBLE_ASST = BUBBLE_USER = THINK_BG = OK = BAD = ""
FIELD_BG = FIELD_LINE = ROOT_BG = DIALOG_BG = ENTRY_BG = ""


def apply_theme(name):
    """切换全局配色。改完需要重建界面才会全部生效。"""
    global THEME, INK, INK_SOFT, MUTED, LINE, CARD, ACCENT, ACCENT_DK
    global ACCENT_SOFT, PINK, BUBBLE_ASST, BUBBLE_USER, THINK_BG, OK, BAD
    global FIELD_BG, FIELD_LINE, ROOT_BG, DIALOG_BG, ENTRY_BG
    pal = DARK if name == "dark" else LIGHT
    THEME = "dark" if name == "dark" else "light"
    INK = pal["INK"]; INK_SOFT = pal["INK_SOFT"]; MUTED = pal["MUTED"]
    LINE = pal["LINE"]; CARD = pal["CARD"]; ACCENT = pal["ACCENT"]
    ACCENT_DK = pal["ACCENT_DK"]; ACCENT_SOFT = pal["ACCENT_SOFT"]
    PINK = pal["PINK"]; BUBBLE_ASST = pal["BUBBLE_ASST"]
    BUBBLE_USER = pal["BUBBLE_USER"]; THINK_BG = pal["THINK_BG"]
    OK = pal["OK"]; BAD = pal["BAD"]
    FIELD_BG = pal["FIELD_BG"]; FIELD_LINE = pal["FIELD_LINE"]
    ROOT_BG = pal["ROOT_BG"]; DIALOG_BG = pal["DIALOG_BG"]
    ENTRY_BG = pal["ENTRY_BG"]


apply_theme("light")

DEFAULTS = {
    # ---- 后端
    "backend": "ollama",                       # ollama | openai
    "base_url": "http://127.0.0.1:11434",
    "api_key": "",
    "model": "",                              # 留空 = 连接后自动选第一个可用模型
    "vision_model": "qwen3-vl-8b",
    # ---- 生成
    "temperature": 0.6, "num_ctx": 32768, "system": "", "think": False,
    "calib": 1.6,
    # ---- 外观
    "bg_image": "", "side_image": "", "theme": "light",
}

ALL_TYPES = (
    "*.pdf", "*.docx", "*.xlsx", "*.xlsm", "*.pptx", "*.csv", "*.tsv",
    "*.txt", "*.md", "*.json", "*.xml", "*.html", "*.htm", "*.log",
    "*.yaml", "*.yml", "*.ini", "*.rtf", "*.epub",
    "*.py", "*.js", "*.ts", "*.java", "*.c", "*.cpp", "*.h", "*.cs",
    "*.go", "*.rs", "*.php", "*.rb", "*.sh", "*.ps1", "*.sql",
    "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.gif",
)


# ---------------------------------------------------------------- 拖拽上传
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes as _wt

    _LONG_PTR = ctypes.c_ssize_t
    _WNDPROC = ctypes.WINFUNCTYPE(_LONG_PTR, _wt.HWND, ctypes.c_uint,
                                  _wt.WPARAM, _wt.LPARAM)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _user32.SetWindowLongPtrW.restype = _LONG_PTR
    _user32.SetWindowLongPtrW.argtypes = [_wt.HWND, ctypes.c_int, _LONG_PTR]
    _user32.CallWindowProcW.restype = _LONG_PTR
    _user32.CallWindowProcW.argtypes = [_LONG_PTR, _wt.HWND, ctypes.c_uint,
                                        _wt.WPARAM, _wt.LPARAM]
    _WM_DROPFILES = 0x0233


class DropTarget:
    """把窗口变成文件拖放目标（仅 Windows；其它平台静默跳过）。"""

    def __init__(self, root, callback):
        self.callback = callback
        self._old = 0
        self._proc = None
        if sys.platform != "win32":
            return
        try:
            hwnd = _user32.GetParent(root.winfo_id()) or root.winfo_id()
            self._proc = _WNDPROC(self._handle)
            _shell32.DragAcceptFiles(hwnd, True)
            addr = ctypes.cast(self._proc, ctypes.c_void_p).value
            self._old = _user32.SetWindowLongPtrW(hwnd, -4, _LONG_PTR(addr))
        except Exception:
            self._proc = None

    def _handle(self, hwnd, msg, wparam, lparam):
        if msg == _WM_DROPFILES:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                n = _shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                paths = []
                for i in range(n):
                    _shell32.DragQueryFileW(wparam, i, buf, 1024)
                    if buf.value:
                        paths.append(buf.value)
                _shell32.DragFinish(wparam)
                if paths:
                    self.callback(paths)
            except Exception:
                pass
            return 0
        return _user32.CallWindowProcW(self._old, hwnd, msg, wparam, lparam)


def F(size, weight="normal"):
    return (FONT_FAMILY, size, weight)


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形（平滑多边形近似）。"""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        out = dict(DEFAULTS)
        out.update({k: s[k] for k in DEFAULTS if k in s})
        return out
    except Exception:
        return dict(DEFAULTS)


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ================================================================ 基础控件
class RoundButton(tk.Canvas):
    """圆角按钮（支持 primary / ghost 两种风格）。"""

    def __init__(self, master, text, command=None, bg=None, kind="ghost",
                 width=None, height=36, radius=14, size=10, parent_bg=None):
        bg = bg or CARD
        super().__init__(master, bg=parent_bg or bg, highlightthickness=0, bd=0,
                         height=height)
        self.command = command
        self.enabled = True
        self._fixed_w = width
        self.radius = radius
        self.text = text
        self.kind = kind
        self.base_bg = bg
        self.font = F(size, "bold" if kind == "primary" else "normal")
        self._bgcolor = parent_bg or bg
        self.configure(bg=self._bgcolor)
        self._compute()
        self.bind("<Configure>", self._on_conf)
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint(hover=False))
        self.bind("<Button-1>", self._click)
        self.bind("<ButtonRelease-1>", lambda e: self._paint(hover=True))

    def _on_conf(self, e):
        if e.width > 1 and e.height > 1 and (e.width, e.height) != (self.w, self.h):
            self.w, self.h = e.width, e.height
            self._paint()

    def _compute(self):
        fnt = tkfont.Font(font=self.font)
        tw = fnt.measure(self.text)
        self.w = self._fixed_w or (tw + 40)
        self.h = int(self["height"])
        self.configure(width=self.w)
        self._paint()

    def colors(self, hover=False):
        if not self.enabled:
            return ("#EFF2F6", MUTED, "")
        if self.kind == "primary":
            return (ACCENT_DK if hover else ACCENT, "#FFFFFF", "")
        if self.kind == "soft":
            return (ACCENT_SOFT if not hover else "#DCE8FF", ACCENT, "")
        return (ACCENT_SOFT if hover else CARD, INK_SOFT, LINE)

    def _paint(self, hover=False):
        self.delete("all")
        bgc, fgc, outline = self.colors(hover)
        if abs(self.w - self.h) <= 4 and self.radius >= self.w / 2 - 6:
            self.create_oval(1, 1, self.w - 1, self.h - 1,
                             fill=bgc, outline=outline or bgc)
        else:
            round_rect(self, 1, 1, self.w - 1, self.h - 1, self.radius,
                       fill=bgc, outline=outline or bgc)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fgc, font=self.font)

    def _click(self, _e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, flag):
        self.enabled = bool(flag)
        self._paint()

    def set_text(self, text):
        self.text = text
        self._compute()


class Chip(tk.Canvas):
    """附件小标签（圆角胶囊）。"""

    def __init__(self, master, name, meta, color, bg=None, on_close=None, thumb=None):
        bg = bg or CARD
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=30)
        self.name, self.meta, self.color = name, meta, color
        self.on_close = on_close
        self._thumb = None
        f1 = tkfont.Font(font=F(9))
        f2 = tkfont.Font(font=F(8))
        pad = 34 if thumb else 0
        w = f1.measure(name) + f2.measure(meta) + 54 + pad
        self.w = max(120, min(340, w))
        self.configure(width=self.w)
        round_rect(self, 1, 1, self.w - 1, 29, 13, fill=CARD, outline=LINE)
        if thumb:
            try:
                from PIL import Image as _Image
                im = _Image.open(thumb).convert("RGB")
                im.thumbnail((24, 24), _Image.LANCZOS)
                self._thumb = ImageTk.PhotoImage(im)
                self.create_image(16, 15, image=self._thumb)
            except Exception:
                pad = 0
        x0 = 32 if pad else 12
        self.create_text(x0, 15, text=name, anchor="w", fill=INK, font=F(9))
        self.create_text(self.w - 30, 15, text=meta, anchor="e", fill=color, font=F(8))
        self.x_item = self.create_text(self.w - 14, 14, text="×", fill=MUTED, font=F(10, "bold"))
        self.tag_bind(self.x_item, "<Button-1>", lambda e: on_close and on_close())
        self.tag_bind(self.x_item, "<Enter>", lambda e: self.itemconfigure(self.x_item, fill=BAD))
        self.tag_bind(self.x_item, "<Leave>", lambda e: self.itemconfigure(self.x_item, fill=MUTED))


class Bubble(tk.Frame):
    """一条消息气泡：自动换行、自动高度、圆角。"""

    def __init__(self, master, side_bg, fill, fg, text="", max_w=620,
                 font=None, italic=False, pad_x=14, pad_y=10, radius=18):
        super().__init__(master, bg=side_bg)
        self.radius = radius
        self.pad_x, self.pad_y = pad_x, pad_y
        self.fill = fill
        self.cv = tk.Canvas(self, bg=side_bg, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        ff = font or F(11)
        if italic:
            ff = (FONT_FAMILY, 10, "italic")
        self.label = tk.Label(self.cv, text=text, bg=fill, fg=fg, font=ff,
                              justify="left", anchor="w", wraplength=max_w - 2 * pad_x)
        self._win = self.cv.create_window(pad_x, pad_y, window=self.label, anchor="nw")
        self.label.bind("<Configure>", self._resize)

    def _resize(self, e):
        w = e.width + 2 * self.pad_x
        h = e.height + 2 * self.pad_y
        self.cv.configure(width=w, height=h)
        self.cv.delete("bg")
        round_rect(self.cv, 1, 1, w - 1, h - 1, self.radius,
                   fill=self.fill, outline="", tags="bg")
        self.cv.tag_lower("bg")

    def append(self, text):
        self.label.configure(text=self.label.cget("text") + text)

    def set_text(self, text):
        self.label.configure(text=text)

    def get_text(self):
        return self.label.cget("text")


class SlimScroll(tk.Canvas):
    """极简滚动条：一条细长的圆角滑块。"""

    def __init__(self, master, view, bg=None, width=8):
        bg = bg or CARD
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, width=width)
        self.view = view
        self.w = width
        self.first, self.last = 0.0, 1.0
        self._drag = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._start)
        self.bind("<B1-Motion>", self._move)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _draw(self):
        self.delete("all")
        h = max(1, self.winfo_height())
        if self.last - self.first >= 0.999:
            return
        y1 = self.first * h
        y2 = max(y1 + 24, self.last * h)
        self.create_line(self.w / 2, y1 + 4, self.w / 2, y2 - 4,
                         width=6, fill="#CBD3DF", capstyle="round")

    def _start(self, e):
        h = max(1, self.winfo_height())
        if self.first * h <= e.y <= self.last * h:
            self._drag = (e.y, self.first)
        else:
            self.view_moveto(max(0, min(1, e.y / h)))

    def _move(self, e):
        if not self._drag:
            return
        h = max(1, self.winfo_height())
        dy = (e.y - self._drag[0]) / h
        self.view_moveto(max(0, min(1 - (self.last - self.first), self._drag[1] + dy)))

    def view_moveto(self, frac):
        try:
            self.view.yview_moveto(frac)
            self.set(*self.view.yview())
        except Exception:
            pass


# ================================================================ 主程序
class ChatApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        apply_theme(self.settings.get("theme", "light"))
        self.messages = []
        self.session_id = None
        self.session_path = None
        self.streaming = False
        self.cancel_flag = False
        self.resp = None
        self.q = queue.Queue()
        self.last_answer = ""
        self.sess_paths = []
        self.attachments = []
        self._ingesting = 0
        self._chars = 0
        self._t0 = time.time()
        self._first = None
        self.calib = float(self.settings.get("calib") or 1.6)
        self.current_model = self.settings.get("model") or "qwen3-8b-cline"
        self.backend = None
        self._make_backend()
        self.bubbles = []
        self._cur_bubble = None
        self._last_size = (0, 0)
        self._rz_job = None
        self._bg_photo = None

        os.makedirs(SESSION_DIR, exist_ok=True)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        self._build()
        self._load_sessions()
        self._new_session(confirm=False)
        self._ping()
        self.root.after(40, self._drain)

    # ------------------------------------------------------------ 后端
    def _make_backend(self):
        try:
            self.backend = providers.make_backend(
                self.settings.get("backend", "ollama"),
                self.settings.get("base_url", ""),
                self.settings.get("api_key", ""))
        except Exception as e:
            self.backend = None
            print("后端初始化失败：", e)

    # ------------------------------------------------------------ 图片
    def _bg_path(self):
        p = (self.settings.get("bg_image") or "").strip()
        return p if p and os.path.isfile(p) else BG_IMAGE

    def _side_path(self):
        p = (self.settings.get("side_image") or "").strip()
        if p and os.path.isfile(p):
            return p
        if os.path.isfile(SIDE_IMAGE):
            return SIDE_IMAGE
        return self._bg_path()

    def _apply_images(self):
        self._last_size = (0, 0)
        self._do_layout()

    # ------------------------------------------------------------ 骨架
    def _build(self):
        self.root.title("本地大模型助手")
        self.root.geometry("1280x860")
        self.root.minsize(1060, 680)
        self.root.configure(bg=ROOT_BG)
        try:
            self.root.attributes("-alpha", 0.995)
        except Exception:
            pass

        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=ROOT_BG)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # 侧栏面板
        self.side = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=CARD)
        # 对话面板
        self.chat_panel = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=CARD)
        # 输入面板
        self.input_panel = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=CARD)

        self._build_side()
        self._build_chat()
        self._build_input()

        self.canvas.bind("<Configure>", self._on_resize)
        self.root.bind("<MouseWheel>", self._wheel)

        # 拖拽文件到窗口即添加（Windows 生效；重建界面时不重复挂）
        if not getattr(self, "_drop", None):
            self._drop = DropTarget(self.root, self._on_drop)

        # 点顶栏胶囊切换模型
        self.canvas.tag_bind("hdr_pill", "<Button-1>", self._show_model_menu)
        self.canvas.tag_bind("hdr_pill", "<Enter>",
                             lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("hdr_pill", "<Leave>",
                             lambda e: self.canvas.configure(cursor=""))

    # ---------------- 侧栏
    def _build_side(self):
        self.side_card = tk.Canvas(self.side, highlightthickness=0, bd=0, bg=CARD)
        self.side_card.place(x=16, y=16, width=200, height=214)

        self.new_btn = RoundButton(self.side, "＋   新 对 话", command=self._new_session,
                                   kind="primary", width=200, height=42, radius=16,
                                   size=11, parent_bg=CARD)
        self.new_btn.place(x=16, y=244)

        self.sess_title = tk.Label(self.side, text="最近对话", bg=CARD, fg=MUTED, font=F(9))
        self.sess_title.place(x=22, y=300)

        self.sess_wrap = tk.Frame(self.side, bg=CARD)
        self.sess_wrap.place(x=10, y=324, width=200, height=330)
        self.sess_cv = tk.Canvas(self.sess_wrap, bg=CARD, highlightthickness=0, bd=0)
        self.sess_cv.pack(side="left", fill="both", expand=True)
        self.sess_scroll = SlimScroll(self.sess_wrap, self.sess_cv, bg=CARD)
        self.sess_scroll.pack(side="right", fill="y")
        self.sess_cv.configure(yscrollcommand=self.sess_scroll.set)
        self.sess_inner = tk.Frame(self.sess_cv, bg=CARD)
        self.sess_win = self.sess_cv.create_window(0, 0, window=self.sess_inner, anchor="nw")
        self.sess_cv.bind("<Configure>", lambda e: self.sess_cv.itemconfigure(
            self.sess_win, width=e.width))
        self.sess_inner.bind("<Configure>", lambda e: self.sess_cv.configure(
            scrollregion=self.sess_cv.bbox("all")))

        self.bench_btn = RoundButton(self.side, "测速", command=self._open_benchmark,
                                     width=96, height=34, radius=13, parent_bg=CARD)
        self.bench_btn.place(x=16, y=664)
        self.set_btn = RoundButton(self.side, "设置", command=self._open_settings,
                                   width=96, height=34, radius=13, parent_bg=CARD)
        self.set_btn.place(x=120, y=664)

    def _build_chat(self):
        self.chat_cv = tk.Canvas(self.chat_panel, bg=CARD, highlightthickness=0, bd=0)
        self.chat_cv.pack(side="left", fill="both", expand=True, padx=(0, 0))
        self.chat_scroll = SlimScroll(self.chat_panel, self.chat_cv, bg=CARD)
        self.chat_scroll.pack(side="right", fill="y", padx=(0, 6), pady=10)
        self.chat_cv.configure(yscrollcommand=self.chat_scroll.set)
        self.chat_inner = tk.Frame(self.chat_cv, bg=CARD)
        self.chat_win = self.chat_cv.create_window(0, 0, window=self.chat_inner, anchor="nw")
        self.chat_cv.bind("<Configure>", self._on_chat_resize)
        self.chat_inner.bind("<Configure>", lambda e: self.chat_cv.configure(
            scrollregion=self.chat_cv.bbox("all")))
        self.chat_inner.bind("<Configure>", lambda e: self._auto_scroll(), add="+")

    def _build_input(self):
        self.input_frame = tk.Frame(self.input_panel, bg=CARD)

        self.row_chips = tk.Frame(self.input_frame, bg=CARD)
        self.chips_row = tk.Frame(self.row_chips, bg=CARD)
        self.chips_row.pack(side="left")

        self.row_top = tk.Frame(self.input_frame, bg=CARD)
        self.row_top.pack(fill="x", padx=18, pady=(16, 0))

        self.field = tk.Canvas(self.row_top, bg=CARD, height=52,
                               highlightthickness=0, bd=0)
        self.field.pack(side="left", fill="both", expand=True)
        self.entry = tk.Text(self.field, bg=FIELD_BG, fg=INK, font=F(11),
                             borderwidth=0, highlightthickness=0, padx=10, pady=6,
                             insertbackground=ACCENT, wrap="word", spacing1=2, spacing2=3)
        self._entry_win = self.field.create_window(14, 7, window=self.entry, anchor="nw")
        self.field.bind("<Configure>", self._draw_field)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Control-v>", self._on_paste)

        self.send_btn = RoundButton(self.row_top, "发送", command=self._send,
                                    kind="primary", width=76, height=52, radius=16,
                                    size=10, parent_bg=CARD)
        self.send_btn.pack(side="right", padx=(10, 0))

        self.row_bot = tk.Frame(self.input_frame, bg=CARD)
        self.row_bot.pack(fill="x", padx=18, pady=(10, 0))
        self.file_btn = RoundButton(self.row_bot, "＋ 文件", command=self._pick_files,
                                    width=92, height=32, radius=12, parent_bg=CARD)
        self.file_btn.pack(side="left")
        self.stop_btn = RoundButton(self.row_bot, "停止", command=self._stop,
                                    width=68, height=32, radius=12, parent_bg=CARD)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.set_enabled(False)

        self.hint = tk.Label(self.row_bot, text="", bg=CARD, fg=MUTED, font=F(8))
        self.hint.pack(side="right", padx=(12, 0))
        self.static_hint = tk.Label(self.row_bot,
                                    text="Enter 发送 · Shift+Enter 换行 · Ctrl+V 粘贴图片",
                                    bg=CARD, fg=MUTED, font=F(8))
        self.static_hint.pack(side="right")

        self._set_placeholder()

    # ------------------------------------------------------------ 背景与布局
    def _on_resize(self, _e=None):
        if self._rz_job:
            self.root.after_cancel(self._rz_job)
        self._rz_job = self.root.after(120, self._do_layout)

    def _bg_source(self):
        """背景源图缓存：避免每次重排都重新解码 JPEG。"""
        path = self._bg_path()
        cache = getattr(self, "_src_cache", None)
        if cache and cache[0] == path:
            return cache[1]
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            img = Image.new("RGB", (16, 9), (232, 237, 245))
        self._src_cache = (path, img)
        return img

    def _make_backdrop(self, w, h):
        try:
            src = self._bg_source().copy()
        except Exception:
            return Image.new("RGB", (w, h), (232, 237, 245))
        s = max(w / src.width, h / src.height)
        src = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))),
                         Image.LANCZOS)
        left = (src.width - w) // 2
        top = max(0, int((src.height - h) * 0.35))
        src = src.crop((left, top, left + w, top + h))
        src = src.filter(ImageFilter.GaussianBlur(5))
        if THEME == "dark":
            src = Image.blend(src, Image.new("RGB", (w, h), (8, 10, 14)), 0.74)
        else:
            src = Image.blend(src, Image.new("RGB", (w, h), (255, 255, 255)), 0.26)
        veil = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(veil)
        for y in range(h):
            a = int(max(0, 34 - 44 * (y / max(1, h))))
            d.line([(0, y), (w, y)], fill=(236, 242, 252, a))
        out = Image.alpha_composite(src.convert("RGBA"), veil).convert("RGB")
        return out

    def _panel_image(self, x, y, w, h, radius=24):
        """从背景裁一块，做磨砂 + 圆角 + 阴影（带缓存）。"""
        w, h = max(8, int(w)), max(8, int(h))
        key = (int(x), int(y), w, h, radius, self.glass)
        cache = getattr(self, "_panel_cache", None)
        if cache is None:
            cache = self._panel_cache = {}
        hit = cache.get(key)
        if hit is not None:
            return hit
        if len(cache) > 12:
            cache.clear()
        bw, bh = self.backdrop.size
        x, y = max(0, min(bw - w, int(x))), max(0, min(bh - h, int(y)))
        base = self.backdrop.crop((x, y, x + w, y + h)).convert("RGBA")
        frost = base.filter(ImageFilter.GaussianBlur(4))
        frost = Image.blend(frost.convert("RGB"),
                            Image.new("RGB", (w, h), (255, 255, 255)), 0.30).convert("RGBA")

        pad = 26
        sh = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [pad, pad + 4, pad + w, pad + h + 4], radius=radius,
            fill=(90, 110, 150, 40))
        sh = sh.filter(ImageFilter.GaussianBlur(12)).crop((pad, pad, pad + w, pad + h))
        out = Image.alpha_composite(sh, frost)

        body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gr, gg, gb = getattr(self, "glass_rgb", (250, 249, 251))
        alpha = 224 if THEME == "dark" else getattr(self, "glass_alpha", 150)
        ImageDraw.Draw(body).rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=radius,
            fill=(gr, gg, gb, alpha))
        out = Image.alpha_composite(out, body)
        border = (255, 255, 255, 38) if THEME == "dark" else (255, 255, 255, 200)
        ImageDraw.Draw(out).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius,
                                              outline=border, width=1)
        cache[key] = out
        return out

    def _do_layout(self):
        self._rz_job = None
        W = self.root.winfo_width()
        H = self.root.winfo_height()
        if W < 200 or H < 200:
            return
        if (W, H) == self._last_size:
            return
        self._last_size = (W, H)

        self.backdrop = self._make_backdrop(W, H)
        self._compute_glass()
        self._bg_photo = ImageTk.PhotoImage(self.backdrop)
        self.canvas.delete("bg")
        self.canvas.create_image(0, 0, image=self._bg_photo, anchor="nw", tags="bg")

        PAD, HEADER, SIDEBAR, GAP = 28, 66, 238, 22
        top = HEADER
        bottom = H - PAD - 26
        side_h = bottom - top
        rx = PAD + SIDEBAR + GAP
        rw = W - rx - PAD

        input_h = 132 + (44 if self.attachments else 0)
        chat_h = bottom - top - input_h - 14

        # 顶栏文字
        self.canvas.delete("hdr")
        self.canvas.create_text(PAD + 4, 34, text="Local", anchor="w",
                                fill=INK, font=F(19, "bold"), tags="hdr")
        tw = tkfont.Font(font=F(19, "bold")).measure("Local")
        self.canvas.create_text(PAD + 4 + tw + 12, 38, text="LLM Chat", anchor="w",
                                fill=INK_SOFT, font=F(11), tags="hdr")
        pill_w = 210
        px = W - PAD - pill_w
        round_rect(self.canvas, px, 20, px + pill_w, 52, 16,
                   fill=CARD, outline=LINE, tags=("hdr", "hdr_pill"))
        self.canvas.create_oval(px + 16, 31, px + 24, 39, fill=OK, outline="", tags="hdr")

        # 面板
        self._place_panel(self.side, PAD, top, SIDEBAR, side_h, 26)
        self._place_panel(self.chat_panel, rx, top, rw, chat_h, 26)
        self._place_panel(self.input_panel, rx, top + chat_h + 14, rw, input_h, 22)

        # 侧栏内部
        self.new_btn.configure(width=SIDEBAR - 32)
        self.new_btn._fixed_w = SIDEBAR - 32
        self.new_btn._compute()
        self.sess_wrap.place_configure(x=10, y=324, width=SIDEBAR - 20,
                                       height=max(120, side_h - 324 - 110))
        self.bench_btn.place_configure(x=16, y=side_h - 62)
        self.set_btn.place_configure(x=116, y=side_h - 62)

        # 输入区（Frame 布局，不会裁切）
        self.input_frame.place_configure(x=0, y=0, width=rw, height=input_h)

        self._redraw_side_card()
        self._apply_glass()
        self._do_layout_soft()
        self._auto_scroll(force=False)

    def _compute_glass(self):
        """从背景取平均色，混白后作为玻璃底色。"""
        try:
            r, g, b = self.backdrop.resize((1, 1), Image.LANCZOS).getpixel((0, 0))[:3]
        except Exception:
            r, g, b = (246, 244, 249)
        if THEME == "dark":
            base, mix = (22, 26, 34), 0.80
        else:
            base, mix = (255, 255, 255), 0.70
        r = int(r * (1 - mix) + base[0] * mix)
        g = int(g * (1 - mix) + base[1] * mix)
        b = int(b * (1 - mix) + base[2] * mix)
        self.glass_rgb = (r, g, b)
        self.glass = "#%02X%02X%02X" % (r, g, b)

    def _apply_glass(self):
        g = getattr(self, "glass", CARD)
        for w in (self.side, self.side_card, self.sess_cv, self.sess_inner,
                  self.chat_cv, self.chat_inner, self.input_frame, self.row_top,
                  self.row_chips, self.chips_row, self.row_bot, self.field):
            try:
                w.configure(bg=g)
            except Exception:
                pass
        for lb in (self.sess_title, self.static_hint, self.hint):
            try:
                lb.configure(bg=g)
            except Exception:
                pass
        for btn in (self.new_btn, self.bench_btn, self.set_btn,
                    self.file_btn, self.stop_btn, self.send_btn):
            try:
                btn._bgcolor = g
                btn.configure(bg=g)
                btn._paint()
            except Exception:
                pass
        for row in getattr(self, "sess_rows", []):
            try:
                row.configure(bg=g)
                row.paint()
            except Exception:
                pass
        for b in self.bubbles:
            try:
                b.configure(bg=g)
                b.cv.configure(bg=g)
                b._row.configure(bg=g)
            except Exception:
                pass
        # 系统提示行等没有气泡的行，也要统一底色
        try:
            for row in self.chat_inner.winfo_children():
                row.configure(bg=g)
                for child in row.winfo_children():
                    if isinstance(child, tk.Label):
                        child.configure(bg=g)
        except Exception:
            pass

    def _place_panel(self, panel_cv, x, y, w, h, radius):
        img = self._panel_image(x, y, w, h, radius)
        panel_cv.configure(width=int(w), height=int(h))
        panel_cv.photo = ImageTk.PhotoImage(img)
        panel_cv.delete("panel")
        panel_cv.create_image(0, 0, image=panel_cv.photo, anchor="nw", tags="panel")
        panel_cv.place(x=int(x), y=int(y), width=int(w), height=int(h))

    def _redraw_side_card(self):
        try:
            src = Image.open(self._side_path()).convert("RGB")
        except Exception:
            return
        w, h = 200, 214
        s = max(w / src.width, h / src.height)
        src = src.resize((int(src.width * s), int(src.height * s)), Image.LANCZOS)
        left = int((src.width - w) * 0.42)
        top = max(0, int((src.height - h) * 0.10))
        src = src.crop((left, top, left + w, top + h)).convert("RGBA")
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=20, fill=255)
        src.putalpha(mask)
        self.side_card_photo = ImageTk.PhotoImage(src)
        self.side_card.delete("all")
        self.side_card.create_image(0, 0, image=self.side_card_photo, anchor="nw")

    def _model_text(self):
        label = self.backend.label if self.backend else "未连接"
        return f"{label} · {self.current_model}"

    def _status_text(self):
        base = f"{self.current_model} · 上下文 {int(self.settings['num_ctx']) // 1024}K"
        if self.streaming and self._first and self._chars:
            gen = max(0.1, time.time() - self._first)
            base += f" · 实时 ≈{(self._chars / self.calib) / gen:.0f} tok/s"
        return base

    def _refresh_header(self):
        try:
            self.canvas.delete("hdr_dyn")
        except Exception:
            pass
        self._do_layout_soft()

    def _do_layout_soft(self):
        """只重画顶栏与底栏文字，不重算面板。"""
        W = self.root.winfo_width()
        H = self.root.winfo_height()
        self.canvas.delete("hdr_txt")
        pill_w = 210
        px = W - 22 - pill_w
        self.canvas.create_text(px + 32, 36, anchor="w", fill=INK_SOFT, font=F(9),
                                text=self._model_text(), tags=("hdr_txt", "hdr_pill"))
        self.canvas.create_text(W - 26, H - 12, anchor="e", fill=INK_SOFT, font=F(9),
                                text=self._status_text(), tags="hdr_txt")

    # ------------------------------------------------------------ 会话
    def _session_files(self):
        try:
            fs = [os.path.join(SESSION_DIR, f) for f in os.listdir(SESSION_DIR)
                  if f.endswith(".json")]
        except Exception:
            return []
        try:
            fs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        except Exception:
            pass
        return fs

    def _load_sessions(self):
        for w in self.sess_inner.winfo_children():
            w.destroy()
        self.sess_paths = []
        self.sess_rows = []
        for p in self._session_files():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                title = d.get("title") or "未命名对话"
            except Exception:
                continue
            self.sess_paths.append(p)
            row = self._make_session_row(title[:20], len(self.sess_paths) - 1)
            self.sess_rows.append(row)

    def _make_session_row(self, title, idx):
        cv = tk.Canvas(self.sess_inner, bg=CARD, height=34, highlightthickness=0, bd=0)
        cv.pack(fill="x", pady=1)
        selected = {"v": False}

        def paint(hover=False):
            cv.delete("all")
            col = ACCENT_SOFT if (hover or selected["v"]) else getattr(self, "glass", CARD)
            round_rect(cv, 2, 3, cv.winfo_width() - 2, 31, 12, fill=col, outline="")
            cv.create_text(14, 17, text=title, anchor="w",
                           fill=ACCENT if selected["v"] else INK_SOFT, font=F(9))

        cv.bind("<Configure>", lambda e: paint())
        cv.bind("<Enter>", lambda e: paint(True))
        cv.bind("<Leave>", lambda e: paint(False))
        cv.bind("<Button-1>", lambda e: self._on_pick_session(idx))
        cv.selected_state = selected
        cv.paint = paint
        return cv

    def _mark_selected(self, idx):
        for i, row in enumerate(getattr(self, "sess_rows", [])):
            row.selected_state["v"] = (i == idx)
            row.paint()

    def _new_session(self, confirm=True):
        if confirm and self.streaming:
            messagebox.showinfo("提示", "正在生成中，先停止再开新对话。")
            return
        self.session_id = uuid.uuid4().hex[:12]
        self.session_path = os.path.join(SESSION_DIR, self.session_id + ".json")
        self.messages = []
        self.last_answer = ""
        self.attachments = []
        self._ingesting = 0
        self.bubbles = []
        self._cur_bubble = None
        for w in self.chat_inner.winfo_children():
            w.destroy()
        self._mark_selected(-1)
        self._refresh_chips()
        if self.current_model:
            self._add_system_note(
                f"已连接 {self.current_model}"
                f"（{self.backend.label if self.backend else '未配置'}）。"
                "输入问题，或点「＋ 文件」添加文档/图片。")
        else:
            self._add_system_note(
                "还没有连接模型。点左下角「设置」，选个预设或填服务地址，"
                "再点「获取列表」挑一个模型。")
        self.entry.focus_set()

    def _save_session(self):
        if not self.messages:
            return
        title = self.messages[0]["content"].strip().replace("\n", " ")[:24] or "未命名对话"
        data = {"id": self.session_id, "title": title,
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "messages": self.messages}
        try:
            with open(self.session_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._load_sessions()
        except Exception:
            pass

    def _on_pick_session(self, idx):
        if self.streaming or idx >= len(self.sess_paths):
            return
        try:
            with open(self.sess_paths[idx], "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        self.session_path = self.sess_paths[idx]
        self.session_id = d.get("id") or uuid.uuid4().hex[:12]
        self.messages = d.get("messages", [])
        self.last_answer = ""
        self.bubbles = []
        self._cur_bubble = None
        for w in self.chat_inner.winfo_children():
            w.destroy()
        self._mark_selected(idx)
        for m in self.messages:
            if m["role"] == "user":
                self._add_bubble(m["content"].strip(), "user")
            elif m["role"] == "assistant":
                self._add_bubble(m["content"].strip(), "asst")
                self.last_answer = m["content"]
        self._auto_scroll(force=True)

    # ------------------------------------------------------------ 气泡渲染
    def _row(self):
        row = tk.Frame(self.chat_inner, bg=getattr(self, "glass", CARD))
        row.pack(fill="x", padx=18, pady=4)
        return row

    def _add_bubble(self, text, role):
        row = self._row()
        max_w = max(320, int(self.chat_cv.winfo_width() * 0.72))
        g = getattr(self, "glass", CARD)
        if role == "user":
            b = Bubble(row, g, BUBBLE_USER, "#FFFFFF", text=text, max_w=max_w,
                       radius=20)
            b.pack(side="right")
        elif role == "think":
            b = Bubble(row, g, THINK_BG, MUTED, text=text, max_w=max_w,
                       italic=True, radius=14, pad_x=12, pad_y=8)
            b.pack(side="left")
        else:
            b = Bubble(row, g, BUBBLE_ASST, INK, text=text, max_w=max_w, radius=20)
            b.pack(side="left")
        b._row = row
        if role != "think":
            b.label.bind("<Button-3>", lambda e, bb=b: self._copy_bubble(bb))
        self.bubbles.append(b)
        self._auto_scroll(force=True)
        return b

    def _add_system_note(self, text):
        row = self._row()
        tk.Label(row, text=text, bg=getattr(self, "glass", CARD), fg=MUTED, font=F(9),
                 wraplength=max(360, int(self.chat_cv.winfo_width() * 0.8)),
                 justify="center").pack(side="top")
        self._auto_scroll(force=True)

    def _copy_bubble(self, bubble):
        txt = bubble.get_text()
        if txt:
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self._toast("已复制这条消息")

    def _auto_scroll(self, force=False):
        try:
            first, last = self.chat_cv.yview()
        except Exception:
            return
        if force or last >= 0.98:
            self.chat_cv.update_idletasks()
            self.chat_cv.yview_moveto(1.0)
            self._on_chat_scroll()

    def _on_chat_scroll(self):
        try:
            self.chat_scroll.set(*self.chat_cv.yview())
        except Exception:
            pass

    def _on_chat_resize(self, e):
        self.chat_cv.itemconfigure(self.chat_win, width=e.width)
        self._on_chat_scroll()
        self._auto_scroll()

    def _wheel(self, event):
        try:
            self.chat_cv.yview_scroll(int(-1 * (event.delta / 120)), "units")
            self._on_chat_scroll()
        except Exception:
            pass

    # ------------------------------------------------------------ 附件
    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="选择要发给模型的文件",
            filetypes=[("常用文档与图片", ALL_TYPES), ("所有文件", "*.*")])
        if paths:
            self._add_paths(list(paths))

    def _on_paste(self, _event):
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
        except Exception:
            return None
        if data is None:
            return None
        if isinstance(data, list):
            files = [p for p in data if isinstance(p, str) and os.path.isfile(p)]
            if files:
                self._add_paths(files)
                return "break"
            return None
        try:
            path = os.path.join(UPLOAD_DIR, f"paste_{time.strftime('%H%M%S')}.png")
            data.save(path)
            self._add_paths([path])
            return "break"
        except Exception:
            return None

    def _on_drop(self, paths):
        """拖拽回调可能在 Tk 的消息循环外触发，切回主线程处理。"""
        try:
            self.root.after(0, lambda: self._add_paths(paths))
        except Exception:
            pass

    def _add_paths(self, paths):
        paths = [p for p in paths if p][:12]
        if not paths:
            return
        self._ingesting += len(paths)
        self._refresh_chips()
        threading.Thread(target=self._ingest_worker, args=(paths,), daemon=True).start()

    def _ingest_worker(self, paths):
        for p in paths:
            self.q.put(("file", extract.extract(p)))

    def _refresh_chips(self):
        for w in self.chips_row.winfo_children():
            w.destroy()
        for idx, a in enumerate(self.attachments):
            if a.get("error"):
                meta, color = "失败", BAD
            elif a.get("kind") == "image":
                meta, color = a.get("detail", "图片"), ACCENT
            else:
                meta, color = f"{a['chars']}字", OK
            thumb = a.get("path") if a.get("kind") == "image" and not a.get("error") else None
            Chip(self.chips_row, a["name"], meta, color,
                 bg=getattr(self, "glass", CARD), thumb=thumb,
                 on_close=lambda i=idx: self._remove_attachment(i)).pack(side="left", padx=4)
        if self._ingesting:
            tk.Label(self.chips_row, text=f"解析中 {self._ingesting}…", bg=CARD,
                     fg=MUTED, font=F(8)).pack(side="left", padx=6)
        if self.attachments:
            if not self.row_chips.winfo_ismapped():
                self.row_chips.pack(fill="x", padx=18, pady=(14, 0),
                                    before=self.row_top)
                self._last_size = (0, 0)
                self._on_resize()
        else:
            if self.row_chips.winfo_ismapped():
                self.row_chips.pack_forget()
                self._last_size = (0, 0)
                self._on_resize()

    def _remove_attachment(self, idx):
        if 0 <= idx < len(self.attachments):
            self.attachments.pop(idx)
            self._refresh_chips()

    # ------------------------------------------------------------ 输入
    def _draw_field(self, _e=None):
        w = self.field.winfo_width()
        h = self.field.winfo_height()
        if w < 8 or h < 8:
            return
        self.field.delete("bg")
        round_rect(self.field, 1, 1, w - 1, h - 1, 16,
                   fill=FIELD_BG, outline=FIELD_LINE, tags="bg")
        self.field.tag_lower("bg")
        self.field.itemconfigure(self._entry_win, width=w - 28, height=h - 14)

    def _set_placeholder(self, _e=None):
        pass

    def _clear_placeholder(self, _e=None):
        pass

    def _on_enter(self, event):
        if event.state & 0x0001:
            return None
        self._send()
        return "break"

    def _toast(self, text):
        self.hint.configure(text=text)
        self.root.after(2500, lambda: self.hint.configure(text=""))

    # ------------------------------------------------------------ 发送
    def _send(self):
        if self.streaming or self._ingesting > 0:
            return
        text = self.entry.get("1.0", "end").strip()
        if not text and not self.attachments:
            return
        self.entry.delete("1.0", "end")

        infos = list(self.attachments)
        images = []
        for a in infos:
            if a.get("kind") == "image" and not a.get("error"):
                try:
                    with open(a["path"], "rb") as f:
                        images.append(base64.b64encode(f.read()).decode())
                except Exception:
                    pass

        self.current_model = ((self.settings.get("vision_model") or
                               self.settings.get("model")) if images
                              else self.settings.get("model"))
        self._do_layout_soft()

        note = []
        for a in infos:
            if a.get("error"):
                note.append(f"{a['name']}（失败）")
            elif a.get("kind") == "image":
                note.append(f"图片 {a['name']}")
            else:
                note.append(f"{a['name']}（{a['chars']}字）")
        shown = text if text else "（请阅读附件）"
        if note:
            shown = "📎 " + "、".join(note) + "\n" + shown
        self._add_bubble(shown, "user")

        context_block, warnings = extract.build_context(
            infos, budget_tokens=int(int(self.settings["num_ctx"]) * 0.6))
        for w in warnings:
            self._add_system_note(f"提示：{w}")

        if not text:
            text = "请阅读以上文件内容，并用中文总结要点。" if context_block else \
                   "请看这张图片，描述里面的内容。"
        full = (context_block + "\n\n【用户的问题】\n" + text) if context_block else text

        self.messages.append({"role": "user", "content": full})
        self.attachments = []
        self._refresh_chips()

        self._cur_bubble = self._add_bubble("", "asst")
        self.streaming = True
        self.cancel_flag = False
        self.stop_btn.set_enabled(True)
        self.send_btn.set_enabled(False)
        self._t0 = time.time()
        self._chars = 0
        self._first = None
        self._tick()
        threading.Thread(target=self._worker, args=(images,), daemon=True).start()

    def _worker(self, images):
        msgs = []
        sys_prompt = (self.settings.get("system") or "").strip()
        if sys_prompt:
            msgs.append({"role": "system", "content": sys_prompt})
        msgs.extend(self.messages)

        answer = []
        metrics = {}
        if self.backend is None:
            self.q.put(("error", "没有配置模型服务，点左下角「设置」填服务地址"))
        elif not (self.current_model or "").strip():
            self.q.put(("error", "还没有选择模型，去「设置」里点「获取列表」选一个"))
        else:
            try:
                for kind, val in self.backend.stream_chat(
                        self.current_model, msgs, images=images,
                        temperature=float(self.settings.get("temperature", 0.6)),
                        num_ctx=int(self.settings.get("num_ctx", 32768)),
                        think=bool(self.settings.get("think"))):
                    if self.cancel_flag:
                        break
                    if kind == "content":
                        self.q.put(("content", val))
                        answer.append(val)
                    elif kind == "thinking":
                        self.q.put(("think", val))
                    elif kind == "done":
                        metrics = val or {}
            except Exception as e:
                self.q.put(("error", str(e)))
        self.q.put(("done", {"text": "".join(answer), "metrics": metrics}))

    def _stop(self):
        self.cancel_flag = True

    def _tick(self):
        if not self.streaming:
            return
        self._do_layout_soft()
        self.root.after(300, self._tick)

    def _drain(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "content":
                    if self._first is None:
                        self._first = time.time()
                    if self._cur_bubble is not None:
                        self._cur_bubble.append(val)
                        self._chars += len(val)
                        self._auto_scroll()
                elif kind == "think":
                    if self._first is None:
                        self._first = time.time()
                elif kind == "file":
                    self._ingesting = max(0, self._ingesting - 1)
                    if val.get("error"):
                        self._add_system_note(f"附件失败：{val['name']} — {val['error']}")
                    else:
                        self.attachments.append(val)
                    self._refresh_chips()
                elif kind == "error":
                    self._add_system_note(f"出错：{val}")
                elif kind == "done":
                    self._finish(val)
        except queue.Empty:
            pass
        self.root.after(40, self._drain)

    def _finish(self, payload):
        self.streaming = False
        self.stop_btn.set_enabled(False)
        self.send_btn.set_enabled(True)
        text = (payload.get("text") or "").strip()
        if text:
            self.messages.append({"role": "assistant", "content": text})
            self.last_answer = text
            if self._cur_bubble is not None:
                self._cur_bubble.set_text(text)
            self._save_session()
        else:
            if self._cur_bubble is not None:
                self._cur_bubble.set_text("（没有返回内容）")
        self._cur_bubble = None
        m = payload.get("metrics") or {}
        ec, ed = m.get("eval_count") or 0, m.get("eval_duration") or 0
        ttft = (self._first - self._t0) if self._first else None
        if ec and ed:
            tps = ec / (ed / 1e9)
            extra = f" · {tps:.1f} tok/s"
            if ttft:
                extra += f" · 首字 {ttft:.2f}s"
            self._last_speed = extra
            if self._chars and ec:
                self.calib = max(0.8, min(5.0, self._chars / ec))
                self.settings["calib"] = round(self.calib, 3)
                save_settings(self.settings)
        self._do_layout_soft()
        self._auto_scroll(force=True)

    # ------------------------------------------------------------ 设置 / 测速
    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.configure(bg=DIALOG_BG)
        win.geometry("560x680")
        win.transient(self.root)
        win.grab_set()

        def lab(t, y, x=28):
            tk.Label(win, text=t, bg=DIALOG_BG, fg=INK_SOFT,
                     font=F(9)).place(x=x, y=y)

        def entry(var, y, x=28, w=504, show=""):
            e = tk.Entry(win, textvariable=var, bg=ENTRY_BG, fg=INK,
                         insertbackground=ACCENT, borderwidth=0, font=F(10), show=show)
            e.place(x=x, y=y, width=w, height=30)
            return e

        def head(t, y):
            tk.Label(win, text=t, bg=DIALOG_BG, fg=INK,
                     font=F(11, "bold")).place(x=28, y=y)

        # ---------------- 模型服务
        head("模型服务", 14)

        lab("常用预设", 40)
        preset_var = tk.StringVar(value="")
        cb_preset = ttk.Combobox(win, textvariable=preset_var, state="readonly",
                                 font=F(9),
                                 values=[x[0] for x in providers.PRESETS] + ["自定义"])
        cb_preset.place(x=28, y=60, width=220, height=28)

        lab("协议类型", 40, x=268)
        kind_var = tk.StringVar(value=self.settings.get("backend", "ollama"))
        ttk.Combobox(win, textvariable=kind_var, state="readonly", font=F(9),
                     values=list(providers.BACKENDS.keys())
                     ).place(x=268, y=60, width=120, height=28)

        lab("服务地址", 96)
        url_var = tk.StringVar(value=self.settings.get("base_url", ""))
        entry(url_var, 116, w=380)
        test_btn = RoundButton(win, "测试", command=lambda: do_test(),
                               width=110, height=30, parent_bg=DIALOG_BG)
        test_btn.place(x=422, y=116)

        lab("API Key（本地服务通常留空）", 152)
        key_var = tk.StringVar(value=self.settings.get("api_key", ""))
        entry(key_var, 172, show="*")

        lab("模型", 208)
        model_var = tk.StringVar(value=self.settings.get("model", ""))
        model_cb = ttk.Combobox(win, textvariable=model_var, font=F(9), values=[])
        model_cb.place(x=28, y=228, width=380, height=28)
        RoundButton(win, "获取列表", command=lambda: do_fetch(),
                    width=110, height=30, parent_bg=DIALOG_BG).place(x=422, y=228)

        lab("视觉模型（可选，留空则图片直接发给主模型）", 264)
        vmodel_var = tk.StringVar(value=self.settings.get("vision_model", ""))
        entry(vmodel_var, 284)

        # ---------------- 生成参数
        head("生成参数", 326)
        lab("温度", 352)
        temp_var = tk.StringVar(value=str(self.settings["temperature"]))
        tk.Spinbox(win, from_=0.0, to=2.0, increment=0.05, textvariable=temp_var,
                   bg=ENTRY_BG, fg=INK, borderwidth=0, font=F(9),
                   buttonbackground=ENTRY_BG).place(x=28, y=372, width=120, height=28)

        lab("上下文", 352, x=168)
        ctx_var = tk.StringVar(value=str(self.settings["num_ctx"]))
        ttk.Combobox(win, textvariable=ctx_var, state="readonly", font=F(9),
                     values=["2048", "4096", "8192", "16384", "32768", "40960"]
                     ).place(x=168, y=372, width=130, height=28)

        think_var = tk.BooleanVar(value=bool(self.settings.get("think")))
        tk.Checkbutton(win, text="开启思考模式（慢，推理更细）", variable=think_var,
                       bg=DIALOG_BG, fg=INK_SOFT, selectcolor=ENTRY_BG,
                       activebackground=DIALOG_BG, font=F(9), borderwidth=0,
                       highlightthickness=0).place(x=318, y=370)

        lab("系统提示词（可留空）", 408)
        sys_var = tk.StringVar(value=self.settings.get("system", ""))
        entry(sys_var, 428)

        # ---------------- 外观
        head("外观", 462)

        lab("主题", 488)
        theme_var = tk.StringVar(value=self.settings.get("theme", "light"))
        ttk.Combobox(win, textvariable=theme_var, state="readonly", font=F(9),
                     values=["light", "dark"]
                     ).place(x=108, y=486, width=140, height=26)
        lab("（保存后立即生效）", 516)

        bg_lbl = tk.Label(win, text=os.path.basename(self._bg_path()),
                          bg=DIALOG_BG, fg=MUTED, font=F(8), anchor="w")
        side_lbl = tk.Label(win, text=os.path.basename(self._side_path()),
                            bg=DIALOG_BG, fg=MUTED, font=F(8), anchor="w")

        lab("窗口背景图", 548)
        bg_lbl.place(x=108, y=549, width=200)
        RoundButton(win, "选择", command=lambda: pick("bg_image", bg_lbl),
                    width=70, height=26, parent_bg=DIALOG_BG).place(x=318, y=546)
        RoundButton(win, "默认", command=lambda: reset("bg_image", bg_lbl),
                    width=70, height=26, parent_bg=DIALOG_BG).place(x=396, y=546)

        lab("侧栏图片", 584)
        side_lbl.place(x=108, y=585, width=200)
        RoundButton(win, "选择", command=lambda: pick("side_image", side_lbl),
                    width=70, height=26, parent_bg=DIALOG_BG).place(x=318, y=582)
        RoundButton(win, "默认", command=lambda: reset("side_image", side_lbl),
                    width=70, height=26, parent_bg=DIALOG_BG).place(x=396, y=582)

        # ---------------- 行为
        def sync_backend():
            self.settings["backend"] = kind_var.get()
            self.settings["base_url"] = url_var.get().strip()
            self.settings["api_key"] = key_var.get()
            self._make_backend()

        def on_preset(_e=None):
            name = preset_var.get()
            for label, kind, url in providers.PRESETS:
                if label == name:
                    kind_var.set(kind)
                    url_var.set(url)
                    return

        cb_preset.bind("<<ComboboxSelected>>", on_preset)

        def do_test():
            sync_backend()
            if self.backend is None:
                messagebox.showerror("失败", "地址没填或协议不对", parent=win)
                return

            def work():
                try:
                    v = self.backend.ping()
                    win.after(0, lambda: messagebox.showinfo(
                        "连接成功", f"{self.backend.label} 在线：{v}", parent=win))
                except Exception as ex:
                    win.after(0, lambda: messagebox.showerror(
                        "连接失败", str(ex), parent=win))
            threading.Thread(target=work, daemon=True).start()

        def do_fetch():
            sync_backend()
            if self.backend is None:
                return

            def work():
                try:
                    ms = self.backend.list_models()
                except Exception as ex:
                    win.after(0, lambda: messagebox.showerror(
                        "获取失败", str(ex), parent=win))
                    return

                def fill():
                    model_cb.configure(values=ms)
                    if ms and not model_var.get().strip():
                        model_var.set(ms[0])
                    messagebox.showinfo("完成", f"找到 {len(ms)} 个模型", parent=win)
                win.after(0, fill)
            threading.Thread(target=work, daemon=True).start()

        def pick(key, lbl):
            path = filedialog.askopenfilename(
                title="选择图片",
                filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"),
                           ("所有文件", "*.*")])
            if not path:
                return
            self.settings[key] = path
            lbl.configure(text=os.path.basename(path))
            self._apply_images()

        def reset(key, lbl):
            self.settings[key] = ""
            lbl.configure(text=os.path.basename(
                self._bg_path() if key == "bg_image" else self._side_path()))
            self._apply_images()

        def apply():
            self.settings["model"] = model_var.get().strip() or self.settings.get("model")
            self.settings["vision_model"] = vmodel_var.get().strip()
            try:
                self.settings["temperature"] = max(0.0, min(2.0, float(temp_var.get())))
            except Exception:
                pass
            try:
                self.settings["num_ctx"] = int(ctx_var.get())
            except Exception:
                pass
            self.settings["system"] = sys_var.get()
            self.settings["think"] = bool(think_var.get())
            sync_backend()
            save_settings(self.settings)
            self.current_model = self.settings["model"]
            new_theme = theme_var.get()
            self._apply_images()
            self._do_layout_soft()
            win.destroy()
            if new_theme != THEME:
                self._switch_theme(new_theme)

        RoundButton(win, "保存", command=apply, kind="primary",
                    width=110, height=34, parent_bg=DIALOG_BG).place(x=318, y=618)
        RoundButton(win, "取消", command=win.destroy,
                    width=110, height=34, parent_bg=DIALOG_BG).place(x=200, y=618)

    def _show_model_menu(self, _event=None):
        """点顶栏胶囊弹出模型列表，直接切换。"""
        if self.backend is None:
            return
        menu = tk.Menu(self.root, tearoff=0, bg=CARD, fg=INK, bd=0,
                       activebackground=ACCENT, activeforeground="#FFFFFF",
                       font=F(9))
        try:
            models = self.backend.list_models()
        except Exception:
            models = []
        for name in models:
            def pick(n=name):
                self.current_model = n
                self.settings["model"] = n
                save_settings(self.settings)
                self._do_layout_soft()
            mark = "● " if name == self.current_model else "   "
            menu.add_command(label=mark + name, command=pick)
        if not models:
            menu.add_command(label="（没找到模型）", state="disabled")
        menu.add_separator()
        menu.add_command(label="模型管理…", command=self._open_models)
        menu.add_command(label="刷新列表", command=self._do_layout_soft)
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def _open_models(self):
        ModelManager(self)

    def _switch_theme(self, name):
        """切主题：改全局配色后整窗重建，保留对话内容。"""
        if name == THEME:
            return
        apply_theme(name)
        self.settings["theme"] = THEME
        save_settings(self.settings)
        msgs = list(self.messages)
        for w in self.root.winfo_children():
            w.destroy()
        self.bubbles = []
        self._cur_bubble = None
        self._last_size = (0, 0)
        self._panel_cache = {}
        self._build()
        self._load_sessions()
        self._new_session(confirm=False)
        self.messages = msgs
        for m in msgs:
            role = "user" if m.get("role") == "user" else "asst"
            self._add_bubble(m.get("content", ""), role)
        self._do_layout_soft()

    def _open_benchmark(self):
        BenchmarkWindow(self)

    # ------------------------------------------------------------ 状态
    def _ping(self):
        def work():
            try:
                if self.backend is None:
                    raise RuntimeError("未配置")
                v = self.backend.ping()
                self.q.put(("online", f"{self.backend.label} {v}"))
                if not (self.settings.get("model") or "").strip():
                    try:
                        ms = self.backend.list_models()
                        if ms:
                            self.settings["model"] = ms[0]
                            self.current_model = ms[0]
                            save_settings(self.settings)
                            self.root.after(0, self._do_layout_soft)
                    except Exception:
                        pass
            except Exception:
                self.q.put(("offline", None))
        threading.Thread(target=work, daemon=True).start()
        self.root.after(8000, self._ping)


class ModelManager(tk.Toplevel):
    """本地模型管理：查看体积/量化、拉取、删除、设为当前。"""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("模型管理")
        self.configure(bg=DIALOG_BG)
        self.geometry("780x520")
        self.minsize(660, 440)
        self.transient(app.root)

        tk.Label(self, text="本地模型", bg=DIALOG_BG, fg=INK,
                 font=F(11, "bold")).place(x=24, y=14)
        RoundButton(self, "刷新", command=self.refresh, width=80, height=28,
                    parent_bg=DIALOG_BG).place(x=676, y=10)

        self.tree = ttk.Treeview(self, columns=("size", "params", "quant", "status"),
                                 show="tree headings", height=12)
        self.tree.heading("#0", text="模型")
        self.tree.heading("size", text="大小")
        self.tree.heading("params", text="参数")
        self.tree.heading("quant", text="量化")
        self.tree.heading("status", text="状态")
        self.tree.column("#0", width=280, anchor="w")
        self.tree.column("size", width=90, anchor="e")
        self.tree.column("params", width=80, anchor="center")
        self.tree.column("quant", width=100, anchor="center")
        self.tree.column("status", width=180, anchor="w")
        self.tree.place(x=24, y=44, width=732, height=290)
        self.tree.bind("<Double-1>", lambda e: self.use())

        y = 348
        self.entry = tk.Entry(self, bg=ENTRY_BG, fg=INK, insertbackground=ACCENT,
                              borderwidth=0, font=F(10))
        self.entry.place(x=24, y=y, width=380, height=32)
        self.entry.insert(0, "qwen3:8b")

        RoundButton(self, "拉取", command=self.pull, kind="primary", width=90,
                    height=32, parent_bg=DIALOG_BG).place(x=416, y=y)
        RoundButton(self, "设为当前", command=self.use, width=100,
                    height=32, parent_bg=DIALOG_BG).place(x=516, y=y)
        RoundButton(self, "删除", command=self.remove, width=90,
                    height=32, parent_bg=DIALOG_BG).place(x=626, y=y)

        self.status = tk.Label(self, text="", bg=DIALOG_BG, fg=MUTED,
                               font=F(9), anchor="w")
        self.status.place(x=24, y=396, width=732)

        tk.Label(self, text="双击某一行可直接切换；拉取后会自动出现在列表里",
                 bg=DIALOG_BG, fg=MUTED, font=F(8), anchor="w").place(x=24, y=424, width=732)

        self.refresh()

    # ---------------- 数据
    def _backend(self):
        return getattr(self.app, "backend", None)

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        b = self._backend()
        if b is None:
            self.status.configure(text="还没配置后端")
            return
        try:
            details = b.list_models_detail()
            running = b.running() if hasattr(b, "running") else {}
        except Exception as e:
            self.status.configure(text=f"读取失败：{e}")
            return
        for d in details:
            name = d["name"]
            key = name if name in running else (
                name + ":latest" if (name + ":latest") in running else None)
            st = ""
            if key:
                st = "运行中 · 显存 %.1f GB" % (running[key]["vram"] / 1e9)
            size = d.get("size") or 0
            self.tree.insert("", "end", text=name,
                             values=(("%.2f GB" % (size / 1e9)) if size else "—",
                                     d.get("params") or "—",
                                     d.get("quant") or "—", st))
        self.status.configure(text=f"共 {len(details)} 个模型")

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            self.status.configure(text="先选一个模型")
            return None
        return self.tree.item(sel[0], "text")

    # ---------------- 操作
    def use(self):
        name = self._selected()
        if not name:
            return
        self.app.current_model = name
        self.app.settings["model"] = name
        save_settings(self.app.settings)
        self.app._do_layout_soft()
        self.status.configure(text=f"当前模型已切换为 {name}")

    def remove(self):
        name = self._selected()
        if not name:
            return
        if not messagebox.askyesno("删除模型", f"确定删除 {name}？\n磁盘上的权重会被移除。",
                                   parent=self):
            return
        try:
            self._backend().delete(name)
            self.status.configure(text=f"已删除 {name}")
        except Exception as e:
            self.status.configure(text=f"删除失败：{e}")
        self.refresh()

    def pull(self):
        name = self.entry.get().strip()
        if not name:
            return
        b = self._backend()
        if b is None or not hasattr(b, "pull"):
            self.status.configure(text="当前后端不支持拉取")
            return
        self.status.configure(text=f"开始拉取 {name} …")

        def ui(msg):
            try:
                self.status.configure(text=msg)
            except Exception:
                pass

        def work():
            try:
                for obj in b.pull(name):
                    err = obj.get("error")
                    if err:
                        self.after(0, lambda e=err: ui(f"失败：{e}"))
                        return
                    st = obj.get("status") or ""
                    total = obj.get("total") or 0
                    done = obj.get("completed") or 0
                    if total:
                        pct = done * 100 // total
                        msg = "%s  %d%%  (%.1f / %.1f GB)" % (
                            st, pct, done / 1e9, total / 1e9)
                    else:
                        msg = st
                    self.after(0, lambda m=msg: ui(m))
                self.after(0, lambda: ui(f"{name} 拉取完成"))
                self.after(0, self.refresh)
            except Exception as e:
                self.after(0, lambda: ui(f"失败：{e}"))

        threading.Thread(target=work, daemon=True).start()


class BenchmarkWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("输出速度测试")
        self.configure(bg=DIALOG_BG)
        self.geometry("600x520")
        self.transient(app.root)
        self.running = False
        self.q = queue.Queue()
        self.t0 = 0.0
        self.first = None
        self.chars = 0

        tk.Label(self, text="固定提示词与生成长度，tok/s 才有可比性。",
                 bg=DIALOG_BG, fg=MUTED, font=F(9)).place(x=24, y=18)
        self.p_text = tk.Text(self, height=3, bg=ENTRY_BG, fg=INK, insertbackground=ACCENT,
                              borderwidth=0, font=F(10), padx=10, pady=8, wrap="word")
        self.p_text.place(x=24, y=44, width=552, height=76)
        self.p_text.insert("1.0", "用一个段落介绍光合作用，要求 200 字左右，语言通俗。")

        tk.Label(self, text="生成上限", bg=DIALOG_BG, fg=INK_SOFT,
                 font=F(9)).place(x=24, y=132)
        self.n_var = tk.StringVar(value="256")
        tk.Spinbox(self, from_=32, to=2048, increment=32, textvariable=self.n_var,
                   bg=ENTRY_BG, fg=INK, borderwidth=0, font=F(10),
                   buttonbackground=ENTRY_BG).place(x=88, y=128, width=90, height=30)
        self.think_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text="开思考模式", variable=self.think_var, bg=DIALOG_BG,
                       fg=INK_SOFT, selectcolor=ENTRY_BG, activebackground=DIALOG_BG,
                       font=F(9), borderwidth=0,
                       highlightthickness=0).place(x=196, y=130)

        self.run_btn = RoundButton(self, text="开始测速", command=self._run, kind="primary",
                                   width=552, height=38, radius=14, parent_bg=DIALOG_BG)
        self.run_btn.place(x=24, y=168)
        self.live = tk.Label(self, text="就绪", bg=DIALOG_BG, fg=MUTED, font=F(11, "bold"))
        self.live.place(x=24, y=216)
        self.out = tk.Text(self, bg=ENTRY_BG, fg=INK_SOFT, borderwidth=0,
                           font=("Consolas", 9), padx=12, pady=10, wrap="none",
                           state="disabled")
        self.out.place(x=24, y=248, width=552, height=250)
        self.out.configure(state="normal")
        self.out.insert("end", "  时间      tokens   耗时    tok/s    首字   提示词tok/s     总计\n")
        self.out.configure(state="disabled")

    def _run(self):
        if self.running:
            return
        prompt = self.p_text.get("1.0", "end").strip()
        if not prompt:
            return
        try:
            n = max(16, min(2048, int(self.n_var.get())))
        except Exception:
            n = 256
        self.running = True
        self.run_btn.set_enabled(False)
        self.live.configure(text="请求中…", fg=ACCENT)
        self.t0 = time.time()
        self.first = None
        self.chars = 0
        threading.Thread(target=self._work, args=(prompt, n, bool(self.think_var.get())),
                         daemon=True).start()
        self.after(80, self._poll)

    def _work(self, prompt, n, think):
        try:
            msgs = [{"role": "user", "content": prompt}]
            for kind, val in self.app.backend.stream_chat(
                    self.app.current_model, msgs, temperature=0.6,
                    num_ctx=8192, think=think):
                if kind == "done":
                    self.q.put(("done", val or {}))
                    return
                if val:
                    self.q.put(("chunk", val))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "chunk":
                    if self.first is None:
                        self.first = time.time()
                    self.chars += len(val)
                    gen = max(0.08, time.time() - self.first)
                    self.live.configure(
                        text=f"运行中 · {self.chars} 字 · ≈{self.chars / self.app.calib / gen:.0f} tok/s",
                        fg=ACCENT)
                elif kind == "done":
                    self._done(val)
                    return
                elif kind == "error":
                    self.running = False
                    self.run_btn.set_enabled(True)
                    self.live.configure(text="失败：" + val, fg=BAD)
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _done(self, o):
        self.running = False
        self.run_btn.set_enabled(True)
        ec, ed = o.get("eval_count") or 0, o.get("eval_duration") or 0
        pc, pd = o.get("prompt_eval_count") or 0, o.get("prompt_eval_duration") or 0
        tps = ec / (ed / 1e9) if ed else 0.0
        ttft = (self.first - self.t0) if self.first else 0.0
        total = time.time() - self.t0
        ptps = pc / (pd / 1e9) if pd else 0.0
        self.live.configure(text=f"完成：{tps:.1f} tok/s", fg=OK)
        line = ("  {ts}  {ec:>6}  {ed:5.2f}s  {tps:6.1f}"
                "  {ttft:5.2f}s  {ptps:10.0f}  {tot:6.2f}s\n").format(
                    ts=time.strftime("%H:%M:%S"), ec=ec, ed=ed / 1e9, tps=tps,
                    ttft=ttft, ptps=ptps, tot=total)
        self.out.configure(state="normal")
        self.out.insert("end", line)
        self.out.see("end")
        self.out.configure(state="disabled")
        if ec and self.chars:
            self.app.calib = max(0.8, min(5.0, self.chars / ec))


def main():
    root = tk.Tk()
    app = ChatApp(root)
    app._on_resize()

    argv = sys.argv[1:]
    if "--think" in argv:
        app.settings["think"] = True
    if "--ask" in argv:
        i = argv.index("--ask")
        if i + 1 < len(argv):
            q = argv[i + 1]

            def ask():
                app._clear_placeholder()
                app.entry.delete("1.0", "end")
                app.entry.insert("1.0", q)
                app._send()
            root.after(600, ask)
    if "--bench" in argv or "--bench-run" in argv:
        b = BenchmarkWindow(app)
        if "--bench-run" in argv:
            root.after(1200, b._run)

    root.mainloop()


if __name__ == "__main__":
    main()
