"""
card_player.py - High-End Floating Lyric Player
Supports transparent floating text (no box), sleek dark rounded cards, and neon glow.
Press ESC at any time to stop playback.
"""

import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

# Set SDL audio driver to match PipeWire before importing pygame
if sys.platform.startswith("linux"):
    os.environ.setdefault("SDL_AUDIODRIVER", "pipewire")

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


# Default animation settings
RISE_SPEED = 65
BOTTOM_SPAWN_OFFSET = 120

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

# Preset Styles
STYLES = {
    "text_only": {
        "name": "✨ ตัวหนังสือลอย (ไร้กรอบ)",
        "box_w": 480,
        "box_h": 120,
        "font_size": 22,
        "font_weight": "bold",
        "has_card": False,
        "text_color": "#ffffff",
        "shadow_color": "#000000",
        "shadow_offset": 2,
    },
    "dark_card": {
        "name": "🌙 การ์ดขอบมน (Modern Dark)",
        "box_w": 420,
        "box_h": 130,
        "font_size": 18,
        "font_weight": "bold",
        "has_card": True,
        "card_fill": "#181825",
        "card_outline": "#89b4fa",
        "card_radius": 24,
        "card_border_width": 2,
        "text_color": "#ffffff",
        "shadow_color": "#0d0d15",
        "shadow_offset": 1,
    },
    "neon_glow": {
        "name": "⚡ นีออนเรืองแสง (Cyber Glow)",
        "box_w": 420,
        "box_h": 130,
        "font_size": 18,
        "font_weight": "bold",
        "has_card": True,
        "card_fill": "#0e0919",
        "card_outline": "#00f5d4",
        "card_radius": 24,
        "card_border_width": 2,
        "text_color": "#00f5d4",
        "shadow_color": "#7b2cbf",
        "shadow_offset": 1,
    },
    "soft_light": {
        "name": "☁️ การ์ดมินิมอล (Soft Light)",
        "box_w": 420,
        "box_h": 130,
        "font_size": 18,
        "font_weight": "bold",
        "has_card": True,
        "card_fill": "#fcfbf7",
        "card_outline": "#d3cec4",
        "card_radius": 24,
        "card_border_width": 2,
        "text_color": "#1e1e2e",
        "shadow_color": None,
        "shadow_offset": 0,
    },
}


