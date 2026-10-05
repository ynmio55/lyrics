"""
sync_engine.py - Lyric Search, Parsing, and Alignment Engine
Supports online search via LrcLib, LRC file import/export, and automatic alignment.
"""

import difflib
import json
import os
import re
import urllib.parse
import urllib.request


def clean_text(s: str) -> str:
    """Normalize text for fuzzy comparison."""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def parse_lrc(lrc_content: str):
    """
    Parses LRC formatted string into a list of (timestamp_seconds, text).
    Example line: [01:23.45] Hello world -> (83.45, "Hello world")
    """
    results = []
    pattern = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
    for raw_line in lrc_content.splitlines():
        line = raw_line.strip()
        matches = list(pattern.finditer(line))
        if not matches:
            continue

        # Text is whatever follows the last timestamp tag
        last_match = matches[-1]
        text = line[last_match.end() :].strip()

        # Some LRCs have multiple tags per line like [00:10.00][00:20.00] Repeat
        for m in matches:
            minutes = int(m.group(1))
            seconds = float(m.group(2))
            total_seconds = minutes * 60 + seconds
            if text:
                results.append((total_seconds, text))

    results.sort(key=lambda x: x[0])
    return results


def format_lrc(lyrics_list, title="Song", artist="Unknown"):
    """Converts a list of (seconds, text) into standard LRC format string."""
    lines = [f"[ti:{title}]", f"[ar:{artist}]", "[by:LyricStudio]", ""]
    for t, text in sorted(lyrics_list, key=lambda x: x[0]):
        mins = int(t // 60)
        secs = t % 60
        lines.append(f"[{mins:02d}:{secs:05.2f}] {text}")
    return "\n".join(lines)


def clean_song_query(query: str) -> str:
    """Cleans up messy YouTube/video download filenames into clean song names."""
    if not query:
        return ""
    # Remove file extension
    s = re.sub(r"\.[a-zA-Z0-9]+$", "", query)
    # Split camelCase and snake_case
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    s = s.replace("_", " ").replace("-", " ")
    # Remove bracketed tags like [Official Video], (Audio)
    s = re.sub(r"\[.*?\]|\(.*?\)", "", s)
    # Remove junk words
    junk = r"\b(music|video|official|lyrics|lyric|audio|mv|hd|hq|4k|tv|op|ed|ost|tviop|tviiop|full|ver|version)\b"
    cleaned = re.sub(junk, "", s, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if cleaned else query.strip()


def search_online_lyrics(query: str):
    """
    Searches LrcLib for songs matching the query and returns list of songs with synced lyrics.
    """
    if not query.strip():
        return []

    # First try exact query, then cleaned query if failed
    queries_to_try = [query.strip()]
    cleaned = clean_song_query(query)
    if cleaned and cleaned.lower() != query.strip().lower():
        queries_to_try.append(cleaned)

    for q in queries_to_try:
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://lrclib.net/api/search?q={encoded}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "LyricStudioApp/1.0 (Windows NT 10.0)"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                synced_results = []
                for item in data:
                    if item.get("syncedLyrics"):
                        synced_results.append(
                            {
                                "id": item.get("id"),
                                "trackName": item.get("trackName", "Unknown Track"),
                                "artistName": item.get("artistName", "Unknown Artist"),
                                "albumName": item.get("albumName", ""),
                                "duration": item.get("duration", 0),
                                "syncedLyrics": item.get("syncedLyrics"),
                            }
                        )
                if synced_results:
                    return synced_results
        except Exception as e:
            print(f"LrcLib search error for '{q}': {e}")

    return []



def rank_lyrics_results(results, query="", audio_duration=0.0):
    """Rank synced lyric candidates using title similarity and audio duration."""
    q = clean_song_query(query)
    qn = clean_text(q)
    def score(item):
        title = clean_text(item.get("trackName", ""))
        artist = clean_text(item.get("artistName", ""))
        name_score = max(
            difflib.SequenceMatcher(None, qn, title).ratio(),
            difflib.SequenceMatcher(None, qn, (title + " " + artist).strip()).ratio(),
        ) if qn else 0.0
        duration = float(item.get("duration") or 0)
        if audio_duration > 0 and duration > 0:
            diff = abs(duration - audio_duration)
            duration_score = max(0.0, 1.0 - diff / 20.0)
        else:
            duration_score = 0.5
        return name_score * 0.72 + duration_score * 0.28
    return sorted(results or [], key=score, reverse=True)

def auto_align_lyrics(user_lines, reference_lrc_text, start_from_zero=True):
    """
    Automatically aligns user's pasted raw lyric lines with a full reference synced lyrics.
    Directly solves matching when user pastes lyrics for a clip or whole song.
    """
    ref_items = parse_lrc(reference_lrc_text)
    if not ref_items or not user_lines:
        return []

    # Clean lines
    valid_user_lines = [l.strip() for l in user_lines if l.strip()]
    if not valid_user_lines:
        return []

    # Step 1: Find best starting reference line for the first 1-2 lines
    u0 = clean_text(valid_user_lines[0])
    best_start_idx = 0
    best_start_score = 0.0

    for idx, (t, ref_txt) in enumerate(ref_items):
        score = difflib.SequenceMatcher(None, u0, clean_text(ref_txt)).ratio()
        if score > best_start_score:
            best_start_score = score
            best_start_idx = idx

    # Step 2: Forward sequential matching
    curr_idx = best_start_idx
    first_time = ref_items[best_start_idx][0]
    aligned = []

    for u in valid_user_lines:
        u_clean = clean_text(u)
        best_score = 0.0
        best_idx = curr_idx

        # Search window of next 8 lines in reference
        window_end = min(len(ref_items), curr_idx + 8)
        for i in range(curr_idx, window_end):
            score = difflib.SequenceMatcher(
                None, u_clean, clean_text(ref_items[i][1])
            ).ratio()
            if score > best_score:
                best_score = score
                best_idx = i

        if best_score >= 0.45:
            matched_time = ref_items[best_idx][0]
            curr_idx = best_idx + 1
            if start_from_zero:
                t_final = max(0.0, matched_time - first_time)
            else:
                t_final = matched_time
            aligned.append((round(t_final, 2), u))
        else:
            # Fallback estimation: add ~3.5s after previous
            prev_t = aligned[-1][0] if aligned else 0.0
            aligned.append((round(prev_t + 3.5, 2), u))

    return aligned


def get_audio_duration(filepath):
    """Returns duration in seconds for an audio file."""
    if not filepath or not os.path.exists(filepath):
        return 0.0
    try:
        import pygame

        if not pygame.mixer.get_init():
            try:
                pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=4096)
                pygame.mixer.init()
            except Exception:
                pygame.mixer.init()
        sound = pygame.mixer.Sound(filepath)
        return sound.get_length()
    except Exception:
        return 0.0


def save_lrc_file(lyrics_list, filepath, title="Song", artist="Unknown"):
    """Saves lyrics to an .lrc file."""
    content = format_lrc(lyrics_list, title=title, artist=artist)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def load_lrc_file(filepath):
    """Loads an .lrc file and returns list of (seconds, text)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return parse_lrc(content)


def detect_lead_silence(filepath, threshold_rms=300):
    """
    Detects the duration (in seconds) of silence at the beginning of an audio file.
    Helps auto-align lyrics if audio has leading video intro silence.
    """
    if not filepath or not os.path.exists(filepath):
        return 0.0
    try:
        import math
        import struct
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sound = pygame.mixer.Sound(filepath)
        raw = sound.get_raw()
        chunk_ms = 50
        chunk_size = int(44100 * 4 * (chunk_ms / 1000.0))
        total_chunks = len(raw) // chunk_size
        max_check = min(total_chunks, 400)  # check up to 20 seconds
        for i in range(max_check):
            sub = raw[i * chunk_size : (i + 1) * chunk_size]
            count = len(sub) // 2
            if count == 0:
                continue
            ints = struct.unpack(f"<{count}h", sub[: count * 2])
            rms = math.sqrt(sum(x * x for x in ints) / count)
            if rms > threshold_rms:
                return round(i * (chunk_ms / 1000.0), 2)
    except Exception:
        pass
    return 0.0

