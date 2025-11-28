from datetime import datetime
import os
import json
import html
import re
import subprocess
import threading
import time

from aqt.utils import showInfo
from send2trash import send2trash
import constants
import manage_database
from typing import Tuple, Optional, List
from constants import (
    log_filename,
    log_error,
    log_image,
    log_command,
log_database,
)



# todo: implement 4 character sha hash to disambiguate files with the same name and extension
# extracts all data in a sound line and returns it as a dict
# performs only string operations
def extract_sound_line_data(sound_line):
    format_type = detect_format(sound_line)

    if format_type == "backtick":
        match = constants.BACKTICK_PATTERN.match(sound_line)
        if not match:
            log_error("no match for backtick")
            return None

        groups = match.groupdict()
        filename_base = groups["filename_base"]
        filename_base = constants.format_anki_safe_filename(filename_base, revert=True)
        if not filename_base:
            return None

        source_file_extension = groups.get("source_file_extension") or ""
        lang_code = groups.get("lang_code") or ""
        timing_lang_code = groups.get("timing_lang_code") or ""
        start_time = groups["start_time"]
        end_time = groups["end_time"]
        subtitle_range = groups["subtitle_range"]
        sound_file_extension = groups["sound_file_extension"]
        normalize_tag = groups.get("normalize_tag") or ""
        start_index, end_index = map(int, subtitle_range.split("-"))
        full_source_filename = f"{filename_base}{source_file_extension}"
        meta_parts = [full_source_filename]

        if lang_code:
            codes = lang_code
            if timing_lang_code:
                codes += f"-{timing_lang_code}"
            meta_parts.append(codes)


        meta_parts.append(f"{start_time}-{end_time}")
        meta_parts.append(subtitle_range)

        if normalize_tag:
            meta_parts.append(normalize_tag)

        timestamp_filename = "`".join(meta_parts) + f".{sound_file_extension}"
        audio_collection_path = os.path.join(constants.get_collection_dir(), timestamp_filename)
        audio_collection_path = constants.format_anki_safe_filename(audio_collection_path, revert=False)
        if not audio_collection_path:
            return None


        m4b_image_filename = f"{filename_base}{source_file_extension}.jpg"
        image_filename = f"{filename_base}.{sound_file_extension}`{start_time}.jpg"
        image_collection_path = os.path.join(constants.get_collection_dir(), image_filename)
        m4b_image_collection_path = os.path.join(constants.get_collection_dir(), m4b_image_filename)

        log_image(f"image collection path: {image_collection_path}")

        return {
            "filename_base": filename_base,
            "source_file_extension": source_file_extension,
            "lang_code": lang_code,
            "timing_lang_code": timing_lang_code,
            "start_time": start_time,
            "end_time": end_time,
            "start_index": start_index,
            "end_index": end_index,
            "normalize_tag": normalize_tag,
            "sound_file_extension": sound_file_extension,
            "full_source_filename": full_source_filename,
            "collection_path": audio_collection_path,
            "image_filename": image_filename,
            "m4b_image_filename": m4b_image_filename,
            "image_collection_path": image_collection_path,
            "m4b_image_collection_path": m4b_image_collection_path,
        }

    # fallback if not a recognized pattern
    if not sound_line:
        log_error("extract_sound_line_data received None or empty string")
        return None

    log_error(f"no data extracted from sound line: {sound_line}, format type: {format_type}")
    return None

# returns all current config values as a dict
def get_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")

    if not os.path.exists(config_path):
        log_error(f"Config file not found at {config_path}")
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    keys = [
        "default_model", "default_deck", "audio_ext", "bitrate", "image_height",
        "pad_start", "pad_end", "target_language", "translation_language",
        "target_language_code", "translation_language_code", "normalize_audio",
        "lufs", "target_audio_track", "target_subtitle_track",
        "translation_audio_track", "translation_subtitle_track",
        "target_timing_code", "translation_timing_code",
        "target_timing_track", "translation_timing_track",
        "timing_tracks_enabled", "mapped_fields", "selected_tab_index"
    ]

    missing = [k for k in keys if k not in config]
    if missing:
        log_error(f"Missing required config fields: {missing}")

    zero_tracks = [k for k in [
        "target_audio_track", "target_subtitle_track",
        "translation_audio_track", "translation_subtitle_track",
        "target_timing_track", "translation_timing_track"
    ] if config.get(k) == 0]
    if zero_tracks:
        log_error(f"Track fields set to 0: {zero_tracks}")
        showInfo("Please set a valid track number:\n" + "\n".join(zero_tracks))
        return None

    return config

# returns the name of the users field that is set to use a label
# ex. "Target Subtitle Line" might return "Expression" field
def get_field_key_from_label(note_type_name: str, label: str, config: dict) -> str:
    mapped_fields = config[note_type_name].get("mapped_fields", {})
    for field_key, mapped_label in mapped_fields.items():
        if mapped_label == label:
            return field_key
    if label == "Target Subtitle Line":
        log_error(f"could not find Target Subtitle Line in note_type {note_type_name}, mapped field: {mapped_fields}, mapped fields items {mapped_fields.items()}")
    return ""

# gets data from a subtitle path string and returns as a dict
def extract_subtitle_path_data(subtitle_path):
    log_filename(f"received subtitle path: {subtitle_path}")
    if not subtitle_path:
        log_error("subtitle_path is None")
        return None

    subtitle_filename = os.path.basename(subtitle_path)
    pattern = r"^(.*?)(?:`track_(-?\d+))?(?:`([a-z]{2,3}))?\.(\w+)$"
    match = re.match(pattern, subtitle_filename, re.IGNORECASE)
    if not match:
        return None

    filename, track, code, extension = match.groups()

    subtitle_data = {
        "filename": filename,
        "track": int(track) if track is not None else None,
        "code": code.lower() if code else None,
        "extension": extension.lower()
    }

    log_filename(f"returning subtitle path data: {subtitle_data}")
    return subtitle_data

