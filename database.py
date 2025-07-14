import json
import os
import sqlite3
import re
import constants
from aqt.utils import showInfo
import subprocess

from constants import (
    log_filename,
    log_error,
    log_image,
    log_command,
    addon_source_folder,
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
        conn.close()
        conn = None


audio_exts = constants.audio_exts
video_exts = constants.video_exts



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

def update_database():
    db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
    conn = sqlite3.connect(db_path)
    conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(filename, language, track, content)')
    conn.execute('CREATE TABLE IF NOT EXISTS media_tracks (filename TEXT, track INTEGER, language TEXT, type TEXT, PRIMARY KEY(filename, track, type))')

    folder = os.path.join(constants.addon_dir, constants.addon_source_folder)

    # Get currently indexed subtitles filenames in the format: "video`track_X`lang.srt"
    cursor = conn.execute('SELECT filename, language, track FROM subtitles')
    indexed_subtitle_files = set(f"{row[0]}`track_{row[2]}`{row[1]}.srt" for row in cursor)

    # Get current subtitle files on disk
    current_subtitle_files = set(f for f in os.listdir(folder) if f.endswith('.srt') and '`track_' in f)

    # Get currently indexed media files from media_tracks table
    cursor = conn.execute('SELECT DISTINCT filename FROM media_tracks')
    indexed_media_files = set(row[0] for row in cursor)

    # Get current media files on disk
    current_media_files = set(f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in audio_exts + video_exts)

    # Process subtitle files: add new and remove deleted
    to_remove_subtitles = indexed_subtitle_files - current_subtitle_files
    for f in to_remove_subtitles:
        parts = f.split('`')
        if len(parts) == 3:
            video_file = parts[0]
            track = parts[1][len('track_'):]
            language = parts[2][:-4]
            conn.execute('DELETE FROM subtitles WHERE filename=? AND language=? AND track=?',
                         (video_file, language, track))

    to_add_subtitles = current_subtitle_files - indexed_subtitle_files
    for f in to_add_subtitles:
        parts = f.split('`')
        if len(parts) == 3:
            video_file = parts[0]
            track = parts[1][len('track_'):]
            language = parts[2][:-4]
            srt_path = os.path.join(folder, f)

            with open(srt_path, encoding='utf-8') as file:
                full_text = file.read()

            blocks = full_text.strip().split('\n\n')
            parsed_blocks = []

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    srt_index = lines[0].strip()
                    times = lines[1].strip()
                    text_lines = lines[2:]
                    match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', times)
                    if match:
                        start_time, end_time = match.groups()
                    else:
                        start_time, end_time = '', ''
                    text = ' '.join(text_lines).strip()
                    parsed_blocks.append([srt_index, start_time, end_time, text])

            content_json = json.dumps(parsed_blocks, ensure_ascii=False)
            conn.execute('INSERT INTO subtitles VALUES (?, ?, ?, ?)', (video_file, language, track, content_json))

    # Process media files: add new and remove deleted
    to_remove_media = indexed_media_files - current_media_files
    for media_file in to_remove_media:
        conn.execute('DELETE FROM media_tracks WHERE filename=?', (media_file,))

    to_add_media = current_media_files - indexed_media_files
    for media_file in to_add_media:
        full_path = os.path.join(folder, media_file)
        probe_data = run_ffprobe(full_path)
        if not probe_data:
            continue
        streams = probe_data.get('streams', [])

        audio_count = 0
        subtitle_count = 0

        for stream in streams:
            codec_type = stream.get('codec_type')
            if codec_type == 'audio':
                audio_count += 1
                language = stream.get('tags', {}).get('language', 'und').lower()
                conn.execute('INSERT OR REPLACE INTO media_tracks VALUES (?, ?, ?, ?)',
                             (media_file, audio_count, language, 'audio'))
            elif codec_type == 'subtitle':
                subtitle_count += 1
                language = stream.get('tags', {}).get('language', 'und').lower()
                conn.execute('INSERT OR REPLACE INTO media_tracks VALUES (?, ?, ?, ?)',
                             (media_file, subtitle_count, language, 'subtitle'))

        cursor = conn.execute('SELECT track, language, type FROM media_tracks WHERE filename=? ORDER BY type, track', (media_file,))
        print(f"Added media file: {media_file}")
        for row in cursor:
            print(f"  Track {row[0]} | Language: {row[1]} | Type: {row[2]}")
        print()

    conn.commit()
    return conn


update_database()



import json

def print_subtitle_previews_from_database():
    conn = get_database()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, language, track, content FROM subtitles ORDER BY filename, track, language")

    for filename, language, track, content_json in cursor.fetchall():
        subtitle_id = f"{filename}`track_{track}`{language}.srt"
        print(f"--- {subtitle_id} ---")

        try:
            blocks = json.loads(content_json)
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            continue

        lines = []
        for block in blocks:
            text = block[3] if len(block) > 3 else ''
            for line in text.splitlines():
                if line.strip():
                    lines.append(line.strip())
                if len(lines) >= 3:
                    break
            if len(lines) >= 3:
                break

        for line in lines[:3]:
            print(line)
        print()

print_subtitle_previews_from_database()

import time
def timed_call(func, *args, **kwargs):
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    print(f"{func.__name__} took {elapsed:.4f} seconds")
    return result

# timed_call(lambda: print_first_subtitle_line(index_subtitles(), "53.mkv`track_2`jpn.srt"))
# timed_call(lambda: print("（コニー）お… おい"))
# timed_call(lambda: index_subtitles())





conn = get_database()
cursor = conn.execute("SELECT filename, track, language FROM subtitles WHERE filename=?", ("Sousou no Frieren - 01.mkv",))
for row in cursor:
    print(f"Indexed DB row: {row}")


def print_all_subtitle_files():
    conn = get_database()
    cursor = conn.execute("SELECT filename, track, language FROM subtitles")
    for filename, track, language in cursor:
        print(f"{filename}`track_{track}`{language}.srt")


def check_subtitle_entries(base_filename):
    conn = get_database()
    cursor = conn.execute(
        "SELECT filename, language, track FROM subtitles WHERE filename LIKE ?",
        (f"%{base_filename}%",)
    )
    rows = cursor.fetchall()
    if not rows:
        print(f"No subtitle entries found matching base filename pattern: {base_filename}")
        return

    print(f"Subtitle entries found for base filename pattern '{base_filename}':")
    for filename, language, track in rows:
        print(f"  filename: {filename} | language: {language} | track: {track}")


check_subtitle_entries(f"Solo Leveling - S02E01")