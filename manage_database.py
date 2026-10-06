# imports
import sys
import os
import threading
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QProgressDialog
from aqt import mw
from aqt.utils import tooltip, showInfo

import sqlite3
import json
import tempfile
import shutil
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import constants
from .constants import log_error, ffmpeg_exe_name
from .constants import log_database
from .constants import folder

# global variables
conn = None
audio_exts = constants.audio_extensions
video_exts = constants.video_extensions
media_exts = audio_exts + video_exts
ffmpeg_path, ffprobe_path = constants.get_ffmpeg_exe_path(True)
_thread_local = threading.local()

# ffprobe/ffmpeg run as separate processes, so several files can be probed and
# extracted at the same time when the database is updated
MAX_EXTRACTION_WORKERS = max(1, min(8, (os.cpu_count() or 2)))

def get_database():
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
        _thread_local.conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
        try:
            _thread_local.conn.execute('PRAGMA journal_mode = WAL;')
            _thread_local.conn.execute('PRAGMA synchronous = NORMAL;')
            _thread_local.conn.execute('PRAGMA busy_timeout = 30000;')
            # this database grows to hundreds of MB, so a larger page cache,
            # memory-mapped reads and in-memory temp tables make the big scans
            # and inserts noticeably faster
            _thread_local.conn.execute('PRAGMA cache_size = -65536;')     # 64 MB
            _thread_local.conn.execute('PRAGMA mmap_size = 268435456;')   # 256 MB
            _thread_local.conn.execute('PRAGMA temp_store = MEMORY;')
        except Exception:
            pass
        
        _thread_local.conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(filename, language, auto_language_code, track, content)')
        _thread_local.conn.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS subtitle_lines_fts USING fts5(
            filename UNINDEXED,
            track UNINDEXED,
            language UNINDEXED,
            line_index UNINDEXED,
            start_time UNINDEXED,
            end_time UNINDEXED,
            clean_text UNINDEXED,
            search_tokens,
            tokenize="unicode61"
        )
        ''')

        _thread_local.conn.execute('CREATE TABLE IF NOT EXISTS media_tracks (filename TEXT, track INTEGER, language TEXT, type TEXT, PRIMARY KEY(filename, track, type))')
        _thread_local.conn.execute('''
        CREATE TABLE IF NOT EXISTS media_audio_start_times (
            filename TEXT,
            audio_track INTEGER,
            delay_ms INTEGER,
            PRIMARY KEY (filename, audio_track)
        )''')

        _thread_local.conn.execute('''
        CREATE TABLE IF NOT EXISTS subtitle_access (
            filename TEXT PRIMARY KEY,
            last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # sort_key remembers the order files are searched in (see search_order)
        access_cols = {row[1] for row in _thread_local.conn.execute('PRAGMA table_info(subtitle_access)')}
        if 'sort_key' not in access_cols:
            _thread_local.conn.execute('ALTER TABLE subtitle_access ADD COLUMN sort_key INTEGER')

        # Fast O(1) check: backfill subtitle_lines_fts if table is empty but subtitles has data
        has_fts = _thread_local.conn.execute("SELECT 1 FROM subtitle_lines_fts LIMIT 1").fetchone()
        if not has_fts:
            cursor = _thread_local.conn.execute("SELECT filename, track, language, content FROM subtitles")
            rows = cursor.fetchall()
            if rows:
                _thread_local.conn.execute("BEGIN TRANSACTION")
                for fn, trk, lang, content in rows:
                    try:
                        blocks = json.loads(content)
                        index_parsed_subtitles_fts(_thread_local.conn, fn, trk, lang, blocks)
                    except Exception:
                        pass
                _thread_local.conn.execute("COMMIT")


    return _thread_local.conn

def close_database():
    global conn
    if conn is not None:
        conn = None

# run ffprobe on file and return the results as json
def run_ffprobe(file_path):

    # check if ffmpeg exists
    if not ffmpeg_path or not ffprobe_path:
        log_error(f"ffprobe not found, skipping {file_path}")
        return None

    cmd = [
        f"{ffprobe_path}",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        file_path
    ]
    result = constants.silent_run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result is None or result.returncode != 0:
        err = result.stderr.strip() if result and result.stderr else "(no error output)"
        log_error(f"[error] ffprobe failed on {file_path}: {err}")
        return None

    return json.loads(result.stdout)

def remove_subtitle_formatting(text: str) -> str:
    if '\\p' in text or '{\\p' in text:
        return ''

    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'{[^{}]*}', '', text)
    text = re.sub(r'[\[\(].*?[\]\)]', '', text)
    text = text.strip()

    return text