# todo: add another section to subtitle file names so the method knows which pattern to search for
# searches all possible name patterns using the base filename, track, and code
def get_subtitle_file_from_database(full_source_filename, track, code, config, database, note_type_name):
    if not code:
        code = "und"
    def find_subtitle():
        selected_tab_index = config.get(note_type_name, {}).get("selected_tab_index", config.get("selected_tab_index", 1))
        log_filename(f"received filename: {full_source_filename}, track/code: {track}/{code}")
        sub_source_path = get_source_path_from_full_filename(full_source_filename)

        if not os.path.exists(constants.addon_source_folder):
            os.makedirs(constants.addon_source_folder)

        if not os.path.exists(sub_source_path):
            log_error(f"Source file not found: {sub_source_path}")
            return None

        if not code or code.lower() == "none":
            log_error(f"Invalid subtitle language code: {code}")
            return None

        # try exact match
        log_filename(f"trying exact match")
        cursor = database.execute('''
        SELECT s.filename, s.language, s.track, s.content
        FROM subtitles s
        JOIN subtitle_access a ON s.filename = a.filename
        WHERE s.filename = ? AND s.track = ? AND s.language = ?
        ORDER BY a.last_accessed DESC
        ''', (full_source_filename, str(track), code))
        result = cursor.fetchone()

        if result:
            tagged_subtitle_file = f"{full_source_filename}`track_{track}`{code}.srt"
            tagged_subtitle_path = os.path.join(constants.addon_source_folder, tagged_subtitle_file)
            if os.path.exists(tagged_subtitle_path):
                log_filename(f"tagged_subtitle_path: {tagged_subtitle_path}")

                # Update last_accessed for this access
                database.execute('''
                INSERT INTO subtitle_access(filename, last_accessed)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
                ''', (full_source_filename,))

                return tagged_subtitle_path

        # try matching basename (user placed file)
        log_filename(f"trying to match basename with filename: {full_source_filename}")
        cursor = database.cursor()
        query = '''
        SELECT s.filename
        FROM subtitles s
        JOIN subtitle_access a ON s.filename = a.filename
        WHERE s.filename = ? AND s.track = '-1' AND s.language = 'und'
        ORDER BY a.last_accessed DESC
        LIMIT 1
        '''
        cursor.execute(query, (full_source_filename,))
        result = cursor.fetchone()

        if result:
            log_filename(f"Found subtitle in DB for {full_source_filename} with track=-1 and language=und")

            # Update last_accessed for this access
            database.execute('''
            INSERT INTO subtitle_access(filename, last_accessed)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
            ''', (full_source_filename,))

            return f"{full_source_filename}.srt"

        # prioritize finding the code if that tab is selected
        log_filename(f"trying match code")
        like_pattern = f"{full_source_filename}%"
        if selected_tab_index == 0:
            query = '''
            SELECT s.filename, s.track, s.language
            FROM subtitles s
            JOIN subtitle_access a ON s.filename = a.filename
            WHERE s.filename LIKE ? AND s.language = ?
            ORDER BY a.last_accessed DESC
            LIMIT 1
            '''
            cursor.execute(query, (like_pattern, code))
            row = cursor.fetchone()
            if row:
                base_filename, found_track, found_code = row
                subtitle_filename = f"{base_filename}`track_{found_track}`{found_code}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                log_filename(f"[tab 0] subtitle_path (by code, recent-first): {subtitle_path}")

                # Update last_accessed for this access
                database.execute('''
                INSERT INTO subtitle_access(filename, last_accessed)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
                ''', (base_filename,))

                return subtitle_path

        # search for track
        log_filename(f"trying to match track")
        query = '''
        SELECT s.filename, s.track, s.language
        FROM subtitles s
        JOIN subtitle_access a ON s.filename = a.filename
        WHERE s.filename LIKE ?
        ORDER BY a.last_accessed DESC
        '''
        cursor.execute(query, (like_pattern,))
        rows = cursor.fetchall()
        for db_filename, db_track, db_lang in rows:
            if db_filename.startswith(full_source_filename) and f"`track_{track}`" in db_filename:
                subtitle_filename = f"{db_filename}`track_{track}`{db_lang}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                log_filename(f"[tab {selected_tab_index}] subtitle_path (by track, recent-first): {subtitle_path}")

                # Update last_accessed for this access
                database.execute('''
                INSERT INTO subtitle_access(filename, last_accessed)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
                ''', (db_filename,))

                return subtitle_path

        # search for code as a fallback if track was not found
        log_filename(f"trying code as fallback")
        if selected_tab_index != 0:
            query = '''
            SELECT s.filename, s.track, s.language
            FROM subtitles s
            JOIN subtitle_access a ON s.filename = a.filename
            WHERE s.filename LIKE ? AND s.language = ?
            ORDER BY a.last_accessed DESC
            LIMIT 1
            '''
            cursor.execute(query, (like_pattern, code))
            row = cursor.fetchone()
            if row:
                base_filename, found_track, found_code = row
                subtitle_filename = f"{base_filename}`track_{found_track}`{found_code}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                log_filename(f"[tab 1+] subtitle_path (fallback by code, recent-first): {subtitle_path}")

                # Update last_accessed for this access
                database.execute('''
                INSERT INTO subtitle_access(filename, last_accessed)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
                ''', (base_filename,))

                return subtitle_path

        return None

    # try finding subtitle
    path = find_subtitle()
    if path:
        return path


    log_error(f"No matching subtitle file found for:\n{full_source_filename}|`track_{track}`|{code}")
    # todo showInfo(f"No matching subtitle file found for:\n{full_source_filename}|'track_{track}'|{code}")

    if config.get(note_type_name, {}).get("selected_tab_index", 0) == 0:
        log_error(f"Both the code '{code}' and track 'track_{track}' do not exist for the file: {full_source_filename}.")
        showInfo(f"Both the code '{code}' and track 'track_{track}' do not exist for the file: {full_source_filename}.")
    return None

# returns newly generated formatted image line if image field is empty, otherwise returns current image
def get_image_line_from_sound_line(image_line, sound_line, image_height):
    # check if any field already has an image
    if image_line:
        return image_line

    sound_line_data = extract_sound_line_data(sound_line)
    log_image(f"sound line: {sound_line}")
    if not sound_line_data:
        log_error(f"extract_sound_line_data returned None.")
        return ""

    full_source_filename = sound_line_data.get("full_source_filename")
    image_collection_path = sound_line_data.get("image_collection_path")
    m4b_image_collection_path = sound_line_data.get("m4b_image_collection_path")
    image_filename = sound_line_data.get("image_filename")
    start_time = sound_line_data.get("start_time")

    video_source_path = get_source_path_from_full_filename(full_source_filename)
    if not video_source_path:
        log_image(f"video source path not found, returning")
        return ""

    _, ext = os.path.splitext(video_source_path)
    video_extension = ext.lower()


    # generate image and get its path
    image_path = run_ffmpeg_extract_image_command(
        video_source_path,
        start_time,
        image_collection_path,
        m4b_image_collection_path,
        image_height
    )

    log_image(f"No image found, extracting from source: {image_path}")

    # add formatting to image
    if image_path:
        if video_extension == ".m4b":
            embed_image = f'<img src="{os.path.basename(m4b_image_collection_path)}">'
        else:
            embed_image = f'<img src="{os.path.basename(image_filename)}">'

        log_image(f"add image: {embed_image}")
        return embed_image
    else:
        return ""

