"""Modern Lyric Studio launcher.

The Qt build is the primary app. If PySide6 is not installed yet, this launcher
falls back to the preserved Tkinter build so the project never becomes unusable.
"""

from __future__ import annotations

import runpy


def main() -> int:
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