# removes subtitle lines if 4 or more have the same start times
# helps clean .ass files with a lot of formatting
# TODO find more efficient way to convert from ass to srt 
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

# Split CJK text into individual characters so FTS can search it, while keeping Latin words together
def tokenize_for_fts(text: str) -> str:
    if not text:
        return ""
    tokens = []
    current_latin = []
    for ch in text:
        # Check CJK Ideographs, Hiragana, Katakana
        if ('\u4e00' <= ch <= '\u9fff') or ('\u3040' <= ch <= '\u309f') or ('\u30a0' <= ch <= '\u30ff'):
            if current_latin:
                tokens.append(''.join(current_latin))
                current_latin = []
            tokens.append(ch)
        elif ch.isalnum():
            current_latin.append(ch)
        else:
            if current_latin:
                tokens.append(''.join(current_latin))
                current_latin = []
    if current_latin:
        tokens.append(''.join(current_latin))
    return ' '.join(tokens)

# Tokenize search text and format it as an FTS5 phrase query
def build_fts_query(text: str) -> str:
    tokens = tokenize_for_fts(text)
    if not tokens:
        return ""
    safe_tokens = tokens.replace('"', '""')
    return f'"{safe_tokens}"'


# Inserts all blocks of a subtitle track into the FTS index
def index_parsed_subtitles_fts(conn, filename: str, track: str, language: str, parsed_blocks):
    if not parsed_blocks:
        return
    entries = []
    for b in parsed_blocks:
        if isinstance(b, list) and len(b) >= 4:
            idx, start, end, raw_text = b[:4]
        elif isinstance(b, str):
            formatted = constants.format_subtitle_block(b)
            if not formatted:
                continue
            idx, start, end, raw_text = formatted
        else:
            continue
        clean = remove_subtitle_formatting(raw_text)
        tokens = tokenize_for_fts(clean)
        if tokens:
            entries.append((filename, str(track), language, str(idx), str(start), str(end), clean, tokens))
    if entries:
        conn.executemany(
            'INSERT INTO subtitle_lines_fts (filename, track, language, line_index, start_time, end_time, clean_text, search_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            entries
        )

# Deletes entries from FTS index
def delete_subtitles_fts(
    conn,
    filename: str,
    track: str | int | None = None,
    language: str | None = None,
):
    if not conn or not filename:
        return

    clauses = ["filename = ?"]
    params = [filename]

    if track is not None:
        clauses.append("track = ?")
        params.append(str(track))

    if language is not None:
        clauses.append("language = ?")
        params.append(language)

    query = f"DELETE FROM subtitle_lines_fts WHERE {' AND '.join(clauses)}"
    conn.execute(query, tuple(params))


def delete_subtitles_fts_bulk(conn, filenames, track=None, chunk_size=200):
    """Delete the search index rows of many files at once.

    filename/track/language are UNINDEXED columns of subtitle_lines_fts, so any
    lookup on them is a full table scan. Deleting file by file therefore costs
    one scan per file while deleting in chunks costs one scan per chunk, which
    is orders of magnitude faster when a folder with many files is removed.
    When `track` is given only that track is deleted (used for user placed
    subtitles, which are stored with track = -1).
    """
    if not conn:
        return
    names = sorted({f for f in filenames if f})
    for i in range(0, len(names), chunk_size):
        batch = names[i:i + chunk_size]
        placeholders = ','.join('?' * len(batch))
        if track is None:
            conn.execute(f"DELETE FROM subtitle_lines_fts WHERE filename IN ({placeholders})", batch)
            conn.execute(f"DELETE FROM subtitles WHERE filename IN ({placeholders})", batch)
        else:
            conn.execute(
                f"DELETE FROM subtitle_lines_fts WHERE filename IN ({placeholders}) AND track = ?",
                batch + [str(track)]
            )
            conn.execute(
                f"DELETE FROM subtitles WHERE filename IN ({placeholders}) AND track = ?",
                batch + [str(track)]
            )
        conn.execute(f"DELETE FROM subtitle_access WHERE filename IN ({placeholders})", batch)