# returns a translation line based on overlapping timings from the target's sound line, also returns the translation subtitle file
def get_translation_line_and_subtitle_from_target_sound_line(target_sound_line, config, sound_line_data, note_type_name):
    if not target_sound_line:
        log_error("get_translation_line_from_sound_line received None sound_line.")
        return "", ""

    log_filename(f"extracting sound_line_data from target_sound_line: {target_sound_line}")
    if not sound_line_data:
        log_error(f"extract_sound_line_data returned None.")
        return "", ""

    translation_audio_track = config[note_type_name]["translation_audio_track"]
    translation_language_code = config[note_type_name]["translation_language_code"]
    start_time = sound_line_data["start_time"]
    end_time = sound_line_data["end_time"]
    full_source_filename = sound_line_data["full_source_filename"]
    subtitle_database = manage_database.get_database()

    # get translation subtitle file and the subtitle blocks that overlap timings with the sound line
    translation_subtitle_path = get_subtitle_file_from_database(full_source_filename, translation_audio_track, translation_language_code, config, subtitle_database, note_type_name)
    overlapping_translation_blocks = get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(translation_subtitle_path, start_time, end_time)

    # adds text from each block and formats it, remove curly braces, html formatting, etc.
    translation_line = "\n".join(block[3] for block in overlapping_translation_blocks)
    translation_line = re.sub(r"\{.*?}", "", translation_line)
    log_filename(f"getting translation line: {translation_line}, tl audio track/code: {translation_audio_track}/{translation_language_code}, path from database: {translation_subtitle_path}")

    return translation_line, translation_subtitle_path

# generates a new sound line with the blocks overlapping from another sound line
def get_new_timing_sound_line_from_target_sound_line(target_sound_line, config, audio_language_code, use_translation_data, note_type_name):
    if not target_sound_line:
        log_error(f"received None sound_line. ")
        return ""

    sound_line_data = extract_sound_line_data(target_sound_line)
    log_filename(f"extracting sound_line_data from target_sound_line: {target_sound_line}")
    if not sound_line_data:
        log_error(f"extract_sound_line_data returned None.")
        return ""

    timing_tracks_enabled = config[note_type_name]["timing_tracks_enabled"]
    if use_translation_data:
        if timing_tracks_enabled:
            timing_audio_track = config[note_type_name]["translation_timing_track"]
            timing_language_code = config[note_type_name]["translation_timing_code"]
        else:
            timing_audio_track = config[note_type_name]["translation_audio_track"]
            timing_language_code = config[note_type_name]["translation_language_code"]
    else:
        if timing_tracks_enabled:
            timing_audio_track = config[note_type_name]["target_timing_track"]
            timing_language_code = config[note_type_name]["target_timing_code"]
        else:
            timing_audio_track = config[note_type_name]["target_audio_track"]
            timing_language_code = config[note_type_name]["target_language_code"]


    filename_base = sound_line_data["filename_base"]
    source_file_extension = sound_line_data["source_file_extension"]
    full_source_filename = sound_line_data["full_source_filename"]

    subtitle_database = manage_database.get_database()

    timing_subtitle_path = get_subtitle_file_from_database(
        full_source_filename, timing_audio_track, timing_language_code, config, subtitle_database, note_type_name)

    overlapping_blocks = get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(
        timing_subtitle_path, sound_line_data["start_time"], sound_line_data["end_time"]
    )

    if not overlapping_blocks:
        log_error("No overlapping blocks found.")
        return ""

    try:
        first_start = to_hmsms_format(overlapping_blocks[0][1])
        last_end = to_hmsms_format(overlapping_blocks[-1][2])
        start_index = overlapping_blocks[0][0]
        end_index = overlapping_blocks[-1][0]
        audio_ext = config[note_type_name]["audio_ext"]
        subtitle_data = extract_subtitle_path_data(timing_subtitle_path)
        timing_language_code = subtitle_data["code"]

        log_filename(f"building new timing sound line with filename: {filename_base}, and extension: {source_file_extension}, audio langauge code: {audio_language_code}, timing langauge code: {timing_language_code}")
        timestamp, sound_line = build_filename_and_sound_line(filename_base, source_file_extension, audio_language_code, timing_language_code, first_start, last_end, start_index, end_index, None, audio_ext)

        log_filename(f"timing sound line: {sound_line}")
        return sound_line
    except Exception as e:
        log_error(f"Error generating sound line: {e}")
        return ""


def get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(subtitle_path, start_time, end_time):
    if not subtitle_path:
        log_error("Subtitle path is None.")
        return []

    db = manage_database.get_database()

    base = os.path.basename(subtitle_path)

    if '`' in base:
        base = base.split('`')[0]

    # Remove extension to get base filename only
    base_no_ext = os.path.splitext(base)[0]

    subtitle_data = extract_subtitle_path_data(subtitle_path)
    if subtitle_data is None:
        log_error("extract_subtitle_path_data returned None.")
        return []

    track = subtitle_data.get("track")
    code = subtitle_data.get("code")

    if track is None:
        track = "-1"
    if not code:
        code = "und"

    # Try exact match first (using base without extension)
    query = '''
    SELECT s.content, s.filename
    FROM subtitles s
    JOIN subtitle_access a ON s.filename = a.filename
    WHERE s.filename=? AND s.track=? AND s.language=?
    ORDER BY a.last_accessed DESC
    LIMIT 1
    '''
    params = [base_no_ext, str(track), code]
    cursor = db.execute(query, params)
    row = cursor.fetchone()

    # If no exact match, try LIKE query to find filename starting with base_no_ext (ignore extension differences)
    if row is None:
        like_pattern = base_no_ext + "%"
        query_like = '''
        SELECT s.content, s.filename
        FROM subtitles s
        JOIN subtitle_access a ON s.filename = a.filename
        WHERE s.filename LIKE ? AND s.track=? AND s.language=?
        ORDER BY a.last_accessed DESC
        LIMIT 1
        '''
        cursor = db.execute(query_like, (like_pattern, str(track), code))
        row = cursor.fetchone()

    # Optionally, update last_accessed after fetching
    if row:
        db.execute('''
        INSERT INTO subtitle_access(filename, last_accessed)
        VALUES (?, CURRENT_TIMESTAMP)
        ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
        ''', (row[1],))

    if row is None:
        log_error(f"No subtitle content found in DB for filename={base_no_ext} track={track} language={code}")
        return []


    content_json = row[0]

    try:
        blocks = json.loads(content_json)
    except Exception as e:
        log_error(f"Failed to parse subtitle JSON for {base_no_ext}: {e}")
        return []

    start_ms = time_hmsms_to_milliseconds(start_time)
    end_ms = time_hmsms_to_milliseconds(end_time)

    overlapping_blocks = []
    for block in blocks:
        if not block or len(block) < 3:
            continue
        try:
            sub_start_ms = time_hmsms_to_milliseconds(block[1])
            sub_end_ms = time_hmsms_to_milliseconds(block[2])
        except Exception:
            continue

        if sub_start_ms is None or sub_end_ms is None:
            log_error(f"Unrecognized timestamp format: {block}")
            continue

        if sub_start_ms > end_ms:
            break

        if sub_start_ms < end_ms and sub_end_ms > start_ms:
            overlapping_blocks.append(block)

    return overlapping_blocks


