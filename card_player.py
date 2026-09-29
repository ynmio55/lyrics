"""
card_player.py - High-End Floating Lyric Player (Next-Gen Edition)
Features:
- Hardware audio synchronization (pygame.mixer.music.get_pos)
- Real-time live sync offset adjustment (Hotkeys: [ / ] or Left / Right arrows)
- Dynamic Island / Apple Music HUD, Modern Glass Cards, Cyberpunk Glow, and Cinema Subtitles
- Unicode/Thai combining-character safe typewriter effect & instant mode
- Floating toast HUD & top-right micro control toolbar
- Press ESC at any time to return to studio.
"""

import math
import os
import time
import tkinter as tk
import tkinter.font as tkfont
import unicodedata
from PIL import Image, ImageDraw, ImageTk
import pygame

# Default animation physics
RISE_SPEED = 60
BOTTOM_SPAWN_OFFSET = 140
TRANS_KEY = "#000002"
TRANS_KEY_RGB = (0, 0, 2)


def get_best_font():
    """Selects the cleanest, most modern font available on Windows."""
    try:
        fams = tkfont.families()
        for cand in [
            "Segoe UI Variable Display",
            "Segoe UI",
            "Leelawadee UI",
            "Bahnschrift",
            "Inter",
            "Tahoma",
        ]:
            if cand in fams:
                return cand
    except Exception:
        pass
    return "Helvetica"


BEST_FONT = get_best_font()


def split_graphemes(text: str):
    """
    Splits text into user-perceived character clusters (graphemes),
    ensuring Thai vowels and tone marks remain safely attached to base consonants.
    """
    clusters = []
    current = ""
    for char in text:
        is_combining = (
            unicodedata.combining(char) != 0
            or char in "\u0e30\u0e32\u0e33\u0e45\u0e46\u0e4d"
        )
        if is_combining and current:
            current += char
        else:
            if current:
                clusters.append(current)
            current = char
    if current:
        clusters.append(current)
    return clusters


def make_card_background(
    width, height, radius, bg_rgb, border_rgb, border_width=2
):
    """Draws a smooth rounded card using PIL and converts to PhotoImage."""
    img = Image.new("RGB", (width, height), TRANS_KEY_RGB)
    draw = ImageDraw.Draw(img)
    pad = 2
    draw.rounded_rectangle(
        [(pad, pad), (width - pad - 1, height - pad - 1)],
        radius=radius,
        fill=bg_rgb,
        outline=border_rgb,
        width=border_width,
    )
    return ImageTk.PhotoImage(img)


# Preset Visual Styles
STYLES = {
    "liquid_glass": {
        "name": "💎 Liquid Glass Karaoke",
        "mode": "island",
        "has_card": True,
        "box_w": 820,
        "box_h": 158,
        "radius": 34,
        "bg_rgb": (12, 22, 40),
        "border_rgb": (125, 211, 252),
        "border_width": 2,
        "badge_color": "#c4b5fd",
        "text_color": "#f8fafc",
        "subtext_color": "#64748b",
        "accent_color": "#7dd3fc",
        "future_color": "#64748b",
        "past_color": "#a5f3fc",
        "active_color": "#ffffff",
        "font_size": 23,
        "font_weight": "bold",
        "word_karaoke": True,
    },
    "floating_cards": {
        "name": "🌙 การ์ดลอยแก้วมน (Modern Glass Float)",
        "mode": "floating",
        "has_card": True,
        "box_w": 500,
        "box_h": 130,
        "radius": 24,
        "bg_rgb": (24, 24, 37),
        "border_rgb": (137, 180, 250),
        "border_width": 2,
        "badge_color": "#89b4fa",
        "text_color": "#ffffff",
        "font_size": 19,
        "font_weight": "bold",
    },
    "text_only": {
        "name": "✨ ตัวหนังสือลอยไร้กรอบ (Minimal Float Text)",
        "mode": "floating",
        "has_card": False,
        "box_w": 560,
        "box_h": 120,
        "text_color": "#ffffff",
        "shadow_color": "#0d0d15",
        "shadow_offset": 2,
        "font_size": 22,
        "font_weight": "bold",
    },
    "neon_cyber": {
        "name": "⚡ การ์ดนีออนไซเบอร์ลอย (Cyberpunk Neon Float)",
        "mode": "floating",
        "has_card": True,
        "box_w": 500,
        "box_h": 130,
        "radius": 24,
        "bg_rgb": (10, 8, 22),
        "border_rgb": (0, 245, 212),
        "border_width": 2,
        "badge_color": "#f72585",
        "text_color": "#00f5d4",
        "font_size": 19,
        "font_weight": "bold",
    },
    "glass_aurora": {
        "name": "☁️ การ์ดออโรราลอย (Aurora Pastel Float)",
        "mode": "floating",
        "has_card": True,
        "box_w": 500,
        "box_h": 130,
        "radius": 24,
        "bg_rgb": (24, 24, 38),
        "border_rgb": (203, 166, 247),
        "border_width": 2,
        "badge_color": "#94e2d5",
        "text_color": "#cdd6f4",
        "font_size": 19,
        "font_weight": "bold",
    },
    "dynamic_island": {
        "name": "🏝️ แถบ Dynamic Island (Apple Music HUD)",
        "mode": "island",
        "has_card": True,
        "box_w": 720,
        "box_h": 135,
        "radius": 28,
        "bg_rgb": (16, 15, 26),
        "border_rgb": (137, 180, 250),
        "border_width": 2,
        "badge_color": "#cba6f7",
        "text_color": "#ffffff",
        "subtext_color": "#7f849c",
        "accent_color": "#89b4fa",
        "font_size": 21,
        "font_weight": "bold",
    },
}


