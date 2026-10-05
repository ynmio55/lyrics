"""Modern Lyric Studio launcher.

The Qt build is the primary app. If PySide6 is not installed yet, this launcher
falls back to the preserved Tkinter build so the project never becomes unusable.
"""

from __future__ import annotations

import os
import runpy
import sys


def _prepare_linux_overlay_backend() -> None:
    """Use XWayland/X11 for the global overlay behavior on Linux.

    GNOME/Wayland deliberately keeps ordinary application windows scoped to a
    workspace. The original Tk overlay behaved like an unmanaged X11 overlay,
    so the modern player uses Qt's xcb backend by default on Linux.
    Set LYRIC_STUDIO_NATIVE_WAYLAND=1 to opt out.
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("LYRIC_STUDIO_NATIVE_WAYLAND") == "1":
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


def main() -> int:
    _prepare_linux_overlay_backend()
    try:
        from modern_app import run
    except ImportError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print(
                "Modern UI dependency is not installed yet. "
                "Run: python -m pip install -r requirements.txt"
            )
            print("Starting legacy UI for now.\n")
            runpy.run_module("legacy_main", run_name="__main__")
            return 0
        raise

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
