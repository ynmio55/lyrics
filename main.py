"""
main.py - Lyric Studio (Easy & Automatic Edition)
Designed to be as effortless as possible:
1. Pick a song -> 2. Everything auto-syncs -> 3. Click PLAY!
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from card_player import LyricFloatPlayer
import sync_engine
from tap_syncer import TapSyncDialog


class EasyLyricStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎵 Lyric Studio - โหมดอัตโนมัติ ใช้ง่ายที่สุด")
        self.geometry("980x680")
        self.minsize(860, 580)
        self.configure(bg="#14141e")

        self.audio_path = None
        self.synced_lyrics = []
        self.sync_offset = 0.0

        self.setup_styles()
        self.build_ui()
        self.load_initial_state()
        self.setup_universal_clipboard()

        # Press Enter to Play directly if ready
        self.bind("<Return>", lambda e: self.play_lyric_cards())

    def setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(
            "Treeview",
            background="#1e1e2e",
            foreground="#cdd6f4",
            fieldbackground="#1e1e2e",
            rowheight=30,
            font=("Helvetica", 11),
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#2b2b3d",
            foreground="#89b4fa",
            font=("Helvetica", 11, "bold"),
            relief="flat",
            padding=6,
        )
        style.map(
            "Treeview",
            background=[("selected", "#45475a")],
            foreground=[("selected", "#a6e3a1")],
        )

    def build_ui(self):
        # 1. Header
        header = tk.Frame(self, bg="#0d0d15", height=65)
        header.pack(fill="x")

        lbl_app = tk.Label(
            header,
            text="🎵 Lyric Studio",
            font=("Helvetica", 16, "bold"),
            bg="#0d0d15",
            fg="#89b4fa",
        )
        lbl_app.pack(side="left", padx=(20, 10), pady=12)

        lbl_tag = tk.Label(
            header,
            text="✨ เลือกเพลงปุ๊บ ระบบดึงเนื้อเพลงพร้อมเวลาให้อัตโนมัติทันที",
            font=("Helvetica", 10),
            bg="#0d0d15",
            fg="#7f849c",
        )
        lbl_tag.pack(side="left", pady=(15, 12))

        # 2. Main Step 1 Card: Song Picker & Auto Status
        step1_frame = tk.Frame(
            self,
            bg="#1e1e2e",
            highlightbackground="#313244",
            highlightthickness=1,
        )
        step1_frame.pack(fill="x", padx=20, pady=(15, 10))

        # Big Pick Audio Button
        btn_pick = tk.Button(
            step1_frame,
            text="📂 1. เลือกไฟล์เพลง (.mp3)",
            font=("Helvetica", 12, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            relief="flat",
            padx=18,
            pady=10,
            cursor="hand2",
            command=self.browse_audio,
        )
        btn_pick.pack(side="left", padx=15, pady=12)

        # Song info display
        info_frame = tk.Frame(step1_frame, bg="#1e1e2e")
        info_frame.pack(side="left", fill="both", expand=True, padx=5, pady=8)

        self.lbl_song_title = tk.Label(
            info_frame,
            text="ยังไม่ได้เลือกเพลง (กดปุ่มซ้ายเพื่อเลือก)",
            font=("Helvetica", 12, "bold"),
            bg="#1e1e2e",
            fg="#cdd6f4",
            anchor="w",
        )
        self.lbl_song_title.pack(fill="x", pady=(2, 2))

        self.lbl_song_status = tk.Label(
            info_frame,
            text="รอเลือกเพลง...",
            font=("Helvetica", 10),
            bg="#1e1e2e",
            fg="#a6adc8",
            anchor="w",
        )
        self.lbl_song_status.pack(fill="x")

        # Quick Search Box (only if user wants to change search title)
        search_box = tk.Frame(step1_frame, bg="#1e1e2e")
        search_box.pack(side="right", padx=15, pady=12)

        tk.Label(
            search_box,
            text="ชื่อเพลง:",
            font=("Helvetica", 9, "bold"),
            bg="#1e1e2e",
            fg="#a6adc8",
        ).pack(side="left", padx=4)

        self.entry_search = tk.Entry(
            search_box,
            font=("Helvetica", 10),
            bg="#2b2b3d",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
            width=20,
        )
        self.entry_search.pack(side="left", padx=4)
        self.entry_search.bind("<Return>", lambda e: self.trigger_manual_search())
        self.attach_context_menu(self.entry_search)

        btn_re_search = tk.Button(
            search_box,
            text="🔍 ค้นหาใหม่",
            font=("Helvetica", 9, "bold"),
            bg="#45475a",
            fg="#cdd6f4",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.trigger_manual_search,
        )
        btn_re_search.pack(side="left", padx=4)

        # 3. Step 2: Content Area (Notebook/Tabs: Preview vs Edit)
        content_frame = tk.Frame(self, bg="#14141e")
        content_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # Top bar of content: Tools & Actions
        tools_bar = tk.Frame(content_frame, bg="#14141e")
        tools_bar.pack(fill="x", pady=(0, 6))

        tk.Label(
            tools_bar,
            text="📋 รายการเนื้อเพลง & เวลา (พร้อมเล่น)",
            font=("Helvetica", 11, "bold"),
            bg="#14141e",
            fg="#a6e3a1",
        ).pack(side="left")

        # Tool buttons on right
        btn_load_lrc = tk.Button(
            tools_bar,
            text="📂 โหลด .lrc",
            font=("Helvetica", 9),
            bg="#313244",
            fg="#cdd6f4",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.load_lrc_dialog,
        )
        btn_load_lrc.pack(side="right", padx=3)

        btn_tap = tk.Button(
            tools_bar,
            text="⌨️ เคาะ Spacebar สด",
            font=("Helvetica", 9, "bold"),
            bg="#fab387",
            fg="#11111b",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.open_tap_sync,
        )
        btn_tap.pack(side="right", padx=5)

        btn_edit_text = tk.Button(
            tools_bar,
            text="📝 แปะ/แก้ไขเนื้อเพลง",
            font=("Helvetica", 9),
            bg="#45475a",
            fg="#cdd6f4",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.toggle_editor,
        )
        btn_edit_text.pack(side="right", padx=3)

        # Main Table (Treeview)
        table_container = tk.Frame(
            content_frame,
            bg="#1e1e2e",
            highlightbackground="#313244",
            highlightthickness=1,
        )
        table_container.pack(fill="both", expand=True)

        cols = ("time", "text")
        self.tree = ttk.Treeview(
            table_container, columns=cols, show="headings", selectmode="browse"
        )
        self.tree.heading("time", text="เวลา (วินาที)")
        self.tree.heading("text", text="เนื้อเพลงที่กำลังจะแสดง")
        self.tree.column("time", width=120, anchor="center")
        self.tree.column("text", width=700, anchor="w")

        scrollbar = ttk.Scrollbar(
            table_container, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Collapsible text editor (initially hidden)
        self.editor_frame = tk.Frame(
            content_frame,
            bg="#1e1e2e",
            highlightbackground="#fab387",
            highlightthickness=1,
        )
        tk.Label(
            self.editor_frame,
            text="วางเนื้อเพลงที่ต้องการด้านล่าง แล้วกด [ ✨ ซิงค์เวลาตามข้อความนี้ ]",
            font=("Helvetica", 10, "bold"),
            bg="#1e1e2e",
            fg="#fab387",
        ).pack(anchor="w", padx=10, pady=(6, 4))

        self.txt_editor = tk.Text(
            self.editor_frame,
            height=7,
            font=("Helvetica", 10),
            bg="#14141e",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
            padx=8,
            pady=8,
        )
        self.txt_editor.pack(fill="both", expand=True, padx=10, pady=4)
        self.attach_context_menu(self.txt_editor)

        editor_btn_bar = tk.Frame(self.editor_frame, bg="#1e1e2e")
        editor_btn_bar.pack(fill="x", padx=10, pady=(0, 6))

        tk.Button(
            editor_btn_bar,
            text="✨ ซิงค์เวลาตามข้อความนี้",
            font=("Helvetica", 9, "bold"),
            bg="#a6e3a1",
            fg="#11111b",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.sync_from_editor,
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            editor_btn_bar,
            text="📋 วาง (Paste)",
            font=("Helvetica", 9, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.paste_to_editor,
        ).pack(side="left", padx=4)

        tk.Button(
            editor_btn_bar,
            text="📄 คัดลอก (Copy)",
            font=("Helvetica", 9),
            bg="#45475a",
            fg="#cdd6f4",
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.copy_from_editor,
        ).pack(side="left", padx=4)

        tk.Button(
            editor_btn_bar,
            text="❌ ล้าง (Clear)",
            font=("Helvetica", 9),
            bg="#45475a",
            fg="#e78284",
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.clear_editor,
        ).pack(side="left", padx=4)

        tk.Button(
            editor_btn_bar,
            text="ปิดกล่องแก้ไข",
            font=("Helvetica", 9),
            bg="#313244",
            fg="#cdd6f4",
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
            command=self.toggle_editor,
        ).pack(side="right")

        # 4. Bottom Giant Play Bar & Calibration Dock
        bottom_bar = tk.Frame(self, bg="#0d0d15")
        bottom_bar.pack(fill="x", side="bottom")

        # Row 1: Fine-tuning Offset Bar
        offset_bar = tk.Frame(
            bottom_bar,
            bg="#181825",
            highlightbackground="#313244",
            highlightthickness=1,
        )
        offset_bar.pack(fill="x", padx=20, pady=(8, 4))

        lbl_off_title = tk.Label(
            offset_bar,
            text="⏱️ ชดเชยเวลา (Offset):",
            font=("Helvetica", 10, "bold"),
            bg="#181825",
            fg="#89b4fa",
        )
        lbl_off_title.pack(side="left", padx=(12, 6), pady=6)

        self.lbl_offset_val = tk.Label(
            offset_bar,
            text=f"{self.sync_offset:+.2f}s",
            font=("Helvetica", 11, "bold"),
            bg="#252538",
            fg="#a6e3a1",
            padx=8,
            pady=2,
        )
        self.lbl_offset_val.pack(side="left", padx=4, pady=6)

        # Quick preset buttons
        preset_buttons = [
            (-0.5, "-0.5s"),
            (-0.2, "-0.2s"),
            (-0.1, "-0.1s"),
            (0.0, "0.0s (รีเซ็ต)"),
            (0.1, "+0.1s"),
            (0.2, "+0.2s"),
            (0.5, "+0.5s"),
        ]
        for val, label in preset_buttons:
            if val == 0.0:
                cmd = lambda: self.adjust_offset(0.0, absolute=True)
                bg_col = "#313244"
                fg_col = "#cdd6f4"
            elif val > 0:
                cmd = (lambda v=val: lambda: self.adjust_offset(v))()
                bg_col = "#2a324b"
                fg_col = "#89b4fa"
            else:
                cmd = (lambda v=val: lambda: self.adjust_offset(v))()
                bg_col = "#3b2d35"
                fg_col = "#fab387"

            tk.Button(
                offset_bar,
                text=label,
                font=("Helvetica", 9),
                bg=bg_col,
                fg=fg_col,
                relief="flat",
                padx=6,
                pady=2,
                cursor="hand2",
                command=cmd,
            ).pack(side="left", padx=2, pady=6)

        # Auto silence button
        tk.Button(
            offset_bar,
            text="⚡ ตรวจจับช่วงเงียบต้นเพลง",
            font=("Helvetica", 9, "bold"),
            bg="#45475a",
            fg="#f9e2af",
            activebackground="#585b70",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
            command=self.auto_detect_silence,
        ).pack(side="right", padx=(4, 12), pady=6)

        # Helper tip
        tk.Label(
            offset_bar,
            text="💡 เนื้อขึ้นเร็วไปกด [+ ชะลอ] | กด [ / ] ตอนกำลังเล่นได้ทันที",
            font=("Helvetica", 9),
            bg="#181825",
            fg="#a6adc8",
        ).pack(side="right", padx=6, pady=6)

        # Row 2: Play Bar & Style Selector
        play_bar = tk.Frame(bottom_bar, bg="#0d0d15")
        play_bar.pack(fill="x", padx=20, pady=(2, 10))

        # Style Selector
        style_box = tk.Frame(play_bar, bg="#0d0d15")
        style_box.pack(side="left", pady=4)

        tk.Label(
            style_box,
            text="🎨 รูปแบบหน้าจอ:",
            font=("Helvetica", 11, "bold"),
            bg="#0d0d15",
            fg="#cdd6f4",
        ).pack(side="left", padx=(0, 8))

        self.style_var = tk.StringVar(
            value="🌙 การ์ดลอยแก้วมน (แนะนำ - สวยโมเดิร์น)"
        )
        self.style_map = {
            "🌙 การ์ดลอยแก้วมน (แนะนำ - สวยโมเดิร์น)": "floating_cards",
            "✨ ตัวหนังสือลอยไร้กรอบ (Minimal Float)": "text_only",
            "⚡ การ์ดนีออนไซเบอร์ลอย (Cyberpunk Neon)": "neon_cyber",
            "☁️ การ์ดออโรราลอย (Aurora Pastel)": "glass_aurora",
            "🏝️ แถบ Dynamic Island (Apple Music HUD)": "dynamic_island",
        }

        self.cb_style = ttk.Combobox(
            style_box,
            textvariable=self.style_var,
            values=list(self.style_map.keys()),
            state="readonly",
            width=44,
            font=("Helvetica", 10),
        )
        self.cb_style.pack(side="left", padx=4)

        # Giant Play Button
        self.btn_play = tk.Button(
            play_bar,
            text="🚀 ▶️ เล่น Lyric Cards (Enter)",
            font=("Helvetica", 13, "bold"),
            bg="#a6e3a1",
            fg="#11111b",
            activebackground="#94e2d5",
            activeforeground="#11111b",
            relief="flat",
            padx=28,
            pady=10,
            cursor="hand2",
            command=self.play_lyric_cards,
        )
        self.btn_play.pack(side="right")

    def load_initial_state(self):
        """Loads available songs/lyrics automatically so it's ready out of the box."""
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Priority 1: Check for IGNITE_Eir_Aoi or other lrc
        possible_lrcs = [
            os.path.join(base_dir, "lyrics", "IGNITE_Eir_Aoi.lrc"),
            os.path.join(base_dir, "lyrics", "EndOfTheRoad.lrc"),
        ]
        chosen_lrc = None
        for lrc_p in possible_lrcs:
            if os.path.exists(lrc_p):
                chosen_lrc = lrc_p
                break

        # Priority 2: Check for song files
        possible_songs = [
            os.path.join(base_dir, "songs", "IGNITEMusic_VideoTVIIOP.mp3"),
            os.path.join(base_dir, "IGNITEMusic_VideoTVIIOP.mp3"),
            os.path.join(base_dir, "songs", "song.mp3"),
            os.path.join(base_dir, "song.mp3"),
        ]
        for song_p in possible_songs:
            if os.path.exists(song_p):
                self.auto_setup_song(song_p, preferred_lrc=chosen_lrc)
                return

        # If chosen lrc exists without song, load it anyway
        if chosen_lrc:
            self.load_lrc_file_path(chosen_lrc)

    def auto_setup_song(self, song_path, preferred_lrc=None):
        """
        The magic function: given a song file, it automatically configures
        everything: name, duration, searches online or loads local .lrc!
        """
        self.audio_path = song_path
        filename = os.path.basename(song_path)
        duration = sync_engine.get_audio_duration(song_path)
        clean_name = sync_engine.clean_song_query(filename)

        self.lbl_song_title.config(
            text=f"🎵 {clean_name}", fg="#a6e3a1"
        )
        self.lbl_song_status.config(
            text=f"ไฟล์: {filename} • ความยาว: {duration:.1f} วินาที",
            fg="#a6adc8",
        )

        self.entry_search.delete(0, "end")
        self.entry_search.insert(0, clean_name)

        # Automatically check for leading silence in audio (e.g. video intro)
        lead_silence = sync_engine.detect_lead_silence(song_path)
        if lead_silence >= 0.8:
            self.adjust_offset(lead_silence, absolute=True)
            self.lbl_song_status.config(
                text=f"ไฟล์: {filename} • ตรวจพบช่วงเงียบต้นเพลง {lead_silence:.1f}s (ตั้งค่าชดเชย +{lead_silence:.1f}s ให้อัตโนมัติแล้ว)",
                fg="#a6e3a1",
            )

        # 1. Check if a local .lrc file in lyrics/ matches this song
        base_dir = os.path.dirname(os.path.abspath(__file__))
        lyrics_dir = os.path.join(base_dir, "lyrics")

        if preferred_lrc and os.path.exists(preferred_lrc):
            self.load_lrc_file_path(preferred_lrc)
            return

        matched_local_lrc = None
        if os.path.exists(lyrics_dir):
            for f in os.listdir(lyrics_dir):
                if f.endswith(".lrc"):
                    f_clean = f.lower()
                    if clean_name.lower() in f_clean or f_clean in clean_name.lower():
                        matched_local_lrc = os.path.join(lyrics_dir, f)
                        break

        if matched_local_lrc:
            self.load_lrc_file_path(matched_local_lrc)
            return

        # 2. If not local, automatically search online in the background!
        self.auto_search_online(clean_name)

    def auto_search_online(self, query):
        self.lbl_song_status.config(
            text="⚡ กำลังค้นหาเนื้อเพลงและเวลาจากฐานข้อมูลอัตโนมัติ...",
            fg="#f9e2af",
        )
        self.update_idletasks()

        def worker():
            results = sync_engine.search_online_lyrics(query)
            if not results:
                # If single word, try with query + popular tags
                results = sync_engine.search_online_lyrics(f"{query} Eir Aoi")

            if results:
                best = results[0]
                t_name = best.get("trackName", query)
                a_name = best.get("artistName", "")
                parsed = sync_engine.parse_lrc(best.get("syncedLyrics", ""))
                # Filter empty lines
                valid_items = [
                    (t, txt.strip())
                    for t, txt in parsed
                    if txt and txt.strip()
                ]

                self.after(0, lambda: self.update_synced_table(valid_items))
                self.after(
                    0,
                    lambda: self.lbl_song_status.config(
                        text=f"✅ พร้อมเล่นทันที! พบเนื้อเพลงจาก '{t_name} - {a_name}' ({len(valid_items)} ท่อน)",
                        fg="#a6e3a1",
                    ),
                )
            else:
                self.after(
                    0,
                    lambda: self.lbl_song_status.config(
                        text="⚠️ ไม่พบในฐานข้อมูลอัตโนมัติ คุณสามารถกด '📝 แปะเนื้อเพลง' หรือ '⌨️ เคาะ Spacebar' ได้ครับ",
                        fg="#fab387",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def browse_audio(self):
        filepath = filedialog.askopenfilename(
            title="เลือกไฟล์เพลง MP3",
            filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.flac")],
        )
        if filepath:
            self.auto_setup_song(filepath)

    def trigger_manual_search(self):
        q = self.entry_search.get().strip()
        if q:
            self.auto_search_online(q)

    def load_lrc_file_path(self, filepath):
        try:
            items = sync_engine.load_lrc_file(filepath)
            valid_items = [
                (t, txt.strip()) for t, txt in items if txt and txt.strip()
            ]
            self.update_synced_table(valid_items)
            lrc_name = os.path.basename(filepath)
            self.lbl_song_status.config(
                text=f"✅ โหลดเนื้อเพลงจากไฟล์ {lrc_name} เรียบร้อย ({len(valid_items)} ท่อน)",
                fg="#a6e3a1",
            )
        except Exception as e:
            self.lbl_song_status.config(
                text=f"เกิดข้อผิดพลาดในการโหลด .lrc: {e}", fg="#e78284"
            )

    def load_lrc_dialog(self):
        filepath = filedialog.askopenfilename(
            title="เลือกไฟล์ .lrc", filetypes=[("LRC Lyrics", "*.lrc")]
        )
        if filepath:
            self.load_lrc_file_path(filepath)

    def update_synced_table(self, items):
        self.synced_lyrics = sorted(
            [(t, txt) for t, txt in items if txt and txt.strip()],
            key=lambda x: x[0],
        )
        self.tree.delete(*self.tree.get_children())
        for t, text in self.synced_lyrics:
            mins = int(t // 60)
            secs = t % 60
            time_str = f"{mins:02d}:{secs:04.1f} ({t:.1f}s)"
            self.tree.insert("", "end", values=(time_str, text))

        # Also populate text editor in case user opens it
        raw = "\n".join([item[1] for item in self.synced_lyrics])
        self.txt_editor.delete("1.0", "end")
        self.txt_editor.insert("1.0", raw)

    def toggle_editor(self):
        if self.editor_frame.winfo_ismapped():
            self.editor_frame.pack_forget()
        else:
            self.editor_frame.pack(fill="x", pady=5, after=self.tree.master)

    def sync_from_editor(self):
        raw_text = self.txt_editor.get("1.0", "end").strip()
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        if not lines:
            return

        query = self.entry_search.get().strip()
        self.lbl_song_status.config(
            text="กำลังจับเวลาตามเนื้อเพลงที่วาง...", fg="#f9e2af"
        )

        def worker():
            results = sync_engine.search_online_lyrics(query)
            if results:
                ref_lrc = results[0].get("syncedLyrics", "")
                aligned = sync_engine.auto_align_lyrics(
                    lines, ref_lrc, start_from_zero=True
                )
                self.after(0, lambda: self.update_synced_table(aligned))
                self.after(0, lambda: self.toggle_editor())
                self.after(
                    0,
                    lambda: self.lbl_song_status.config(
                        text=f"✅ จัดเวลาสำเร็จตามเนื้อเพลงที่คุณวาง ({len(aligned)} ท่อน)",
                        fg="#a6e3a1",
                    ),
                )
            else:
                self.after(
                    0,
                    lambda: self.lbl_song_status.config(
                        text="ไม่พบข้อมูลเพลงนี้ในเน็ต แนะนำให้กด 'เคาะ Spacebar สด' ครับ",
                        fg="#fab387",
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def open_tap_sync(self):
        if not self.audio_path or not os.path.exists(self.audio_path):
            messagebox.showwarning(
                "แจ้งเตือน", "กรุณาเลือกเพลง (.mp3) ก่อนเริ่มเคาะจังหวะครับ"
            )
            return

        lines = [item[1] for item in self.synced_lyrics]
        if not lines:
            raw = self.txt_editor.get("1.0", "end").strip()
            lines = [l.strip() for l in raw.splitlines() if l.strip()]

        if not lines:
            messagebox.showwarning(
                "แจ้งเตือน",
                "กรุณากด '📝 แปะเนื้อเพลง' แล้ววางเนื้อเพลงก่อนเคาะครับ",
            )
            return

        def on_done(timestamps):
            self.update_synced_table(timestamps)
            self.lbl_song_status.config(
                text=f"✅ บันทึกเวลาจากการเคาะ Spacebar เรียบร้อย ({len(timestamps)} ท่อน)",
                fg="#a6e3a1",
            )

        TapSyncDialog(self, self.audio_path, lines, on_complete=on_done)

    def adjust_offset(self, delta, absolute=False):
        if absolute:
            self.sync_offset = round(delta, 2)
        else:
            self.sync_offset = round(self.sync_offset + delta, 2)

        if hasattr(self, "lbl_offset_val"):
            self.lbl_offset_val.config(text=f"{self.sync_offset:+.2f}s")
            if self.sync_offset > 0:
                self.lbl_offset_val.config(fg="#89b4fa")
            elif self.sync_offset < 0:
                self.lbl_offset_val.config(fg="#fab387")
            else:
                self.lbl_offset_val.config(fg="#a6e3a1")

        if self.sync_offset > 0:
            status_hint = f"⏱️ ตั้งค่าหน่วงเวลา: +{self.sync_offset:.2f}s (เนื้อร้องจะขึ้นช้าลงอีกนิด พอดีกับเสียงร้อง)"
        elif self.sync_offset < 0:
            status_hint = f"⏱️ ตั้งค่าเร่งเวลา: {self.sync_offset:.2f}s (เนื้อร้องจะขึ้นเร็วขึ้น)"
        else:
            status_hint = "⏱️ รีเซ็ตการชดเชยเวลาเป็น 0.00s (ตามไฟล์ .lrc เดิม)"
        self.lbl_song_status.config(text=status_hint, fg="#89b4fa")

    def auto_detect_silence(self):
        if not self.audio_path:
            messagebox.showinfo("แจ้งเตือน", "กรุณาเลือกไฟล์เพลงก่อนครับ")
            return
        silence = sync_engine.detect_lead_silence(self.audio_path)
        if silence > 0.4:
            self.adjust_offset(silence, absolute=True)
            messagebox.showinfo(
                "ตรวจพบช่วงเงียบต้นเพลง",
                f"ตรวจพบว่าไฟล์เพลงมีช่วงเงียบที่ต้นเพลง {silence:.2f} วินาที\n"
                f"ระบบได้ตั้งค่าชดเชยเวลา +{silence:.2f}s ให้อัตโนมัติแล้ว\n"
                f"เนื้อร้องจะเริ่มขึ้นพอดีเมื่อเสียงร้องดังขึ้นครับ!",
            )
        else:
            messagebox.showinfo(
                "ผลการตรวจจับ",
                "ไฟล์เพลงนี้มีเสียงดนตรีเริ่มทันทีตั้งแต่ต้นเพลงครับ (ไม่พบช่วงเงียบผิดปกติ)",
            )

    def play_lyric_cards(self):
        if not self.synced_lyrics:
            messagebox.showwarning(
                "แจ้งเตือน",
                "ยังไม่มีเนื้อเพลงและเวลา กรุณาเลือกเพลงก่อนครับ",
            )
            return

        # Hide studio window while playing
        self.withdraw()

        def on_done(final_offset):
            self.sync_offset = final_offset
            if hasattr(self, "lbl_offset_val"):
                self.lbl_offset_val.config(text=f"{self.sync_offset:+.2f}s")
            self.deiconify()

        chosen_style = self.style_map.get(
            self.style_var.get(), "floating_cards"
        )
        player = LyricFloatPlayer(
            self,
            self.synced_lyrics,
            audio_path=self.audio_path,
            style=chosen_style,
            initial_offset=self.sync_offset,
            on_finished=on_done,
        )
        player.start()

    def paste_to_editor(self):
        try:
            clip = self.clipboard_get()
            if clip:
                self.txt_editor.insert("insert", clip)
        except Exception:
            messagebox.showwarning("แจ้งเตือน", "ไม่พบข้อความในคลิปบอร์ดครับ")

    def clear_editor(self):
        self.txt_editor.delete("1.0", "end")

    def copy_from_editor(self):
        text = self.txt_editor.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.lbl_song_status.config(
                text="✅ คัดลอกเนื้อเพลงลงคลิปบอร์ดแล้ว", fg="#a6e3a1"
            )

    def attach_context_menu(self, widget):
        """Right-click context menu (Cut, Copy, Paste, Select All) for any text widget."""
        menu = tk.Menu(
            widget,
            tearoff=0,
            bg="#2b2b3d",
            fg="#cdd6f4",
            activebackground="#45475a",
            activeforeground="#a6e3a1",
            font=("Helvetica", 10),
        )

        def do_cut():
            try:
                if isinstance(widget, tk.Text) and widget.tag_ranges("sel"):
                    sel = widget.get("sel.first", "sel.last")
                    widget.delete("sel.first", "sel.last")
                    self.clipboard_clear()
                    self.clipboard_append(sel)
                elif isinstance(widget, (tk.Entry, ttk.Entry)) and widget.selection_present():
                    sel = widget.selection_get()
                    widget.delete("sel.first", "sel.last")
                    self.clipboard_clear()
                    self.clipboard_append(sel)
            except Exception:
                pass

        def do_copy():
            try:
                if isinstance(widget, tk.Text) and widget.tag_ranges("sel"):
                    sel = widget.get("sel.first", "sel.last")
                    self.clipboard_clear()
                    self.clipboard_append(sel)
                elif isinstance(widget, (tk.Entry, ttk.Entry)) and widget.selection_present():
                    sel = widget.selection_get()
                    self.clipboard_clear()
                    self.clipboard_append(sel)
            except Exception:
                pass

        def do_paste():
            try:
                clip = self.clipboard_get()
                if clip:
                    if isinstance(widget, tk.Text):
                        if widget.tag_ranges("sel"):
                            widget.delete("sel.first", "sel.last")
                        widget.insert("insert", clip)
                    elif isinstance(widget, (tk.Entry, ttk.Entry)):
                        if widget.selection_present():
                            widget.delete("sel.first", "sel.last")
                        widget.insert("insert", clip)
            except Exception:
                pass

        def do_select_all():
            if isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end")
            elif isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.select_range(0, "end")

        menu.add_command(label="✂️ ตัด (Cut)", command=do_cut)
        menu.add_command(label="📄 คัดลอก (Copy)", command=do_copy)
        menu.add_command(label="📋 วาง (Paste)", command=do_paste)
        menu.add_separator()
        menu.add_command(label="🔘 เลือกทั้งหมด (Select All)", command=do_select_all)

        widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def setup_universal_clipboard(self):
        """
        Enables Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+A to work across all Entry and Text widgets,
        even when typing in Thai keyboard mode or non-English layouts on Windows.
        """
        def handle_ctrl_keys(event):
            state = getattr(event, "state", 0)
            if not (state & 4):
                return

            w = event.widget
            kc = getattr(event, "keycode", 0)

            # Keycode 65 = A (Select All)
            if kc == 65:
                if isinstance(w, tk.Text):
                    w.tag_add("sel", "1.0", "end")
                    return "break"
                elif isinstance(w, (tk.Entry, ttk.Entry)):
                    w.select_range(0, "end")
                    return "break"

            # Keycode 67 = C (Copy)
            elif kc == 67:
                try:
                    text_to_copy = ""
                    if isinstance(w, tk.Text) and w.tag_ranges("sel"):
                        text_to_copy = w.get("sel.first", "sel.last")
                    elif isinstance(w, (tk.Entry, ttk.Entry)) and w.selection_present():
                        text_to_copy = w.selection_get()
                    if text_to_copy:
                        self.clipboard_clear()
                        self.clipboard_append(text_to_copy)
                    return "break"
                except Exception:
                    pass

            # Keycode 86 = V (Paste)
            elif kc == 86:
                try:
                    clip = self.clipboard_get()
                    if clip:
                        if isinstance(w, tk.Text):
                            if w.tag_ranges("sel"):
                                w.delete("sel.first", "sel.last")
                            w.insert("insert", clip)
                            return "break"
                        elif isinstance(w, (tk.Entry, ttk.Entry)):
                            if w.selection_present():
                                w.delete("sel.first", "sel.last")
                            w.insert("insert", clip)
                            return "break"
                except Exception:
                    pass

            # Keycode 88 = X (Cut)
            elif kc == 88:
                try:
                    text_cut = ""
                    if isinstance(w, tk.Text) and w.tag_ranges("sel"):
                        text_cut = w.get("sel.first", "sel.last")
                        w.delete("sel.first", "sel.last")
                    elif isinstance(w, (tk.Entry, ttk.Entry)) and w.selection_present():
                        text_cut = w.selection_get()
                        w.delete("sel.first", "sel.last")
                    if text_cut:
                        self.clipboard_clear()
                        self.clipboard_append(text_cut)
                    return "break"
                except Exception:
                    pass

        self.bind_all("<KeyPress>", handle_ctrl_keys)


if __name__ == "__main__":
    app = EasyLyricStudio()
    app.mainloop()
