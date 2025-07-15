import os
import shutil
import subprocess
import json
import html
import re
from aqt.utils import showInfo
from send2trash import send2trash
import constants
import manage_database

from constants import (
    log_filename,
    log_error,
    log_image,
    log_command,
)













# get sound_line_data


def get_collection_dir():
    from aqt import mw
    if not mw or not mw.col:
        print("Collection is not loaded yet.")
    return mw.col.media.dir()

def extract_sound_line_data(sound_line):
    format_type = detect_format(sound_line)

    if format_type == "backtick":
        match = constants.BACKTICK_PATTERN.match(sound_line)
        if not match:
            log_error("no match for backtick")
            return None

        groups = match.groupdict()
        filename_base = groups["filename_base"]
        source_file_extension = groups.get("source_file_extension") or ""
        lang_code = groups.get("lang_code") or ""
        sha = groups.get("sha") or ""
        start_time = groups["start_time"]
        end_time = groups["end_time"]
        subtitle_range = groups["subtitle_range"]
        sound_file_extension = groups["sound_file_extension"]
        normalize_tag = groups.get("normalize_tag") or ""

        start_index, end_index = map(int, subtitle_range.split("-"))
        full_source_filename = f"{filename_base}{source_file_extension}"
        meta_parts = [full_source_filename]

        if lang_code:
            meta_parts.append(lang_code)
        if sha:
            meta_parts.append(sha)
        meta_parts.append(f"{start_time}-{end_time}")
        meta_parts.append(subtitle_range)
        if normalize_tag:
            meta_parts.append(normalize_tag)

        timestamp_filename = "`".join(meta_parts) + f".{sound_file_extension}"
        timestamp_filename_no_normalize = "`".join(meta_parts[:-1 if normalize_tag else None])

        audio_collection_path = os.path.join(get_collection_dir(), timestamp_filename)

        m4b_image_filename = f"{filename_base}.{sound_file_extension}.jpg"
        image_filename = f"{filename_base}.{sound_file_extension}`{start_time}.jpg"
        image_collection_path = os.path.join(get_collection_dir(), image_filename)
        m4b_image_collection_path = os.path.join(get_collection_dir(), m4b_image_filename)

        log_filename(
            f"extracting sound_line_data from: {sound_line}\n"
            f"format detected: {format_type}\n"
            f"full_source_filename: {full_source_filename}\n"
            f"timestamp filename: {timestamp_filename}\n"
        )
        log_image(f"image collection path: {image_collection_path}")

        return {
            "filename_base": filename_base,
            "source_file_extension": source_file_extension,
            "lang_code": lang_code,
            "sha": sha,
            "start_time": start_time,
            "end_time": end_time,
            "start_index": start_index,
            "end_index": end_index,
            "normalize_tag": normalize_tag,
            "sound_file_extension": sound_file_extension,
            "full_source_filename": full_source_filename,
            "timestamp_filename": timestamp_filename,
            "timestamp_filename_no_normalize": timestamp_filename_no_normalize,
            "collection_path": audio_collection_path,
            "image_filename": image_filename,
            "m4b_image_filename": m4b_image_filename,
            "image_collection_path": image_collection_path,
            "m4b_image_collection_path": m4b_image_collection_path,
        }

    # fallback if not backtick
    if not sound_line:
        log_error("extract_sound_line_data received None or empty string")
        return None

    return None

def extract_config_data():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print(f"Config file not found at {config_path}")

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

    values = [config.get(k) for k in keys]
    missing = [k for k, v in zip(keys, values) if v is None]

    if missing:
        log_error(f"Warning: Missing required config field(s): {missing}")
        showInfo("Please assign fields to your note type in the menu.\n\nMissing fields:\n" + "\n".join(missing))
        return None

    # Warn specifically if any track values are set to 0
    track_keys = [
        "target_audio_track", "target_subtitle_track",
        "translation_audio_track", "translation_subtitle_track",
        "target_timing_track", "translation_timing_track"
    ]
    zero_tracks = [k for k in track_keys if config.get(k) == 0]
    if zero_tracks:
        showInfo("Please set a valid track number.\n" + "\n".join(zero_tracks))
        log_error(f"Track fields set to 0: {zero_tracks}")
        return None

    return dict(zip(keys, values))

def get_field_key_from_label(note_type_name: str, label: str, config: dict) -> str:
    mapped_fields = config["mapped_fields"][note_type_name]
    for field_key, mapped_label in mapped_fields.items():
        if mapped_label == label:
            return field_key
    if label == "Target Subtitle Line":
        log_error(f"could not find Target Subtitle Line in note_type {note_type_name}, mapped field: {mapped_fields}, mapped fields items {mapped_fields.items()}")
    return ""