def draw_rounded_card(canvas, x1, y1, x2, y2, r=22, **kwargs):
    """Draws a smooth rounded rectangle on a canvas."""
    points = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class LyricCard:
    def __init__(self, parent, text, x, y, style_config):
        self.win = tk.Toplevel(parent)
        self.cfg = style_config
        self.full_text = text
        font_spec = (get_cached_best_font(), self.cfg["font_size"], self.cfg["font_weight"])
        
        # Calculate dynamic width to prevent text truncation
        f_measure = tkfont.Font(font=font_spec)
        text_width = f_measure.measure(text)
        
        # Card width dynamically fits text with padding, within reasonable min/max
        base_w = self.cfg["box_w"]
        needed_w = text_width + 80
        self.box_w = max(base_w, min(needed_w, 900))
        self.box_h = self.cfg["box_h"]

        # Borderless & Topmost window
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        # Chroma-key transparency on Windows
        TRANS_KEY = "#000001"
        self.win.configure(bg=TRANS_KEY)
        try:
            self.win.wm_attributes("-transparentcolor", TRANS_KEY)
        except Exception:
            pass

        self.win.geometry(f"{self.box_w}x{self.box_h}+{int(x)}+{int(y)}")
        self.win.resizable(False, False)

        self.canvas = tk.Canvas(
            self.win,
            width=self.box_w,
            height=self.box_h,
            bg=TRANS_KEY,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        center_x = self.box_w // 2
        center_y = self.box_h // 2
        wrap_w = self.box_w - 40

        # Draw rounded card if requested
        if self.cfg.get("has_card"):
            draw_rounded_card(
                self.canvas,
                4,
                4,
                self.box_w - 4,
                self.box_h - 4,
                r=self.cfg.get("card_radius", 22),
                fill=self.cfg.get("card_fill", "#181825"),
                outline=self.cfg.get("card_outline", "#89b4fa"),
                width=self.cfg.get("card_border_width", 2),
            )

        # Draw shadow layer
        self.shadow_id = None
        if self.cfg.get("shadow_color"):
            off = self.cfg.get("shadow_offset", 2)
            self.shadow_id = self.canvas.create_text(
                center_x + off,
                center_y + off,
                text="",
                font=font_spec,
                fill=self.cfg["shadow_color"],
                justify="center",
                width=wrap_w,
            )

        # Draw foreground text
        self.text_id = self.canvas.create_text(
            center_x,
            center_y,
            text="",
            font=font_spec,
            fill=self.cfg["text_color"],
            justify="center",
            width=wrap_w,
        )

        self.typewriter_index = 0
        self.is_alive = True
        self.typewriter()

        self.x = x
        self.y = float(y)

    def rise(self, dy):
        if not self.is_alive:
            return
        self.y -= dy
        try:
            self.win.geometry(
                f"{self.box_w}x{self.box_h}+{int(self.x)}+{int(self.y)}"
            )
        except tk.TclError:
            self.is_alive = False

    def is_offscreen(self):
        return self.y + self.box_h < -50

    def typewriter(self):
        if not self.is_alive:
            return
        try:
            text_len = len(self.full_text)
            if self.typewriter_index <= text_len:
                sub_text = self.full_text[: self.typewriter_index]
                if self.shadow_id:
                    self.canvas.itemconfigure(self.shadow_id, text=sub_text)
                self.canvas.itemconfigure(self.text_id, text=sub_text)

                if self.typewriter_index < text_len:
                    # Advance by 2, but clamp to text_len so we never skip past the end
                    self.typewriter_index = min(self.typewriter_index + 2, text_len)
                    self.win.after(90, self.typewriter)
                # else: full text displayed, done
        except tk.TclError:
            self.is_alive = False

    def destroy(self):
        self.is_alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class LyricFloatPlayer:
    def __init__(
        self,
        root,
        lyrics,
        audio_path=None,
        style="text_only",
        on_finished=None,
    ):
        """
        lyrics: list of (timestamp_seconds, text)
        audio_path: path to .mp3 file
        style: key in STYLES dict ('text_only', 'dark_card', 'neon_glow', 'soft_light')
        """
        self.root = root
        self.style_key = style if style in STYLES else "text_only"
        self.cfg = STYLES[self.style_key]

        # Cache font for text measurement (avoid creating new Font objects every tick)
        self._font_spec = (get_cached_best_font(), self.cfg["font_size"], self.cfg["font_weight"])
        self._cached_font = None  # lazy init (needs Tk mainloop)

        # Filter out empty or whitespace-only lines
        self.lyrics = sorted(
            [(t, text.strip()) for t, text in lyrics if text and text.strip()],
            key=lambda item: item[0],
        )
        self.audio_path = audio_path
        self.on_finished = on_finished

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

        self.next_lyric_idx = 0
        self.boxes = []
        self.last_frame_time = None
        self.current_side = "left"
        self.is_running = False

        # Bind ESC to stop playback anytime
        self.root.bind_all("<Escape>", self.stop)

        # Control overlay (small floating stop button)
        self.stop_btn_win = tk.Toplevel(self.root)
        self.stop_btn_win.overrideredirect(True)
        self.stop_btn_win.attributes("-topmost", True)
        self.stop_btn_win.configure(bg="#2d2d3a")
        self.stop_btn_win.geometry(f"160x38+{self.screen_w - 180}+20")

        stop_btn = tk.Button(
            self.stop_btn_win,
            text="⏹ หยุดเล่น (ESC)",
            font=("Helvetica", 10, "bold"),
            bg="#e78284",
            fg="#ffffff",
            activebackground="#ea999c",
            relief="flat",
            cursor="hand2",
            command=self.stop,
        )
        stop_btn.pack(expand=True, fill="both", padx=2, pady=2)

    def _get_font(self):
        """Returns cached Font object for text measurement."""
        if self._cached_font is None:
            self._cached_font = tkfont.Font(font=self._font_spec)
        return self._cached_font

    def random_safe_x(self, box_w=None):
        if box_w is None:
            box_w = self.cfg["box_w"]
        center_x = self.screen_w // 2
        spacing = box_w + 50
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
        self.start_time = time.time()
        self.last_frame_time = self.start_time

        # Play audio if available
        if self.audio_path and os.path.exists(self.audio_path):
            try:
                init_audio()
                pygame.mixer.music.load(self.audio_path)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"Audio playback warning: {e}")

        self.tick()

    def tick(self):
        if not self.is_running:
            return

        now = time.time()
        elapsed = now - self.start_time
        dt = now - self.last_frame_time
        self.last_frame_time = now

        box_h = self.cfg["box_h"]

        # Spawn new lyric cards when timestamp arrives
        while (
            self.next_lyric_idx < len(self.lyrics)
            and self.lyrics[self.next_lyric_idx][0] <= elapsed
        ):
            _, text = self.lyrics[self.next_lyric_idx]

            # Estimate card width from text using cached font
            needed_w = self._get_font().measure(text) + 80
            est_box_w = max(self.cfg["box_w"], min(needed_w, 900))

            x = self.random_safe_x(est_box_w)
            y = self.screen_h - box_h - BOTTOM_SPAWN_OFFSET
            box = LyricCard(self.root, text, x, y, self.cfg)
            self.boxes.append(box)
            self.next_lyric_idx += 1

        # Float existing cards upward
        dy = RISE_SPEED * dt
        still_visible = []
        for box in self.boxes:
            box.rise(dy)
            if box.is_offscreen():
                box.destroy()
            else:
                if box.is_alive:
                    still_visible.append(box)
        self.boxes = still_visible

        # Continue loop if there are lyrics remaining or cards on screen
        # Use TICK_INTERVAL (30fps) instead of 16ms (60fps) to reduce X11 pressure
        if self.next_lyric_idx < len(self.lyrics) or self.boxes:
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

        # Destroy all cards
        for box in self.boxes:
            box.destroy()
        self.boxes.clear()

        # Destroy stop button window
        try:
            self.stop_btn_win.destroy()
        except tk.TclError:
            pass

        # Unbind ESC
        try:
            self.root.unbind_all("<Escape>")
        except Exception:
            pass

        if self.on_finished:
            self.on_finished()


def play_standalone(lyrics, audio_path=None, style="text_only"):
    root = tk.Tk()
    root.withdraw()

    def on_done():
        root.quit()
        root.destroy()

    player = LyricFloatPlayer(
        root, lyrics, audio_path=audio_path, style=style, on_finished=on_done
    )
    player.start()
    root.mainloop()


if __name__ == "__main__":
    sample_lyrics = [
        (0.5, "Do you think I have forgotten?"),
        (3.5, "迷わずに今 矛盾だらけの世界を"),
        (7.0, "その手で撃ち放て"),
    ]
    play_standalone(sample_lyrics, style="text_only")
