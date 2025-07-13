import json
import os
import sqlite3
import re
import constants
from aqt.utils import showInfo

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









def update_database():
    db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
    conn = sqlite3.connect(db_path)
    conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(filename, language, track, content)')

    folder = os.path.join(constants.addon_dir, constants.addon_source_folder)

    cursor = conn.execute('SELECT filename, language, track FROM subtitles')
    indexed_files = set(f"{row[0]}`track_{row[2]}`{row[1]}.srt" for row in cursor)

    current_files = set(f for f in os.listdir(folder) if f.endswith('.srt') and '`track_' in f)

    to_remove = indexed_files - current_files
    for f in to_remove:
        parts = f.split('`')
        if len(parts) == 3:
            video_file = parts[0]
            track = parts[1][len('track_'):]
            language = parts[2][:-4]
            conn.execute('DELETE FROM subtitles WHERE filename=? AND language=? AND track=?',
                         (video_file, language, track))

    to_add = current_files - indexed_files
    for f in to_add:
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

    conn.commit()
    return conn

update_database()

def print_first_subtitle_line(conn, subtitle_filename):
    import json
    parts = subtitle_filename.split('`')
    if len(parts) != 3:
        print("Invalid subtitle filename format")
        return
    video_file = parts[0]
    track = parts[1][len('track_'):]
    language = parts[2][:-4]

    cursor = conn.execute(
        'SELECT content FROM subtitles WHERE filename=? AND language=? AND track=?',
        (video_file, language, track)
    )
    row = cursor.fetchone()
    if not row:
        print(f"No entry found for {subtitle_filename}")
        return

    content_json = row[0]
    blocks = json.loads(content_json)
    if not blocks or not isinstance(blocks, list) or len(blocks[0]) < 4:
        print(f"No subtitle text found in {subtitle_filename}")
        return

    print(blocks[0][3])





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

