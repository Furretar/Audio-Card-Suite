
import os
import shutil

from aqt.utils import showInfo
from send2trash import send2trash
addon_dir = os.path.dirname(os.path.abspath(__file__))
addon_source_folder = os.path.join(addon_dir, "Sources")
temp_ffmpeg_folder = os.path.join(addon_dir, "ffmpeg")
temp_ffmpeg_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffmpeg.exe")
temp_ffprobe_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffprobe.exe")
import subprocess
import re
import json

addon_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(addon_dir, "config.json")


def get_collection_dir():
    from aqt import mw
    if not mw or not mw.col:
        raise RuntimeError("Collection is not loaded yet.")
    return mw.col.media.dir()

audio_exts = [
    ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus", ".m4b"
]

video_exts = [
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4b"
]

BACKTICK_PATTERN = re.compile(
    r'^\[sound:'
    r'(?P<filename_base>[^`]+?)`'                            # filename base
    r'(?P<sha>[A-Za-z0-9]{4})`'                              # 4-char SHA
    r'(?P<start_time>\d{2}h\d{2}m\d{2}s\d{3}ms)-'            # start time
    r'(?P<end_time>\d{2}h\d{2}m\d{2}s\d{3}ms)`'              # end time
    r'(?P<subtitle_range>\d+-\d+)'                           # subtitle range
    r'(?:`(?P<normalize_tag>[^`]+))?'                        # optional normalize tag
    r'\.(?P<file_extension>\w+)\]$'                          # file extension
)

SUBS2SRS_PATTERN = re.compile(
    r"""\[sound:
    (?P<filename_base>.+?)_                      # base filename ending with underscore
    (?P<start_time>\d{2}\.\d{2}\.\d{2}\.\d{3})- # start time (dot format)
    (?P<end_time>\d{2}\.\d{2}\.\d{2}\.\d{3})    # end time
    \.(?P<file_extension>\w+)                     # extension
    \]$""",
    re.VERBOSE
)



def detect_format(sound_line: str) -> str:
    if not sound_line:
        return None

    line = sound_line.strip()
    if BACKTICK_PATTERN.match(line):
        return "backtick"
    elif SUBS2SRS_PATTERN.match(line):
        return "subs2srs"
    else:
        return "unknown"

