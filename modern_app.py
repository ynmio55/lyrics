"""
modern_app.py
Commercial-style Qt desktop studio for Lyric Studio.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from mutagen import File as MutagenFile
from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import sync_engine
from modern_overlay import ModernLyricOverlay


APP_STYLE = """
QWidget {
    background: #0B0B0C;
    color: #EEEEF0;
    font-family: "Noto Sans Thai", "Inter", "Segoe UI", sans-serif;
    font-size: 14px;
}
QMainWindow {
    background: #0B0B0C;
}
QFrame#Panel {
    background: #141416;
    border: 1px solid #29292E;
    border-radius: 18px;
}
QFrame#SubtlePanel {
    background: #101012;
    border: 1px solid #242428;
    border-radius: 14px;
}
QLabel#Brand {
    color: #F4F4F5;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#Overline {
    color: #77777F;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
}
QLabel#TrackTitle {
    color: #F7F7F8;
    font-size: 19px;
    font-weight: 650;
}
QLabel#Status {
    color: #8D8D94;
    font-size: 12px;
}
QLabel#AccentLabel {
    color: #D7FF45;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
}
QPushButton {
    background: #202024;
    border: 1px solid #323238;
    border-radius: 11px;
    padding: 9px 14px;
    color: #E9E9EC;
    font-weight: 600;
}
QPushButton:hover {
    background: #27272C;
    border-color: #3C3C43;
}
QPushButton:pressed {
    background: #18181B;
}
QPushButton#Primary {
    background: #D7FF45;
    color: #0B0B0C;
    border: 1px solid #D7FF45;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 750;
    padding: 11px 22px;
}
QPushButton#Primary:hover {
    background: #E2FF70;
    border-color: #E2FF70;
}
QPushButton#Quiet {
    background: transparent;
    border-color: #2A2A2F;
    color: #A9A9B0;
}
QPushButton#Chip {
    background: #171719;
    border: 1px solid #2D2D32;
    border-radius: 9px;
    padding: 7px 10px;
    color: #BDBDC3;
    min-width: 52px;
}
QPushButton#Chip:hover {
    color: #FFFFFF;
    border-color: #45454C;
}
QLineEdit {
    background: #101012;
    border: 1px solid #303036;
    border-radius: 11px;
    padding: 10px 12px;
    selection-background-color: #D7FF45;
    selection-color: #0B0B0C;
    color: #F2F2F4;
}
QLineEdit:focus {
    border-color: #595961;
}
QTableWidget {
    background: #101012;
    alternate-background-color: #121214;
    border: 1px solid #28282D;
    border-radius: 14px;
    gridline-color: transparent;
    selection-background-color: #252529;
    selection-color: #FFFFFF;
    outline: none;
}
QTableWidget::item {
    padding: 8px 10px;
    border-bottom: 1px solid #1C1C20;
}
QHeaderView::section {
    background: #101012;
    color: #77777F;
    border: none;
    border-bottom: 1px solid #29292E;
    padding: 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #34343A;
    border-radius: 4px;
    min-height: 36px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
"""


def _duration_seconds(path: str) -> float:
    try:
        media = MutagenFile(path)
        if media is not None and getattr(media, "info", None) is not None:
            return float(media.info.length)
    except Exception:
        pass
    return 0.0


class LyricsSearchThread(QThread):
    completed = Signal(object, str)
    failed = Signal(str)

    def __init__(self, query: str, duration: float, parent=None):
        super().__init__(parent)
        self.query = query
        self.duration = duration

    def run(self) -> None:
        try:
            results = sync_engine.search_online_lyrics(self.query)
            ranked = sync_engine.rank_lyrics_results(
                results,
                self.query,
                self.duration,
            )
            if not ranked:
                self.completed.emit([], "")
                return

            best = ranked[0]
            parsed = sync_engine.parse_lrc(best.get("syncedLyrics", ""))
            parsed = [(t, txt.strip()) for t, txt in parsed if txt and txt.strip()]
            source = f'{best.get("trackName", self.query)} — {best.get("artistName", "")}'.strip(" —")
            self.completed.emit(parsed, source)
        except Exception as exc:
            self.failed.emit(str(exc))


class ModernStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lyric Studio")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self.setAcceptDrops(True)

        self.audio_path: str | None = None
        self.duration = 0.0
        self.synced_lyrics: list[tuple[float, str]] = []
        self.offset = 0.0
        self.search_thread: LyricsSearchThread | None = None
        self.overlay: ModernLyricOverlay | None = None

        self.settings = QSettings("Mio", "LyricStudio")
        self.offset = float(self.settings.value("offset", 0.0))

        self._build_ui()
        self._bind_shortcuts()
        self._set_offset(self.offset)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(2)
        brand = QLabel("LYRIC STUDIO")
        brand.setObjectName("Brand")
        overline = QLabel("DESKTOP SYNC WORKSPACE")
        overline.setObjectName("Overline")
        brand_box.addWidget(brand)
        brand_box.addWidget(overline)

        header.addLayout(brand_box)
        header.addStretch(1)

        local_badge = QLabel("LOCAL AUDIO")
        local_badge.setObjectName("Overline")
        render_badge = QLabel("60 FPS OVERLAY")
        render_badge.setObjectName("Overline")
        header.addWidget(local_badge)
        header.addSpacing(18)
        header.addWidget(render_badge)

        outer.addLayout(header)

        # Track panel
        track_panel = QFrame()
        track_panel.setObjectName("Panel")
        track_layout = QHBoxLayout(track_panel)
        track_layout.setContentsMargins(18, 16, 18, 16)
        track_layout.setSpacing(16)

        choose = QPushButton("Choose song")
        choose.setObjectName("Primary")
        choose.clicked.connect(self.choose_audio)
        track_layout.addWidget(choose, 0)

        track_info = QVBoxLayout()
        track_info.setSpacing(4)
        self.track_title = QLabel("Drop a song here or choose a local audio file")
        self.track_title.setObjectName("TrackTitle")
        self.track_status = QLabel("MP3 · FLAC · WAV · OGG · M4A")
        self.track_status.setObjectName("Status")
        track_info.addWidget(self.track_title)
        track_info.addWidget(self.track_status)
        track_layout.addLayout(track_info, 1)

        search_wrap = QVBoxLayout()
        search_wrap.setSpacing(6)
        search_label = QLabel("LYRIC SEARCH")
        search_label.setObjectName("Overline")
        search_wrap.addWidget(search_label)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Song title / artist")
        self.search_input.returnPressed.connect(self.search_lyrics)
        search_row.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.search_lyrics)
        search_row.addWidget(self.search_btn)
        search_wrap.addLayout(search_row)

        track_layout.addLayout(search_wrap, 0)
        outer.addWidget(track_panel)

        # Timeline header
        timeline_header = QHBoxLayout()
        timeline_title = QLabel("TIMELINE")
        timeline_title.setObjectName("AccentLabel")
        timeline_header.addWidget(timeline_title)

        self.lyric_count = QLabel("0 lines")
        self.lyric_count.setObjectName("Status")
        timeline_header.addWidget(self.lyric_count)
        timeline_header.addStretch(1)

        load_lrc = QPushButton("Load .lrc")
        load_lrc.setObjectName("Quiet")
        load_lrc.clicked.connect(self.load_lrc)
        timeline_header.addWidget(load_lrc)

        outer.addLayout(timeline_header)

        # Timeline table
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["TIME", "LYRIC"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(0, 126)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(self.table, 1)

        # Bottom control panel
        bottom = QFrame()
        bottom.setObjectName("SubtlePanel")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(14, 12, 14, 12)
        bottom_layout.setSpacing(9)

        offset_label = QLabel("OFFSET")
        offset_label.setObjectName("Overline")
        bottom_layout.addWidget(offset_label)

        self.offset_value = QLabel("+0.00s")
        self.offset_value.setObjectName("AccentLabel")
        self.offset_value.setMinimumWidth(62)
        bottom_layout.addWidget(self.offset_value)

        for value, label in [
            (-0.50, "-0.5"),
            (-0.10, "-0.1"),
            (0.0, "Reset"),
            (0.10, "+0.1"),
            (0.50, "+0.5"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("Chip")
            if value == 0:
                btn.clicked.connect(lambda checked=False: self._set_offset(0.0))
            else:
                btn.clicked.connect(
                    lambda checked=False, delta=value: self._set_offset(self.offset + delta)
                )
            bottom_layout.addWidget(btn)

        bottom_layout.addSpacing(12)
        view_label = QLabel("VIEW  ·  FLOATING")
        view_label.setObjectName("Overline")
        bottom_layout.addWidget(view_label)
        bottom_layout.addStretch(1)

        self.play_btn = QPushButton("PLAY")
        self.play_btn.setObjectName("Primary")
        self.play_btn.clicked.connect(self.play)
        bottom_layout.addWidget(self.play_btn)

        outer.addWidget(bottom)

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.choose_audio)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.load_lrc)
        QShortcut(QKeySequence("Return"), self, activated=self.play)

    def choose_audio(self) -> None:
        start = self.settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio",
            str(start),
            "Audio (*.mp3 *.flac *.wav *.ogg *.m4a);;All files (*)",
        )
        if path:
            self.set_audio(path)

    def set_audio(self, path: str) -> None:
        path = os.path.abspath(path)
        self.audio_path = path
        self.duration = _duration_seconds(path)
        self.settings.setValue("last_dir", str(Path(path).parent))

        clean = sync_engine.clean_song_query(Path(path).name)
        self.track_title.setText(clean or Path(path).stem)

        if self.duration > 0:
            mins = int(self.duration // 60)
            secs = int(self.duration % 60)
            self.track_status.setText(f"{Path(path).name}   ·   {mins}:{secs:02d}")
        else:
            self.track_status.setText(Path(path).name)

        self.search_input.setText(clean)

        if self._load_best_local_lrc(clean):
            return
        self.search_lyrics()

    def _load_best_local_lrc(self, clean_name: str) -> bool:
        folder = Path(__file__).resolve().parent / "lyrics"
        if not folder.exists():
            return False

        best_path = None
        best_score = 0.0
        for candidate in folder.glob("*.lrc"):
            score = sync_engine.name_similarity(clean_name, candidate.stem)
            if score > best_score:
                best_score = score
                best_path = candidate

        if best_path is not None and best_score >= 0.76:
            try:
                items = sync_engine.load_lrc_file(str(best_path))
                self._set_lyrics(items)
                self.track_status.setText(
                    f"{Path(self.audio_path).name}   ·   local lyrics: {best_path.name}"
                )
                return True
            except Exception:
                return False
        return False

    def search_lyrics(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return

        if self.search_thread is not None and self.search_thread.isRunning():
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching…")
        self.track_status.setText("Finding the best synchronized lyric match…")

        thread = LyricsSearchThread(query, self.duration, self)
        self.search_thread = thread
        thread.completed.connect(self._search_done)
        thread.failed.connect(self._search_failed)
        thread.finished.connect(self._search_thread_finished)
        thread.start()

    def _search_done(self, items, source: str) -> None:
        if items:
            self._set_lyrics(items)
            self.track_status.setText(
                f"Synced lyrics ready   ·   {source}   ·   {len(items)} lines"
            )
        else:
            self.track_status.setText(
                "No synchronized lyrics found. Load an .lrc file for this recording."
            )

    def _search_failed(self, message: str) -> None:
        self.track_status.setText(f"Lyric search failed: {message}")

    def _search_thread_finished(self) -> None:
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")

    def load_lrc(self) -> None:
        start = self.settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load synchronized lyrics",
            str(start),
            "LRC lyrics (*.lrc);;All files (*)",
        )
        if not path:
            return
        try:
            items = sync_engine.load_lrc_file(path)
            self._set_lyrics(items)
            self.track_status.setText(f"Loaded lyrics   ·   {Path(path).name}")
        except Exception as exc:
            QMessageBox.warning(self, "Lyric Studio", f"Could not load LRC:\n{exc}")

    def _set_lyrics(self, items) -> None:
        self.synced_lyrics = sorted(
            [(float(t), str(text).strip()) for t, text in items if str(text).strip()],
            key=lambda item: item[0],
        )

        self.table.setRowCount(len(self.synced_lyrics))
        for row, (stamp, text) in enumerate(self.synced_lyrics):
            mins = int(stamp // 60)
            secs = stamp % 60

            time_item = QTableWidgetItem(f"{mins:02d}:{secs:04.1f}")
            time_item.setForeground(QColor("#85858D"))
            lyric_item = QTableWidgetItem(text)

            self.table.setItem(row, 0, time_item)
            self.table.setItem(row, 1, lyric_item)
            self.table.setRowHeight(row, 38)

        self.lyric_count.setText(f"{len(self.synced_lyrics)} lines")

    def _set_offset(self, value: float) -> None:
        self.offset = round(float(value), 2)
        self.offset_value.setText(f"{self.offset:+.2f}s")
        self.settings.setValue("offset", self.offset)

    def play(self) -> None:
        if not self.audio_path or not os.path.exists(self.audio_path):
            QMessageBox.information(self, "Lyric Studio", "Choose a song first.")
            return
        if not self.synced_lyrics:
            QMessageBox.information(
                self,
                "Lyric Studio",
                "No synchronized lyrics are loaded for this song.",
            )
            return

        self.overlay = ModernLyricOverlay(
            self.synced_lyrics,
            self.audio_path,
            initial_offset=self.offset,
        )
        self.overlay.offset_changed.connect(self._set_offset)
        self.overlay.finished.connect(self._overlay_finished)
        self.hide()
        self.overlay.start()

    def _overlay_finished(self, final_offset: float) -> None:
        self._set_offset(final_offset)
        self.show()
        self.raise_()
        self.activateWindow()
        self.overlay = None

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            suffix = Path(urls[0].toLocalFile()).suffix.lower()
            if suffix in {".mp3", ".flac", ".wav", ".ogg", ".m4a"}:
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.set_audio(urls[0].toLocalFile())
            event.acceptProposedAction()


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Lyric Studio")
    app.setOrganizationName("Mio")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    font = QFont("Noto Sans Thai", 10)
    app.setFont(font)

    window = ModernStudio()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