def get_source_path_from_full_filename(full_source_filename) -> str:
    all_exts = constants.audio_extensions + constants.video_extensions

    basename_no_ext = os.path.splitext(full_source_filename)[0]
    possible_bases = [basename_no_ext, basename_no_ext.replace("_", " ")]

    folder = constants.addon_source_folder

    # If input has a valid audio/video extension, check it directly first (in base folder)
    ext = os.path.splitext(full_source_filename)[1].lower()
    if ext in all_exts:
        path = os.path.join(folder, full_source_filename)
        log_image(f"searching path for video/audio: {path}")
        log_command(f"now checking: {path}")
        if os.path.exists(path):
            return path

    # Walk recursively through all subfolders except 'ignore'
    for root, dirs, files in os.walk(folder):
        if 'ignore' in root.split(os.sep):
            continue
        for base in possible_bases:
            for ext in all_exts:
                candidate = base + ext
                if candidate in files:
                    full_path = os.path.join(root, candidate)
                    log_image(f"searching path for video/audio: {full_path}")
                    log_command(f"now checking: {full_path}")
                    if os.path.exists(full_path):
                        return full_path

    log_error(f"No source file found for base name: {full_source_filename}")
    return ""

def get_subtitle_track_number_by_code(source_path, code):
    db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
    conn = manage_database.get_database()
    filename = os.path.basename(source_path)

    cursor = conn.execute('''
    SELECT m.track
    FROM media_tracks m
    JOIN subtitle_access a ON m.filename = a.filename
    WHERE m.filename = ? AND m.language = ? AND m.type = 'subtitle'
    ORDER BY a.last_accessed DESC
    LIMIT 1
    ''', (filename, code.lower()))

    row = cursor.fetchone()
    if row:
        # Update last_accessed for this access
        conn.execute('''
        INSERT INTO subtitle_access(filename, last_accessed)
        VALUES (?, CURRENT_TIMESTAMP)
        ON CONFLICT(filename) DO UPDATE SET last_accessed = CURRENT_TIMESTAMP
        ''', (filename,))
        return row[0]

    return None

def get_subtitle_code_by_track_number(source_path, track_number):
    _, ffprobe_exe = constants.get_ffmpeg_exe_path()
    try:
        cmd = [
            ffprobe_exe, "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json", source_path
        ]
        result = constants.silent_run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_command(f"[ffprobe subtitle code lookup]\ncmd: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")

        streams = json.loads(result.stdout).get("streams", [])
        if 1 <= int(track_number) <= len(streams):
            return streams[int(track_number) - 1].get("tags", {}).get("language", "")
        else:
            log_error(f"Invalid subtitle track number {track_number} for {source_path} — only {len(streams)} subtitle track(s) found.")
    except Exception as e:
        log_error(f"ffprobe error while reading subtitle code: {e}")
    return None

def get_subtitle_blocks_from_index_range_and_path(start_index, end_index, subtitle_path, keep_start, keep_end):
    log_filename(f"getting timing blocks, start_index {start_index},  end_index {end_index}, timing subtitle path: {subtitle_path}")

    if not subtitle_path:
        log_error("subtitle path is None")
        return []

    subtitle_data = extract_subtitle_path_data(subtitle_path)
    filename = subtitle_data["filename"]
    track = str(subtitle_data["track"])
    code = subtitle_data["code"]
    conn = manage_database.get_database()
    cursor = conn.cursor()

    if track is None or track == "None":
        track = "-1"
    if not code:
        code = "und"



    log_filename(f"searching for blocks with filename: {filename}, code: {code}, track: {track}")
    cursor.execute('''
    SELECT s.content
    FROM subtitles s
    JOIN subtitle_access a ON s.filename = a.filename
    WHERE s.filename = ? AND s.track = ? AND s.language = ?
    ORDER BY a.last_accessed DESC
    ''', (filename, track, code))
    row = cursor.fetchone()

    if row is None:
        log_error(f"No subtitle content found in DB for filename={filename} track={track} language={code}")
        return []

    content_json = row[0]

    try:
        blocks = json.loads(content_json)
    except Exception as e:
        log_error(f"Failed to parse subtitle JSON")
        return []

    total_blocks = len(blocks)

    log_filename(f"start index: {start_index}, end index: {end_index}, total blocks: {total_blocks}")

    if total_blocks == 0:
        log_error(f"no subtitle blocks returned")
        return []

    if start_index <= 0:
        showInfo("You've reached the first subtitle line.")
        return []

    if end_index > total_blocks:
        log_error(f"last subtitle line, end index: {end_index}, total blocks: {total_blocks}")
        showInfo("You've reached the last subtitle line.")

    if start_index > end_index:
        showInfo(f"Start index cannot be after end index: {start_index}-{end_index}.")
        return []

    usable_blocks = []
    if 0 <= start_index - 1 < len(blocks):
        log_error(f"starting block at index: {start_index - 1}, {blocks[start_index - 1]}")
    else:
        log_error(f"[warning] Invalid access attempt: start_index={start_index}, total_blocks={len(blocks)}")
        return []
    for i, raw_block in enumerate(blocks[start_index - 1:end_index]):
        if isinstance(raw_block, str):
            parsed = constants.format_subtitle_block(raw_block)
            if parsed:
                usable_blocks.append(parsed)
        elif isinstance(raw_block, list) and len(raw_block) == 4:
            usable_blocks.append(raw_block)

    if keep_start:
        usable_blocks[0][1] = keep_start

    if keep_end:
        usable_blocks[-1][2] = keep_end

    return usable_blocks


