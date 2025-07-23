import sys, os
sys.path.append(os.path.dirname(__file__))
import os
import sqlite3
import re
import constants
import subprocess
import json
import unicodedata
import tempfile
import shutil
import re
from collections import Counter

from constants import (
    log_database,
    log_error,
    log_image,
    log_command,
log_database,
)


conn = None

def get_database():
    global conn
    if conn is None:
        db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
        conn = sqlite3.connect(db_path)
        conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(filename, language, track, content)')
    return conn

def close_database():
    global conn
    if conn is not None:
        conn = None


audio_exts = constants.audio_extensions
video_exts = constants.video_extensions



def run_ffprobe(file_path):
    _, ffprobe_path = constants.get_ffmpeg_exe_path()
    cmd = [
        f"{ffprobe_path}",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        file_path
    ]
    result = constants.silent_run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def remove_subtitle_formatting(text: str) -> str:
    if '\\p' in text or '{\\p' in text:
        return ''

    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'{[^{}]*}', '', text)
    text = re.sub(r'[\[\(].*?[\]\)]', '', text)
    text = text.strip()

    if re.fullmatch(r'[a-zA-Z0-9\s]+', text):
        letter_ratio = len(re.findall(r'[a-zA-Z]', text)) / (len(text) + 1e-6)
        if letter_ratio < 0.3:
            return ''

    return text

def filter_subtitles(subtitles):
    timing_counts = Counter((sub[0], sub[1]) for sub in subtitles)

    seen = set()
    filtered = []
    for start, end, text in subtitles:
        if timing_counts[(start, end)] >= 4:
            filtered.append((start, end, ''))
            continue

        clean_text = remove_subtitle_formatting(text)
        key = (start, end, clean_text)
        if key in seen:
            filtered.append((start, end, ''))
        else:
            seen.add(key)
            filtered.append((start, end, clean_text))
    return filtered



def check_already_indexed(conn, media_file, track, lang=None):
    query = "SELECT 1 FROM subtitles WHERE filename=? AND track=?"
    params = [media_file, str(track)]
    if lang is not None:
        query += " AND language=?"
        params.append(lang)
    query += " LIMIT 1"

    cursor = conn.execute(query, params)
    return cursor.fetchone() is not None

