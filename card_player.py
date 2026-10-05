"""
card_player.py - Synchronized lyric overlay player
Features:
- Hardware audio synchronization (pygame.mixer.music.get_pos)
- Real-time live sync offset adjustment (Hotkeys: [ / ] or Left / Right arrows)
- Focused single-line overlay plus minimal optional card styles
- Unicode/Thai combining-character safe typewriter effect & instant mode
- Floating toast HUD & top-right micro control toolbar
- Press ESC at any time to return to studio.
"""

import math
import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
# Set SDL audio driver to match PipeWire before importing pygame
if sys.platform.startswith("linux"):
    os.environ.setdefault("SDL_AUDIODRIVER", "pipewire")

import unicodedata
from PIL import Image, ImageDraw, ImageTk
import pygame


def init_audio():
    """Initializes pygame mixer with large audio buffer for Linux (PipeWire/PulseAudio) to prevent stuttering."""
    if not pygame.mixer.get_init():
        # Try multiple buffer sizes, largest first for best stability
        for buf_size in (8192, 4096, 2048):
            try:
                pygame.mixer.pre_init(frequency=48000, size=-16, channels=2, buffer=buf_size)
                pygame.mixer.init()
                return
            except Exception:
                continue
        # Last resort: let SDL pick defaults
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Mixer init error: {e}")


# Default animation physics
RISE_SPEED = 42
BOTTOM_SPAWN_OFFSET = 140
TRANS_KEY = "#000002"
TRANS_KEY_RGB = (0, 0, 2)

# Animation tick interval (ms) - 30fps is plenty smooth for floating text
# and reduces X11 round-trip pressure that causes audio stuttering on Linux
TICK_INTERVAL = 33


def get_best_font():
    """Selects the cleanest, most modern font available across OS (Linux/Windows)."""
    try:
        fams = tkfont.families()
        for cand in [
            "Noto Sans Thai",
            "Sarabun",
            "Segoe UI Variable Display",
            "Segoe UI",
            "Leelawadee UI",
            "Bahnschrift",
            "DejaVu Sans",
            "Inter",
            "Tahoma",
        ]:
            if cand in fams:
                return cand
    except Exception:
        pass
    return "Helvetica"


_BEST_FONT = None

def get_cached_best_font():
    """Lazy getter for best font — only resolves when Tk mainloop is active."""
    global _BEST_FONT
    if _BEST_FONT is None:
        _BEST_FONT = get_best_font()
    return _BEST_FONT

# For backward compatibility — will be updated on first actual use
BEST_FONT = "Helvetica"


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