# write here
def get_target_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line, config, note_type_name):
    log_filename(f"getting block from sentence line: {sentence_line}")

    note_config = config.get(note_type_name, {})
    target_language_code = note_config.get("target_language_code")
    target_audio_track = str(note_config.get("target_audio_track", 0))



    if not target_language_code and target_audio_track == "0":
        log_error(f"Target language code and track not set for note type: '{note_type_name}'")
        return None, None

    sentence_line = sentence_line or ""
    normalized_sentence = constants.normalize_text(sentence_line)
    log_filename(f"Normalized sentence to match: '{normalized_sentence}'")

    subtitle_database = manage_database.get_database()
    cursor = subtitle_database.execute('''
        SELECT
            s.filename,
            s.language,
            s.track,
            s.content,
            COALESCE(a.last_accessed, '1970-01-01 00:00:00') AS last_accessed
        FROM subtitles s
        LEFT JOIN subtitle_access a ON s.filename = a.filename
        WHERE (s.language = 'und' AND s.track = '-1') OR s.language = ? OR s.track = ?
        ORDER BY last_accessed DESC, s.filename COLLATE NOCASE ASC
    ''', (target_language_code, target_audio_track))
    rows = cursor.fetchall()

    for db_filename, lang, trk, content_json, last_accessed in rows:
        log_filename(f"Checking subtitle file: {db_filename}, lang={lang}, track={trk}")
        try:
            raw_blocks = json.loads(content_json)
        except Exception as e:
            log_error(f"Failed to parse content for {db_filename}: {e}")
            continue

        usable_blocks = []
        for raw_block in raw_blocks:
            if isinstance(raw_block, str):
                parsed = constants.format_subtitle_block(raw_block)
                if parsed:
                    usable_blocks.append(parsed)
            elif isinstance(raw_block, list) and len(raw_block) == 4:
                usable_blocks.append(raw_block)

        normalized_lines = [constants.normalize_text(b[3]) for b in usable_blocks]

        if len(sentence_line) <= 10:
            max_window = max(1, len(sentence_line))
        elif len(sentence_line) <= 100:
            max_window = max(1, 10 + len(sentence_line) // 10)
        elif len(sentence_line) <= 1000:
            max_window = max(1, len(sentence_line) // 10)
        else:
            max_window = 100

        log_filename(f"search subtitle window length: {max_window}")

        joined_lines = normalized_lines

        for i in range(len(joined_lines) - max_window + 1):
            window = joined_lines[i:i + max_window]
            joined = ''.join(window)
            if normalized_sentence in joined:
                subtitle_database.execute(
                    "UPDATE subtitle_access SET last_accessed = CURRENT_TIMESTAMP WHERE filename = ?",
                    (db_filename,)
                )
                subtitle_database.commit()

                subtitle_name = f"{db_filename}"
                if lang != "und" or str(trk) != "-1":
                    subtitle_name += f"`track_{trk}`{lang}"
                subtitle_name += ".srt"
                actual_path = os.path.join(constants.addon_source_folder, subtitle_name)

                # search for the correct block if the subtitle line is smaller than the search window
                if i == 0:
                    start_index = joined.index(normalized_sentence)
                    pos = 0
                    for offset, line in enumerate(window):
                        next_pos = pos + len(line)
                        if start_index < next_pos:
                            return usable_blocks[i + offset], actual_path
                        pos = next_pos

                # otherwise the last block will contain the correct line
                print(f"i: {i}, max window: {max_window}")
                return usable_blocks[i + max_window - 1], actual_path

    log_command("No subtitle match found across blocks.")
    return None, None



# option to provide codes to choose what's displayed in the sentence line
def get_sound_sentence_line_from_subtitle_blocks_and_path(blocks, subtitle_path, sentence_code, timing_code, config, note_type_name):
    if not subtitle_path:
        log_error("Error: subtitle_path is None")
        return None, None

    if (not blocks) or (len(blocks) == 0):
        log_error(f"no blocks")
        return None, None

    if not (isinstance(blocks, (list, tuple)) and isinstance(blocks[0], (list, tuple))):
        blocks = [blocks]

    base = os.path.basename(subtitle_path)
    if '`' in base:
        parts = base.split('`')
        filename_with_ext = parts[0]
        filename_base, file_extension = os.path.splitext(filename_with_ext)
        file_extension = file_extension.lstrip(".")
    else:
        filename_base, file_extension = os.path.splitext(base)
        file_extension = file_extension.lstrip(".")
        filename_with_ext = f"{filename_base}.{file_extension}"

    log_filename(f"split filename: {filename_with_ext} from base: {base}, from sub path: {subtitle_path}\nextracted file extension: {file_extension}")

    start_index = blocks[0][0]
    end_index = blocks[-1][0]
    start_time = to_hmsms_format(blocks[0][1])
    end_time = to_hmsms_format(blocks[-1][2])

    audio_ext = config[note_type_name]["audio_ext"]
    subtitle_data = extract_subtitle_path_data(subtitle_path)


    normalize_audio = config[note_type_name]["normalize_audio"]
    if normalize_audio:
        lufs = config[note_type_name]["lufs"]
    else:
        lufs = None

    # gets codes if applicable
    if subtitle_data:
        if sentence_code and timing_code:
            code = sentence_code
        else:
            code = subtitle_data["code"]
            timing_code = None
    else:
        log_error(f"No subtitle data extracted from: {subtitle_path}")
        code = None
        timing_code = None


    log_filename(f"trying to get sourch path from filename_with_ext: {filename_with_ext}")
    log_filename(
        f"building sound line with filename: {filename_base}, and extension: {file_extension}, audio langauge code: {code}, timing langauge code: {timing_code}")

    timestamp, new_sound_line = build_filename_and_sound_line(filename_base, file_extension, code, timing_code, start_time, end_time, start_index, end_index, lufs, audio_ext)
    print(f"blocks: {blocks}")
    combined_text = "\n".join(b[3].strip() for b in blocks if len(b) > 3)
    log_filename(f"generated sound_line: {new_sound_line}\nsentence line: {combined_text}")

    return new_sound_line, combined_text

# todo: make more efficient by only searching files after the current file
# finds the location of the current sentence field, then uses the selected text to find the next line that
# contains the selection and re-generates every field
def get_next_matching_subtitle_block(sentence_line, selected_text, sound_line, config, sound_line_data, note_type_name):
    log_filename(f"extracting sound_line_data from sound_line: {sound_line}")

    if not sound_line_data:
        log_error(f"no sound_line_data extracted from {sound_line}")
        return None, None

    target_index = sound_line_data["start_index"]
    filename_base = sound_line_data["filename_base"]
    track = config[note_type_name]["target_subtitle_track"]
    code = config[note_type_name]["target_language_code"]
    normalized_target_text = constants.normalize_text(selected_text or sentence_line)
    log_filename(f"Searching for: {normalized_target_text}")

    def search_blocks(after_current: bool):
        found_current = not after_current

        db = manage_database.get_database()
        rows = db.execute('''
            SELECT s.filename, s.language, s.track, s.content
            FROM subtitles s
            JOIN subtitle_access a ON s.filename = a.filename
        ''').fetchall()

        def priority(lang, trk):
            trk = str(trk)
            if lang == "und" and trk == "-1":
                return 0
            if lang == code:
                return 1
            if trk == str(track):
                return 2
            return 3

        # only search files with target code or track
        candidates = [
            (fn, lang, trk, content_json)
            for fn, lang, trk, content_json in sorted(rows, key=lambda row: priority(row[1], row[2]))
            if priority(lang, trk) < 3
        ]

        for fn, lang, trk, content_json in candidates:
            log_filename(f"checking for next result: {fn}, {lang}, {trk}")
            base_candidate, _ = os.path.splitext(fn)

            # convert to blocks
            try:
                raw_blocks = json.loads(content_json)
            except Exception as e:
                log_error(f"Failed to parse {fn}: {e}")
                continue

            # normalize and format
            usable = []
            for rb in raw_blocks:
                if isinstance(rb, list) and len(rb) == 4:
                    usable.append(rb)
                elif isinstance(rb, str):
                    parsed = constants.format_subtitle_block(rb)
                    if parsed:
                        usable.append(parsed)

            # scan through blocks
            for b in usable:
                block_idx = int(b[0])
                text = b[3]
                if not found_current:
                    if base_candidate == filename_base and block_idx == target_index:
                        found_current = True
                    continue

                subtitle_filename = f"{fn}`track_{track}`{code}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                if normalized_target_text in constants.normalize_text(text):
                    log_filename(f"Match found in block {block_idx} of {base_candidate}, path is: {subtitle_path}")
                    return b, subtitle_path

        return None, None

    # first pass: after the current block
    result, path = search_blocks(after_current=True)
    if result:
        return result, path

    # wrap‑around: search from the top
    log_command("Wrapping to start of subtitle files...")
    return search_blocks(after_current=False)


def run_ffmpeg_extract_image_command(source_path, image_timestamp, image_collection_path, m4b_image_collection_path, image_height) -> str:
    if os.path.exists(m4b_image_collection_path):
        log_image(f"image already exists: {m4b_image_collection_path}")
        return m4b_image_collection_path

    out_dir = os.path.dirname(image_collection_path)
    ffmpeg_path, _ = constants.get_ffmpeg_exe_path()
    os.makedirs(out_dir, exist_ok=True)
    if not os.access(out_dir, os.W_OK):
        log_error(f"Cannot write to directory: {out_dir}")
        return ""

    if source_path.lower().endswith(".m4b"):
        cmd = [
            ffmpeg_path, "-y",
            "-i", source_path,
            "-map", "0:v",
            "-codec", "copy",
            "-loglevel", "error",
            m4b_image_collection_path
        ]
        log_command(f"Extracting cover from m4b:\n{' '.join(cmd)}")
        result = constants.silent_run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != 0:
            log_error(f"FFmpeg cover extraction failed:\n{result.stderr}")
            return ""
        if os.path.exists(m4b_image_collection_path):
            log_command(f"Extracted cover: {m4b_image_collection_path}")
            return m4b_image_collection_path
        else:
            log_error("Cover extraction failed: output file not found")
            return ""

    timestamp = convert_hmsms_to_ffmpeg_time_notation(image_timestamp)
    cmd = [
        ffmpeg_path, "-y",
        "-ss", timestamp,
        "-i", source_path,
        "-frames:v", "1",
        "-q:v", "15",
        "-vf", f"scale=-2:min(ih\\,{image_height})",
        image_collection_path
    ]

    log_image(f"Extracting image:\n{' '.join(cmd)}")
    result = constants.silent_run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        log_error(f"FFmpeg image extraction failed:\n{result.stderr}")
        return ""

    log_command(f"Extracted image: {image_collection_path}")
    return image_collection_path

def create_ffmpeg_extract_audio_command(source_path, start_time, end_time, collection_path, sound_line, config, sound_line_data, use_translation_data, note_type_name) -> list:
    if not source_path:
        log_error(f"source path is null")
        return []

    log_command(f"FFmpeg source path: {source_path}")
    log_command(f"FFmpeg sound line: {sound_line}")

    lufs = config.get(note_type_name, {}).get("lufs", -14)
    bitrate = config.get(note_type_name, {}).get("bitrate", 192)
    normalize_audio = config.get(note_type_name, {}).get("normalize_audio", True)
    target_code = config.get(note_type_name, {}).get("target_language_code", "")
    translation_code = config.get(note_type_name, {}).get("translation_language_code", "")
    target_track = config.get(note_type_name, {}).get("target_audio_track", "")
    translation_track = config.get(note_type_name, {}).get("translation_audio_track", "")
    selected_tab_index = config.get(note_type_name, {}).get("selected_tab_index", 0)
    log_filename(f"Extracting sound_line_data from sound_line: {sound_line}")

    ffmpeg_path, ffprobe_path = constants.get_ffmpeg_exe_path()
    start = convert_hmsms_to_ffmpeg_time_notation(start_time)
    end = convert_hmsms_to_ffmpeg_time_notation(end_time)
    duration_sec = time_hmsms_to_seconds(end) - time_hmsms_to_seconds(start)
    if duration_sec <= 0:
        log_error(f"End time must be after start time: {start}, {end}")
        return []

    # get or add start time to database
    conn = manage_database.get_database()
    filename = os.path.basename(source_path)
    delay_ms = get_audio_start_time_ms_from_db(filename, conn)

    if delay_ms is None:
        delay_ms = get_audio_start_time_ms(source_path)
        set_audio_start_time_ms_in_db(filename, delay_ms, conn)

    base, file_extension = os.path.splitext(collection_path)
    ext_no_dot = file_extension[1:].lower()

    if ext_no_dot == "mp3":
        codec = "libmp3lame"
        output_ext = ".mp3"
    elif ext_no_dot == "opus":
        codec = "libopus"
        output_ext = ".opus"
    elif ext_no_dot == "flac":
        codec = "flac"
        output_ext = ".flac"
    else:
        codec = "copy"
        output_ext = file_extension

    new_collection_path = f"{base}{output_ext}"

    # Determine which audio track to use
    code = translation_code if use_translation_data else target_code
    track = translation_track if use_translation_data else target_track

    audio_track_index = None
    try:
        result = constants.silent_run(
            [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index:stream_tags=language", "-of", "json", source_path],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log_command(f"[ffprobe audio stream scan]\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        info = json.loads(result.stdout)
        streams = info.get("streams", [])

        if not info:
            log_error(f"no info from file: {source_path}")
            return []

        if selected_tab_index == 0:
            for stream in streams:
                if stream.get("tags", {}).get("language", "").lower() == code.lower():
                    audio_track_index = stream["index"]
                    break

        if audio_track_index is None:
            if 1 <= track <= len(streams):
                audio_track_index = streams[track - 1]["index"]

        if audio_track_index is None and streams:
            basename = os.path.basename(source_path)
            if not code:
                code = "und"
            showInfo(f"No audio track found for '{basename}' with the code '{code}' or track '{track}'.")
            return []

    except Exception as e:
        log_error(f"Error selecting audio track: {e}")
        audio_track_index = 0

    # --- Retrieve delay_ms for this audio stream from DB ---
    conn = manage_database.get_database()
    filename = os.path.basename(source_path)

    cursor = conn.execute(
        "SELECT delay_ms FROM media_audio_start_times WHERE filename=? AND audio_track=?",
        (filename, audio_track_index)
    )
    row = cursor.fetchone()

    if row:
        delay_ms = row[0]
    else:
        delay_ms = constants.get_audio_start_time_ms_for_track(source_path, audio_track_index)
        conn.execute(
            "INSERT OR REPLACE INTO media_audio_start_times (filename, audio_track, delay_ms) VALUES (?, ?, ?)",
            (filename, audio_track_index, delay_ms)
        )
        conn.commit()

    # --- build ffmpeg command using delay_ms ---
    cmd = [
        ffmpeg_path, "-y",
        "-ss", start,
        "-i", source_path,
        "-map", f"0:{audio_track_index}",
        "-t", str(duration_sec),
    ]

    filters = []
    if delay_ms > 0:
        filters.append(f"adelay={delay_ms}|{delay_ms}")

    if normalize_audio and int(lufs) < 1:
        filters.append(f"loudnorm=I={lufs}:TP=-1.5:LRA=11")

    if filters:
        cmd += ["-af", ",".join(filters)]

    cmd += ["-c:a", codec]

    if codec in ("libmp3lame", "libopus") and bitrate:
        bitrate_val = f"{bitrate}k" if codec == "libmp3lame" else str(bitrate * 1000)
        cmd += ["-b:a", bitrate_val]

    cmd.append(new_collection_path)

    log_command(f"[FFmpeg command]\n{' '.join(cmd)}")
    return cmd


def ffmpeg_extract_full_audio(source_file_path, config, note_type_name) -> str:
    ffmpeg_path, _ = constants.get_ffmpeg_exe_path()
    audio_ext = config[note_type_name]["audio_ext"]

    base, _ = os.path.splitext(source_file_path)
    output_path = base + f".{audio_ext}"

    delay_ms = get_audio_start_time_ms(source_file_path)

    cmd = [
        ffmpeg_path, "-y",
        "-i", source_file_path,
        "-map", "0:a:0"
    ]

    if delay_ms != 0:
        adelay_str = f"{delay_ms}|{delay_ms}"
        cmd += ["-af", f"adelay={adelay_str}"]

    cmd += ["-b:a", "192k", output_path]

    log_command(f"[FFmpeg extract full audio]\n{' '.join(cmd)}")

    try:
        result = constants.silent_run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != 0:
            log_error(f"FFmpeg failed with return code {result.returncode}:\n{result.stderr}")
            return ""
        log_command(f"FFmpeg stdout:\n{result.stdout}")
        log_command(f"Converted to {audio_ext}: {output_path}")
        return output_path
    except Exception as e:
        log_error(f"FFmpeg conversion error: {e}")
        return ""


def create_just_normalize_audio_command(source_path, config, note_type_name):
    lufs = config[note_type_name]["lufs"]
    bitrate = config[note_type_name]["bitrate"]

    ffmpeg_path, _ = constants.get_ffmpeg_exe_path()

    base, file_extension = os.path.splitext(source_path)
    ext_no_dot = file_extension[1:].lower()

    if lufs != -1:
        new_collection_path = f"{base}`{lufs}LUFS{file_extension}"
        filter_args = ["-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11"]
    else:
        new_collection_path = f"{base}.{file_extension}"
        filter_args = []

    cmd = [ffmpeg_path, "-y", "-i", source_path] + filter_args

    if ext_no_dot == "mp3":
        cmd += ["-c:a", "libmp3lame"]
        if bitrate:
            cmd += ["-b:a", f"{bitrate}k"]
    elif ext_no_dot == "opus":
        cmd += ["-c:a", "libopus"]
        if bitrate:
            cmd += ["-b:a", str(bitrate * 1000)]
    elif ext_no_dot == "flac":
        cmd += ["-c:a", "flac"]
    else:
        log_error(f"Unsupported audio format: {ext_no_dot}")
        return ""

    cmd.append(new_collection_path)
    return cmd




# convert and detect

def detect_format(sound_line: str):
    if not sound_line:
        return None

    line = sound_line.strip()
    if constants.BACKTICK_PATTERN.match(line):
        return "backtick"
    else:
        return "unknown"

def is_backtick_format(sound_line: str) -> bool:
    return '`' in sound_line and '-' in sound_line and ']' in sound_line


def get_audio_start_time_ms_from_db(filename, conn):
    cursor = conn.execute(
        "SELECT delay_ms FROM media_audio_start_times WHERE filename = ?",
        (filename,)
    )
    row = cursor.fetchone()
    return row[0] if row else None

def set_audio_start_time_ms_in_db(filename, delay_ms, conn):
    conn.execute(
        "INSERT OR REPLACE INTO media_audio_start_times (filename, delay_ms) VALUES (?, ?)",
        (filename, delay_ms)
    )
    conn.commit()


# todo deprecate
def get_audio_start_time_ms(source_file_path: str) -> int:
    if not os.path.exists(source_file_path):
        log_error(f"[skip] file missing: {source_file_path}")
        return 0

    _, ffprobe_path = constants.get_ffmpeg_exe_path()
    cmd = [
        ffprobe_path, "-v", "error",
        "-select_streams", "a:0",
        "-show_packets", "-read_intervals", "0%+#5",
        "-print_format", "compact", source_file_path
    ]
    try:
        result = constants.silent_run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_command(f"ffprobe output: {result.stdout.strip()}")
        match = re.search(r"pts_time=(\d+(?:\.\d+)?)", result.stdout)
        return round(float(match.group(1)) * 1000) if match else 0
    except Exception as e:
        log_error(f"ffprobe failed: {e}")
        return 0



def timestamp_to_dot_format(ts: str) -> str:
    ts = ts.replace(',', '.')
    parts = ts.split(':')
    if len(parts) != 3:
        log_error(f"Invalid timestamp format for conversion: {ts}")
        return ts
    hours = parts[0]
    minutes = parts[1]
    sec_millis = parts[2].split('.')
    if len(sec_millis) != 2:
        log_error(f"Invalid seconds.milliseconds format for conversion: {parts[2]}")
        return ts
    seconds, milliseconds = sec_millis
    return f"{hours}.{minutes}.{seconds}.{milliseconds}"


def time_srt_to_milliseconds(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def to_hmsms_format(ts) -> str:
    if isinstance(ts, int):
        hours = ts // (3600 * 1000)
        ts %= (3600 * 1000)
        minutes = ts // (60 * 1000)
        ts %= (60 * 1000)
        seconds = ts // 1000
        millis = ts % 1000
        return f"{hours:02d}h{minutes:02d}m{seconds:02d}s{millis:03d}ms"

    ts = ts.strip()
    parts = []

    if '.' in ts and ts.count('.') == 3:
        parts = ts.split('.')
    elif ':' in ts and ',' in ts:
        time_part, ms_part = ts.split(',')
        hms = time_part.split(':')
        if len(hms) == 3:
            parts = hms + [ms_part]
    elif ':' in ts and '.' in ts:
        time_part, ms_part = ts.split('.')
        hms = time_part.split(':')
        if len(hms) == 3:
            parts = hms + [ms_part]

    if len(parts) == 4:
        h, m, s, ms = parts
        return f"{int(h):02d}h{int(m):02d}m{int(s):02d}s{int(ms):03d}ms"

    log_error(f"Invalid timestamp format: {ts}")
    return ts


def convert_hmsms_to_ffmpeg_time_notation(t: str):
    hmsms_match = re.match(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms", t)
    if hmsms_match:
        h, m, s, ms = hmsms_match.groups()
        return f"{h}:{m}:{s}.{ms}"

    parts = t.strip().split(".")
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"

    log_error(f"Unrecognized timestamp format: {t}")

def time_hmsms_to_seconds(t):
    h, m, s = t.split(':')
    s, ms = (s.split(',') if ',' in s else s.split('.'))
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def time_hmsms_to_milliseconds(ts: str):
    pattern_hmsms = re.compile(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms")
    pattern_colon = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")

    match = pattern_hmsms.match(ts)
    if match:
        h, m, s, ms = match.groups()
    else:
        match = pattern_colon.match(ts)
        if match:
            h, m, s, ms = match.groups()
        elif '.' in ts:
            parts = ts.split('.')
            if len(parts) != 4:
                log_error(f"Unrecognized timestamp format: {ts}")
                return None
            h, m, s, ms = parts
        else:
            log_error(f"Unrecognized timestamp format: {ts}")
            return None

    total_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    return total_ms


def build_filename_and_sound_line(filename_base, source_file_extension, audio_code, timing_code, first_start, last_end, start_index, end_index, lufs, audio_ext):

    if (not "." in source_file_extension) and source_file_extension:
        source_file_extension = f".{source_file_extension}"

    full_filename = f"{filename_base}{source_file_extension}"
    if full_filename.endswith(".srt"):
        full_filename = full_filename[:-4]

    if audio_code == timing_code:
        timing_code = None

    timestamp = full_filename

    if timing_code:
        timestamp += f"`{audio_code}-{timing_code}"
    elif audio_code:
        timestamp += f"`{audio_code}"

    timestamp += f"`{first_start}-{last_end}`{start_index}-{end_index}"

    if lufs:
        timestamp += f"`{lufs}LUFS.{audio_ext}"
    else:
        timestamp += f".{audio_ext}"

    sound_line = f"[sound:{timestamp}]"

    return timestamp, sound_line


def get_altered_sound_data(sound_line, lengthen_start_ms, lengthen_end_ms, config, sound_line_data, note_type_name) -> dict:
    normalize_audio = config[note_type_name]["normalize_audio"]

    log_filename(f"extracting sound_line_data from sound_line: {sound_line}")
    if not sound_line_data:
        log_error(f"sound line data is empty for: {sound_line}")
        return {}

    orig_start_ms = time_hmsms_to_milliseconds(sound_line_data["start_time"])
    orig_end_ms = time_hmsms_to_milliseconds(sound_line_data["end_time"])

    start_index = sound_line_data["start_index"]
    end_index = sound_line_data["end_index"]

    new_start_ms = max(0, orig_start_ms - lengthen_start_ms)
    new_end_ms = max(0, orig_end_ms + lengthen_end_ms)

    if new_end_ms <= new_start_ms:
        log_error(f"Invalid time range: {to_hmsms_format(new_start_ms)}-{to_hmsms_format(new_end_ms)}")
        showInfo(f"Invalid time range: {to_hmsms_format(new_start_ms)}-{to_hmsms_format(new_end_ms)}.\nPadded timings may be the problem.")
        return {
            "new_sound_line": sound_line,
            "new_start_time": None,
            "new_end_time": None,
            "new_filename": None,
            "new_path": None,
            "old_path": None,
            "filename_base": None,
            "full_source_filename": None,
        }

    new_start_time = to_hmsms_format(new_start_ms)
    new_end_time = to_hmsms_format(new_end_ms)
    filename_base = sound_line_data["filename_base"]
    full_source_filename = sound_line_data["full_source_filename"]
    source_file_extension = sound_line_data["source_file_extension"]
    lang_code = sound_line_data.get("lang_code")

    if normalize_audio:
        lufs = config[note_type_name]["lufs"]
    else:
        lufs = None

    sound_file_extension = sound_line_data["sound_file_extension"]
    timing_lang_code = sound_line_data["timing_lang_code"]

    log_filename(f"building altered sound line with filename: {filename_base}, and extension: {source_file_extension}, audio langauge code: {lang_code}, timing langauge code: {timing_lang_code}")

    new_filename, _ = build_filename_and_sound_line(filename_base, source_file_extension, lang_code, timing_lang_code, new_start_time, new_end_time, start_index, end_index, lufs, sound_file_extension)
    new_filename = constants.format_anki_safe_filename(new_filename, revert=False)
    if not new_filename:
        return None

    new_path = os.path.join(constants.get_collection_dir(), new_filename)
    new_sound_line = f"[sound:{new_filename}]"
    old_path = sound_line_data["collection_path"]

    log_filename(
    f"sending to extract sound line: {sound_line}\n"
    f"full source filename from sound_line_data: {full_source_filename}\n"
    f"new_filename: {new_filename}")

    return {
        "new_start_time": new_start_time,
        "new_end_time": new_end_time,
        "new_filename": new_filename,
        "new_sound_line": new_sound_line,
        "new_path": new_path,
        "old_path": old_path,
        "filename_base": filename_base,
        "full_source_filename": full_source_filename,
    }

def alter_sound_file_times(altered_data, sound_line, config, use_translation_data, note_type_name):
    if not altered_data:
        log_error("altered sound_line_data is empty")
        return None

    if not sound_line:
        log_error("sound line is empty")
        return None

    if not altered_data["old_path"]:
        return None

    if os.path.exists(altered_data["old_path"]):
        send2trash(altered_data["old_path"])

    full_source_filename = altered_data["full_source_filename"]
    log_filename(f"full source filename4: {full_source_filename}")
    source_path = get_source_path_from_full_filename(full_source_filename)
    if not source_path:
        log_error(f"Source file not found for: {full_source_filename}.")
        return None

    cmd = create_ffmpeg_extract_audio_command(
        source_path,
        altered_data["new_start_time"],
        altered_data["new_end_time"],
        altered_data["new_path"],
        sound_line,
        config,
        extract_sound_line_data(altered_data["new_sound_line"]),
        use_translation_data,
        note_type_name
    )

    if not cmd:
        log_error(f"command was not generated")
        return None

    # run without freezing anki
    def run_ffmpeg():
        try:
            log_filename(f"generating new sound file: {altered_data['new_path']}")
            log_filename(f"Running FFmpeg command: {' '.join(cmd)}")
            result = constants.silent_run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != 0:
                log_error(f"FFmpeg failed:\n{result.stderr}")
                return
            log_command(f"FFmpeg output:\n{result.stdout}")
        except Exception as e:
            log_error(f"FFmpeg error: {e}")
            return

        if not os.path.exists(altered_data["new_path"]):
            log_error(f"Expected output file not found: {altered_data['new_path']}")

    # wait until file is generated to return
    def run_and_wait():
        run_ffmpeg()
        for _ in range(80):
            if os.path.exists(altered_data["new_path"]):
                break
            time.sleep(0.05)

    thread = threading.Thread(target=run_and_wait)
    thread.start()
    thread.join(timeout=4)  # won't freeze Anki UI
    return f"[sound:{altered_data['new_filename']}]"