def extract_subtitle_path_data(subtitle_path):
    if not subtitle_path:
        log_error("subtitle_path is None")
        return None

    subtitle_filename = os.path.basename(subtitle_path)
    pattern = r"^(.*?)`track_(\d+)`([a-z]{2,3})\.(\w+)$"
    match = re.match(pattern, subtitle_filename, re.IGNORECASE)
    if not match:
        return None

    filename, track, code, extension = match.groups()
    return {
        "filename": filename,
        "track": int(track),
        "code": code.lower(),
        "extension": extension.lower()
    }

def get_subtitle_file_from_database(filename, track, code, config, database):
    def find_subtitle():
        selected_tab_index = config["selected_tab_index"]
        translation_language_code = config["translation_language_code"]
        log_filename(f"received filename: {filename}, track/code: {track}/{code}")
        source_path = get_source_path_from_full_filename(filename)

        if not os.path.exists(source_path):
            log_error(f"Source video not found: {source_path}")
            return None

        if not code or code.lower() == "none":
            log_error(f"Invalid subtitle language code: {code!r}")
            return None

        cursor = database.cursor()

        # Try exact match
        log_filename(f"trying exact match")
        query = "SELECT 1 FROM subtitles WHERE filename = ? AND track = ? AND language = ? LIMIT 1"
        cursor.execute(query, (filename, str(track), code))
        result = cursor.fetchone()
        if result:
            tagged_subtitle_file = f"{filename}`track_{track}`{code}.srt"
            tagged_subtitle_path = os.path.join(constants.addon_source_folder, tagged_subtitle_file)
            if os.path.exists(tagged_subtitle_path):
                log_filename(f"tagged_subtitle_path: {tagged_subtitle_path}")
                return tagged_subtitle_path

        # Try matching basename if translation and target are not same
        if code != translation_language_code:
            basename_subtitle_file = f"{filename}.srt"
            basename_subtitle_path = os.path.join(constants.addon_source_folder, basename_subtitle_file)
            if os.path.exists(basename_subtitle_path):
                log_filename(f"basename_subtitle_path: {basename_subtitle_path}")
                return basename_subtitle_path

        like_pattern = f"{filename}%"

        if selected_tab_index == 0:
            query = "SELECT filename, track, language FROM subtitles WHERE filename LIKE ? AND language = ?"
            cursor.execute(query, (like_pattern, code))
            row = cursor.fetchone()
            if row:
                base_filename, found_track, found_code = row
                subtitle_filename = f"{base_filename}`track_{found_track}`{found_code}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                log_filename(f"[tab 0] subtitle_path (by code): {subtitle_path}")
                return subtitle_path

        query = "SELECT filename, track, language FROM subtitles WHERE filename LIKE ?"
        cursor.execute(query, (like_pattern,))
        rows = cursor.fetchall()
        for db_filename, db_track, db_lang in rows:
            if db_filename.startswith(filename) and f"`track_{track}`" in db_filename:
                subtitle_filename = f"{db_filename}`track_{track}`{db_lang}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                log_filename(f"[tab {selected_tab_index}] subtitle_path (by track): {subtitle_path}")
                return subtitle_path

        if selected_tab_index != 0:
            query = "SELECT filename, track, language FROM subtitles WHERE filename LIKE ? AND language = ?"
            cursor.execute(query, (like_pattern, code))
            row = cursor.fetchone()
            if row:
                base_filename, found_track, found_code = row
                subtitle_filename = f"{base_filename}`track_{found_track}`{found_code}.srt"
                subtitle_path = os.path.join(constants.addon_source_folder, subtitle_filename)
                log_filename(f"[tab 1+] subtitle_path (fallback by code): {subtitle_path}")
                return subtitle_path

        return None

    # === Step 1: Try finding subtitle
    path = find_subtitle()
    if path:
        return path

    # === Step 2: Extract subtitle files
    log_error("Subtitle not found; extracting and retrying...")
    source_path = get_source_path_from_full_filename(filename)
    extract_subtitle_files(source_path, track, code, config)

    # === Step 3: Update database and retry
    manage_database.update_database()
    path = find_subtitle()
    if path:
        return path

    log_error(f"No matching subtitle file found for:\n{filename}|`track_{track}`|{code}")
    if config["selected_tab_index"] == 0:
        log_error(f"Both the code `{code}` and track `track_{track}` do not exist for the file: {filename}\nPlease check your settings.")
    return None