def update_database():
    log_database(f"update database called")
    db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
    conn = sqlite3.connect(db_path)

    conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(filename, language, track, content)')
    conn.execute('CREATE TABLE IF NOT EXISTS media_tracks (filename TEXT, track INTEGER, language TEXT, type TEXT, PRIMARY KEY(filename, track, type))')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS media_audio_start_times (
        filename TEXT,
        audio_track INTEGER,
        delay_ms INTEGER,
        PRIMARY KEY (filename, audio_track)
    )
    ''')

    folder = os.path.join(constants.addon_dir, constants.addon_source_folder)
    audio_exts = constants.audio_extensions
    video_exts = constants.video_extensions

    current_files = set(os.listdir(folder))
    current_media = {f for f in current_files if os.path.splitext(f)[1].lower() in audio_exts + video_exts}

    cursor = conn.execute('SELECT filename, language, track FROM subtitles')
    indexed_subs = {f"{r[0]}`track_{r[2]}`{r[1]}.srt" for r in cursor}
    # log_database(f"current indexed subs: {indexed_subs}")

    # Remove subtitles with no media file or missing subtitle file
    for f in sorted(indexed_subs):
        vid, tpart, lang_s = f.split('`')
        track = tpart[len('track_'):]
        lang = lang_s[:-4]

        media_exists = vid in current_media

        if not media_exists:
            conn.execute('DELETE FROM subtitles WHERE filename=? AND language=? AND track=?',
                         (vid, lang, track))
            log_database(f"Removed subtitle: file={vid}, track={track}, lang={lang}")

    # add user placed subtitles
    current_media = {
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in audio_exts + video_exts
    }

    media_basenames = {os.path.splitext(f)[0] for f in current_media}

    subtitles_in_folder = {
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() == ".srt"
    }

    cursor = conn.execute(
        "SELECT DISTINCT filename FROM subtitles WHERE track = '-1' AND language = 'und'"
    )


    indexed_subtitle_files = {row[0] for row in cursor}
    indexed_subtitle_basenames = {os.path.splitext(f)[0] for f in indexed_subtitle_files}

    log_database(f"current subtitles in folder: {subtitles_in_folder}")
    for subtitle_file in subtitles_in_folder:
        base_name = os.path.splitext(subtitle_file)[0]
        if base_name in media_basenames and base_name not in indexed_subtitle_basenames:
            log_database(f"adding subtitle to database: {base_name}")
            subtitle_path = os.path.join(folder, subtitle_file)
            for media_file in (m for m in current_media if os.path.splitext(m)[0] == base_name):
                # No need to check DB again here; just process
                log_database(f"Processing new subtitle {subtitle_path} for media file {media_file}")
                # Insert your subtitle processing logic here

                try:
                    with open(subtitle_path, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                    blocks = text.split("\n\n")
                    parsed = []
                    for blk in blocks:
                        lines = blk.strip().split("\n")
                        if len(lines) < 3:
                            continue
                        idx = lines[0]
                        m = re.match(
                            r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})',
                            lines[1]
                        )
                        if not m:
                            continue
                        start, end = m.groups()
                        content = ' '.join(lines[2:]).strip()
                        parsed.append([idx, start, end, content])

                    conn.execute(
                        'INSERT INTO subtitles (filename, language, track, content) VALUES (?, ?, ?, ?)',
                        (media_file, "und", "-1", json.dumps(parsed, ensure_ascii=False))
                    )
                    log_database(f"Added subtitle content for {subtitle_path} linked to media {media_file}")
                except Exception as e:
                    log_database(f"Failed to add subtitle content from {subtitle_path}: {e}")


    # extract subtitles from all source files
    extract_all_subtitle_tracks_and_update_db(conn)

    # remove missing media
    cursor = conn.execute('SELECT DISTINCT filename FROM media_tracks')
    indexed_media = {r[0] for r in cursor}

    for mf in sorted(indexed_media - current_media):
        conn.execute('DELETE FROM media_tracks WHERE filename=?', (mf,))
        conn.execute('DELETE FROM media_audio_start_times WHERE filename=?', (mf,))
        log_database(f"Removed media entries for: {mf}")


    conn.commit()
    conn.execute("VACUUM;")
    return conn


def extract_all_subtitle_tracks_and_update_db(conn):
    folder = os.path.join(constants.addon_dir, constants.addon_source_folder)
    audio_exts = constants.audio_extensions
    video_exts = constants.video_extensions
    media_exts = audio_exts + video_exts
    exe_path, ffprobe_path = constants.get_ffmpeg_exe_path()

    def run_ffprobe(path):
        cmd = [
            ffprobe_path, "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name:stream_tags=language",
            "-select_streams", "s",
            "-of", "json", path
        ]
        result = constants.silent_run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_error(f"ffprobe failed on {path}: {result.stderr.strip()}")
            return None
        try:
            return json.loads(result.stdout)
        except Exception as e:
            log_error(f"ffprobe JSON parse error for {path}: {e}")
            return None



    def parse_srt_blocks(srt_text):
        blocks = []
        parts = srt_text.strip().split('\n\n')
        for part in parts:
            lines = part.splitlines()
            if len(lines) >= 3:
                index = lines[0]
                timing = lines[1]
                content = '\n'.join(lines[2:])
                start_end = timing.split(' --> ')
                if len(start_end) == 2:
                    start, end = start_end
                    blocks.append({
                        'index': index,
                        'start': start.strip(),
                        'end': end.strip(),
                        'text': content.strip()
                    })
        return blocks

    def rebuild_srt_blocks(blocks):
        srt_lines = []
        for i, block in enumerate(blocks, 1):
            srt_lines.append(str(i))
            srt_lines.append(f"{block['start']} --> {block['end']}")
            srt_lines.append(block['text'])
            srt_lines.append('')
        return '\n'.join(srt_lines)

    def filter_duplicate_timings(blocks):
        timing_counts = Counter((b['start'], b['end']) for b in blocks)
        filtered = []
        for b in blocks:
            if timing_counts[(b['start'], b['end'])] >= 4:
                continue
            cleaned_text = remove_subtitle_formatting(b['text'])
            if cleaned_text:
                b['text'] = cleaned_text
                filtered.append(b)
        return filtered

    def extract_all_subs_single(media_path, subtitle_streams):
        temp_dir = tempfile.mkdtemp()
        try:
            cmd = [exe_path, "-y", "-i", media_path]
            for i, _ in enumerate(subtitle_streams):
                cmd += ["-map", f"0:s:{i}", "-c:s", "srt", os.path.join(temp_dir, f"track_{i}.srt")]
            result = constants.silent_run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                log_error(f"ffmpeg failed on {media_path}: {result.stderr.strip()}")
                return None

            filtered_texts = []
            for i in range(len(subtitle_streams)):
                p = os.path.join(temp_dir, f"track_{i}.srt")
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        srt_content = f.read()
                    blocks = parse_srt_blocks(srt_content)
                    blocks = filter_duplicate_timings(blocks)
                    filtered_texts.append(rebuild_srt_blocks(blocks))
                else:
                    filtered_texts.append("")
            return filtered_texts
        finally:
            shutil.rmtree(temp_dir)
    current_media = {
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in media_exts
    }
    cursor = conn.execute('SELECT DISTINCT filename FROM subtitles')
    indexed = {r[0] for r in cursor}
    media_to_process = sorted(n for n in current_media if n not in indexed)

    for media_file in media_to_process:
        log_database(f"processing file: {media_file}")
        path = os.path.join(folder, media_file)
        info = run_ffprobe(path)
        if not info:
            continue
        # only add text based subtitles, no pgs or sup
        streams = [
            s for s in info.get("streams", [])
            if s.get("codec_type") == "subtitle" and s.get("codec_name") in ("subrip", "ass", "srt", "ssa", "mov_text",
                                                                             "webvtt")
        ]

        if not streams:
            log_database(f"No subtitle streams in {media_file}, skipping")
            continue
        log_database(f"Found {len(streams)} subtitle streams in {media_file}")
        all_texts = extract_all_subs_single(path, streams)
        if all_texts is None:
            continue
        for idx, (stream, text) in enumerate(zip(streams, all_texts), 1):
            track = idx
            lang = stream.get("tags", {}).get("language", "und")
            codec = stream.get("codec_name")
            log_database(f"Extracting track={track}, lang={lang}, codec={codec}")
            if codec not in ("subrip", "ass", "srt", "ssa"):
                log_database(f"skip unsupported codec {codec}")
                continue
            if check_already_indexed(conn, media_file, track, lang):
                log_database(f"skip already indexed track={track}, lang={lang}")
                continue
            blocks = text.strip().split("\n\n")
            parsed = []
            for blk in blocks:
                lines = blk.split("\n")
                if len(lines) < 3:
                    continue
                m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", lines[1])
                if not m:
                    continue
                start, end = m.groups()
                content = " ".join(lines[2:]).strip()
                content = remove_subtitle_formatting(content)
                if not content:
                    continue
                parsed.append([lines[0], start, end, content])
            conn.executemany(
                'INSERT INTO subtitles (filename, language, track, content) VALUES (?,?,?,?)',
                [(media_file, lang, str(track), json.dumps(parsed, ensure_ascii=False))]
            )
            log_database(f"Inserted {len(parsed)} blocks for {media_file}, track={track}, lang={lang}")
            conn.commit()
    conn.commit()
    return conn

def print_top_20_largest_subtitle_entries():
    conn = get_database()
    cursor = conn.cursor()

    query = """
    SELECT filename, language, track, LENGTH(content) as size
    FROM subtitles
    ORDER BY size DESC
    LIMIT 20
    """
    rows = cursor.execute(query).fetchall()

    if rows:
        folder = os.path.join(constants.addon_dir, constants.addon_source_folder)
        for i, row in enumerate(rows, 1):
            filename, language, track, size = row
            file_path = os.path.join(folder, filename)
            try:
                file_size_bytes = os.path.getsize(file_path)
                file_size_kb = round(file_size_bytes / 1024, 1)
            except FileNotFoundError:
                file_size_kb = -1
            log_database(f"{i}. {filename} | Lang: {language} | Track: {track} | Subtitle: {size} chars | File: {file_size_kb} KB")
    else:
        log_database("No entries found.")

#print_top_20_largest_subtitle_entries()



def print_largest_subtitle_entry_content():
    conn = get_database()
    cursor = conn.cursor()

    query = """
    SELECT filename, language, track, content
    FROM subtitles
    ORDER BY LENGTH(content) DESC
    LIMIT 1
    """
    row = cursor.execute(query).fetchone()

    if row:
        filename, language, track, content = row
        log_database(f"Largest entry: {filename}, Lang: {language}, Track: {track}")
        parsed = json.loads(content)
        for i, line in enumerate(parsed[:500]):  # Limit output for preview
            idx, start, end, text = line
            log_database(f"{idx}: {start} --> {end} | {text}")
        if len(parsed) > 20:
            log_database(f"... (truncated, total lines: {len(parsed)})")
    else:
        log_database("No entries found.")

# print_largest_subtitle_entry_content()


def print_all_subtitle_contents():
    conn = get_database()
    cursor = conn.execute('SELECT filename, track, language, content FROM subtitles')
    for filename, track, language, content in cursor:
        log_database(f"Subtitle: filename={filename}, track={track}, language={language}")
        try:
            log_database(f"Raw content: {content}")
            parsed = json.loads(content)
            log_database(f"parsed: {parsed}")
            for i, line in enumerate(parsed[:20]):  # limit output to first 20 lines per subtitle
                if len(line) >= 4:
                    idx, start, end, text = line[:4]
                    log_database(f"  {idx}: {start} --> {end} | {text}")
                else:
                    log_database(f"  Incomplete line {i}: {line}")
            if len(parsed) > 20:
                log_database(f"  ... (truncated, total lines: {len(parsed)})")
        except Exception as e:
            log_database(f"  [error] Failed to parse content: {e}")

#print_all_subtitle_contents()
