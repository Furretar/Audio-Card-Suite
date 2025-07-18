import sys, os
sys.path.append(os.path.dirname(__file__))
import os
import sqlite3
import re
import constants
import subprocess
import json

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
        conn.close()
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

def update_database():
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

    # indexed vs on‑disk subtitles
    cursor = conn.execute('SELECT filename, language, track FROM subtitles')
    indexed_subs = {f"{r[0]}`track_{r[2]}`{r[1]}.srt" for r in cursor}
    current_subs = {f for f in os.listdir(folder) if f.endswith('.srt') and '`track_' in f}

    # remove missing subtitles
    for f in sorted(indexed_subs - current_subs):
        vid, tpart, lang_s = f.split('`')
        track = tpart[len('track_'):]
        lang = lang_s[:-4]
        conn.execute('DELETE FROM subtitles WHERE filename=? AND language=? AND track=?',
                     (vid, lang, track))
        print(f"Removed subtitle: file={vid}, track={track}, lang={lang}")

    # add new subtitles
    for f in sorted(current_subs - indexed_subs):
        vid, tpart, lang_s = f.split('`')
        track = tpart[len('track_'):]
        lang = lang_s[:-4]
        path = os.path.join(folder, f)
        with open(path, encoding='utf-8') as fp:
            text = fp.read().strip()
        blocks = text.split('\n\n')
        parsed = []
        for blk in blocks:
            lines = blk.split('\n')
            if len(lines) < 3: continue
            idx = lines[0]
            m = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', lines[1])
            start, end = m.groups() if m else ('','')
            content = ' '.join(lines[2:]).strip()
            parsed.append([idx, start, end, content])
        conn.execute('INSERT INTO subtitles VALUES(?,?,?,?)',
                     (vid, lang, track, json.dumps(parsed, ensure_ascii=False)))
        print(f"Added subtitle: {f}")

    # indexed vs on‑disk media
    cursor = conn.execute('SELECT DISTINCT filename FROM media_tracks')
    indexed_media = {r[0] for r in cursor}
    current_media = {f for f in os.listdir(folder)
                     if os.path.splitext(f)[1].lower() in audio_exts + video_exts}

    # remove missing media
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
    return conn