# def get_subtitle_path_and_code_from_full_filename_track_and_code(filename, track, code, config):
#     filename_base, _ = os.path.splitext(filename)
#     selected_tab_index = config["selected_tab_index"]
#     translation_language_code = config["translation_language_code"]
#     log_filename(f"received filename: {filename}, track/code: {track}/{code}")
#     source_path = get_source_path_from_full_filename(filename)
#
#     if not os.path.exists(source_path):
#         log_error(f"Source video not found: {source_path}")
#         return None
#
#     if not code or code.lower() == "none":
#         log_error(f"Invalid subtitle language code: {code!r}")
#         return None
#
#     extract_subtitle_files(source_path, track, code, config)
#
#     # 1. Try exact match
#     tagged_subtitle_file = f"{filename_base}`track_{track}`{code}.srt"
#     tagged_subtitle_path = os.path.join(addon_source_folder, tagged_subtitle_file)
#     if os.path.exists(tagged_subtitle_path):
#         log_filename(f"tagged_subtitle_path: {tagged_subtitle_path}")
#         return tagged_subtitle_path
#
#     # # try name matching basename
#     # if not code == translation_language_code:
#     #     basename_subtitle_file = f"{filename_base}.srt"
#     #     basename_subtitle_path = os.path.join(addon_source_folder, basename_subtitle_file)
#     #     if os.path.exists(basename_subtitle_path):
#     #         log_filename(f"basename_subtitle_path: {basename_subtitle_path}")
#     #         return basename_subtitle_path
#
#     # 2. Fallback: match by code or track
#     log_command(f"fallback, looking for {code} or {track}")
#     if selected_tab_index == 0:
#         for file in os.listdir(addon_source_folder):
#             if file.startswith(filename_base) and file.endswith(f"{code}.srt"):
#                 subtitle_path = os.path.join(addon_source_folder, file)
#                 log_filename(f"subtitle_path: {subtitle_path}")
#                 return subtitle_path
#
#     track_str = f"`track_{track}`"
#     for file in os.listdir(addon_source_folder):
#         starts = file.startswith(filename)
#         has_track = track_str in file
#         log_command(f"checking: {file}, starts with {filename}: {starts}, has_track: {has_track}")
#
#         if file.startswith(filename_base) and track_str in file:
#             subtitle_path = os.path.join(addon_source_folder, file)
#             log_filename(f"subtitle_path: {subtitle_path}")
#             return subtitle_path
#
#     log_error(f"No matching subtitle file found for:\n{filename}|{track_str}|{code}")
#     if selected_tab_index == 0:
#         showInfo(f"Both the code `{code}` and track {track_str} do not exist for the file: {filename}\nPlease check your settings.")
#     return None

def generate_image_line_from_sound_line(image_line, sound_line):
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

    image_path = run_ffmpeg_extract_image_command(
        video_source_path,
        start_time,
        image_collection_path,
        m4b_image_collection_path
    )

    log_image(f"No image found, extracting from source: {image_path}")

    if image_path:
        if video_extension == ".m4b":
            embed_image = f'<img src="{os.path.basename(m4b_image_collection_path)}">'
        else:
            embed_image = f'<img src="{os.path.basename(image_filename)}">'


        log_image(f"add image: {embed_image}")
        return embed_image
    else:
        showInfo("Could not add image")
        return ""

def get_translation_line_and_subtitle_from_target_sound_line(target_sound_line, config, sound_line_data):
    if not target_sound_line:
        log_error("get_translation_line_from_sound_line received None sound_line.")
        return "", ""

    log_filename(f"extracting sound_line_data from target_sound_line: {target_sound_line}")
    if not sound_line_data:
        log_error(f"extract_sound_line_data returned None.")
        return "", ""

    translation_audio_track = config["translation_audio_track"]
    translation_language_code = config["translation_language_code"]
    start_time = sound_line_data["start_time"]
    end_time = sound_line_data["end_time"]
    full_source_filename = sound_line_data["full_source_filename"]


    subtitle_database = manage_database.get_database()
    translation_subtitle_path = get_subtitle_file_from_database(full_source_filename, translation_audio_track, translation_language_code, config, subtitle_database)

    overlapping_translation_blocks = get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(translation_subtitle_path, start_time, end_time)

    translation_line = "\n\n".join(block[3] for block in overlapping_translation_blocks)
    translation_line = re.sub(r"\{.*?}", "", translation_line)
    translation_line = constants.format_text(translation_line.strip())
    log_filename(f"getting translation line: {translation_line}, tl audio track/code: {translation_audio_track}/{translation_language_code}, path from database: {translation_subtitle_path}")

    return translation_line, translation_subtitle_path