def delete_media_rows_bulk(conn, filenames, chunk_size=200):
    """Delete the per-media bookkeeping rows of many missing files at once."""
    if not conn:
        return
    names = sorted({f for f in filenames if f})
    for i in range(0, len(names), chunk_size):
        batch = names[i:i + chunk_size]
        placeholders = ','.join('?' * len(batch))
        conn.execute(f"DELETE FROM media_tracks WHERE filename IN ({placeholders})", batch)
        conn.execute(f"DELETE FROM media_audio_start_times WHERE filename IN ({placeholders})", batch)
        conn.execute(f"DELETE FROM subtitle_access WHERE filename IN ({placeholders})", batch)


def store_subtitles(conn, filename, track, language, parsed_blocks):
    """Store one subtitle track plus its search index rows in one transaction.

    The connection runs in autocommit mode, so without an explicit transaction
    every row index_parsed_subtitles_fts() writes would be committed on its own,
    which measures ~20x slower than writing them all in a single transaction.
    """
    conn.execute("BEGIN")
    try:
        conn.execute(
            'INSERT INTO subtitles (filename, language, auto_language_code, track, content) VALUES (?, ?, ?, ?, ?)',
            (filename, language, language, str(track), json.dumps(parsed_blocks, ensure_ascii=False))
        )
        index_parsed_subtitles_fts(conn, filename, str(track), language, parsed_blocks)
        conn.execute('''
        INSERT INTO subtitle_access(filename, last_accessed)
        VALUES (?, CURRENT_TIMESTAMP)
        ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
        ''', (filename,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

def search_subtitles_fts(
    conn,
    search_text: str,
    language: str | None = None,
    track: str | int | None = None,
    filename: str | None = None,
    limit: int | None = None,
):
    """
    Search subtitle_lines_fts using FTS5 phrase matching.
    Returns: list of tuples (filename, track, language, line_index, start_time, end_time, clean_text)
    """
    query_str = build_fts_query(search_text)
    if not query_str:
        return []

    clauses = ["f.search_tokens MATCH ?"]
    params = [query_str]

    if filename is not None:
        clauses.append("f.filename = ?")
        params.append(filename)

    if track is not None:
        clauses.append("f.track = ?")
        params.append(str(track))

    if language and language != "und":
        clauses.append("(f.language = ? OR f.language = 'und')")
        params.append(language)

    sql = f"""
        SELECT f.filename, f.track, f.language, f.line_index, f.start_time, f.end_time, f.clean_text
        FROM subtitle_lines_fts f
        LEFT JOIN subtitle_access a ON f.filename = a.filename
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(a.sort_key, 2147483647) ASC,
                 f.filename ASC,
                 CAST(f.line_index AS INTEGER) ASC
    """

    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    try:
        cursor = conn.execute(sql, tuple(params))
        return cursor.fetchall()
    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "locked" in err_msg or "busy" in err_msg:
            log_error(f"Subtitle database is locked: {e}")
            showInfo("The subtitle database is currently busy updating in the background.\nPlease wait a moment for it to finish and try again.")
        else:
            log_error(f"Database error in search_subtitles_fts: {e}")
        return []


# Check whether the subtitle track is already stored in the database
def check_already_indexed(conn, media_file, track, lang=None):
    query = "SELECT 1 FROM subtitles WHERE filename=? AND track=?"
    params = [media_file, str(track)]
    if lang is not None:
        query += " AND language=?"
        params.append(lang)
    query += " LIMIT 1"

    cursor = conn.execute(query, params)
    return cursor.fetchone() is not None

def get_srt_converted_subtitle_from_path(subtitle_path):
    try:
        if not ffmpeg_path:
            log_database(f"FFmpeg not found, cannot convert {subtitle_path}")
            return None

        # use ffmpeg to convert subtitle to SRT and output to stdout
        cmd = [
            ffmpeg_path,
            '-i', subtitle_path,
            '-c:s', 'srt',
            '-f', 'srt',  # force SRT format
            'pipe:1'  # output to stdout
        ]

        # only use create no window on windows
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        result = constants.silent_run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=creationflags
        )

        if result.returncode != 0:
            log_database(f"ffmpeg conversion failed for {subtitle_path}: {result.stderr}")
            return None

        # Parse the SRT content directly from stdout
        return parse_srt_from_text(result.stdout)

    except Exception as e:
        log_database(f"Failed to convert subtitle with ffmpeg: {e}, trying manual SRT parsing")
        return None

def parse_srt_from_text(srt_text):
    try:
        blocks = srt_text.strip().split("\n\n")
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

            # Apply the same formatting removal as the main extraction function
            content = remove_subtitle_formatting(content)
            if not content:
                continue

            # Use the same format: [index, start, end, content]
            parsed.append([idx, start, end, content])

        return parsed
    except Exception as e:
        log_database(f"Failed to parse SRT text: {e}")
        return []

def extract_subtitle_file_data(subtitle_filename):
    # Remove the subtitle extension (.srt, .ass, etc.)
    name_no_ext = os.path.splitext(subtitle_filename)[0]

    # Extract language code after last ` or .
    index_backtick = name_no_ext.rfind('`')
    index_dot = name_no_ext.rfind('.')
    separator_index = max(index_backtick, index_dot)

    if separator_index != -1:
        base_name = name_no_ext[:separator_index]
        lang_code = name_no_ext[separator_index + 1:]
    else:
        base_name = name_no_ext
        lang_code = "und"

    return {
        'lang_code': lang_code,
        'base_name': base_name,
    }

def ordered_source_files(folder, extensions):
    """Every file under `folder` whose extension is in `extensions`, in a
    deterministic alphabetical order.

    Folders are walked in alphabetical order (nested folders included) and the
    files inside a folder are collected alphabetically before moving on to the
    next folder, i.e. folder a (and all the files inside it) first, then
    folder b, and so on.
    """
    paths = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        files.sort()
        if 'ignore' in root.lower().split(os.sep):
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() in extensions:
                paths.append(os.path.join(root, f))
    return paths


def search_order(paths, root):
    """The order files are searched/prioritised in.

    Files of one series are kept together instead of being interleaved with the
    other series, and the series themselves are ordered by their alphabetically
    first file. So the series whose first file sorts first is searched first,
    in full, before the next series: e.g. every file of
    "2 [物語シリーズ] Monogatari ..." (first file "01 - 化物語 上 ...") is
    searched before "1 [Furretar] 戯言 ..." (first file "01 クビキリ...").
    """
    groups = {}
    for p in paths:
        rel = os.path.relpath(p, root)
        series = rel.split(os.sep)[0]
        groups.setdefault(series, []).append(os.path.basename(p))

    ordered = []
    for series in sorted(groups, key=lambda s: (min(groups[s]), s)):
        ordered.extend(sorted(groups[series]))
    return ordered


def update_database():
    constants.database_updating.set()
    log_database(f"update database called")

    close_database()
    conn = get_database()

    # create tables
    conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS subtitles USING fts5(filename, language, auto_language_code, track, content)')
    conn.execute('''
    CREATE TABLE IF NOT EXISTS media_audio_start_times (
        filename TEXT,
        audio_track INTEGER,
        delay_ms INTEGER,
        PRIMARY KEY (filename, audio_track)
    )
    ''')

    conn.execute('''
    CREATE TABLE IF NOT EXISTS subtitle_access (
        filename TEXT PRIMARY KEY,
        last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    if not os.path.exists(folder):
        os.makedirs(folder)


    # recursively get all media files, except "ignore" folder, in alphabetical
    # order: folder a and its files first, then folder b, ...
    log_database(f"folder: {folder}")
    media_paths_in_folder = ordered_source_files(folder, media_exts)
    current_media = {os.path.basename(p) for p in media_paths_in_folder}

    subtitle_extensions = constants.subtitle_extensions
    subtitle_paths_in_folder = ordered_source_files(folder, subtitle_extensions)
    subtitles_in_folder = {os.path.basename(p) for p in subtitle_paths_in_folder}

    # record the order files are searched in, so the lookups prioritise them in
    # exactly that order (see search_order)
    media_search_order = search_order(media_paths_in_folder, folder)
    try:
        conn.execute("BEGIN")
        conn.executemany(
            "INSERT INTO subtitle_access (filename, last_accessed, sort_key) VALUES (?, CURRENT_TIMESTAMP, ?) "
            "ON CONFLICT(filename) DO UPDATE SET sort_key = excluded.sort_key",
            [(name, i) for i, name in enumerate(media_search_order)],
        )
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        log_error(f"Failed to record the file search order: {e}")

    # collect orphaned subtitles
    cursor = conn.execute('SELECT filename, language, track FROM subtitles')
    indexed_subs = {f"{r[0]}`track_{r[2]}`{r[1]}.srt" for r in cursor}

    to_delete = []
    for f in sorted(indexed_subs):
        basename, tpart, lang_s = f.split('`')
        track = tpart[len('track_'):]
        lang = lang_s[:-4]

        if basename not in current_media:
            log_database(f"deleting sub: {basename}")
            to_delete.append((basename, lang, track))

    constants.database_items_left = len(current_media) + len(subtitles_in_folder) + len(to_delete)

    # log and delete them. The deletes are batched because looking rows up by
    # filename in the search index is a full table scan, so one delete per file
    # would mean one scan per file.
    if to_delete:
        try:
            conn.execute("BEGIN")
            delete_subtitles_fts_bulk(conn, [basename for basename, _, _ in to_delete])
            for basename, lang, track in to_delete:
                log_database(f"Removed subtitle: file={basename}, track={track}, lang={lang}")
                constants.database_items_left -= 1
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            log_error(f"Failed to delete orphaned subtitles: {e}")

    # get current media basenames (without extension)
    media_basenames = {os.path.splitext(f)[0] for f in current_media}

    cursor = conn.execute(
        "SELECT DISTINCT filename FROM subtitles WHERE track = '-1'"
    )
    indexed_subtitle_files = {row[0] for row in cursor}

    indexed_subtitle_basenames = {os.path.splitext(f)[0] for f in indexed_subtitle_files}

    # listed in the order the subtitles are searched/prioritised in: one series
    # at a time, each series ordered by its alphabetically first file
    log_database(f"current subtitles in folder (searched in this order): "
                 f"{search_order(subtitle_paths_in_folder, folder)}")
    for subtitle_path in subtitle_paths_in_folder:
        filename = os.path.basename(subtitle_path)

        name_no_ext, ext = os.path.splitext(filename)

        parts = name_no_ext.rsplit('.', 1)
        if len(parts) == 2 and re.fullmatch(r'[a-zA-Z]{2,3}', parts[1]):
            base_name = parts[0]
            lang_code = parts[1].lower()
        else:
            base_name = name_no_ext
            lang_code = "und"

        if base_name not in indexed_subtitle_basenames:
            if base_name in media_basenames:
                for media_file in sorted(m for m in current_media if os.path.splitext(m)[0] == base_name):
                    try:
                        parsed = get_srt_converted_subtitle_from_path(subtitle_path)
                        if not parsed:
                            log_database(f"No valid subtitle content found in {subtitle_path}")
                            continue

                        store_subtitles(conn, media_file, "-1", lang_code, parsed)

                        log_database(f"Added subtitle content for {subtitle_path} linked to media {media_file} ({len(parsed)} entries)")
                    except Exception as e:
                        log_database(f"Failed to add subtitle content from {subtitle_path}: {e}")
            else:
                log_database(f"no media basename found for {base_name}")

            constants.database_items_left -= 1

    # Extract subtitles from all source files
    extract_all_subtitle_tracks_and_update_db(conn)

    # Remove missing media entries
    cursor = conn.execute("SELECT DISTINCT filename FROM media_tracks")
    indexed_media = {r[0] for r in cursor}
    missing_media = sorted(indexed_media - current_media)
    for mf in missing_media:
        log_database(f"Removed media entries for: {mf}")
    if missing_media:
        try:
            conn.execute("BEGIN")
            delete_media_rows_bulk(conn, missing_media)
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            log_error(f"Failed to remove missing media rows: {e}")

    # Remove orphaned user-placed subtitle entries (track = -1) whose source files no longer exist
    # Recompute current subtitle base_names in folder (same logic as above)
    present_subtitle_basenames = set()
    for subtitle_file in subtitles_in_folder:
        base_name = os.path.splitext(subtitle_file)[0]  # just strip extension
        present_subtitle_basenames.add(base_name)

    cursor = conn.execute("SELECT filename, language, track FROM subtitles WHERE track = '-1'")
    orphaned_user_subs = [
        (filename, language, track) for filename, language, track in cursor
        if os.path.splitext(filename)[0] not in present_subtitle_basenames
    ]
    if orphaned_user_subs:
        try:
            conn.execute("BEGIN")
            delete_subtitles_fts_bulk(conn, [filename for filename, _, _ in orphaned_user_subs], track="-1")
            for filename, language, track in orphaned_user_subs:
                log_database(f"Removed orphaned user subtitle: file={filename}, lang={language}, track={track}\n"
                             f"base name: {os.path.splitext(filename)[0]} not in present sub basenames: {present_subtitle_basenames}")
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            log_error(f"Failed to remove orphaned user subtitles: {e}")

    conn.commit()
    try:
        conn.execute("PRAGMA optimize;")
    except Exception:
        pass
    constants.database_updating.clear()
    constants.database_items_left = 0
    return conn


def extract_all_subtitle_tracks_and_update_db(conn):
    folder = os.path.join(constants.addon_dir, constants.addon_source_folder)

    if not ffmpeg_path or not ffprobe_path:
        log_error("ffmpeg/ffprobe not found, skipping subtitle extraction")
        return conn

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
            cmd = [ffmpeg_path, "-y", "-i", media_path]
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

    def probe_and_extract(media_file):
        """Runs in a worker thread; only ffmpeg/ffprobe are used, never the DB."""
        path = os.path.join(folder, media_file)
        info = run_ffprobe(path)
        if not info:
            return media_file, None, None

        streams = [
            s for s in info.get("streams", [])
            if s.get("codec_type") == "subtitle" and s.get("codec_name") in ("subrip", "ass", "srt", "ssa", "mov_text", "webvtt")
        ]

        if not streams:
            log_database(f"No subtitle streams in {media_file}, skipping")
            return media_file, [], None

        log_database(f"Found {len(streams)} subtitle streams in {media_file}")
        return media_file, streams, extract_all_subs_single(path, streams)

    # every (filename, track, language) already stored, so the per-track check
    # below doesn't have to run a query each time
    indexed_keys = {
        (r[0], str(r[1]), r[2])
        for r in conn.execute('SELECT DISTINCT filename, track, language FROM subtitles')
    }

    # alphabetical walk: folder a and its files first, then folder b, ...
    current_media_paths = ordered_source_files(folder, media_exts)
    current_media = {os.path.relpath(p, folder) for p in current_media_paths}

    # fetch all filenames with any subtitle entry, use basenames only
    cursor = conn.execute('SELECT DISTINCT filename FROM subtitles')
    indexed_basenames = {os.path.basename(r[0]) for r in cursor}

    media_to_process = [
        os.path.relpath(p, folder) for p in current_media_paths
        if os.path.basename(p) not in indexed_basenames
    ]

    # probe and extract a few files at a time, in parallel (ffprobe/ffmpeg are
    # separate processes); results are consumed in order and only the database
    # writes happen on this thread
    def extraction_stream(files):
        if not files:
            return
        workers = max(1, min(MAX_EXTRACTION_WORKERS, len(files)))
        if workers > 1:
            log_database(f"extracting subtitles with {workers} parallel workers")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            yield from pool.map(probe_and_extract, files)

    for media_file, streams, all_texts in extraction_stream(media_to_process):
        if not streams or all_texts is None:
            constants.database_items_left -= 1
            continue

        for idx, (stream, text) in enumerate(zip(streams, all_texts), 1):
            track = idx
            lang = stream.get("tags", {}).get("language", "und")
            codec = stream.get("codec_name")
            log_database(f"Extracting track={track}, lang={lang}, codec={codec}")

            if codec not in ("subrip", "ass", "srt", "ssa", "webvtt"):
                log_database(f"skip unsupported codec {codec}")
                continue

            basename = os.path.basename(media_file)
            if (basename, str(track), lang) in indexed_keys:
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

            try:
                store_subtitles(conn, basename, track, lang, parsed)
                # remember which streams the file has, so lookups by language
                # code (get_subtitle_track_number_by_code) can work
                conn.execute(
                    'INSERT OR REPLACE INTO media_tracks (filename, track, language, type) VALUES (?, ?, ?, ?)',
                    (basename, track, lang, 'subtitle')
                )
            except Exception as e:
                log_error(f"Failed to store subtitles for {basename}, track={track}, lang={lang}: {e}")
                continue

            indexed_keys.add((basename, str(track), lang))
            log_database(f"Inserted {len(parsed)} blocks for {basename}, track={track}, lang={lang}")
        constants.database_items_left -= 1

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

def print_all_subtitle_names():
    conn = get_database()
    cursor = conn.execute('SELECT filename, track, language, auto_language_code FROM subtitles ORDER BY filename, track')
    for filename, track, language, auto_language_code in cursor:
        msg = f"{filename} | Track: {track} | Language: {language} | Auto: {auto_language_code}"
        constants.write_log(msg)
print_all_subtitle_names()

def print_subtitles_by_last_accessed():
    conn = get_database()

    cursor = conn.execute('''
        SELECT filename, last_accessed
        FROM subtitle_access
        ORDER BY last_accessed DESC
    ''')

    for filename, last_accessed in cursor:
        print(f"{last_accessed} - {filename}")
# print_subtitles_by_last_accessed()