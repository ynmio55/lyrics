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
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget


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
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if sys.platform.startswith("linux"):
            # The pre-Qt player used overrideredirect() lyric windows. The key
            # behavior was that the desktop behind the lyrics stayed usable.
            # Keep the modern full-screen compositor unmanaged but completely
            # transparent to mouse/keyboard input.
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        self.player.mediaStatusChanged.connect(self._on_media_status)

        # QMediaPlayer.position() can advance in coarse backend steps on Linux.
        # The old player moved cards from a continuous frame clock, which is why
        # its motion felt connected. Keep audio sync, but interpolate smoothly
        # between media-position updates with a monotonic high-resolution clock.
        self._clock_media_s = 0.0
        self._clock_perf = time.perf_counter()
        self.player.positionChanged.connect(self._sync_media_clock)
        self.player.playbackStateChanged.connect(self._sync_playback_clock_state)

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

        # Separate tiny interactive window. The large lyric compositor itself
        # is click-through, exactly so Chrome/VS Code/desktop remain clickable.
        self.controls = None
        self.offset_label = None
        self.pause_button = None

    def start(self) -> None:
        self.show()
        self.raise_()
        self._apply_x11_global_overlay_hints()
        if self.controls is not None:
            try:
                self.controls.raise_()
            except Exception:
                pass
        self._show_controls()
        self.player.play()
        self.timer.start()
        self.topmost_timer.start()

    def _show_controls(self) -> None:
        """Small interactive bar; everything else on screen remains clickable."""
        if self.controls is not None:
            try:
                self.controls.show()
                self.controls.raise_()
                return
            except Exception:
                self.controls = None

        bar = QWidget()
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        if sys.platform.startswith("linux"):
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        bar.setWindowFlags(flags)
        bar.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        bar.setObjectName("OverlayControls")
        bar.setStyleSheet(
            """
            QWidget#OverlayControls {
                background: #101012;
                border: 1px solid #303036;
                border-radius: 12px;
            }
            QLabel {
                color: #D7FF45;
                background: transparent;
                border: none;
                font-size: 11px;
                font-weight: 700;
                padding: 0 6px;
            }
            QPushButton {
                color: #DADADF;
                background: #1B1B1F;
                border: 1px solid #303036;
                border-radius: 8px;
                padding: 6px 9px;
                font-size: 10px;
                font-weight: 650;
            }
            QPushButton:hover {
                background: #25252A;
                border-color: #414148;
            }
            QPushButton#Close {
                color: #E9E9EC;
                background: #26262B;
            }
            """
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        self.offset_label = QLabel(f"OFFSET {self.offset:+.2f}s")
        layout.addWidget(self.offset_label)

        delay = QPushButton("+0.1")
        delay.setToolTip("Delay lyrics")
        delay.clicked.connect(lambda: self.adjust_offset(+0.10))
        layout.addWidget(delay)

        advance = QPushButton("-0.1")
        advance.setToolTip("Advance lyrics")
        advance.clicked.connect(lambda: self.adjust_offset(-0.10))
        layout.addWidget(advance)

        self.pause_button = QPushButton("PAUSE")
        self.pause_button.clicked.connect(self.toggle_pause)
        layout.addWidget(self.pause_button)

        close = QPushButton("CLOSE")
        close.setObjectName("Close")
        close.clicked.connect(self.finish)
        layout.addWidget(close)

        bar.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            bar.move(geo.right() - bar.width() - 22, geo.top() + 20)

        self.controls = bar
        bar.show()
        bar.raise_()

    def adjust_offset(self, delta: float) -> None:
        self.offset = round(self.offset + float(delta), 2)
        if self.offset_label is not None:
            self.offset_label.setText(f"OFFSET {self.offset:+.2f}s")
        self.offset_changed.emit(self.offset)
        self.update()

    def toggle_pause(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self._paused = True
            if self.pause_button is not None:
                self.pause_button.setText("RESUME")
        else:
            self.player.play()
            self._paused = False
            if self.pause_button is not None:
                self.pause_button.setText("PAUSE")

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

    def _sync_media_clock(self, position_ms: int) -> None:
        """Re-anchor the smooth clock to the real media backend."""
        self._clock_media_s = max(0.0, float(position_ms) / 1000.0)
        self._clock_perf = time.perf_counter()

    def _sync_playback_clock_state(self, state) -> None:
        # Re-anchor on every play/pause transition so interpolation never jumps.
        self._clock_media_s = max(0.0, self.player.position() / 1000.0)
        self._clock_perf = time.perf_counter()

    def _audio_time(self) -> float:
        """Continuous playback time, corrected by QMediaPlayer but rendered smoothly."""
        base = self._clock_media_s
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            base += max(0.0, time.perf_counter() - self._clock_perf)

        # Guard against a backend discontinuity/seek without adding visible jitter.
        raw = max(0.0, self.player.position() / 1000.0)
        if abs(base - raw) > 0.22:
            self._clock_media_s = raw
            self._clock_perf = time.perf_counter()
            return raw
        return max(0.0, base)

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

        # Cards use the interpolated audio clock: audio-locked like the new engine,
        # but visually continuous like the original floating-card player.
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

    def _reveal_fraction(self, card: LyricCard, current: float) -> float:
        """Continuous reveal progress for the active lyric.

        The first implementation revealed one grapheme every ~35 ms and felt
        naturally continuous, but a fixed speed could finish after the singer.
        This keeps that visual character while adapting to each LRC line:
        start slightly early, reveal continuously, and finish before the line ends.
        """
        duration = max(0.50, card.end - card.start)
        lead = min(0.14, duration * 0.08)
        reveal_duration = max(0.34, duration * 0.72)
        fraction = (current - card.start + lead) / reveal_duration
        fraction = max(0.0, min(1.0, fraction))
        # Very light ease-out. No discrete word/chunk steps.
        if 0.0 < fraction < 1.0:
            fraction = 1.0 - math.pow(1.0 - fraction, 1.12)
        return fraction

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
            text_rect = QRectF(
                rect.left() + 28,
                rect.top() + 40,
                rect.width() - 56,
                rect.height() - 52,
            )
            text_flags = (
                Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap
            )

            if active:
                # Render the complete shaped string once, then reveal it with a
                # continuously moving clip edge. Unlike word-by-word replacement,
                # this never jumps and never breaks Thai combining glyphs.
                reveal = self._reveal_fraction(card, current)
                actual = painter.boundingRect(text_rect, int(text_flags), card.text)
                clip_width = max(0.0, actual.width() * reveal)

                painter.save()
                painter.setClipRect(
                    QRectF(
                        actual.left() - 2.0,
                        actual.top() - 3.0,
                        clip_width + 4.0,
                        actual.height() + 6.0,
                    )
                )
                text_color = QColor(TEXT)
                text_color.setAlphaF(alpha)
                painter.setPen(text_color)
                painter.drawText(text_rect, text_flags, card.text)
                painter.restore()
            else:
                text_color = QColor("#C9C9CE")
                text_color.setAlphaF(alpha)
                painter.setPen(text_color)
                painter.drawText(text_rect, text_flags, card.text)

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
            self.toggle_pause()
            self.update()
            return

        if key in (Qt.Key.Key_BracketLeft, Qt.Key.Key_Left):
            self.adjust_offset(+0.10)
            return

        if key in (Qt.Key.Key_BracketRight, Qt.Key.Key_Right):
            self.adjust_offset(-0.10)
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
        if self.controls is not None:
            try:
                self.controls.close()
            except Exception:
                pass
            self.controls = None
        self.finished.emit(self.offset)
        self.close()