def get_new_timing_sound_line_from_target_sound_line(target_sound_line, config, audio_language_code, use_translation_data):
    if not target_sound_line:
        log_error(f"received None sound_line. ")
        return ""

    sound_line_data = extract_sound_line_data(target_sound_line)
    log_filename(f"extracting sound_line_data from target_sound_line: {target_sound_line}")
    if not sound_line_data:
        log_error(f"extract_sound_line_data returned None.")
        return ""

    timing_tracks_enabled = config["timing_tracks_enabled"]
    if use_translation_data:
        if timing_tracks_enabled:
            timing_audio_track = config["translation_timing_track"]
            timing_language_code = config["translation_timing_code"]
        else:
            timing_audio_track = config["translation_audio_track"]
            timing_language_code = config["translation_language_code"]
    else:
        if timing_tracks_enabled:
            timing_audio_track = config["target_timing_track"]
            timing_language_code = config["target_timing_code"]
        else:
            timing_audio_track = config["target_audio_track"]
            timing_language_code = config["target_language_code"]



    filename_base = sound_line_data["filename_base"]
    source_file_extension = sound_line_data["source_file_extension"]
    full_source_filename = sound_line_data["full_source_filename"]

    subtitle_database = manage_database.get_database()
    timing_subtitle_path = get_subtitle_file_from_database(
        full_source_filename, timing_audio_track, timing_language_code, config, subtitle_database)


    overlapping_blocks = get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(
        timing_subtitle_path, sound_line_data["start_time"], sound_line_data["end_time"]
    )

    if not overlapping_blocks:
        log_error("No overlapping blocks found.")
        return ""

    try:
        first_start = convert_timestamp_dot_to_hmsms(overlapping_blocks[0][1])
        last_end = convert_timestamp_dot_to_hmsms(overlapping_blocks[-1][2])
        start_index = overlapping_blocks[0][0]
        end_index = overlapping_blocks[-1][0]
        audio_ext = config["audio_ext"]

        timestamp = f"{filename_base}{source_file_extension}`{audio_language_code}`{first_start}-{last_end}`{start_index}-{end_index}.{audio_ext}"
        sound_line = f"[sound:{timestamp}]"
        log_filename(f"sound line: {sound_line}")
        return sound_line
    except Exception as e:
        log_error(f"Error generating sound line: {e}")
        return ""

def get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(subtitle_path, start_time, end_time):
    if not subtitle_path:
        log_error("Subtitle path is None.")
        return []

    print(f"[DEBUG] Provided subtitle path: {subtitle_path}")

    db = manage_database.get_database()
    base = os.path.basename(subtitle_path)
    print(f"[DEBUG] Initial basename: {base}")

    if '`' in base:
        base = base.split('`')[0]
        print(f"[DEBUG] Cleaned base filename (before `): {base}")

    # Find subtitle entry in DB by filename (loosely matching base name)
    subtitle_data = extract_subtitle_path_data(subtitle_path)
    track = subtitle_data["track"]
    track = str(track)
    code = subtitle_data["code"]
    track = str(track)
    cursor = db.execute(
        "SELECT content FROM subtitles WHERE filename=? AND track=? AND language=?",
        (base, track, code)
    )

    row = cursor.fetchone()

    content_json = row[0]

    try:
        blocks = json.loads(content_json)
    except Exception as e:
        log_error(f"Failed to parse subtitle JSON for {base}: {e}")
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

    print(f"[DEBUG] Found {len(overlapping_blocks)} overlapping blocks from {subtitle_path}")
    return overlapping_blocks

def get_source_path_from_full_filename(full_source_filename) -> str:
    log_filename(f"received filename: {full_source_filename}")
    possible_bases = [full_source_filename, full_source_filename.replace("_", " ")]

    all_exts = constants.audio_exts + constants.video_exts

    def has_extension(filename):
        return os.path.splitext(filename)[1] != ""


    for base in possible_bases:
        if has_extension(base):
            path = os.path.join(constants.addon_source_folder, base)
            log_image(f"searching path for video/audio: {path}")
            log_command(f"now checking: {path}")
            if os.path.exists(path):
                return path
        else:
            # no extension, try all extensions
            for ext in all_exts:
                candidate = base + ext
                path = os.path.join(constants.addon_source_folder, candidate)
                log_image(f"searching path for video/audio: {path}")
                log_command(f"now checking: {path}")
                if os.path.exists(path):
                    return path

    log_error(f"No source file found for base name: {full_source_filename}")
    return ""

def get_subtitle_track_number_by_code(source_path, code):
    db_path = os.path.join(constants.addon_dir, 'subtitles_index.db')
    conn = manage_database.get_database()
    filename = os.path.basename(source_path)
    cursor = conn.execute(
        "SELECT track FROM media_tracks WHERE filename = ? AND language = ? AND type = 'subtitle' ORDER BY track",
        (filename, code.lower())
    )
    row = cursor.fetchone()
    if row:
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        log_command(f"[ffprobe subtitle code lookup]\ncmd: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")

        streams = json.loads(result.stdout).get("streams", [])
        if 1 <= int(track_number) <= len(streams):
            return streams[int(track_number) - 1].get("tags", {}).get("language", "")
        else:
            log_error(f"Invalid subtitle track number {track_number} for {source_path} — only {len(streams)} subtitle track(s) found.")
    except Exception as e:
        log_error(f"ffprobe error while reading subtitle code: {e}")
    return None

