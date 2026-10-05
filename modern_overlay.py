"""
modern_overlay.py
Single-surface Qt lyric compositor.

The legacy player used one transparent top-level window per lyric card. That is
expensive on Linux compositors and is the main reason motion can feel uneven.
This implementation paints every card into one transparent Qt surface at 60 fps.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import ctypes.util
import math
import re
import sys
import time
import unicodedata

from PySide6.QtCore import Qt, QTimer, QUrl, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QWidget


ACCENT = QColor("#D7FF45")
TEXT = QColor("#F6F6F7")
MUTED = QColor("#8B8B92")
CARD = QColor(14, 14, 16, 232)
CARD_OLD = QColor(14, 14, 16, 204)
BORDER = QColor(55, 55, 61, 220)


def _split_graphemes(text: str) -> list[str]:
    clusters: list[str] = []
    current = ""
    for char in text:
        combining = unicodedata.combining(char) != 0
        if combining and current:
            current += char
        else:
            if current:
                clusters.append(current)
            current = char
    if current:
        clusters.append(current)
    return clusters


def _reveal_units(text: str) -> list[str]:
    """Prefer word-sized reveal units; use grapheme chunks for scripts without spaces."""
    if not text:
        return []

    if re.search(r"\s", text.strip()):
        parts = re.findall(r"\S+\s*", text)
        return parts or [text]

    clusters = _split_graphemes(text)
    if not clusters:
        return []
    size = 2 if len(clusters) <= 24 else 3
    return ["".join(clusters[i : i + size]) for i in range(0, len(clusters), size)]


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


@dataclass(slots=True)
class LyricCard:
    index: int
    text: str
    start: float
    end: float
    side: int
    width: float
    height: float


class ModernLyricOverlay(QWidget):
    """A polished floating lyric overlay rendered in one compositor surface."""

    finished = Signal(float)
    offset_changed = Signal(float)

    def __init__(
        self,
        lyrics: list[tuple[float, str]],
        audio_path: str,
        initial_offset: float = 0.0,
        parent=None,
    ):
        super().__init__(parent)

        self.lyrics = sorted(
            [(float(t), str(text).strip()) for t, text in lyrics if str(text).strip()],
            key=lambda item: item[0],
        )
        self.audio_path = audio_path
        self.offset = float(initial_offset)
        self.next_index = 0
        self.cards: list[LyricCard] = []
        self._closing = False
        self._paused = False
        self._end_timer_started = False

        self.setWindowTitle("Lyric Studio Overlay")
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        if sys.platform.startswith("linux"):
            # Qt's X11 equivalent of Tk overrideredirect(): keep this surface
            # unmanaged so app/workspace switching does not hide the lyrics.
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        self.player.mediaStatusChanged.connect(self._on_media_status)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

        # Reassert stacking without touching lyric animation/timing. This is
        # intentionally a separate low-frequency timer so the 60 FPS compositor
        # remains exactly as before.
        self.topmost_timer = QTimer(self)
        self.topmost_timer.setInterval(700)
        self.topmost_timer.timeout.connect(self._keep_on_top)

        self.rise_speed = 52.0
        self.card_margin = 46.0
        self.card_gap = 28.0
        self.card_max_width = 650.0
        self.card_min_width = 500.0

        self.font_family = "Noto Sans Thai"
        self.font_lyric = QFont(self.font_family, 20, QFont.Weight.DemiBold)
        self.font_meta = QFont(self.font_family, 9, QFont.Weight.DemiBold)
        self.font_hint = QFont(self.font_family, 9, QFont.Weight.Medium)

    def start(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self._apply_x11_global_overlay_hints()
        self.player.play()
        self.timer.start()
        self.topmost_timer.start()

    def _apply_x11_global_overlay_hints(self) -> None:
        """Mark the X11/XWayland overlay as sticky and above on all workspaces."""
        if not sys.platform.startswith("linux"):
            return

        app = QApplication.instance()
        if app is None or app.platformName().lower() != "xcb":
            return

        lib_name = ctypes.util.find_library("X11")
        if not lib_name:
            return

        display = None
        try:
            x11 = ctypes.cdll.LoadLibrary(lib_name)
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            x11.XInternAtom.restype = ctypes.c_ulong
            x11.XChangeProperty.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_int,
            ]
            x11.XFlush.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

            display = x11.XOpenDisplay(None)
            if not display:
                return

            window = ctypes.c_ulong(int(self.winId()))
            cardinal = x11.XInternAtom(display, b"CARDINAL", 0)
            atom_type = x11.XInternAtom(display, b"ATOM", 0)
            desktop_prop = x11.XInternAtom(display, b"_NET_WM_DESKTOP", 0)
            state_prop = x11.XInternAtom(display, b"_NET_WM_STATE", 0)
            above_atom = x11.XInternAtom(display, b"_NET_WM_STATE_ABOVE", 0)
            sticky_atom = x11.XInternAtom(display, b"_NET_WM_STATE_STICKY", 0)

            all_desktops = (ctypes.c_ulong * 1)(0xFFFFFFFF)
            x11.XChangeProperty(
                display,
                window,
                desktop_prop,
                cardinal,
                32,
                0,
                ctypes.cast(all_desktops, ctypes.POINTER(ctypes.c_ubyte)),
                1,
            )

            states = (ctypes.c_ulong * 2)(above_atom, sticky_atom)
            x11.XChangeProperty(
                display,
                window,
                state_prop,
                atom_type,
                32,
                0,
                ctypes.cast(states, ctypes.POINTER(ctypes.c_ubyte)),
                2,
            )
            x11.XFlush(display)
        except Exception:
            return
        finally:
            if display:
                try:
                    x11.XCloseDisplay(display)
                except Exception:
                    pass

    def _keep_on_top(self) -> None:
        """Keep the overlay above every app/workspace without stealing focus."""
        if self._closing or not self.isVisible():
            return
        self.raise_()
        self._apply_x11_global_overlay_hints()

    def _audio_time(self) -> float:
        return max(0.0, self.player.position() / 1000.0)

    def _calibrated_time(self) -> float:
        return self._audio_time() - self.offset

    def _line_end(self, index: int) -> float:
        if index + 1 < len(self.lyrics):
            return self.lyrics[index + 1][0]
        start, text = self.lyrics[index]
        return start + max(2.8, min(6.0, len(_split_graphemes(text)) * 0.10))

    def _card_size(self, text: str) -> tuple[float, float]:
        screen_w = max(800, self.width())
        width = min(self.card_max_width, max(self.card_min_width, screen_w * 0.40))
        fm = QFontMetrics(self.font_lyric)
        bounds = fm.boundingRect(
            0,
            0,
            int(width - 56),
            220,
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter),
            text,
        )
        height = max(112.0, min(160.0, float(bounds.height() + 62)))
        return width, height

    def _spawn(self, index: int) -> None:
        start, text = self.lyrics[index]
        end = self._line_end(index)
        width, height = self._card_size(text)
        self.cards.append(
            LyricCard(
                index=index,
                text=text,
                start=start,
                end=end,
                side=index % 2,
                width=width,
                height=height,
            )
        )

        # One surface is cheap, but keeping very old cards has no visual value.
        if len(self.cards) > 10:
            self.cards = self.cards[-10:]

    def _tick(self) -> None:
        if self._closing:
            return

        current = self._calibrated_time()

        while (
            self.next_index < len(self.lyrics)
            and self.lyrics[self.next_index][0] <= current
        ):
            self._spawn(self.next_index)
            self.next_index += 1

        # Cards move from audio time, not accumulated frame delta. A dropped frame
        # therefore cannot create permanent drift or a sudden catch-up jump.
        self.cards = [
            card
            for card in self.cards
            if self._card_y(card, current) + card.height > -80.0
        ]
        self.update()

    def _card_y(self, card: LyricCard, current: float) -> float:
        spawn_y = self.height() - card.height - 128.0
        elapsed = max(0.0, current - card.start)

        enter = _smoothstep(min(1.0, elapsed / 0.30))
        entrance_offset = (1.0 - enter) * 34.0

        return spawn_y - elapsed * self.rise_speed + entrance_offset

    def _card_x(self, card: LyricCard) -> float:
        if card.side == 0:
            return self.card_margin
        return self.width() - card.width - self.card_margin

    def _revealed_text(self, card: LyricCard, current: float) -> str:
        units = _reveal_units(card.text)
        if not units:
            return card.text

        duration = max(0.50, card.end - card.start)
        lead = min(0.16, duration * 0.08)
        reveal_duration = max(0.36, duration * 0.72)
        fraction = (current - card.start + lead) / reveal_duration
        fraction = max(0.0, min(1.0, fraction))
        fraction = math.pow(fraction, 0.80) if fraction > 0.0 else 0.0

        count = max(1, min(len(units), math.ceil(len(units) * fraction)))
        return "".join(units[:count])

    def _card_alpha(self, y: float, height: float) -> float:
        # Fade only near the top edge. Finished lyrics remain visible for a while.
        fade_top = 120.0
        bottom = y + height
        if bottom >= fade_top:
            return 1.0
        return max(0.0, min(1.0, bottom / fade_top))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        current = self._calibrated_time()
        active_index = self.next_index - 1

        for card in self.cards:
            x = self._card_x(card)
            y = self._card_y(card, current)
            rect = QRectF(x, y, card.width, card.height)
            alpha = self._card_alpha(y, card.height)
            active = card.index == active_index

            bg = QColor(CARD if active else CARD_OLD)
            bg.setAlphaF(bg.alphaF() * alpha)
            border = QColor(ACCENT if active else BORDER)
            border.setAlphaF((0.75 if active else 0.55) * alpha)

            painter.setPen(QPen(border, 1.2 if active else 1.0))
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 20.0, 20.0)

            meta = f"{int(card.start // 60):02d}:{card.start % 60:04.1f}"
            painter.setFont(self.font_meta)
            meta_color = QColor(ACCENT if active else MUTED)
            meta_color.setAlphaF(alpha)
            painter.setPen(meta_color)
            painter.drawText(
                QRectF(rect.left() + 24, rect.top() + 14, rect.width() - 48, 22),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                meta,
            )

            painter.setFont(self.font_lyric)
            text_color = QColor(TEXT if active else QColor("#C9C9CE"))
            text_color.setAlphaF(alpha)
            painter.setPen(text_color)

            shown = self._revealed_text(card, current) if active else card.text
            painter.drawText(
                QRectF(
                    rect.left() + 28,
                    rect.top() + 40,
                    rect.width() - 56,
                    rect.height() - 52,
                ),
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap,
                shown,
            )

        self._paint_hud(painter)

    def _paint_hud(self, painter: QPainter) -> None:
        width = 430.0
        height = 42.0
        rect = QRectF(self.width() - width - 24, 22, width, height)

        painter.setPen(QPen(QColor(52, 52, 58, 220), 1))
        painter.setBrush(QColor(13, 13, 15, 230))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setFont(self.font_hint)
        painter.setPen(QColor("#D7FF45"))
        painter.drawText(
            QRectF(rect.left() + 14, rect.top(), 118, height),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"OFFSET {self.offset:+.2f}s",
        )

        painter.setPen(QColor("#A0A0A7"))
        painter.drawText(
            QRectF(rect.left() + 132, rect.top(), rect.width() - 146, height),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "[ / ] timing     Space pause     ESC close",
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.finish()
            return

        if key == Qt.Key.Key_Space:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
                self._paused = True
            else:
                self.player.play()
                self._paused = False
            self.update()
            return

        if key in (Qt.Key.Key_BracketLeft, Qt.Key.Key_Left):
            self.offset = round(self.offset + 0.10, 2)
            self.offset_changed.emit(self.offset)
            self.update()
            return

        if key in (Qt.Key.Key_BracketRight, Qt.Key.Key_Right):
            self.offset = round(self.offset - 0.10, 2)
            self.offset_changed.emit(self.offset)
            self.update()
            return

        super().keyPressEvent(event)

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self._end_timer_started:
            self._end_timer_started = True
            QTimer.singleShot(2200, self.finish)

    def finish(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        self.topmost_timer.stop()
        self.player.stop()
        self.finished.emit(self.offset)
        self.close()
