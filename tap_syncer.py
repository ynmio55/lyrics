"""
tap_syncer.py - Interactive Tap-to-Sync Module
Allows users to press SPACEBAR while listening to the song to record timestamps effortlessly.
"""

import time
import tkinter as tk
from tkinter import ttk
import pygame
from card_player import init_audio


class TapSyncDialog(tk.Toplevel):
    def __init__(self, parent, audio_path, raw_lines, on_complete):
        super().__init__(parent)
        self.audio_path = audio_path
        self.lines = [l.strip() for l in raw_lines if l.strip()]
        self.on_complete = on_complete

        self.title("Tap Sync")
        self.geometry("640x520")
        self.configure(bg="#0b0b0c")
        self.transient(parent)
        self.grab_set()

        self.timestamps = []
        self.current_idx = 0
        self.is_playing = False
        self.is_paused = False
        self.started_once = False

        self.setup_ui()
        self.bind("<space>", self.on_tap)
        self.bind("<BackSpace>", lambda e: self.undo_tap())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # Header
        header = tk.Frame(self, bg="#151517", height=60)
        header.pack(fill="x", padx=15, pady=12)

        lbl_title = tk.Label(
            header,
            text="TAP SYNC",
            font=("Helvetica", 14, "bold"),
            bg="#151517",
            fg="#cdd6f4",
        )
        lbl_title.pack(anchor="w", padx=10, pady=4)

        lbl_inst = tk.Label(
            header,
            text="เล่นเพลง แล้วกด SPACE ตรงจังหวะที่แต่ละบรรทัดเริ่มร้อง",
            font=("Helvetica", 10),
            bg="#151517",
            fg="#a6adc8",
        )
        lbl_inst.pack(anchor="w", padx=10, pady=(0, 6))

        # Status & Time bar
        time_bar = tk.Frame(self, bg="#0b0b0c")
        time_bar.pack(fill="x", padx=20, pady=5)

        self.lbl_progress = tk.Label(
            time_bar,
            text=f"ความคืบหน้า: 0 / {len(self.lines)} ท่อน",
            font=("Helvetica", 11, "bold"),
            bg="#0b0b0c",
            fg="#c8ff47",
        )
        self.lbl_progress.pack(side="left")

        self.lbl_time = tk.Label(
            time_bar,
            text="เวลา: 00:00.0",
            font=("Helvetica", 12, "bold"),
            bg="#0b0b0c",
            fg="#c8ff47",
        )
        self.lbl_time.pack(side="right")

        # Current Lyric Box (Card)
        card = tk.Frame(
            self, bg="#1c1c20", highlightbackground="#c8ff47", highlightthickness=2
        )
        card.pack(fill="both", expand=True, padx=20, pady=10)

        tk.Label(
            card,
            text="CURRENT LINE",
            font=("Helvetica", 9),
            bg="#1c1c20",
            fg="#9a9aa2",
        ).pack(pady=(12, 4))

        self.lbl_current = tk.Label(
            card,
            text=self.lines[0] if self.lines else "ไม่มีเนื้อเพลง",
            font=("Helvetica", 16, "bold"),
            bg="#1c1c20",
            fg="#f2f2f3",
            wraplength=560,
            justify="center",
        )
        self.lbl_current.pack(expand=True, fill="both", padx=15, pady=10)

        # Next preview
        self.lbl_next = tk.Label(
            card,
            text=(
                f"ท่อนถัดไป: {self.lines[1]}"
                if len(self.lines) > 1
                else "(ท่อนสุดท้ายแล้ว)"
            ),
            font=("Helvetica", 10, "italic"),
            bg="#1c1c20",
            fg="#77777f",
            wraplength=560,
        )
        self.lbl_next.pack(pady=(0, 12))

        # Bottom Buttons
        btn_bar = tk.Frame(self, bg="#0b0b0c")
        btn_bar.pack(fill="x", padx=20, pady=15)

        self.btn_play = tk.Button(
            btn_bar,
            text="PLAY",
            font=("Helvetica", 11, "bold"),
            bg="#c8ff47",
            fg="#0b0b0c",
            activebackground="#9a9aa2",
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
            command=self.toggle_play,
        )
        self.btn_play.pack(side="left", padx=5)

        self.btn_tap = tk.Button(
            btn_bar,
            text="SPACE  /  MARK LINE",
            font=("Helvetica", 12, "bold"),
            bg="#c8ff47",
            fg="#0b0b0c",
            activebackground="#e5ff8b",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self.record_tap,
        )
        self.btn_tap.pack(side="left", padx=10, fill="x", expand=True)

        self.btn_undo = tk.Button(
            btn_bar,
            text="UNDO",
            font=("Helvetica", 10),
            bg="#2c2c31",
            fg="#cdd6f4",
            activebackground="#39393f",
            relief="flat",
            padx=10,
            pady=8,
            cursor="hand2",
            command=self.undo_tap,
        )
        self.btn_undo.pack(side="left", padx=5)

        self.btn_done = tk.Button(
            btn_bar,
            text="DONE",
            font=("Helvetica", 11, "bold"),
            bg="#f2f2f3",
            fg="#0b0b0c",
            activebackground="#d7ad68",
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
            command=self.finish_sync,
        )
        self.btn_done.pack(side="right", padx=5)

    def get_audio_time(self):
        """Return the playback clock from pygame itself, not wall time."""
        try:
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms >= 0:
                return pos_ms / 1000.0
        except Exception:
            pass
        return 0.0

    def toggle_play(self):
        try:
            init_audio()
            if not self.started_once:
                pygame.mixer.music.load(self.audio_path)
                pygame.mixer.music.play()
                self.started_once = True
                self.is_playing = True
                self.is_paused = False
                self.btn_play.config(text="PAUSE", bg="#d7ad68")
                self.update_timer()
            elif self.is_paused:
                pygame.mixer.music.unpause()
                self.is_paused = False
                self.is_playing = True
                self.btn_play.config(text="PAUSE", bg="#d7ad68")
                self.update_timer()
            else:
                pygame.mixer.music.pause()
                self.is_paused = True
                self.is_playing = False
                self.btn_play.config(text="RESUME", bg="#c8ff47")
        except Exception as e:
            self.lbl_time.config(text=f"เปิดเพลงไม่สำเร็จ: {e}")

    def update_timer(self):
        if self.is_playing:
            elapsed = self.get_audio_time()
            mins = int(elapsed // 60)
            secs = elapsed % 60
            self.lbl_time.config(text=f"เวลา: {mins:02d}:{secs:04.1f}")
            self.after(50, self.update_timer)

    def on_tap(self, event=None):
        if not self.is_playing:
            self.toggle_play()
            return "break"
        self.record_tap()
        return "break"

    def record_tap(self):
        if not self.started_once:
            self.toggle_play()
            return
        if self.is_paused:
            return

        if self.current_idx >= len(self.lines):
            return

        elapsed = self.get_audio_time()
        line_text = self.lines[self.current_idx]
        self.timestamps.append((round(elapsed, 2), line_text))
        self.current_idx += 1

        self.update_card_display()

        if self.current_idx >= len(self.lines):
            self.lbl_current.config(
                text="ครบทุกบรรทัดแล้ว",
                fg="#c8ff47",
            )
            self.lbl_next.config(text="")
            self.btn_tap.config(state="disabled")

    def undo_tap(self):
        if self.timestamps and self.current_idx > 0:
            self.timestamps.pop()
            self.current_idx -= 1
            self.btn_tap.config(state="normal")
            self.update_card_display()

    def update_card_display(self):
        self.lbl_progress.config(
            text=f"ความคืบหน้า: {self.current_idx} / {len(self.lines)} ท่อน"
        )
        if self.current_idx < len(self.lines):
            self.lbl_current.config(
                text=self.lines[self.current_idx], fg="#f2f2f3"
            )
            if self.current_idx + 1 < len(self.lines):
                self.lbl_next.config(
                    text=f"ท่อนถัดไป: {self.lines[self.current_idx + 1]}"
                )
            else:
                self.lbl_next.config(text="(ท่อนสุดท้ายแล้ว)")

    def finish_sync(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

        if self.timestamps:
            self.on_complete(self.timestamps)
        self.destroy()

    def on_close(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self.destroy()