def get_subtitle_blocks_from_index_range_and_path(start_index, end_index, subtitle_path):
    if not subtitle_path:
        log_error(f"subtitle path is none")
        return ""

    if not os.path.exists(subtitle_path):
        log_error(f"subtitle path {subtitle_path} does not exist")

    with open(subtitle_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = content.strip().split('\n\n')

    formatted_blocks = []
    for block in blocks:
        formatted = format_subtitle_block(block)
        formatted_blocks.append(formatted)

    if start_index < 0 or end_index >= len(formatted_blocks) or start_index > end_index:
        print(f"Invalid range: {start_index} to {end_index}, total blocks: {len(formatted_blocks)}")
        return []

    return formatted_blocks[start_index - 1:end_index]

def get_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line, config):
    track = config["target_subtitle_track"]
    code = config["target_language_code"]

    sentence_line = sentence_line or ""
    normalized_sentence = normalize_text(sentence_line)

    subtitle_database = manage_database.get_database()

    def try_match_blocks(blocks, db_filename, track, lang):
        usable_blocks = [b for b in blocks if b and len(b) == 4]
        normalized_lines = [normalize_text(b[3]) for b in usable_blocks]

        for i, norm_line in enumerate(normalized_lines):
            if norm_line.startswith(normalized_sentence):
                log_filename(f"Matched start of line in DB: {db_filename}")
                b = usable_blocks[i]
                return b, f"{db_filename}`track_{track}`{lang}.srt"

        for start in range(len(normalized_lines)):
            joined = ""
            for end in range(start, len(normalized_lines)):
                joined += normalized_lines[end]
                if normalized_sentence in joined:
                    log_filename(f"Matched joined block in DB: {db_filename}")
                    b = usable_blocks[end]
                    return b, f"{db_filename}`track_{track}`{lang}.srt"
                if len(joined) > len(normalized_sentence) + 50:
                    break

        return None, None

    cursor = subtitle_database.execute("SELECT filename, language, track, content FROM subtitles")
    for row in cursor:
        db_filename, lang, trk, content_json = row

        if str(trk) != str(track) and str(lang) != str(code):
            continue

        try:
            blocks = json.loads(content_json)
        except Exception as e:
            log_error(f"Failed to parse content for {db_filename}: {e}")
            continue

        block, pseudo_path = try_match_blocks(blocks, db_filename, trk, lang)
        if block:
            return block, os.path.join(constants.addon_source_folder, pseudo_path)

    log_command("No subtitle match found in any database entry.")
    return None, None

def get_sound_sentence_line_from_subtitle_blocks_and_path(blocks, subtitle_path, config):
    if not subtitle_path:
        log_error("Error: subtitle_path is None")
        return None, None

    if not blocks:
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

    log_filename(f"split filename: {base} from sub path: {subtitle_path}\nextracted file extension: {file_extension}")

    try:
        start_index = blocks[0][0]
        end_index = blocks[-1][0]

        start_time = convert_timestamp_dot_to_hmsms(blocks[0][1])
        end_time = convert_timestamp_dot_to_hmsms(blocks[-1][2])
        print(f"start time: {blocks[0][1]}, end time: {blocks[-1][2]}")


        audio_ext = config["audio_ext"]

        subtitle_data = extract_subtitle_path_data(subtitle_path)
        code = subtitle_data["code"]
        timestamp = f"{filename_base}.{file_extension}`{code}`{start_time}-{end_time}`{start_index}-{end_index}"

        normalize_audio = config["normalize_audio"]
        if normalize_audio:
            lufs = config["lufs"]
            timestamp += f"`{lufs}LUFS"

        timestamp += f".{audio_ext}"
        new_sound_line = f"[sound:{timestamp}]"
        combined_text = "\n\n".join(b[3].strip() for b in blocks if len(b) > 3)

        log_filename(f"generated sound_line: {new_sound_line}\nsentence line: {combined_text}")

        return new_sound_line, combined_text

    except Exception as e:
        log_error(f"Error parsing timestamp in blocks:\n{blocks}\nError: {e}")
        return None, None

def get_next_matching_subtitle_block(sentence_line, selected_text, sound_line, config, sound_line_data):
    log_filename(f"extracting sound_line_data from sound_line: {sound_line}")
    if not sound_line_data:
        print(f"no sound_line_data extracted from {sound_line}")
        return None, None

    target_index = sound_line_data["start_index"]
    filename_base = sound_line_data["filename_base"]

    track = config["target_subtitle_track"]
    code = config["target_language_code"]

    normalized_target_text = normalize_text(selected_text or sentence_line)
    print(f"Searching for: {normalized_target_text}")

    def search_blocks(after_current=True):
        found_current = not after_current
        for filename in os.listdir(constants.addon_source_folder):
            base_candidate, ext = os.path.splitext(filename)
            if ext.lower() not in constants.video_exts + constants.audio_exts:
                continue

            subtitle_database = manage_database.get_database()
            subtitle_path = get_subtitle_file_from_database(filename, track, code, config, subtitle_database)

            if not subtitle_path or not os.path.exists(subtitle_path):
                print(f"Subtitle path not found: {subtitle_path}")
                continue

            with open(subtitle_path, 'r', encoding='utf-8') as f:
                blocks = f.read().strip().split('\n\n')

            formatted = [format_subtitle_block(b) for b in blocks]
            usable = [b for b in formatted if b and len(b) == 4]

            for b in usable:
                block_idx = int(b[0])
                text = b[3]
                if not found_current:
                    if base_candidate == filename_base and block_idx == target_index:
                        found_current = True
                    continue
                if normalized_target_text in normalize_text(text):
                    print(f"Match found in block {block_idx} of {base_candidate}")
                    return b, subtitle_path
        return None, None

    # Try first pass (after current)
    result, path = search_blocks(after_current=True)
    if result:
        return result, path

    # Wraparound pass (from beginning)
    print("Wrapping to start of subtitle files...")
    return search_blocks(after_current=False)



