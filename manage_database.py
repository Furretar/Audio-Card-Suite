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

from constants import (
    log_filename,
    log_error,
    log_image,
    log_command,
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def remove_subtitle_formatting(text: str) -> str:
    # Remove HTML tags like <font>, <b>, <i>, etc.
    text = re.sub(r'<[^>]+>', '', text)
    # Remove ASS override codes {\...}
    text = re.sub(r'{\\.*?}', '', text)
    # Remove any remaining special formatting codes inside brackets
    text = re.sub(r'\[.*?\]', '', text)
    # Strip leading/trailing whitespace
    return text.strip()

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
    log_filename(f"update database called")
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

    # Remove subtitles with no media file or missing subtitle file
    for f in sorted(indexed_subs):
        vid, tpart, lang_s = f.split('`')
        track = tpart[len('track_'):]
        lang = lang_s[:-4]

        media_exists = vid in current_media

        if not media_exists:
            conn.execute('DELETE FROM subtitles WHERE filename=? AND language=? AND track=?',
                         (vid, lang, track))
            print(f"Removed subtitle: file={vid}, track={track}, lang={lang}")

    extract_all_subtitle_tracks_and_update_db(conn)


    # add user placed subtitles
    current_media = {
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in audio_exts + video_exts
    }

    media_basenames = {os.path.splitext(f)[0] for f in current_media}

    current_subtitles = {
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() == ".srt"
    }

    print(f"Current subtitles: {current_subtitles}")

    cursor = conn.execute(
        "SELECT DISTINCT filename FROM subtitles WHERE track = '-1' AND language = 'und'"
    )

    indexed_subtitle_files = {row[0] for row in cursor}
    indexed_subtitle_basenames = {os.path.splitext(f)[0] for f in indexed_subtitle_files}

    for subtitle_file in current_subtitles:
        print(f"Processing subtitle: {subtitle_file}")
        base_name = os.path.splitext(subtitle_file)[0]
        if base_name in media_basenames and base_name not in indexed_subtitle_basenames:
            subtitle_path = os.path.join(folder, subtitle_file)
            for media_file in (m for m in current_media if os.path.splitext(m)[0] == base_name):
                # No need to check DB again here; just process
                print(f"Processing new subtitle {subtitle_path} for media file {media_file}")
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
                    print(f"Added subtitle content for {subtitle_path} linked to media {media_file}")
                except Exception as e:
                    print(f"Failed to add subtitle content from {subtitle_path}: {e}")


    # remove missing media
    cursor = conn.execute('SELECT DISTINCT filename FROM media_tracks')
    indexed_media = {r[0] for r in cursor}

    for mf in sorted(indexed_media - current_media):
        conn.execute('DELETE FROM media_tracks WHERE filename=?', (mf,))
        conn.execute('DELETE FROM media_audio_start_times WHERE filename=?', (mf,))
        print(f"Removed media entries for: {mf}")

    # add new media
    for mf in sorted(current_media - indexed_media):
        path = os.path.join(folder, mf)
        data = run_ffprobe(path)
        if not data: continue
        a_count = 0; s_count = 0
        for st in data.get('streams', []):
            ct = st.get('codec_type')
            lang = st.get('tags', {}).get('language','und').lower()
            if ct == 'audio':
                a_count += 1
                conn.execute('INSERT OR REPLACE INTO media_tracks VALUES(?,?,?,?)',
                             (mf, a_count, lang, 'audio'))
                dm = constants.get_audio_start_time_ms_for_track(path, st['index'])
                conn.execute('INSERT OR REPLACE INTO media_audio_start_times VALUES(?,?,?)',
                             (mf, a_count, dm))
            elif ct == 'subtitle':
                s_count += 1
                conn.execute('INSERT OR REPLACE INTO media_tracks VALUES(?,?,?,?)',
                             (mf, s_count, lang, 'subtitle'))
        print(f"Added media file: {mf}")
        for r in conn.execute('SELECT track,language,type FROM media_tracks WHERE filename=? ORDER BY type,track',(mf,)):
            print(f"  Track {r[0]} | {r[2]} | {r[1]}")
        print()

    conn.commit()
    conn.execute("VACUUM;")

    return conn


def extract_all_subtitle_tracks_and_update_db(conn):
    log_filename("extract_all_subtitle_tracks_and_update_db called")

    folder = os.path.join(constants.addon_dir, constants.addon_source_folder)
    audio_exts = constants.audio_extensions
    video_exts = constants.video_extensions
    media_exts = audio_exts + video_exts

    def run_ffprobe(path):
        exe_path, ffprobe_path = constants.get_ffmpeg_exe_path()
        cmd = [
            ffprobe_path, "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name:stream_tags=language",
            "-select_streams", "s",
            "-of", "json", path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_error(f"ffprobe failed on {path}: {result.stderr}")
            return None
        try:
            return json.loads(result.stdout)
        except Exception as e:
            log_error(f"Failed to parse ffprobe JSON output for {path}: {e}")
            return None

    exe_path, _ = constants.get_ffmpeg_exe_path()

    current_files = set(os.listdir(folder))
    current_media = {f for f in current_files if os.path.splitext(f)[1].lower() in media_exts}

    cursor = conn.execute('SELECT DISTINCT filename FROM subtitles')
    indexed_media = {row[0] for row in cursor}

    media_to_process = sorted(
        n for n in current_media if n not in indexed_media
    )

    # print(f"---------------------\ncurrent_media:\n{current_media}\n-----------------------")
    # print(f"---------------------\nindexed_media:\n{indexed_media}\n-----------------------")


    for media_file in media_to_process:
        print(f"processing file: {media_file}")
        media_path = os.path.join(folder, media_file)
        data = run_ffprobe(media_path)
        if not data:
            log_error(f"No ffprobe data for media file: {media_file}")
            continue

        subtitle_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'subtitle']

        if not subtitle_streams:
            log_filename(f"No subtitle streams found in {media_file}")
            # Insert a placeholder to indicate this file was processed
            conn.execute(
                'INSERT INTO subtitles (filename, language, track, content) VALUES (?, ?, ?, ?)',
                (media_file, "und", "-999", json.dumps([], ensure_ascii=False))
            )
            continue

        log_filename(f"Found {len(subtitle_streams)} subtitle streams in {media_file}")

        for relative_index, stream in enumerate(subtitle_streams):
            index = stream.get('index')
            codec = stream.get('codec_name')
            lang = stream.get('tags', {}).get('language', 'und')
            log_filename(f"Attempting subtitle extraction: file={media_file}, track={index}, codec={codec}, language={lang}")

            if codec not in ("subrip", "ass", "srt", "ssa"):
                log_filename(f"Skipping subtitle track {index} in {media_file} due to unsupported codec: {codec}")
                continue

            if check_already_indexed(conn, media_file, index, lang):
                log_filename(f"Subtitle track {index} for {media_file} lang={lang} already indexed; skipping")
                continue

            try:
                cmd = [
                    exe_path,
                    "-y",
                    "-i", media_path,
                    "-map", f"0:s:{relative_index}",
                    "-c:s", "srt",
                    "-f", "srt",
                    "-"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    log_error(f"Failed to extract subtitle track {index} from {media_file}: {result.stderr.strip()}")
                    continue

                text = result.stdout.strip()
                if not text:
                    log_error(f"Extracted subtitle track {index} from {media_file} is empty")
                    continue

                blocks = text.split('\n\n')
                parsed = []
                for blk in blocks:
                    lines = blk.strip().split('\n')
                    if len(lines) < 3:
                        continue
                    idx = lines[0]
                    m = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                    if not m:
                        continue
                    start, end = m.groups()
                    content = ' '.join(lines[2:]).strip()
                    content = remove_subtitle_formatting(content)
                    parsed.append([idx, start, end, content])

                conn.execute(
                    'INSERT INTO subtitles (filename, language, track, content) VALUES (?, ?, ?, ?)',
                    (media_file, lang, str(index), json.dumps(parsed, ensure_ascii=False))
                )
                log_filename(f"Inserted {len(parsed)} subtitle blocks for {media_file}, track={index}, lang={lang}")
            except Exception as e:
                log_error(f"Exception during subtitle extraction for track {index} from {media_file}: {e}")

    conn.commit()

def print_largest_subtitle_entries(limit=10):
    conn = get_database()
    cursor = conn.cursor()

    query = """
    SELECT filename, language, track, LENGTH(content) as size
    FROM subtitles
    ORDER BY size DESC
    LIMIT ?
    """
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()

    print(f"Top {limit} largest subtitle entries in the database:")
    for filename, language, track, size in rows:
        print(f"File: {filename}, Lang: {language}, Track: {track}, Size (chars): {size}")

# print_largest_subtitle_entries()

def print_all_subtitle_filenames():
    conn = get_database()
    cursor = conn.execute('SELECT DISTINCT filename FROM subtitles')
    for row in cursor:
        print(row[0])
print_all_subtitle_filenames()