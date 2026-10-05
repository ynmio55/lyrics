# Lyric Studio

Desktop lyric synchronization and overlay player for Windows and Linux.

## What it does

- Opens local audio files: MP3, WAV, OGG, FLAC and M4A where supported by the local audio stack.
- Searches LRCLIB for synchronized lyrics.
- Ranks lyric results using both song-name similarity and recording duration to avoid selecting the wrong live/remaster/edit.
- Loads local `.lrc` files.
- Includes Tap Sync for songs that have no reliable synchronized lyrics.
- Shows a persistent Focus Player with the current line, next line and line progress.
- Supports live timing correction while the song is playing.

## Run

```bash
python -m pip install -r requirements.txt
python main.py
```

On Fedora, install Tk if it is not already present:

```bash
sudo dnf install python3-tkinter
```

## Timing controls

During playback:

- `[` or Left Arrow: delay lyrics by +0.1 s
- `]` or Right Arrow: advance lyrics by -0.1 s
- `Space`: pause/resume
- `Tab`: change overlay style
- `Esc`: close the overlay

The default **Focus Player** uses one persistent lyric surface, so lines do not stack on top of each other.

## Sync behavior

Lyric Studio does not automatically add detected intro silence to online synchronized lyrics. Most synchronized LRC files already contain the intro in their timestamps, and applying it a second time makes lyrics lag behind the vocal.

For manual timing, **Tap Sync** records timestamps from the audio playback clock itself rather than wall-clock time.

## Files

- `main.py` — main studio window
- `card_player.py` — lyric overlay and playback
- `sync_engine.py` — LRCLIB search, parsing, ranking and alignment
- `tap_syncer.py` — manual Space-key synchronization
- `lyrics/` — optional local LRC files