# commands and files
def extract_subtitle_files(source_path, track, code, config):
    track = int(track)
    exe_path, ffprobe_path = constants.get_ffmpeg_exe_path()

    def has_subtitle_streams(path):
        cmd = [ffprobe_path, '-v', 'error', '-select_streams', 's', '-show_entries', 'stream=index', '-of', 'json', path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(proc.stdout)
        return bool(data.get('streams'))

    if not has_subtitle_streams(source_path):
        log_filename("No subtitle streams found, skipping extraction.")
        return

    filename_base, file_extension = os.path.splitext(os.path.basename(source_path))
    log_filename(f"extension from sub source path: {file_extension}, from: {source_path}")

    tagged_subtitle_file = f"{filename_base}{file_extension}`track_{track}`{code}.srt"
    log_filename(f"tagged subtitle file: {tagged_subtitle_file}")
    tagged_subtitle_path = os.path.join(constants.addon_source_folder, tagged_subtitle_file)
    basename_subtitle_file = f"{filename_base}`.srt"
    basename_subtitle_path = os.path.join(constants.addon_source_folder, basename_subtitle_file)

    if os.path.exists(tagged_subtitle_path) or os.path.exists(basename_subtitle_path):
        return

    selected_tab_index = config.get("selected_tab_index", 0)

    track_by_code = get_subtitle_track_number_by_code(source_path, code)
    if track_by_code is None:
        log_error(f"track_by_code not found for code {code}")
        track_by_code = track
    log_filename(f"track by code: {track_by_code}")

    if track_by_code != track:
        log_filename(f"track_by_code ({track_by_code}) != set track ({track}), tab index: {selected_tab_index}")

        if selected_tab_index == 0 and track_by_code:
            log_filename("Prioritizing language code")
            track = track_by_code
        else:
            log_filename("Prioritizing set track")

    code = get_subtitle_code_by_track_number(source_path, track)
    if not code:
        log_error(f"Track {track} does not exist for the file: {filename_base}{file_extension}.\nPlease check your settings.")
        return

    tagged_subtitle_file = f"{filename_base}{file_extension}`track_{track}`{code}.srt"
    log_filename(f"tagged_subtitle_file: {tagged_subtitle_file}")
    tagged_subtitle_path = os.path.join(constants.addon_source_folder, tagged_subtitle_file)

    if track and track > 0 and not os.path.exists(tagged_subtitle_path):
        try:
            log_filename(f"Extracting subtitle track {track} from {source_path}")
            result = subprocess.run(
                [
                    exe_path,
                    "-y",
                    "-i", source_path,
                    "-map", f"0:s:{track - 1}",
                    tagged_subtitle_path
                ],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                log_error(f"Subtitle extraction failed with code {result.returncode}:\n{result.stderr} for:\n{source_path}|{track}|{code}")
            else:
                log_command(f"Subtitle extraction succeeded:\n{result.stdout}")
        except Exception as e:
            log_error(f"Subtitle extraction crashed: {e}")


def run_ffmpeg_extract_image_command(source_path, image_timestamp, image_collection_path, m4b_image_collection_path) -> str:
    out_dir = os.path.dirname(image_collection_path)
    ffmpeg_path, _ = constants.get_ffmpeg_exe_path()
    os.makedirs(out_dir, exist_ok=True)
    if not os.access(out_dir, os.W_OK):
        log_error(f"Cannot write to directory: {out_dir}")
        return ""

    if source_path.lower().endswith(".m4b"):
        output_path = m4b_image_collection_path
        cmd = [
            ffmpeg_path, "-y",
            "-i", source_path,
            "-map", "0:v",
            "-codec", "copy",
            "-loglevel", "error",
            output_path
        ]
        log_command(f"Extracting cover from m4b:\n{' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_error(f"FFmpeg cover extraction failed:\n{result.stderr}")
            return ""
        if os.path.exists(output_path):
            log_command(f"Extracted cover: {output_path}")
            return output_path
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
        image_collection_path
    ]
    log_command(f"Extracting image:\n{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log_error(f"FFmpeg image extraction failed:\n{result.stderr}")
        return ""

    log_command(f"Extracted image: {image_collection_path}")
    return image_collection_path

def create_ffmpeg_extract_audio_command(source_path, start_time, end_time, collection_path, sound_line, config, sound_line_data, use_translation_data) -> list:
    log_command(f"FFmpeg source path: {source_path}")
    log_command(f"FFmpeg sound line: {sound_line}")

    lufs = config["lufs"]
    bitrate = config["bitrate"]
    normalize_audio = config["normalize_audio"]
    target_code = config["target_language_code"]
    translation_code = config["translation_language_code"]
    target_track = config["target_audio_track"]
    translation_track = config["translation_audio_track"]
    selected_tab_index = config.get("selected_tab_index", 0)

    log_filename(f"Extracting sound_line_data from sound_line: {sound_line}")

    ffmpeg_path, ffprobe_path = constants.get_ffmpeg_exe_path()

    start = convert_hmsms_to_ffmpeg_time_notation(start_time)
    end = convert_hmsms_to_ffmpeg_time_notation(end_time)
    duration_sec = time_hmsms_to_seconds(end) - time_hmsms_to_seconds(start)
    if duration_sec <= 0:
        log_error(f"End time must be after start time: {start}, {end}")
        return []

    delay_ms = get_audio_start_time_ms(source_path)

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
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index:stream_tags=language", "-of", "json", source_path],
            capture_output=True, text=True
        )
        log_command(f"[ffprobe audio stream scan]\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        info = json.loads(result.stdout)
        streams = info.get("streams", [])

        if selected_tab_index == 0:
            for stream in streams:
                if stream.get("tags", {}).get("language", "").lower() == code.lower():
                    audio_track_index = stream["index"]
                    break

        if audio_track_index is None:
            if 1 <= track <= len(streams):
                audio_track_index = streams[track - 1]["index"]

        if audio_track_index is None and streams:
            audio_track_index = streams[0]["index"]

    except Exception as e:
        log_error(f"Error selecting audio track: {e}")
        audio_track_index = 0

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

def ffmpeg_extract_full_audio(source_file_path, config) -> str:
    ffmpeg_path, _ = constants.get_ffmpeg_exe_path()
    audio_ext = config["audio_ext"]

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
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_error(f"FFmpeg failed with return code {result.returncode}:\n{result.stderr}")
            return ""
        log_command(f"FFmpeg stdout:\n{result.stdout}")
        log_command(f"Converted to {audio_ext}: {output_path}")
        return output_path
    except Exception as e:
        log_error(f"FFmpeg conversion error: {e}")
        return ""


def create_just_normalize_audio_command(source_path, config):
    lufs = config["lufs"]
    bitrate = config["bitrate"]

    print(f"source path test: {source_path}")
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

def format_timestamp_for_filename(timestamp: str) -> str:
    return timestamp.replace(':', '.').replace(',', '.')

def get_audio_start_time_ms(source_file_path: str) -> int:
    _, ffprobe_path = constants.get_ffmpeg_exe_path()
    cmd = [
        ffprobe_path, "-v", "error",
        "-select_streams", "a:0",
        "-show_packets", "-read_intervals", "0%+#5",
        "-print_format", "compact", source_file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        log_command(f"ffprobe output: {result.stdout.strip()}")
        match = re.search(r"pts_time=(\d+(?:\.\d+)?)", result.stdout)
        return round(float(match.group(1)) * 1000) if match else 0
    except Exception as e:
        log_error(f"ffprobe failed: {e}")
        return 0

def normalize_text(s):
    s = html.unescape(s)
    s = re.sub(r'<.*?>', '', s)
    s = re.sub(r'（.*?）|\(.*?\)', '', s)
    s = s.replace('\xa0', '')
    s = re.sub(r'[\s\u3000]+', '', s)
    return s

def timestamp_to_dot_format(ts: str) -> str:
    ts = ts.replace(',', '.')
    parts = ts.split(':')
    if len(parts) != 3:
        print(f"Invalid timestamp format for conversion: {ts}")
        return ts
    hours = parts[0]
    minutes = parts[1]
    sec_millis = parts[2].split('.')
    if len(sec_millis) != 2:
        print(f"Invalid seconds.milliseconds format for conversion: {parts[2]}")
        return ts
    seconds, milliseconds = sec_millis
    return f"{hours}.{minutes}.{seconds}.{milliseconds}"


def time_srt_to_milliseconds(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def convert_timestamp_dot_to_hmsms(ts: str) -> str:
    ts = ts.strip()
    if '.' in ts and ts.count('.') == 3:
        parts = ts.split('.')
    elif ':' in ts and ',' in ts:
        time_part, ms_part = ts.split(',')
        hms = time_part.split(':')
        if len(hms) != 3:
            print(f"Invalid timestamp format: {ts}")
            return ts
        parts = [hms[0], hms[1], hms[2], ms_part]
    else:
        print(f"Invalid timestamp format: {ts}")
        return ts

    if len(parts) != 4:
        print(f"Invalid timestamp format after parsing: {ts}")
        return ts

    hours, minutes, seconds, milliseconds = parts
    return f"{hours}h{minutes}m{seconds}s{milliseconds}ms"


def convert_hmsms_to_ffmpeg_time_notation(t: str):
    hmsms_match = re.match(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms", t)
    if hmsms_match:
        h, m, s, ms = hmsms_match.groups()
        return f"{h}:{m}:{s}.{ms}"

    parts = t.strip().split(".")
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"

    print(f"Unrecognized timestamp format: {t}")

def time_hmsms_to_seconds(t):
    h, m, s = t.split(':')
    s, ms = (s.split(',') if ',' in s else s.split('.'))
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

import re

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
                print(f"Unrecognized timestamp format: {ts}")
                return None
            h, m, s, ms = parts
        else:
            print(f"Unrecognized timestamp format: {ts}")
            return None

    total_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    return total_ms


def milliseconds_to_hmsms_format(ms: int) -> str:
    hours = ms // (3600 * 1000)
    ms %= (3600 * 1000)
    minutes = ms // (60 * 1000)
    ms %= (60 * 1000)
    seconds = ms // 1000
    millis = ms % 1000
    return f"{hours:02d}h{minutes:02d}m{seconds:02d}s{millis:03d}ms"

def format_subtitle_block(subtitle_block):
    if not subtitle_block:
        log_error("No subtitle block")
        return []
    lines = subtitle_block.strip().splitlines()

    if len(lines) < 3:
        return []

    subtitle_index = lines[0]
    time_range = lines[1]

    if '-->' not in time_range:
        log_error(f"Invalid time range in subtitle block: {time_range}")
        return None

    subtitle_text = "\n".join(line.strip() for line in lines[2:])

    start_srt, end_srt = [t.strip() for t in time_range.split('-->')]
    start_time = format_timestamp_for_filename(start_srt)
    end_time = format_timestamp_for_filename(end_srt)

    return [subtitle_index, start_time, end_time, subtitle_text]

def get_altered_sound_data(sound_line, lengthen_start_ms, lengthen_end_ms, config, sound_line_data) -> dict:
    normalize_audio = config["normalize_audio"]
    lufs = config["lufs"]

    log_filename(f"extracting sound_line_data from sound_line: {sound_line}")
    if not sound_line_data:
        return {}

    orig_start_ms = time_hmsms_to_milliseconds(sound_line_data["start_time"])
    orig_end_ms = time_hmsms_to_milliseconds(sound_line_data["end_time"])

    start_index = sound_line_data["start_index"]
    end_index = sound_line_data["end_index"]

    new_start_ms = max(0, orig_start_ms - lengthen_start_ms)
    new_end_ms = max(0, orig_end_ms + lengthen_end_ms)

    if new_end_ms <= new_start_ms:
        log_error(f"Invalid time range for {sound_line}: {new_start_ms}-{new_end_ms}")
        return {}

    new_start_time = milliseconds_to_hmsms_format(new_start_ms)
    new_end_time = milliseconds_to_hmsms_format(new_end_ms)

    time_range = f"{new_start_time}-{new_end_time}"
    filename_base = sound_line_data["filename_base"]
    full_source_filename = sound_line_data["full_source_filename"]

    source_file_extension = "."
    source_file_extension += sound_line_data["source_file_extension"]
    filename_parts = [full_source_filename]

    lang_code = sound_line_data.get("lang_code")
    if lang_code:
        filename_parts.append(lang_code)

    filename_parts.append(time_range)

    subtitle_range = f"{start_index}-{end_index}" if start_index is not None and end_index is not None else ""
    if subtitle_range:
        filename_parts.append(subtitle_range)

    if normalize_audio:
        filename_parts.append(f"{lufs}LUFS")

    new_filename = "`".join(filename_parts) + f".{sound_line_data['sound_file_extension']}"
    new_path = os.path.join(get_collection_dir(), new_filename)
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

def alter_sound_file_times(altered_data, sound_line, config, use_translation_data):
    if not altered_data:
        log_error("altered sound_line_data is empty")
        return None

    if not sound_line:
        log_error("sound line is empty")
        return None

    if os.path.exists(altered_data["old_path"]):
        send2trash(altered_data["old_path"])

    full_source_filename = altered_data["full_source_filename"]
    log_filename(f"full source filename: {full_source_filename}")
    source_path = get_source_path_from_full_filename(full_source_filename)

    cmd = create_ffmpeg_extract_audio_command(
        source_path,
        altered_data["new_start_time"],
        altered_data["new_end_time"],
        altered_data["new_path"],
        sound_line, config, extract_sound_line_data(altered_data["new_sound_line"]), use_translation_data
    )

    try:
        log_filename(f"generating new sound file: {altered_data['new_path']}")
        log_filename(f"Running FFmpeg command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log_error(f"FFmpeg failed:\n{result.stderr}")
            return ""
        log_command(f"FFmpeg output:\n{result.stdout}")
    except Exception as e:
        log_error(f"FFmpeg error: {e}")
        return ""

    if os.path.exists(altered_data["new_path"]):
        return f"[sound:{altered_data['new_filename']}]"
    else:
        log_error(f"Expected output file not found: {altered_data['new_path']}")
        return ""