def split_reveal_units(text: str):
    """Return readable reveal chunks.

    Space-delimited lyrics reveal a whole word at a time so a word never sits
    half-drawn while it is already being sung. Scripts without spaces fall
    back to small grapheme groups.
    """
    clusters = split_graphemes(text)
    if not clusters:
        return []

    if any(ch.isspace() for ch in text.strip()):
        units = []
        current = ""
        for cluster in clusters:
            current += cluster
            if cluster.isspace():
                if current.strip():
                    units.append(current)
                    current = ""
                elif units:
                    units[-1] += current
                    current = ""
        if current:
            units.append(current)
        return units

    chunk_size = 2 if len(clusters) <= 24 else 3
    return [
        "".join(clusters[i : i + chunk_size])
        for i in range(0, len(clusters), chunk_size)
    ]


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
    "karaoke_flow": {
        "name": "Karaoke Flow",
        "mode": "flow",
        "box_w": 980,
        "box_h": 360,
        "radius": 22,
        "bg_rgb": (10, 10, 12),
        "border_rgb": (46, 46, 51),
        "border_width": 1,
        "text_color": "#f6f6f7",
        "past_color": "#77777f",
        "next_color": "#55555c",
        "accent_color": "#c8ff47",
        "font_size": 28,
        "font_weight": "bold",
        "line_gap": 62,
    },
    "dynamic_island": {
        "name": "Focus Player",
        "mode": "island",
        "has_card": True,
        "box_w": 820,
        "box_h": 148,
        "radius": 20,
        "bg_rgb": (12, 12, 14),
        "border_rgb": (52, 52, 57),
        "border_width": 1,
        "badge_color": "#c8ff47",
        "text_color": "#ffffff",
        "subtext_color": "#898990",
        "accent_color": "#c8ff47",
        "font_size": 21,
        "font_weight": "bold",
    },
    "floating_cards": {
        "name": "Minimal Card",
        "mode": "floating",
        "has_card": True,
        "box_w": 560,
        "box_h": 122,
        "radius": 18,
        "bg_rgb": (17, 17, 19),
        "border_rgb": (55, 55, 60),
        "border_width": 1,
        "badge_color": "#c8ff47",
        "text_color": "#f5f5f5",
        "font_size": 20,
        "font_weight": "bold",
    },
    "text_only": {
        "name": "Clean Text",
        "mode": "floating",
        "has_card": False,
        "box_w": 600,
        "box_h": 116,
        "text_color": "#ffffff",
        "shadow_color": "#080809",
        "shadow_offset": 2,
        "font_size": 23,
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
            fill="#c8ff47",
            justify="center",
        )

        self.hide_job = None
        self.win.withdraw()

    def show(self, text, color="#c8ff47", duration_ms=1600):
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

    def __init__(self, parent, text, x, y, timestamp_str, cfg, start_time=0.0, end_time=None):
        self.win = tk.Toplevel(parent)
        self.cfg = cfg

        font_spec = (get_cached_best_font(), cfg["font_size"], cfg["font_weight"])
        f_measure = tkfont.Font(font=font_spec)
        text_width = f_measure.measure(text)
        base_w = cfg["box_w"]
        needed_w = text_width + 80
        self.box_w = max(base_w, min(needed_w, 900))
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
            badge_text = timestamp_str
            self.canvas.create_text(
                self.box_w // 2,
                24,
                text=badge_text,
                font=(BEST_FONT, 9, "bold"),
                fill=cfg.get("badge_color", "#c8ff47"),
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

        # Keep the original floating-card look, but reveal the text using
        # the lyric line's own time window instead of a fixed typewriter speed.
        self.full_text = text
        self.clusters = split_graphemes(text)
        self.reveal_units = split_reveal_units(text)
        self.start_time = float(start_time)
        self.end_time = float(end_time) if end_time is not None else self.start_time + 3.5
        self.last_reveal_count = -1
        if self.shadow_id:
            self.canvas.itemconfigure(self.shadow_id, text="")
        self.canvas.itemconfigure(self.text_id, text="")

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

    def update_reveal(self, current_time):
        """Reveal readable chunks slightly ahead of the raw line interval.

        Plain LRC only gives line timestamps, not exact word timestamps. Revealing
        across 100% of the line interval makes the last word appear too late.
        We therefore start a little early and finish around 76% of the interval,
        then keep the complete line visible while the card continues upward.
        """
        if not self.is_alive or not self.reveal_units:
            return

        duration = max(0.45, self.end_time - self.start_time)
        lead = min(0.18, duration * 0.10)
        reveal_duration = max(0.32, duration * 0.76)

        frac = (current_time - self.start_time + lead) / reveal_duration
        frac = min(1.0, max(0.0, frac))
        # Gentle ease-out: lyrics appear a little faster at the beginning,
        # avoiding the visual feeling that the text is chasing the singer.
        frac = math.pow(frac, 0.78) if frac > 0.0 else 0.0

        count = min(
            len(self.reveal_units),
            max(1, int(math.ceil(len(self.reveal_units) * frac))),
        )
        if count == self.last_reveal_count:
            return

        self.last_reveal_count = count
        shown = "".join(self.reveal_units[:count])
        if self.shadow_id:
            self.canvas.itemconfigure(self.shadow_id, text=shown)
        self.canvas.itemconfigure(self.text_id, text=shown)

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


class KaraokeFlowHUD:
    """Persistent scrolling lyrics with progressive character reveal."""

    def __init__(self, parent, screen_w, screen_h, cfg, lyrics, track_name=""):
        self.parent = parent
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.cfg = cfg
        self.lyrics = lyrics
        self.track_name = track_name or "Playing"
        self.active_index = -1
        self.previous_index = -1
        self.transition_started = time.time()
        self.transition_duration = 0.32

        self.box_w = min(cfg["box_w"], max(720, screen_w - 80))
        self.box_h = cfg["box_h"]

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=TRANS_KEY)
        try:
            self.win.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass

        x = (screen_w - self.box_w) // 2
        y = max(70, screen_h - self.box_h - 90)
        self.win.geometry(f"{self.box_w}x{self.box_h}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.win,
            width=self.box_w,
            height=self.box_h,
            bg=TRANS_KEY,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.bg_photo = make_card_background(
            self.box_w,
            self.box_h,
            radius=cfg.get("radius", 22),
            bg_rgb=cfg.get("bg_rgb", (10, 10, 12)),
            border_rgb=cfg.get("border_rgb", (46, 46, 51)),
            border_width=cfg.get("border_width", 1),
        )
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        self.canvas.create_text(
            28, 24,
            anchor="w",
            text=self.track_name[:54],
            font=(get_cached_best_font(), 9, "bold"),
            fill="#8f8f96",
        )
        self.time_id = self.canvas.create_text(
            self.box_w - 28, 24,
            anchor="e",
            text="00:00.0",
            font=(get_cached_best_font(), 9, "bold"),
            fill=cfg.get("accent_color", "#c8ff47"),
        )

        self.center_y = self.box_h // 2 + 8
        self.line_gap = cfg.get("line_gap", 62)
        self.visible_ids = []
        for _ in range(7):
            item = self.canvas.create_text(
                self.box_w // 2,
                self.center_y,
                text="",
                font=(get_cached_best_font(), cfg.get("font_size", 28), "bold"),
                fill=cfg.get("next_color", "#55555c"),
                justify="center",
                width=self.box_w - 80,
            )
            self.visible_ids.append(item)

        self.progress_bg = self.canvas.create_line(
            28, self.box_h - 22, self.box_w - 28, self.box_h - 22,
            fill="#242428", width=3, capstyle="round"
        )
        self.progress_fg = self.canvas.create_line(
            28, self.box_h - 22, 28, self.box_h - 22,
            fill=cfg.get("accent_color", "#c8ff47"),
            width=3, capstyle="round"
        )

    def set_active(self, index):
        if index == self.active_index:
            return
        self.previous_index = self.active_index
        self.active_index = index
        self.transition_started = time.time()

    def _revealed_text(self, index, current_time):
        if index < 0 or index >= len(self.lyrics):
            return ""
        start, text = self.lyrics[index]
        if index + 1 < len(self.lyrics):
            end = self.lyrics[index + 1][0]
        else:
            end = start + max(2.5, min(6.0, len(split_graphemes(text)) * 0.12))

        duration = max(0.6, end - start)
        frac = min(1.0, max(0.0, (current_time - start) / duration))
        clusters = split_graphemes(text)
        if not clusters:
            return ""
        count = min(len(clusters), max(1, int(math.ceil(len(clusters) * frac))))
        return "".join(clusters[:count])

    def update_frame(self, current_time):
        mins = int(current_time // 60)
        secs = current_time % 60
        self.canvas.itemconfigure(self.time_id, text=f"{mins:02d}:{secs:04.1f}")

        if self.active_index < 0:
            return

        anim = min(1.0, max(0.0, (time.time() - self.transition_started) / self.transition_duration))
        # smoothstep makes line movement feel like a real lyric app instead of jumping.
        p = anim * anim * (3.0 - 2.0 * anim)
        start_idx = self.active_index - 3

        for slot, item_id in enumerate(self.visible_ids):
            idx = start_idx + slot
            if idx < 0 or idx >= len(self.lyrics):
                self.canvas.itemconfigure(item_id, text="")
                continue

            _, full_text = self.lyrics[idx]
            relative = idx - self.active_index
            # During a line change every row travels upward one line-gap.
            shift = (1.0 - p) * self.line_gap if self.previous_index == self.active_index - 1 else 0.0
            y = self.center_y + relative * self.line_gap + shift

            if idx == self.active_index:
                shown = self._revealed_text(idx, current_time)
                color = self.cfg.get("accent_color", "#c8ff47")
                size = self.cfg.get("font_size", 28)
            elif idx < self.active_index:
                shown = full_text
                distance = self.active_index - idx
                color = self.cfg.get("past_color", "#77777f")
                size = max(16, self.cfg.get("font_size", 28) - distance * 3)
            else:
                shown = full_text
                color = self.cfg.get("next_color", "#55555c")
                size = max(17, self.cfg.get("font_size", 28) - 4)

            self.canvas.coords(item_id, self.box_w // 2, y)
            self.canvas.itemconfigure(
                item_id,
                text=shown,
                fill=color,
                font=(get_cached_best_font(), size, "bold" if idx == self.active_index else "normal"),
            )

        start = self.lyrics[self.active_index][0]
        if self.active_index + 1 < len(self.lyrics):
            end = self.lyrics[self.active_index + 1][0]
        else:
            end = start + 4.0
        dur = max(0.1, end - start)
        frac = min(1.0, max(0.0, (current_time - start) / dur))
        x2 = 28 + (self.box_w - 56) * frac
        self.canvas.coords(self.progress_fg, 28, self.box_h - 22, x2, self.box_h - 22)

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass


class DynamicIslandHUD:
    """Centered persistent lyric HUD with current/next lines and progress."""

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
        y = self.screen_h - self.box_h - 120
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
        self.eq_frames = ["●", "●", "●", "●"]
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
            62,
            24,
            anchor="w",
            text=self.track_name[:42],
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
            text="Ready",
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

    def set_lyric(self, current_text, next_text, start_time, next_time):
        self.canvas.itemconfigure(self.txt_main, text=current_text)
        if next_text:
            self.canvas.itemconfigure(
                self.txt_next, text=f"NEXT  {next_text}"
            )
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
        on_finished=None,
    ):
        self.root = root
        self.audio_path = audio_path
        self.on_finished = on_finished
        self.sync_offset = float(initial_offset)
        self.is_paused = False

        # Filter empty lines
        self.lyrics = sorted(
            [(t, text.strip()) for t, text in lyrics if text and text.strip()],
            key=lambda item: item[0],
        )

        self.style_keys = list(STYLES.keys())
        self.style_key = style if style in STYLES else "floating_cards"
        self.cfg = STYLES[self.style_key]

        # Cache font for text measurement (avoid creating new Font objects every tick)
        self._font_spec = (get_cached_best_font(), self.cfg["font_size"], self.cfg["font_weight"])
        self._cached_font = None  # lazy init (needs Tk mainloop)

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
        self.flow_hud = None
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
        self.ctrl_win.configure(bg="#101012")

        bar_w = 560
        bar_h = 42
        self.ctrl_win.geometry(f"{bar_w}x{bar_h}+{self.screen_w - bar_w - 20}+18")

        # Container
        frame = tk.Frame(
            self.ctrl_win,
            bg="#101012",
            highlightbackground="#2a2a2e",
            highlightthickness=1,
        )
        frame.pack(fill="both", expand=True)

        # Offset display
        self.lbl_offset = tk.Label(
            frame,
            text=f"OFFSET {self.sync_offset:+.2f}s",
            font=(BEST_FONT, 9, "bold"),
            bg="#101012",
            fg="#c8ff47",
        )
        self.lbl_offset.pack(side="left", padx=(10, 6))

        # Delay button (appears later)
        tk.Button(
            frame,
            text="+0.1  DELAY",
            font=(BEST_FONT, 8, "bold"),
            bg="#2a2a2e",
            fg="#eeeeef",
            activebackground="#343439",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=lambda: self.adjust_live_offset(0.1),
        ).pack(side="left", padx=2)

        # Advance button (appears sooner)
        tk.Button(
            frame,
            text="-0.1  ADVANCE",
            font=(BEST_FONT, 8, "bold"),
            bg="#2a2a2e",
            fg="#eeeeef",
            activebackground="#343439",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=lambda: self.adjust_live_offset(-0.1),
        ).pack(side="left", padx=2)

        # Pause / Resume
        self.btn_pause = tk.Button(
            frame,
            text="PAUSE",
            font=(BEST_FONT, 8, "bold"),
            bg="#2a2a2e",
            fg="#d9d9dc",
            activebackground="#343439",
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
            text="STYLE",
            font=(BEST_FONT, 8),
            bg="#2a2a2e",
            fg="#a9a9b2",
            activebackground="#343439",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.cycle_style,
        ).pack(side="left", padx=2)

        # Stop (ESC)
        tk.Button(
            frame,
            text="CLOSE  ESC",
            font=(BEST_FONT, 8, "bold"),
            bg="#e06c75",
            fg="#0b0b0c",
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
        self.lbl_offset.config(text=f"OFFSET {self.sync_offset:+.2f}s")

        if delta > 0:
            msg = f"DELAY {self.sync_offset:+.2f}s"
            col = "#c8ff47"
        else:
            msg = f"ADVANCE {self.sync_offset:+.2f}s"
            col = "#d7ad68"
        self.toast.show(msg, color=col)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.pause()
            except Exception:
                pass
            self.btn_pause.config(text="RESUME", fg="#c8ff47")
            self.toast.show("PAUSED", color="#d9d9dc")
        else:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.unpause()
            except Exception:
                pass
            self.btn_pause.config(text="PAUSE", fg="#d9d9dc")
            self.toast.show("PLAYING", color="#c8ff47")

    def cycle_style(self):
        """Cycles between visual styles during playback."""
        cur_idx = self.style_keys.index(self.style_key)
        self.style_key = self.style_keys[(cur_idx + 1) % len(self.style_keys)]
        self.cfg = STYLES[self.style_key]

        # Reset active views for new style mode
        if self.island_hud:
            self.island_hud.destroy()
            self.island_hud = None
        if self.flow_hud:
            self.flow_hud.destroy()
            self.flow_hud = None
        for b in self.floating_boxes:
            b.destroy()
        self.floating_boxes.clear()

        if self.cfg.get("mode") == "island":
            self.island_hud = DynamicIslandHUD(
                self.root, self.screen_w, self.screen_h, self.cfg, self.track_name
            )
        elif self.cfg.get("mode") == "flow":
            self.flow_hud = KaraokeFlowHUD(
                self.root, self.screen_w, self.screen_h, self.cfg, self.lyrics, self.track_name
            )
            if self.next_lyric_idx > 0:
                self.flow_hud.set_active(self.next_lyric_idx - 1)

        self.toast.show(f"STYLE  {self.cfg['name']}", color="#a9a9b2")

    def _get_font(self):
        """Returns cached Font object for text measurement."""
        if self._cached_font is None:
            self._cached_font = tkfont.Font(font=self._font_spec)
        return self._cached_font

    def random_safe_x(self, box_w=None):
        if box_w is None:
            box_w = self.cfg["box_w"]
        center_x = self.screen_w // 2
        spacing = box_w + 70
        left_x = max(20, center_x - spacing)
        right_x = min(self.screen_w - box_w - 20, center_x + 50)

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
                init_audio()
                pygame.mixer.music.load(self.audio_path)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"Audio playback warning: {e}")

        # Persistent lyric surfaces are created once and updated throughout the song.
        if self.cfg.get("mode") == "island":
            self.island_hud = DynamicIslandHUD(
                self.root, self.screen_w, self.screen_h, self.cfg, self.track_name
            )
        elif self.cfg.get("mode") == "flow":
            self.flow_hud = KaraokeFlowHUD(
                self.root, self.screen_w, self.screen_h, self.cfg, self.lyrics, self.track_name
            )

        # Show initial tip toast
        self.toast.show(
            "[ / ] ปรับเวลา  •  Space พัก  •  ESC ออก",
            color="#c8ff47",
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

                if self.cfg.get("mode") == "flow":
                    if not self.flow_hud:
                        self.flow_hud = KaraokeFlowHUD(
                            self.root,
                            self.screen_w,
                            self.screen_h,
                            self.cfg,
                            self.lyrics,
                            self.track_name,
                        )
                    self.flow_hud.set_active(self.next_lyric_idx)
                elif self.cfg.get("mode") == "island":
                    if not self.island_hud:
                        self.island_hud = DynamicIslandHUD(
                            self.root,
                            self.screen_w,
                            self.screen_h,
                            self.cfg,
                            self.track_name,
                        )
                    self.island_hud.set_lyric(text, next_text, t_stamp, next_t)
                else:
                    # Floating cards mode
                    needed_w = self._get_font().measure(text) + 80
                    est_box_w = max(self.cfg["box_w"], min(needed_w, 900))
                    x = self.random_safe_x(est_box_w)
                    y = self.screen_h - self.cfg["box_h"] - BOTTOM_SPAWN_OFFSET
                    # Original behavior: every new lyric becomes a card and
                    # previous cards keep floating upward until they leave the screen.
                    # This keeps the visual stream continuous instead of making a line vanish.
                    card = FloatingCardItem(
                        self.root,
                        text,
                        x,
                        y,
                        t_str,
                        self.cfg,
                        start_time=t_stamp,
                        end_time=next_t,
                    )
                    self.floating_boxes.append(card)
                    # Transparent top-level windows are expensive on Linux.
                    # Keep enough history to preserve the continuous-flow look,
                    # but cap old cards so long/fast songs stay smooth.
                    while len(self.floating_boxes) > 12:
                        oldest = self.floating_boxes.pop(0)
                        oldest.destroy()

                self.next_lyric_idx += 1

            # Update persistent lyric surfaces every frame.
            if self.island_hud:
                self.island_hud.update_frame(raw_audio_t)
            if self.flow_hud:
                self.flow_hud.update_frame(calibrated_t)

            # Move floating cards upward
            if self.floating_boxes:
                dy = RISE_SPEED * dt
                alive = []
                for box in self.floating_boxes:
                    box.update_reveal(calibrated_t)
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
            self.root.after(TICK_INTERVAL, self.tick)
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
        if self.flow_hud:
            self.flow_hud.destroy()
            self.flow_hud = None

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