class FloatingToast:
    """A sleek floating on-screen notification HUD for real-time offset adjustments."""

    def __init__(self, parent, screen_w, screen_h):
        self.parent = parent
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=TRANS_KEY)
        try:
            self.win.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass

        self.w = 420
        self.h = 56
        x = (self.screen_w - self.w) // 2
        y = 50
        self.win.geometry(f"{self.w}x{self.h}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.win,
            width=self.w,
            height=self.h,
            bg=TRANS_KEY,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.bg_photo = make_card_background(
            self.w,
            self.h,
            radius=20,
            bg_rgb=(24, 24, 37),
            border_rgb=(166, 227, 161),
            border_width=2,
        )
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        self.lbl_text = self.canvas.create_text(
            self.w // 2,
            self.h // 2,
            text="",
            font=(BEST_FONT, 12, "bold"),
            fill="#a6e3a1",
            justify="center",
        )

        self.hide_job = None
        self.win.withdraw()

    def show(self, text, color="#a6e3a1", duration_ms=1600):
        if self.hide_job:
            self.parent.after_cancel(self.hide_job)

        self.canvas.itemconfigure(self.lbl_text, text=text, fill=color)
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.hide_job = self.parent.after(duration_ms, self.hide)

    def hide(self):
        try:
            self.win.withdraw()
        except Exception:
            pass

    def destroy(self):
        if self.hide_job:
            self.parent.after_cancel(self.hide_job)
        try:
            self.win.destroy()
        except Exception:
            pass


class FloatingCardItem:
    """An individual floating card for floating mode."""

    def __init__(self, parent, text, x, y, timestamp_str, cfg):
        self.win = tk.Toplevel(parent)
        self.cfg = cfg
        self.box_w = cfg["box_w"]
        self.box_h = cfg["box_h"]

        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=TRANS_KEY)
        try:
            self.win.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass

        self.win.geometry(f"{self.box_w}x{self.box_h}+{int(x)}+{int(y)}")
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True

        self.canvas = tk.Canvas(
            self.win,
            width=self.box_w,
            height=self.box_h,
            bg=TRANS_KEY,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        font_spec = (BEST_FONT, cfg["font_size"], cfg["font_weight"])
        wrap_w = self.box_w - 40

        if self.cfg.get("has_card", True):
            self.bg_photo = make_card_background(
                self.box_w,
                self.box_h,
                radius=cfg.get("radius", 24),
                bg_rgb=cfg.get("bg_rgb", (24, 24, 37)),
                border_rgb=cfg.get("border_rgb", (137, 180, 250)),
                border_width=cfg.get("border_width", 2),
            )
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

            # Header badge (🎵 timestamp)
            badge_text = f"🎵  {timestamp_str}"
            self.canvas.create_text(
                self.box_w // 2,
                24,
                text=badge_text,
                font=(BEST_FONT, 9, "bold"),
                fill=cfg.get("badge_color", "#89b4fa"),
                justify="center",
            )
            text_y = self.box_h // 2 + 10
        else:
            text_y = self.box_h // 2

        # Shadow text if requested
        self.shadow_id = None
        if self.cfg.get("shadow_color"):
            off = self.cfg.get("shadow_offset", 2)
            self.shadow_id = self.canvas.create_text(
                self.box_w // 2 + off,
                text_y + off,
                text="",
                font=font_spec,
                fill=self.cfg["shadow_color"],
                justify="center",
                width=wrap_w,
            )

        # Main lyric text
        self.text_id = self.canvas.create_text(
            self.box_w // 2,
            text_y,
            text="",
            font=font_spec,
            fill=cfg["text_color"],
            justify="center",
            width=wrap_w,
        )

        self.clusters = split_graphemes(text)
        self.type_idx = 0
        self.typewriter()

    def typewriter(self):
        if not self.is_alive:
            return
        try:
            if self.type_idx <= len(self.clusters):
                sub = "".join(self.clusters[: self.type_idx])
                if self.shadow_id:
                    self.canvas.itemconfigure(self.shadow_id, text=sub)
                self.canvas.itemconfigure(self.text_id, text=sub)
                self.type_idx += 1
                self.win.after(35, self.typewriter)
        except Exception:
            self.is_alive = False

    def rise(self, dy):
        if not self.is_alive:
            return
        self.y -= dy
        try:
            self.win.geometry(
                f"{self.box_w}x{self.box_h}+{int(self.x)}+{int(self.y)}"
            )
        except Exception:
            self.is_alive = False

    def is_offscreen(self):
        return self.y + self.box_h < -40

    def destroy(self):
        self.is_alive = False
        try:
            self.win.destroy()
        except Exception:
            pass


class DynamicIslandHUD:
    """The signature Apple Music / Dynamic Island centered floating HUD."""

    def __init__(self, parent, screen_w, screen_h, cfg, track_name=""):
        self.parent = parent
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.cfg = cfg
        self.track_name = track_name or "Playing"

        self.box_w = cfg["box_w"]
        self.box_h = cfg["box_h"]

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=TRANS_KEY)
        try:
            self.win.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass

        x = (self.screen_w - self.box_w) // 2
        y = self.screen_h - self.box_h - 90
        self.win.geometry(f"{self.box_w}x{self.box_h}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.win,
            width=self.box_w,
            height=self.box_h,
            bg=TRANS_KEY,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.render_bg()

        # 1. Header pill / equalizer
        self.eq_frames = [
            " ılı.lıllılı.ıllı ",
            " ıl.ılıll.ıl.ıll ",
            " ıllı.ılı.lıllıl ",
            " lı.llılı.ıllı.ı ",
        ]
        self.eq_idx = 0
        self.txt_eq = self.canvas.create_text(
            36,
            24,
            anchor="w",
            text=self.eq_frames[0],
            font=(BEST_FONT, 9, "bold"),
            fill=self.cfg["accent_color"],
        )

        self.txt_track = self.canvas.create_text(
            170,
            24,
            anchor="w",
            text=f"🎵 {self.track_name[:36]}",
            font=(BEST_FONT, 9, "bold"),
            fill=self.cfg["badge_color"],
        )

        self.txt_time = self.canvas.create_text(
            self.box_w - 36,
            24,
            anchor="e",
            text="00:00.0",
            font=(BEST_FONT, 9, "bold"),
            fill=self.cfg["accent_color"],
        )

        # 2. Main active lyric line
        self.txt_main = self.canvas.create_text(
            self.box_w // 2,
            64,
            text="🎵 เริ่มต้นเล่นเนื้อเพลง...",
            font=(BEST_FONT, self.cfg["font_size"], self.cfg["font_weight"]),
            fill=self.cfg["text_color"],
            justify="center",
            width=self.box_w - 60,
        )

        # 3. Next upcoming lyric line preview
        self.txt_next = self.canvas.create_text(
            self.box_w // 2,
            104,
            text="",
            font=(BEST_FONT, 11),
            fill=self.cfg["subtext_color"],
            justify="center",
            width=self.box_w - 60,
        )

        # 4. Bottom glowing progress line
        self.progress_line = self.canvas.create_line(
            28,
            self.box_h - 7,
            28,
            self.box_h - 7,
            fill=self.cfg["accent_color"],
            width=3,
            capstyle="round",
        )

        self.line_start_time = 0.0
        self.line_end_time = 1.0
        self.word_items = []
        self.active_word_line = None

    def render_bg(self):
        self.bg_photo = make_card_background(
            self.box_w,
            self.box_h,
            radius=self.cfg["radius"],
            bg_rgb=self.cfg["bg_rgb"],
            border_rgb=self.cfg["border_rgb"],
            border_width=self.cfg["border_width"],
        )
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

    def _clear_word_items(self):
        for item_id, *_ in self.word_items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self.word_items = []
        self.active_word_line = None

    def _render_word_line(self, word_line):
        self._clear_word_items()
        words = word_line.get("words", [])
        if not words:
            return False

        font_obj = tkfont.Font(
            family=BEST_FONT,
            size=self.cfg["font_size"],
            weight=self.cfg["font_weight"],
        )
        chunks = [w.get("text", "") for w in words]
        widths = [max(1, font_obj.measure(chunk)) for chunk in chunks]
        total_w = sum(widths)
        max_w = self.box_w - 72

        font_size = self.cfg["font_size"]
        if total_w > max_w and total_w > 0:
            font_size = max(14, int(font_size * max_w / total_w))
            font_obj = tkfont.Font(
                family=BEST_FONT,
                size=font_size,
                weight=self.cfg["font_weight"],
            )
            widths = [max(1, font_obj.measure(chunk)) for chunk in chunks]
            total_w = sum(widths)

        x = (self.box_w - total_w) / 2
        y = 70
        future = self.cfg.get("future_color", self.cfg.get("subtext_color", "#64748b"))

        for word, chunk, width in zip(words, chunks, widths):
            item_id = self.canvas.create_text(
                x,
                y,
                anchor="w",
                text=chunk,
                font=(BEST_FONT, font_size, self.cfg["font_weight"]),
                fill=future,
            )
            self.word_items.append(
                (
                    item_id,
                    float(word.get("start", word_line.get("start", 0.0))),
                    float(word.get("end", word.get("start", 0.0) + 0.35)),
                )
            )
            x += width

        self.active_word_line = word_line
        return True

    def set_lyric(self, current_text, next_text, start_time, next_time, word_line=None):
        rendered_words = False
        if self.cfg.get("word_karaoke") and word_line:
            rendered_words = self._render_word_line(word_line)

        if rendered_words:
            self.canvas.itemconfigure(self.txt_main, text="")
        else:
            self._clear_word_items()
            self.canvas.itemconfigure(self.txt_main, text=current_text)

        if next_text:
            self.canvas.itemconfigure(self.txt_next, text=f"ถัดไป  •  {next_text}")
        else:
            self.canvas.itemconfigure(self.txt_next, text="")
        self.line_start_time = start_time
        self.line_end_time = next_time if next_time > start_time else start_time + 4.0

    def update_frame(self, current_time):
        # Update equalizer animation
        self.eq_idx = (self.eq_idx + 1) % len(self.eq_frames)
        self.canvas.itemconfigure(self.txt_eq, text=self.eq_frames[self.eq_idx])

        # Update time display
        mins = int(current_time // 60)
        secs = current_time % 60
        self.canvas.itemconfigure(
            self.txt_time, text=f"{mins:02d}:{secs:04.1f}"
        )

        # Word-by-word karaoke highlighting (Enhanced LRC)
        if self.word_items:
            past_color = self.cfg.get("past_color", self.cfg.get("accent_color", "#7dd3fc"))
            active_color = self.cfg.get("active_color", "#ffffff")
            future_color = self.cfg.get("future_color", self.cfg.get("subtext_color", "#64748b"))
            for item_id, word_start, word_end in self.word_items:
                if current_time >= word_end:
                    color = past_color
                elif current_time >= word_start:
                    color = active_color
                else:
                    color = future_color
                self.canvas.itemconfigure(item_id, fill=color)

        # Update bottom progress bar
        dur = max(0.1, self.line_end_time - self.line_start_time)
        frac = min(1.0, max(0.0, (current_time - self.line_start_time) / dur))
        max_w = self.box_w - 56
        cur_w = 28 + max_w * frac
        self.canvas.coords(self.progress_line, 28, self.box_h - 7, cur_w, self.box_h - 7)

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass


class LyricFloatPlayer:
    """The master playback controller with audio hardware sync & live offset nudging."""

    def __init__(
        self,
        root,
        lyrics,
        audio_path=None,
        style="floating_cards",
        initial_offset=0.0,
        word_lyrics=None,
        on_finished=None,
    ):
        self.root = root
        self.audio_path = audio_path
        self.on_finished = on_finished
        self.sync_offset = float(initial_offset)
        self.word_lyrics = sorted(word_lyrics or [], key=lambda item: item.get("start", 0.0))
        self.is_paused = False

        # Filter empty lines
        self.lyrics = sorted(
            [(t, text.strip()) for t, text in lyrics if text and text.strip()],
            key=lambda item: item[0],
        )

        self.style_keys = list(STYLES.keys())
        self.style_key = style if style in STYLES else "liquid_glass"
        self.cfg = STYLES[self.style_key]

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

        self.track_name = (
            os.path.splitext(os.path.basename(audio_path))[0]
            if audio_path
            else "เพลงที่คุณเลือก"
        )

        self.next_lyric_idx = 0
        self.floating_boxes = []
        self.island_hud = None
        self.last_frame_time = None
        self.current_side = "left"
        self.is_running = False

        self.toast = FloatingToast(self.root, self.screen_w, self.screen_h)

        self.setup_controls_toolbar()
        self.setup_hotkeys()

    def setup_controls_toolbar(self):
        """Top-Right floating micro control toolbar."""
        self.ctrl_win = tk.Toplevel(self.root)
        self.ctrl_win.overrideredirect(True)
        self.ctrl_win.attributes("-topmost", True)
        self.ctrl_win.configure(bg="#181825")

        bar_w = 460
        bar_h = 42
        self.ctrl_win.geometry(f"{bar_w}x{bar_h}+{self.screen_w - bar_w - 20}+18")

        # Container
        frame = tk.Frame(
            self.ctrl_win,
            bg="#181825",
            highlightbackground="#313244",
            highlightthickness=1,
        )
        frame.pack(fill="both", expand=True)

        # Offset display
        self.lbl_offset = tk.Label(
            frame,
            text=f"⏱️ {self.sync_offset:+.2f}s",
            font=(BEST_FONT, 9, "bold"),
            bg="#181825",
            fg="#a6e3a1",
        )
        self.lbl_offset.pack(side="left", padx=(10, 6))

        # Delay button (appears later)
        tk.Button(
            frame,
            text="⏪ +0.1s (ชะลอ)",
            font=(BEST_FONT, 8, "bold"),
            bg="#313244",
            fg="#cdd6f4",
            activebackground="#45475a",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=lambda: self.adjust_live_offset(0.1),
        ).pack(side="left", padx=2)

        # Advance button (appears sooner)
        tk.Button(
            frame,
            text="⏩ -0.1s (เร่ง)",
            font=(BEST_FONT, 8, "bold"),
            bg="#313244",
            fg="#cdd6f4",
            activebackground="#45475a",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=lambda: self.adjust_live_offset(-0.1),
        ).pack(side="left", padx=2)

        # Pause / Resume
        self.btn_pause = tk.Button(
            frame,
            text="⏸️ พัก",
            font=(BEST_FONT, 8, "bold"),
            bg="#313244",
            fg="#f9e2af",
            activebackground="#45475a",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.toggle_pause,
        )
        self.btn_pause.pack(side="left", padx=3)

        # Style switch
        tk.Button(
            frame,
            text="🎨 สไตล์",
            font=(BEST_FONT, 8),
            bg="#313244",
            fg="#cba6f7",
            activebackground="#45475a",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.cycle_style,
        ).pack(side="left", padx=2)

        # Stop (ESC)
        tk.Button(
            frame,
            text="⏹ ออก (ESC)",
            font=(BEST_FONT, 8, "bold"),
            bg="#e78284",
            fg="#11111b",
            activebackground="#ea999c",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.stop,
        ).pack(side="right", padx=(4, 8))

    def setup_hotkeys(self):
        """Keyboard shortcuts: [ / ] or Left / Right, Space, Tab, ESC."""
        self.root.bind_all("<Escape>", lambda e: self.stop())
        self.root.bind_all("<space>", lambda e: self.toggle_pause())
        self.root.bind_all("<bracketleft>", lambda e: self.adjust_live_offset(0.1))
        self.root.bind_all("<bracketright>", lambda e: self.adjust_live_offset(-0.1))
        self.root.bind_all("<Left>", lambda e: self.adjust_live_offset(0.1))
        self.root.bind_all("<Right>", lambda e: self.adjust_live_offset(-0.1))
        self.root.bind_all("<Tab>", lambda e: self.cycle_style())

    def adjust_live_offset(self, delta):
        """Adjusts sync offset on the fly and shows toast."""
        self.sync_offset = round(self.sync_offset + delta, 2)
        self.lbl_offset.config(text=f"⏱️ {self.sync_offset:+.2f}s")

        if delta > 0:
            msg = f"⏱️ หน่วงเวลา: {self.sync_offset:+.2f}s (เนื้อร้องจะขึ้นช้าลงอีกนิด)"
            col = "#89b4fa"
        else:
            msg = f"⏱️ เร่งเวลา: {self.sync_offset:+.2f}s (เนื้อร้องจะขึ้นเร็วขึ้นอีกนิด)"
            col = "#fab387"
        self.toast.show(msg, color=col)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.pause()
            except Exception:
                pass
            self.btn_pause.config(text="▶️ เล่นต่อ", fg="#a6e3a1")
            self.toast.show("⏸️ พักชั่วคราว (กด Space เพื่อเล่นต่อ)", color="#f9e2af")
        else:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.unpause()
            except Exception:
                pass
            self.btn_pause.config(text="⏸️ พัก", fg="#f9e2af")
            self.toast.show("▶️ เล่นต่อ", color="#a6e3a1")

    def cycle_style(self):
        """Cycles between visual styles during playback."""
        cur_idx = self.style_keys.index(self.style_key)
        self.style_key = self.style_keys[(cur_idx + 1) % len(self.style_keys)]
        self.cfg = STYLES[self.style_key]

        # Reset active views for new style mode
        if self.island_hud:
            self.island_hud.destroy()
            self.island_hud = None
        for b in self.floating_boxes:
            b.destroy()
        self.floating_boxes.clear()

        if self.cfg.get("mode") == "island":
            self.island_hud = DynamicIslandHUD(
                self.root, self.screen_w, self.screen_h, self.cfg, self.track_name
            )

        self.toast.show(f"🎨 เปลี่ยนรูปแบบ: {self.cfg['name']}", color="#cba6f7")

    def get_word_line_for_time(self, timestamp, tolerance=0.45):
        """Return the Enhanced-LRC line matching a normal line timestamp."""
        if not self.word_lyrics:
            return None
        best = min(
            self.word_lyrics,
            key=lambda item: abs(float(item.get("start", 0.0)) - timestamp),
        )
        if abs(float(best.get("start", 0.0)) - timestamp) <= tolerance:
            return best
        return None

    def random_safe_x(self):
        center_x = self.screen_w // 2
        box_w = self.cfg["box_w"]
        spacing = box_w + 40
        left_x = center_x - spacing
        right_x = center_x + 40

        if self.current_side == "left":
            self.current_side = "right"
            return left_x
        else:
            self.current_side = "left"
            return right_x

    def start(self):
        self.is_running = True
        self.start_wall_time = time.time()
        self.last_frame_time = self.start_wall_time
        self.total_paused_duration = 0.0

        # Start audio if available
        if self.audio_path and os.path.exists(self.audio_path):
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(self.audio_path)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"Audio playback warning: {e}")

        # If starting in island mode, create the persistent HUD
        if self.cfg.get("mode") == "island":
            self.island_hud = DynamicIslandHUD(
                self.root, self.screen_w, self.screen_h, self.cfg, self.track_name
            )

        # Show initial tip toast
        self.toast.show(
            "💡 กด [ หรือ ] เพื่อปรับเวลาให้ตรงกับเสียงร้อง | Space เพื่อพัก",
            color="#a6e3a1",
            duration_ms=2500,
        )

        self.tick()

    def get_effective_time(self):
        """Returns accurate audio hardware playback time in seconds."""
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms >= 0:
                return pos_ms / 1000.0

        # Fallback to wall-clock if no audio playing
        return time.time() - self.start_wall_time - self.total_paused_duration

    def tick(self):
        if not self.is_running:
            return

        now = time.time()
        dt = now - self.last_frame_time
        self.last_frame_time = now

        if not self.is_paused:
            raw_audio_t = self.get_effective_time()
            # Effective time adjusted by live offset
            calibrated_t = raw_audio_t - self.sync_offset

            # Check if new lyric line has arrived
            while (
                self.next_lyric_idx < len(self.lyrics)
                and self.lyrics[self.next_lyric_idx][0] <= calibrated_t
            ):
                t_stamp, text = self.lyrics[self.next_lyric_idx]
                mins = int(t_stamp // 60)
                secs = t_stamp % 60
                t_str = f"{mins:02d}:{secs:04.1f}"

                # Next line preview
                next_text = (
                    self.lyrics[self.next_lyric_idx + 1][1]
                    if self.next_lyric_idx + 1 < len(self.lyrics)
                    else ""
                )
                next_t = (
                    self.lyrics[self.next_lyric_idx + 1][0]
                    if self.next_lyric_idx + 1 < len(self.lyrics)
                    else t_stamp + 4.0
                )

                if self.cfg.get("mode") == "island":
                    if not self.island_hud:
                        self.island_hud = DynamicIslandHUD(
                            self.root,
                            self.screen_w,
                            self.screen_h,
                            self.cfg,
                            self.track_name,
                        )
                    word_line = self.get_word_line_for_time(t_stamp)
                    self.island_hud.set_lyric(
                        text, next_text, t_stamp, next_t, word_line=word_line
                    )
                else:
                    # Floating cards mode
                    x = self.random_safe_x()
                    y = self.screen_h - self.cfg["box_h"] - BOTTOM_SPAWN_OFFSET
                    card = FloatingCardItem(
                        self.root, text, x, y, t_str, self.cfg
                    )
                    self.floating_boxes.append(card)

                self.next_lyric_idx += 1

            # Update island HUD frame
            if self.island_hud:
                self.island_hud.update_frame(raw_audio_t)

            # Move floating cards upward
            if self.floating_boxes:
                dy = RISE_SPEED * dt
                alive = []
                for box in self.floating_boxes:
                    box.rise(dy)
                    if box.is_offscreen():
                        box.destroy()
                    elif box.is_alive:
                        alive.append(box)
                self.floating_boxes = alive

        # Continue loop if not stopped
        is_audio_still_busy = False
        if pygame.mixer.get_init():
            is_audio_still_busy = pygame.mixer.music.get_busy()

        if (
            self.next_lyric_idx < len(self.lyrics)
            or self.floating_boxes
            or is_audio_still_busy
        ):
            self.root.after(16, self.tick)
        else:
            self.stop()

    def stop(self, event=None):
        if not self.is_running:
            return
        self.is_running = False

        # Stop audio
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

        # Cleanup windows
        if self.island_hud:
            self.island_hud.destroy()
            self.island_hud = None

        for box in self.floating_boxes:
            box.destroy()
        self.floating_boxes.clear()

        try:
            self.ctrl_win.destroy()
        except Exception:
            pass

        self.toast.destroy()

        # Unbind hotkeys
        for key in [
            "<Escape>",
            "<space>",
            "<bracketleft>",
            "<bracketright>",
            "<Left>",
            "<Right>",
            "<Tab>",
        ]:
            try:
                self.root.unbind_all(key)
            except Exception:
                pass

        if self.on_finished:
            self.on_finished(self.sync_offset)


def play_standalone(lyrics, audio_path=None, style="floating_cards"):
    root = tk.Tk()
    root.withdraw()

    def on_done(offset):
        root.quit()
        root.destroy()

    player = LyricFloatPlayer(
        root,
        lyrics,
        audio_path=audio_path,
        style=style,
        on_finished=on_done,
    )
    player.start()
    root.mainloop()


if __name__ == "__main__":
    sample_lyrics = [
        (0.5, "Do you think I have forgotten?"),
        (3.5, "迷わずに今 矛盾だらけの世界を"),
        (7.0, "その手で撃ち放て"),
    ]
    play_standalone(sample_lyrics, style="floating_cards")
