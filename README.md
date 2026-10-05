# Lyric Studio

A local desktop lyric-sync workspace with a modern Qt interface and a single-surface 60 FPS floating lyric compositor.

## Current architecture

The project now has two UI generations:

- **Modern Qt studio** — launched by \`main.py\`
- **Legacy Tkinter studio** — preserved in \`legacy_main.py\` as a fallback

The modern overlay paints all lyric cards inside one transparent Qt window. It no longer creates a separate operating-system window for every lyric line, which greatly reduces compositor overhead and makes floating motion substantially smoother on Linux and Windows.

## Install

Create/activate your virtual environment, then:

\`\`\`bash
python -m pip install -r requirements.txt
python main.py
\`\`\`

## Modern studio

The Qt workspace includes:

- drag-and-drop local audio
- automatic LRCLIB search
- result ranking by title and recording duration
- local LRC matching
- synchronized timeline table
- persistent offset calibration
- 60 FPS transparent overlay
- floating cards rendered in one surface
- smooth audio-time-based motion (no frame-delta drift)
- progressive lyric reveal
- alternating left/right card lanes
- old-line fade near the top of the screen
- live timing correction

### Playback shortcuts

- \`[\` or Left Arrow — delay lyrics by +0.1 s
- \`]\` or Right Arrow — advance lyrics by -0.1 s
- \`Space\` — pause/resume
- \`Esc\` — close overlay and return to the studio

## Files

- \`main.py\` — modern launcher
- \`modern_app.py\` — Qt studio
- \`modern_overlay.py\` — single-surface lyric compositor
- \`sync_engine.py\` — lyric search, LRC parsing, ranking and alignment
- \`legacy_main.py\` — preserved Tkinter studio
- \`card_player.py\` — legacy floating player
- \`tap_syncer.py\` — legacy manual tap-sync tool

## Notes on word-level sync

Standard LRC usually contains timestamps per line, not per word. The modern overlay therefore reveals words/chunks smoothly within each line's time window. Exact singer-level word highlighting requires a source that provides word-level timestamps or a dedicated vocal alignment pipeline.