def extract_sound_line_data(sound_line):
    print(f"extracting data from {sound_line}")
    format_type = detect_format(sound_line)
    if format_type == "backtick":

        match = BACKTICK_PATTERN.match(sound_line)
        if not match:
            print(f"no match for backtick")
            return None
        groups = match.groupdict()
        filename_base = groups["filename_base"]
        sha = groups["sha"]
        start_time_raw = groups["start_time"]
        end_time_raw = groups["end_time"]

        subtitle_range = groups["subtitle_range"]
        file_extension = groups["file_extension"]

        start_index, end_index = map(int, subtitle_range.split("-"))
        normalize_tag = groups.get("normalize_tag")

        timestamp_filename = "`".join(filter(None, [
            filename_base,
            sha,
            f"{start_time_raw}-{end_time_raw}",
            subtitle_range,
            normalize_tag
        ])) + f".{file_extension}"

        timestamp_filename_no_normalize = "`".join(filter(None, [
            filename_base,
            sha,
            f"{start_time_raw}-{end_time_raw}",
            subtitle_range
        ]))

    elif format_type == "subs2srs":
        match = SUBS2SRS_PATTERN.match(sound_line)
        if not match:
            return None
        groups = match.groupdict()
        filename_base = groups["filename_base"]
        sha = ""
        start_time_raw = groups["start_time"]
        end_time_raw = groups["end_time"]
        start_index = end_index = None
        normalize_tag = ""
        file_extension = groups["file_extension"]
        timestamp_filename = (
            f"{filename_base}_{start_time_raw}-{end_time_raw}.{file_extension}"
        )

        timestamp_filename_no_normalize = (
            f"{filename_base}_{start_time_raw}-{end_time_raw}"
        )
    else:
        if not sound_line:
            print("extract_sound_line_data received None or empty string.")
            return None

        if sound_line.startswith("[sound:") and sound_line.endswith("]"):
            filename = sound_line[len("[sound:"):-1]
            collection_path = os.path.join(get_collection_dir(), filename)

            filename_base = filename.split("`")[0]  # for metadata only, keep full filename for path
            _, file_extension = os.path.splitext(filename)

            print(f"filename: {filename}")
            print(f"filename_base: {filename_base}")
            print(f"file_extension: {file_extension}")
            print(f"collection_path: {collection_path}")

            return {
                "filename_base": filename_base,
                "file_extension": file_extension,
                "collection_path": collection_path
            }

        else:
            return None

    def convert(ts):
        return re.sub(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms", r"\1.\2.\3.\4", ts)

    start_time = convert(start_time_raw)
    end_time = convert(end_time_raw)
    audio_collection_path = os.path.join(get_collection_dir(), timestamp_filename)

    # source_path = get_source_file(filename_base)

    m4b_image_filename = f"{filename_base}.jpg"
    image_filename = f"{filename_base}`{start_time}.jpg"

    image_collection_path = os.path.join(get_collection_dir(), image_filename)
    m4b_image_collection_path = os.path.join(get_collection_dir(), m4b_image_filename)

    return {
        "filename_base": filename_base,
        "sha": sha,
        "start_time": start_time,
        "end_time": end_time,
        "start_index": start_index,
        "end_index": end_index,
        "normalize_tag": normalize_tag,
        "file_extension": file_extension,
        "full_source_filename": f"{filename_base}.{file_extension}",
        "timestamp_filename": timestamp_filename,
        "collection_path": audio_collection_path,
        "image_filename": image_filename,
        "m4b_image_filename": m4b_image_filename,
        "image_collection_path": image_collection_path,
        "m4b_image_collection_path": m4b_image_collection_path,
        "timestamp_filename_no_normalize": timestamp_filename_no_normalize,
    }


def format_timestamp_for_filename(timestamp: str) -> str:
    return timestamp.replace(':', '.').replace(',', '.')

def get_subtitle_block_from_index_and_path(subtitle_index, subtitle_path):
    if not os.path.exists(subtitle_path):
        print(f"Subtitle file does not exist: {subtitle_path}")
        return []

    with open(subtitle_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = content.strip().split('\n\n')

    if 0 <= subtitle_index < len(blocks):
        formatted_block = format_subtitle_block(blocks[subtitle_index])
        return formatted_block if formatted_block else []

    print(f"Index {subtitle_index} out of range for subtitle file {subtitle_path}")
    return []

def get_ffmpeg_exe_path():
    exe_path = shutil.which("ffmpeg")
    probe_path = shutil.which("ffprobe")
    if exe_path:
        return exe_path, probe_path

    if os.path.exists(temp_ffmpeg_exe):
        print("Using bundled FFmpeg executable.")
        return temp_ffmpeg_exe, temp_ffprobe_exe

    print("FFmpeg executable not found in PATH or addon folder.")
    showInfo("FFmpeg is not installed or could not be found.\n\n"
             "Either install FFmpeg globally and add it to your system PATH,\n"
             "or place ffmpeg.exe in the addon folder under: ffmpeg/bin/ffmpeg.exe")
    return None, None


def get_field_key_from_label(note_type_name: str, label: str, config: dict) -> str:
    mapped_fields = config["mapped_fields"][note_type_name]
    for field_key, mapped_label in mapped_fields.items():
        if mapped_label == label:
            return field_key
    return ""





def format_subtitle_block(subtitle_block):
    if not subtitle_block:
        print("No subtitle block")
        return []
    lines = subtitle_block.strip().splitlines()

    if len(lines) < 3:
        return []

    subtitle_index = lines[0]
    time_range = lines[1]
    subtitle_text = "\n".join(line.strip() for line in lines[2:])

    start_srt, end_srt = [t.strip() for t in time_range.split('-->')]
    start_time = format_timestamp_for_filename(start_srt)
    end_time = format_timestamp_for_filename(end_srt)

    return [subtitle_index, start_time, end_time, subtitle_text]

def get_subtitle_block_from_relative_index(relative_index, subtitle_index, subtitle_path) -> str:
    with open(subtitle_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = content.strip().split('\n\n')

    formatted_blocks = []
    for block in blocks:
        formatted = format_subtitle_block(block)
        formatted_blocks.append(formatted)

    target_index = subtitle_index + relative_index
    if 0 <= target_index < len(formatted_blocks):
        return formatted_blocks[target_index - 1]
    else:
        print(f"Relative index {relative_index} out of range from position {subtitle_index}")
        print(f"len(blocks): {len(formatted_blocks)}")
        return []

def is_backtick_format(sound_line: str) -> bool:
    return '`' in sound_line and '-' in sound_line and ']' in sound_line

def is_subs2srs_format(sound_line: str) -> bool:
    return '_' in sound_line and '-' in sound_line and ']' in sound_line

def get_valid_backtick_sound_line_and_block(sound_line: str, sentence_line: str):
    block = None

    if not sound_line:
        block, subtitle_path = get_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line)
        print(f"valid backtick subtitle path: {subtitle_path}")
        print(f"\nblock from text {sentence_line}: {block}\n")
        if not block or not subtitle_path:
            return None, None
        sound_line = get_sound_line_from_subtitle_block_and_path(block, subtitle_path)
        print(f"valid backtick sound line: {sound_line}")
        return sound_line, block

    format = detect_format(sound_line)
    print(f"detected format: {format} for sound line: {sound_line}")

    if format not in ["backtick", "subs2srs"]:
        block, subtitle_path = get_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line)
        if not block or not subtitle_path:
            return None, None
        sound_line = get_sound_line_from_subtitle_block_and_path(block, subtitle_path)

    data = extract_sound_line_data(sound_line)
    filename_base = data["filename_base"]
    config = extract_config_data()
    track = config.get("target_subtitle_track")
    code = config.get("target_language_code")
    print(f"target_language_code: {code}")
    print(f"config: {config}")
    subtitle_path = get_subtitle_path_from_filename_track_code(filename_base, track, code)

    if format == "backtick":
        start_index = data["start_index"]
        end_index = data["end_index"]
        block, _ = get_subtitle_block_from_sound_line_and_sentence_line(sound_line, sentence_line)
        return sound_line, block

    elif format == "subs2srs":
        first_sentence = sentence_line.strip().split()[0]
        print(f"first_sentence: {first_sentence}")
        block, _ = get_subtitle_block_from_sound_line_and_sentence_line(sound_line, first_sentence)
        if block is None:
            return None, None
        sound_line = get_sound_line_from_subtitle_block_and_path(block, subtitle_path)

    return sound_line, block



def get_subtitle_block_from_sound_line_and_sentence_line(sound_line: str, sentence_line: str):
    data = extract_sound_line_data(sound_line)
    if not data:
        print(f"no data extracted from {sound_line}")
        return None, None

    start_index = data["start_index"]
    end_index = data["end_index"]
    filename_base = data["filename_base"]

    config = extract_config_data()
    track = config["target_subtitle_track"]
    code = config["target_language_code"]

    subtitle_path = get_subtitle_path_from_filename_track_code(filename_base, track, code)
    if not subtitle_path or not os.path.exists(subtitle_path):
        print(f"Subtitle path not found or invalid: {subtitle_path}")
        source_path = get_source_file(filename_base)
        extract_subtitle_files(source_path, track, code)
        subtitle_path = get_subtitle_path_from_filename_track_code(filename_base, track, code)

        if not subtitle_path or not os.path.exists(subtitle_path):
            print("Subtitle path still not found after extraction.")
            return None, None

    with open(subtitle_path, 'r', encoding='utf-8') as f:
        blocks = f.read().strip().split('\n\n')

    for block in blocks:
        formatted_block = format_subtitle_block(block)
        if formatted_block and len(formatted_block) == 4:
            subtitle_text = formatted_block[3]
            if normalize_text(sentence_line) in normalize_text(subtitle_text):
                return formatted_block, subtitle_path

    return None, subtitle_path

# 1-based indexing
def get_subtitle_track_number_by_code(source_path, code):
    print(f"code in get_subtitle_track_number_by_code: {code}, source_path: {source_path}")
    ffmpeg_exe, ffprobe_exe = get_ffmpeg_exe_path()
    try:
        cmd = [
            f"{ffprobe_exe}", "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json", source_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        info = json.loads(result.stdout)
        streams = info.get("streams", [])

        if not streams:
            print("No subtitle streams found.")
            return None

        for stream in streams:
            lang = stream.get("tags", {}).get("language", "")
            if lang.lower() == code.lower():
                return stream.get("index", None)

    except Exception as e:
        print(f"ffprobe error: {e}")

    return None


# 1-based indexing
def get_subtitle_code_by_track_number(source_path, track_number):
    ffmpeg_exe, ffprobe_exe = get_ffmpeg_exe_path()
    try:
        cmd = [
            f"{ffprobe_exe}", "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json", source_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        if 1 <= track_number <= len(streams):
            stream = streams[track_number - 1]  # convert to 0-based
            return stream.get("tags", {}).get("language", "")
    except Exception as e:
        print(f"ffprobe error: {e}")
    return None

# translation_field = get_field_key_from_label(note_type_name, "Translation Sub Line", config)
def extract_subtitle_files(source_path, track, code):

    filename_base, _ = os.path.splitext(os.path.basename(source_path))
    tagged_subtitle_file = f"{filename_base}`track_{track}`{code}.srt"
    tagged_subtitle_path = os.path.join(addon_source_folder, tagged_subtitle_file)

    if os.path.exists(tagged_subtitle_path):
        return

    config = extract_config_data()
    selected_tab_index = config["selected_tab_index"]
    exe_path, _ = get_ffmpeg_exe_path()


    track_by_code = get_subtitle_track_number_by_code(source_path, code)
    if track_by_code is None:
        print("No subtitle track found — skipping extraction.")
        return None

    if track_by_code != track:
        print(f"track_by_code ({track_by_code}) != set track ({track})")
        if selected_tab_index == 0 and track_by_code:
            print("Prioritizing language code")
            track = track_by_code
        else:
            print("Prioritizing set track")

    code = get_subtitle_code_by_track_number(source_path, track)

    tagged_subtitle_file = f"{filename_base}`track_{track}`{code}.srt"
    tagged_subtitle_path = os.path.join(addon_source_folder, tagged_subtitle_file)

    if track and track > 0 and not os.path.exists(tagged_subtitle_path):
        try:
            print(f"Extracting subtitle track {track} from {source_path}")
            subprocess.run([
                exe_path,
                "-y",
                "-i", source_path,
                "-map", f"0:s:{track - 1}",
                tagged_subtitle_path
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Subtitle extraction failed: {e}")

def get_subtitle_path_from_filename_track_code(filename, track, code):
    filename_base, _ = os.path.splitext(filename)
    config = extract_config_data()
    selected_tab_index = config["selected_tab_index"]
    source_path = get_source_file(filename_base)

    if not os.path.exists(source_path):
        print(f"Source video not found: {source_path}")
        return None

    if not code or code.lower() == "none":
        print(f"Invalid subtitle language code: {code!r}")
        return None

    extract_subtitle_files(source_path, track, code)

    # 1. Try exact match
    tagged_subtitle_file = f"{filename_base}`track_{track}`{code}.srt"
    tagged_subtitle_path = os.path.join(addon_source_folder, tagged_subtitle_file)
    if os.path.exists(tagged_subtitle_path):
        return tagged_subtitle_path

    # 2. Fallback: match by code or track
    if selected_tab_index == 0:
        for file in os.listdir(addon_source_folder):
            if file.startswith(filename_base) and file.endswith(f"{code}.srt"):
                return os.path.join(addon_source_folder, file)
    else:
        track_str = f"`track_{track}`"
        for file in os.listdir(addon_source_folder):
            if file.startswith(filename_base) and track_str in file:
                return os.path.join(addon_source_folder, file)

    print("No matching subtitle file found.")
    return None


def get_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line: str):
    for filename in os.listdir(addon_source_folder):
        print(f"checking filename: {filename}")
        filename_base, file_extension = os.path.splitext(filename)
        if file_extension.lower() in video_exts or file_extension.lower() in audio_exts:
            source_path = os.path.join(addon_source_folder, filename)
            config = extract_config_data()
            track = config["target_subtitle_track"]
            code = config["target_language_code"]
            tagged_subtitle_path = get_subtitle_path_from_filename_track_code(filename_base, track, code)

            if not tagged_subtitle_path or not os.path.exists(tagged_subtitle_path):
                print("Subtitle path is None or file does not exist.")
                return None, None

            with open(tagged_subtitle_path, 'r', encoding='utf-8') as f:
                blocks = f.read().strip().split('\n\n')

            for block in blocks:
                formatted_block = format_subtitle_block(block)
                if formatted_block and len(formatted_block) == 4:
                    subtitle_text = formatted_block[3]

                    if normalize_text(sentence_line) in normalize_text(subtitle_text):
                        return formatted_block, tagged_subtitle_path

    return None, None

def get_translation_line_from_sound_line(sound_line):
    if not sound_line:
        print("get_translation_line_from_sound_line received None sound_line.")
        return ""

    data = extract_sound_line_data(sound_line)
    if not data:
        print("extract_sound_line_data returned None.")
        return ""

    config = extract_config_data()
    translation_audio_track = config["translation_audio_track"]
    translation_language_code = config["translation_language_code"]
    start_time = data["start_time"]
    end_time = data["end_time"]
    filename_base = data["filename_base"]


    translation_subtitle_path = get_subtitle_path_from_filename_track_code(filename_base, translation_audio_track, translation_language_code)
    print(f"translation subtitle path: {translation_subtitle_path}")
    print(f"translation code: {translation_language_code}")
    overlapping_translation_blocks = get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(translation_subtitle_path, start_time, end_time)

    translation_line = "\n\n".join(block[3] for block in overlapping_translation_blocks)
    return translation_line.strip()


def get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(subtitle_path, start_time, end_time):
    print(f"start time: {start_time}, end time: {end_time}")

    if not subtitle_path:
        print("Subtitle path is None.")
        return []

    if not os.path.exists(subtitle_path):
        print(f"Subtitle file not found: {subtitle_path}")
        return []

    start_ms = time_hmsms_to_milliseconds(start_time)
    end_ms = time_hmsms_to_milliseconds(end_time)

    if not os.path.exists(subtitle_path):
        print(f"Subtitle file not found: {subtitle_path}")
        return []

    with open(subtitle_path, "r", encoding="utf-8") as f:
        raw_blocks = f.read().strip().split("\n\n")

    formatted_blocks = []
    for block in raw_blocks:
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        formatted = format_subtitle_block(block)
        if formatted:
            formatted_blocks.append(formatted)

    overlapping_blocks = []
    for block in formatted_blocks:
        try:
            sub_start_ms = time_hmsms_to_milliseconds(block[1])
            sub_end_ms = time_hmsms_to_milliseconds(block[2])
        except:
            continue

        if sub_start_ms > end_ms:
            break

        if sub_start_ms <= end_ms and sub_end_ms >= start_ms:
            overlapping_blocks.append(block)

    return overlapping_blocks


def normalize_text(s):
    return ''.join(s.strip().split())


def convert_timestamp_dot_to_hmsms(ts: str) -> str:
    parts = ts.split('.')
    if len(parts) != 4:
        raise ValueError(f"Invalid timestamp format: {ts}")
    hours, minutes, seconds, milliseconds = parts
    return f"{hours}h{minutes}m{seconds}s{milliseconds}ms"


def get_sound_line_from_subtitle_block_and_path(block, subtitle_path) -> str:
    if not subtitle_path:
        print("Error: subtitle_path is None")
        return ""

    filename_base = os.path.splitext(os.path.basename(subtitle_path))[0].split('`')[0]

    try:
        start_index = block[0]
        start_time = convert_timestamp_dot_to_hmsms(block[1])
        end_time = convert_timestamp_dot_to_hmsms(block[2])

        timestamp = f"{filename_base}`ABCD`{start_time}-{end_time}`{start_index}-{start_index}.mp3"
        new_sound_line = f"[sound:{timestamp}]"
        return new_sound_line

    except Exception as e:
        print(f"Error parsing timestamp in block:\n{block}\nError: {e}")
        return ""

def check_for_video_source(filename_base) -> str:
    for ext in set(video_exts):
        path = os.path.join(addon_source_folder, filename_base + ext)
        if os.path.exists(path):
            return path
    return ""

def get_source_file(filename_base) -> str:
    video_source_path = check_for_video_source(filename_base)
    if video_source_path:
        return video_source_path

    for ext in set(audio_exts):
        path = os.path.join(addon_source_folder, filename_base + ext)
        print("now checking: ", path)
        if os.path.exists(path):
            return path

    print(f"No source file found for base name: {filename_base}")
    showInfo(f"No source file found for base name: {filename_base}")
    return ""

def get_video_duration_seconds(path):
    _, ffprobe_path = get_ffmpeg_exe_path()
    try:
        result = subprocess.run(
            [f"{ffprobe_path}", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print("Failed to get duration:", e)
        return 0

def get_image_if_empty_helper(image_line, sound_line):
    # check if any field already has an image
    if image_line:
        return image_line

    print(f"No image found, extracting from source. image line: {image_line}, sound line: {sound_line}")

    data = extract_sound_line_data(sound_line)
    if not data:
        print("Failed to extract data from sound tag.")
        return ""

    filename_base = data.get("filename_base")
    image_collection_path = data.get("image_collection_path")
    m4b_image_collection_path = data.get("m4b_image_collection_path")
    image_filename = data.get("image_filename")
    start_time = data.get("start_time")

    video_source_path = check_for_video_source(filename_base)
    if not video_source_path:
        return ""

    _, ext = os.path.splitext(video_source_path)
    video_extension = ext.lower()

    image_path = run_ffmpeg_extract_image_command(
        video_source_path,
        start_time,
        image_collection_path,
        m4b_image_collection_path
    )

    if image_path:
        print(f"video extension: {video_extension}")
        if video_extension == ".m4b":
            print("EXTENSION IS M4B")
            embed_image = f'<img src="{os.path.basename(m4b_image_collection_path)}">'
        else:
            embed_image = f'<img src="{os.path.basename(image_filename)}">'


        print(f"add image: {embed_image}")
        return embed_image
    else:
        showInfo("Could not add image")
        return ""


def run_ffmpeg_extract_image_command(source_path, image_timestamp, image_collection_path, m4b_image_collection_path) -> str:
    out_dir = os.path.dirname(image_collection_path)
    ffmpeg_path, _ = get_ffmpeg_exe_path()
    os.makedirs(out_dir, exist_ok=True)          # create it if needed
    if not os.access(out_dir, os.W_OK):
        raise RuntimeError(f"Cannot write to directory: {out_dir}")

    
    if source_path.lower().endswith(".m4b"):
        print("m4b detected")
        output_path = m4b_image_collection_path
        cmd = [
            f"{ffmpeg_path}", "-y",
            "-i", source_path,
            "-map", "0:v",
            "-codec", "copy",
            "-loglevel", "error",
            output_path
        ]

        try:
            print(f"Extracting cover from m4b: {cmd}")
            subprocess.run(cmd, check=True)
            if os.path.exists(output_path):
                print(f"Extracted cover: {output_path}")
                return output_path
            else:
                print("Cover extraction failed: file not found")
                return ""
        except subprocess.CalledProcessError as e:
            print("FFmpeg cover extraction failed:", e)
            return ""

    # For all other formats (e.g., mp4, mkv, webm, etc.)
    timestamp = convert_hmsms_to_ffmpeg_time_notation(image_timestamp)
    ffmpeg_path, _ = get_ffmpeg_exe_path()
    cmd = [
        f"{ffmpeg_path}", "-y",
        "-ss", timestamp,
        "-i", source_path,
        "-frames:v", "1",
        "-q:v", "15",
        image_collection_path
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"Extracted image: {image_collection_path}")
        return image_collection_path
    except subprocess.CalledProcessError as e:
        print("FFmpeg failed:", e)
        return ""


def create_ffmpeg_extract_audio_command(source_path, start_time, end_time, collection_path) -> list:
    config = extract_config_data()
    lufs = config["lufs"]
    bitrate = config["bitrate"]
    normalize_audio = config["normalize_audio"]


    ffmpeg_path, _ = get_ffmpeg_exe_path()

    start = convert_hmsms_to_ffmpeg_time_notation(start_time)
    end = convert_hmsms_to_ffmpeg_time_notation(end_time)
    duration_sec = time_hmsms_to_seconds(end) - time_hmsms_to_seconds(start)
    if duration_sec <= 0:
        print(f"End time must be after start time, {start}, {end}")
        return []

    delay_ms = get_audio_start_time_ms(source_path)
    base, file_extension = os.path.splitext(collection_path)
    ext_no_dot = file_extension[1:].lower()

    # Determine output extension and codec
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

    cmd = [
        ffmpeg_path, "-y",
        "-ss", start,
        "-i", source_path,
        "-map", "0:a:0",
        "-t", str(duration_sec),
    ]

    filters = []
    if delay_ms > 0:
        filters.append(f"adelay={delay_ms}|{delay_ms}")

    if normalize_audio and int(lufs) < 1:
        filters.append(f"loudnorm=I={lufs}:TP=-1.5:LRA=11")

    if filters:
        filter_str = ",".join(filters)
        cmd += ["-af", filter_str]

    cmd += ["-c:a", codec]

    if codec in ("libmp3lame", "libopus") and bitrate:
        # For opus, bitrate can be specified in bps (e.g., 64000 for 64 kbps)
        bitrate = f"{bitrate}k" if codec == "libmp3lame" else str(bitrate * 1000)
        cmd += ["-b:a", bitrate]

    cmd.append(new_collection_path)

    return cmd


def create_just_normalize_audio_command(source_path):
    config = extract_config_data()
    lufs = config["lufs"]
    bitrate = config["bitrate"]

    print(f"source path test: {source_path}")
    ffmpeg_path, _ = get_ffmpeg_exe_path()

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
        print(f"Unsupported audio format: {ext_no_dot}")
        return ""

    cmd.append(new_collection_path)
    return cmd

def time_srt_to_milliseconds(t):
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)

def convert_hmsms_to_ffmpeg_time_notation(t: str) -> str:
    hmsms_match = re.match(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms", t)
    if hmsms_match:
        h, m, s, ms = hmsms_match.groups()
        return f"{h}:{m}:{s}.{ms}"

    parts = t.strip().split(".")
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"

    raise ValueError(f"Unrecognized timestamp format: {t}")


def time_hmsms_to_seconds(t):
    h, m, s = t.split(':')
    s, ms = (s.split(',') if ',' in s else s.split('.'))
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def time_hmsms_to_milliseconds(ts: str) -> int:
    pattern_hmsms = re.compile(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms")

    if pattern_hmsms.match(ts):
        h, m, s, ms = pattern_hmsms.match(ts).groups()
    else:
        # dot format
        parts = ts.split('.')
        if len(parts) != 4:
            raise ValueError(f"Unrecognized timestamp format: {ts}")
        h, m, s, ms = parts

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

def ffmpeg_extract_full_audio(source_file_path) -> str:
    ffmpeg_path, _ = get_ffmpeg_exe_path()

    base, _ = os.path.splitext(source_file_path)
    output_path = base + ".mp3"

    delay_ms = get_audio_start_time_ms(source_file_path)

    cmd = [
        f"{ffmpeg_path}", "-y",
        "-i", source_file_path,
        "-map", "0:a:0" # first track
    ]

    # add delay to beginning if detected
    if delay_ms != 0:
        adelay_str = f"{delay_ms}|{delay_ms}"
        cmd += [
            "-af", f"adelay={adelay_str}"
        ]

    cmd += [
        "-b:a", "192k",
        output_path
    ]

    print(f"Running FFmpeg command: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print(f"Converted to mp3: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print("FFmpeg conversion failed:", e)
        return ""

def get_audio_start_time_ms(source_file_path: str) -> int:
    _, ffprobe_path = get_ffmpeg_exe_path()
    try:
        result = subprocess.run(
            [
                f"{ffprobe_path}",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_packets",
                "-read_intervals", "0%+#5",
                "-print_format", "compact",
                source_file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        output = result.stdout

        # find first pts_time using regex
        match = re.search(r"pts_time=(\d+)", output)
        if match:
            start_time = float(match.group(1))
            delay_ms = round(start_time * 1000)
            return delay_ms
        else:
            print("No pts_time found in packets output.")
            return 0
    except Exception as e:
        print(f"Could not get pts_time from packets: {e}")
        return 0

def alter_sound_file_times(sound_line, start_ms, end_ms, relative_index) -> str:
    config = extract_config_data()
    lufs = config["lufs"]
    bitrate = config["bitrate"]

    altered_data = get_altered_sound_data(sound_line, start_ms, end_ms, relative_index)
    print("altered_data new_filename: " + altered_data['new_filename'])
    data = extract_sound_line_data(sound_line)
    if not altered_data:
        return ""

    if os.path.exists(altered_data["old_path"]):
        send2trash(altered_data["old_path"])

    filename_base = data["filename_base"]
    source_path = get_source_file(filename_base)

    cmd = create_ffmpeg_extract_audio_command(
        source_path,
        altered_data["new_start_time"],
        altered_data["new_end_time"],
        altered_data["new_path"]
    )
    try:
        print("Running subprocess command1:", cmd)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # print("Audio extraction succeeded.")
    except subprocess.CalledProcessError:
        print("FFmpeg failed.")
        return ""

    if os.path.exists(altered_data["new_path"]):
        return f"[sound:{altered_data['new_filename']}]"
    return ""


def get_altered_sound_data(sound_line, lengthen_start_ms, lengthen_end_ms, relative_index) -> dict:
    config = extract_config_data()
    normalize_audio = config["normalize_audio"]
    lufs = config["lufs"]

    data = extract_sound_line_data(sound_line)
    if not data:
        return {}

    # convert timestamps to ms
    orig_start_ms = time_hmsms_to_milliseconds(data["start_time"])
    orig_end_ms = time_hmsms_to_milliseconds(data["end_time"])

    start_index = data["start_index"]
    end_index = data["end_index"]

    if relative_index == 1:
        if lengthen_end_ms > 0:
            end_index += 1
        elif lengthen_end_ms < 0:
            end_index -= 1
    elif relative_index == -1:

        if lengthen_start_ms > 0:
            start_index -= 1
        elif lengthen_start_ms < 0:
            start_index += 1

    new_start_ms = max(0, orig_start_ms - lengthen_start_ms)
    new_end_ms = max(0, orig_end_ms + lengthen_end_ms)

    if new_end_ms <= new_start_ms:
        print(f"Invalid time range for {sound_line}: {new_start_ms}-{new_end_ms}")
        return {}

    new_start_time = milliseconds_to_hmsms_format(new_start_ms)
    new_end_time = milliseconds_to_hmsms_format(new_end_ms)

    time_range = f"{new_start_time}-{new_end_time}"
    filename_parts = [data["filename_base"], "ABCD", time_range]

    subtitle_range = f"{start_index}-{end_index}" if start_index is not None and end_index is not None else ""
    if subtitle_range:
        filename_parts.append(subtitle_range)

    if normalize_audio:
        filename_parts.append(f"{lufs}LUFS")

    new_filename = "`".join(filename_parts) + f".{data['file_extension']}"
    new_path = os.path.join(get_collection_dir(), new_filename)

    return {
        "new_start_time": new_start_time,
        "new_end_time": new_end_time,
        "new_filename": new_filename,
        "new_path": new_path,
        "old_path": data["collection_path"]
    }




def extract_config_data():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    default_model = config.get("default_model")
    default_deck = config.get("default_deck")
    audio_ext = config.get("audio_ext")
    bitrate = config.get("bitrate")
    image_height = config.get("image_height")
    pad_start = config.get("pad_start")
    pad_end = config.get("pad_end")
    target_language = config.get("target_language")
    translation_language = config.get("translation_language")
    target_language_code = config.get("target_language_code")
    translation_language_code = config.get("translation_language_code")
    normalize_audio = config.get("normalize_audio")
    lufs = config.get("lufs")
    target_audio_track = config.get("target_audio_track")
    target_subtitle_track = config.get("target_subtitle_track")
    translation_audio_track = config.get("translation_audio_track")
    translation_subtitle_track = config.get("translation_subtitle_track")
    mapped_fields = config.get("mapped_fields")
    selected_tab_index = config.get("selected_tab_index")

    variable_names = [
        "default_model", "default_deck", "audio_ext", "bitrate", "image_height",
        "pad_start", "pad_end", "target_language", "translation_language",
        "target_language_code", "translation_language_code", "normalize_audio",
        "lufs", "target_audio_track", "target_subtitle_track",
        "translation_audio_track", "translation_subtitle_track",
        "mapped_fields", "selected_tab_index"
    ]

    variables = [
        default_model, default_deck, audio_ext, bitrate, image_height,
        pad_start, pad_end, target_language, translation_language,
        target_language_code, translation_language_code, normalize_audio,
        lufs, target_audio_track, target_subtitle_track,
        translation_audio_track, translation_subtitle_track,
        mapped_fields, selected_tab_index
    ]

    missing_fields = [name for name, val in zip(variable_names, variables) if val is None]
    if missing_fields:
        showInfo(f"Missing fields: {', '.join(missing_fields)}")
        raise ValueError(f"Missing required config field(s): {missing_fields}")

    return {
        "default_model": default_model,
        "default_deck": default_deck,
        "audio_ext": audio_ext,
        "bitrate": bitrate,
        "image_height": image_height,
        "pad_start": pad_start,
        "pad_end": pad_end,
        "target_language": target_language,
        "translation_language": translation_language,
        "target_language_code": target_language_code,
        "translation_language_code": translation_language_code,
        "normalize_audio": normalize_audio,
        "lufs": lufs,
        "target_audio_track": target_audio_track,
        "target_subtitle_track": target_subtitle_track,
        "translation_audio_track": translation_audio_track,
        "translation_subtitle_track": translation_subtitle_track,
        "mapped_fields": mapped_fields,
        "selected_tab_index": selected_tab_index
    }


