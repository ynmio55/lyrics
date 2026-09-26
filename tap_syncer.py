"""
tap_syncer.py - Interactive Tap-to-Sync Module
Allows users to press SPACEBAR while listening to the song to record timestamps effortlessly.
"""

import time
import tkinter as tk
from tkinter import ttk
import pygame


class TapSyncDialog(tk.Toplevel):
    def __init__(self, parent, audio_path, raw_lines, on_complete):
        super().__init__(parent)
        self.audio_path = audio_path
        self.lines = [l.strip() for l in raw_lines if l.strip()]
        self.on_complete = on_complete

        self.title("⌨️ เคาะจับเวลาสด (Tap to Sync)")
        self.geometry("640x520")
        self.configure(bg="#1e1e2e")
        self.transient(parent)
        self.grab_set()

        self.timestamps = []
        self.current_idx = 0
        self.start_time = None
        self.is_playing = False
        self.paused_time = 0.0

        self.setup_ui()
        self.bind("<space>", self.on_tap)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        # Header
        header = tk.Frame(self, bg="#252538", height=60)
        header.pack(fill="x", padx=15, pady=12)

        lbl_title = tk.Label(
            header,
            text="🎧 โหมดเคาะจับเวลาสด (Tap to Sync)",
            font=("Helvetica", 14, "bold"),
            bg="#252538",
            fg="#cdd6f4",
        )
        lbl_title.pack(anchor="w", padx=10, pady=4)

        lbl_inst = tk.Label(
            header,
            text="กด [ เริ่มเล่น ] แล้วเมื่อถึงท่อนร้อง ให้กด [ SPACEBAR ] เพื่อจับเวลาแต่ละบรรทัด",
            font=("Helvetica", 10),
            bg="#252538",
            fg="#a6adc8",
        )
        lbl_inst.pack(anchor="w", padx=10, pady=(0, 6))

        # Status & Time bar
        time_bar = tk.Frame(self, bg="#1e1e2e")
        time_bar.pack(fill="x", padx=20, pady=5)

        self.lbl_progress = tk.Label(
            time_bar,
            text=f"ความคืบหน้า: 0 / {len(self.lines)} ท่อน",
            font=("Helvetica", 11, "bold"),
            bg="#1e1e2e",
            fg="#89b4fa",
        )
        self.lbl_progress.pack(side="left")

        self.lbl_time = tk.Label(
            time_bar,
            text="เวลา: 00:00.0",
            font=("Helvetica", 12, "bold"),
            bg="#1e1e2e",
            fg="#a6e3a1",
        )
        self.lbl_time.pack(side="right")

        # Current Lyric Box (Card)
        card = tk.Frame(
            self, bg="#313244", highlightbackground="#89b4fa", highlightthickness=2
        )
        card.pack(fill="both", expand=True, padx=20, pady=10)

        tk.Label(
            card,
            text="กำลังรอท่อนนี้ ร้องปุ๊บ เคาะ Spacebar ปั๊บ:",
            font=("Helvetica", 9),
            bg="#313244",
            fg="#94e2d5",
        ).pack(pady=(12, 4))

        self.lbl_current = tk.Label(
            card,
            text=self.lines[0] if self.lines else "ไม่มีเนื้อเพลง",
            font=("Helvetica", 16, "bold"),
            bg="#313244",
            fg="#f9e2af",
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
            bg="#313244",
            fg="#6c7086",
            wraplength=560,
        )
        self.lbl_next.pack(pady=(0, 12))

        # Bottom Buttons
        btn_bar = tk.Frame(self, bg="#1e1e2e")
        btn_bar.pack(fill="x", padx=20, pady=15)

        self.btn_play = tk.Button(
            btn_bar,
            text="▶️ เริ่มเล่นเพลง (Play)",
            font=("Helvetica", 11, "bold"),
            bg="#a6e3a1",
            fg="#11111b",
            activebackground="#94e2d5",
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
            command=self.toggle_play,
        )
        self.btn_play.pack(side="left", padx=5)

        self.btn_tap = tk.Button(
            btn_bar,
            text="🎯 SPACEBAR (เคาะท่อนนี้)",
            font=("Helvetica", 12, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self.record_tap,
        )
        self.btn_tap.pack(side="left", padx=10, fill="x", expand=True)

        self.btn_undo = tk.Button(
            btn_bar,
            text="⏪ ย้อนกลับ",
            font=("Helvetica", 10),
            bg="#45475a",
            fg="#cdd6f4",
            activebackground="#585b70",
            relief="flat",
            padx=10,
            pady=8,
            cursor="hand2",
            command=self.undo_tap,
        )
        self.btn_undo.pack(side="left", padx=5)

        self.btn_done = tk.Button(
            btn_bar,
            text="✅ เสร็จสิ้น",
            font=("Helvetica", 11, "bold"),
            bg="#f9e2af",
            fg="#11111b",
            activebackground="#fab387",
            relief="flat",
            padx=15,
            pady=8,
            cursor="hand2",
            command=self.finish_sync,
        )
        self.btn_done.pack(side="right", padx=5)

    def toggle_play(self):
        if not self.is_playing:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(self.audio_path)
                pygame.mixer.music.play()
                self.start_time = time.time()
                self.is_playing = True
                self.btn_play.config(
                    text="⏸ หยุดชั่วคราว (Pause)", bg="#fab387"
                )
                self.update_timer()
            except Exception as e:
                self.lbl_time.config(text=f"เปิดเพลงไม่สำเร็จ: {e}")
        else:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.btn_play.config(text="▶️ เล่นต่อ (Resume)", bg="#a6e3a1")

    def update_timer(self):
        if self.is_playing and self.start_time:
            elapsed = time.time() - self.start_time
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
        if not self.is_playing or self.start_time is None:
            self.toggle_play()
            return

        if self.current_idx >= len(self.lines):
            return

        elapsed = time.time() - self.start_time
        line_text = self.lines[self.current_idx]
        self.timestamps.append((round(elapsed, 2), line_text))
        self.current_idx += 1

        self.update_card_display()

        if self.current_idx >= len(self.lines):
            self.lbl_current.config(
                text="🎉 เคาะครบทุกท่อนแล้ว! กด [ เสร็จสิ้น ] ได้เลย",
                fg="#a6e3a1",
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
                text=self.lines[self.current_idx], fg="#f9e2af"
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
