
import os
import shutil

from aqt.utils import showInfo
from send2trash import send2trash
from aqt import mw
addon_dir = os.path.dirname(os.path.abspath(__file__))
addon_source_folder = os.path.join(addon_dir, "Sources")
temp_ffmpeg_folder = os.path.join(addon_dir, "ffmpeg")
temp_ffmpeg_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffmpeg.exe")
temp_ffprobe_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffprobe.exe")
from aqt.editor import Editor
import subprocess
import re
import json
from .button_actions import get_field_key_from_label

addon_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(addon_dir, "config.json")

def get_config_data():
    if os.path.exists(config_dir):
        with open(config_dir, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


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
    print(f"format_type: {format_type}")
    if format_type == "backtick":

        match = BACKTICK_PATTERN.match(sound_line)
        if not match:
            print(f"no match for backtick")
            return None
        groups = match.groupdict()
        filename_base = groups["filename_base"].replace(" ", "_")
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
        filename_base = groups["filename_base"].replace(" ", "_")
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
        if sound_line.startswith("[sound:") and sound_line.endswith("]"):
            filename = sound_line[len("[sound:"):-1]
            filename = filename.replace(" ", "_")  # replace spaces if any
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


def extract_subtitle_files(video_path, srt_output_path):
    config = get_config_data()
    print(f"config: {config}")
    target_subtitle_track_num = config.get("target_subtitle_track_num")
    translation_subtitle_track_num = config.get("translation_subtitle_track_num")

    exe_path, probe_path = get_ffmpeg_exe_path()

    def get_lang_code(track_num):
        if not track_num:
            showInfo("tracks not set")
            return
        cmd = [
            probe_path,
            "-v", "error",
            "-select_streams", f"s:{track_num-1}",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            data = json.loads(result.stdout)
            return data['streams'][0]['tags'].get('language', '')
        except Exception:
            return ''

    target_lang_code = get_lang_code(target_subtitle_track_num)
    if not target_lang_code:
        showInfo("tracks not set")
        return
    translation_lang_code = get_lang_code(translation_subtitle_track_num)
    if not translation_lang_code:
        showInfo("tracks not set")
        return
    srt_output_path_no_ext = os.path.splitext(srt_output_path)[0]
    note_type_name = list(config.get("mapped_fields", {}).keys())[0]
    translation_field = get_field_key_from_label(note_type_name, "Translation Sub Line", config)

    # target line
    tagged_target_subtitle = f"{srt_output_path_no_ext}`track_{target_subtitle_track_num}`{target_lang_code}.srt"
    target_path = os.path.join(addon_source_folder, os.path.basename(tagged_target_subtitle))
    if target_subtitle_track_num > 0 and not os.path.exists(target_path):
        try:
            print(f"Extracting target_subtitle_track subtitle for {video_path}")
            subprocess.run([
                exe_path,
                "-y",
                "-i", video_path,
                "-map", f"0:s:{target_subtitle_track_num - 1}",
                f"{tagged_target_subtitle}"
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to extract target subtitles from {video_path}: {e}")

    # translation line
    tagged_translation_subtitle = f"{srt_output_path_no_ext}`track_{translation_subtitle_track_num}`{translation_lang_code}.srt"
    translation_path = os.path.join(addon_source_folder, os.path.basename(tagged_translation_subtitle))
    if translation_subtitle_track_num > 0 and translation_field and not os.path.exists(translation_path):
        try:
            print(f"Extracting translation_subtitle_track_num subtitle for {video_path}")
            subprocess.run([
                exe_path,
                "-y",
                "-i", video_path,
                "-map", f"0:s:{translation_subtitle_track_num - 1}",
                f"{tagged_translation_subtitle}"
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to extract translation subtitles from {video_path}: {e}")
            showInfo(f"Failed to extract translation subtitles from {video_path}: {e}")


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

def get_valid_backtick_sound_line_and_block(sound_line: str, sentence_text: str) -> str:

    if not sound_line:
        block, subtitle_path = get_subtitle_block_and_subtitle_path_from_sentence_text(sentence_text)
        print(f"\nblock from text {sentence_text}: {block}\n")
        if not block or not subtitle_path:
            return None, None
        sound_line = get_sound_line_from_subtitle_block_and_path(block, subtitle_path)
        return sound_line, block

    format = detect_format(sound_line)
    print(f"detected format: {format}")
    if format != "backtick" and format!= "subs2srs":
        block, subtitle_path = get_subtitle_block_and_subtitle_path_from_sentence_text(sentence_text)
        if block is None or subtitle_path is None:
            return None, None
        sound_line = get_sound_line_from_subtitle_block_and_path(block, subtitle_path)

    data = extract_sound_line_data(sound_line)


    filename_base = data["filename_base"]
    source_path = get_source_file(filename_base)
    subtitle_path = os.path.splitext(source_path)[0] + ".srt"


    if format == "backtick":
        start_index = data["start_index"]
        end_index = data["end_index"]
        single_block = get_subtitle_block_from_sound_line_and_sentence_text(sound_line, sentence_text)
        return sound_line, single_block
    elif format == "subs2srs":
        first_sentence = sentence_text.strip().split()[0]
        print(f"first_sentence: {first_sentence}")
        # returns first matching sentence so subs2srs card can be reformatted
        block = get_subtitle_block_from_sound_line_and_sentence_text(sound_line, first_sentence)
        if block is None:
            return None, None
        sound_line = get_sound_line_from_subtitle_block_and_path(block, subtitle_path)


    return sound_line, block



def get_subtitle_block_from_sound_line_and_sentence_text(sound_line: str, sentence_text: str):
    data = extract_sound_line_data(sound_line)
    if not data:
        print(f"no data extracted from {sound_line}")
        return None, None

    start_index = data["start_index"]
    end_index   = data["end_index"]

    filename_base = data["filename_base"]
    source_path = get_source_file(filename_base)
    subtitle_path = os.path.splitext(source_path)[0] + ".srt"

    if not os.path.exists(subtitle_path):
        source_path = get_source_file(filename_base)
        subtitle_path = os.path.join(addon_source_folder, filename_base + ".srt")
        extract_subtitle_files(source_path, subtitle_path)

        if not os.path.exists(subtitle_path):
            print(f"Failed to extract subtitles from {source_path}")
            return None


    with open(subtitle_path, 'r', encoding='utf-8') as f:
        blocks = f.read().strip().split('\n\n')

    for block in blocks:
        formatted_block = format_subtitle_block(block)
        if formatted_block and len(formatted_block) == 4:
            subtitle_text = formatted_block[3]
            if normalize_text(sentence_text) in normalize_text(subtitle_text):
                return formatted_block

    return None
def get_subtitle_path_from_filename(filename):
    filename_base, file_extension = os.path.splitext(filename)
    config = get_config_data()
    target_language_code = config.get("subs_target_language_code")
    target_subtitle_track_num = config.get("target_subtitle_track_num")

def get_subtitle_block_and_subtitle_path_from_sentence_text(sentence_text: str):
    for filename in os.listdir(addon_source_folder):
        print(f"checking filename: {filename}")
        filename_base, file_extension = os.path.splitext(filename)
        if file_extension.lower() in video_exts or file_extension.lower() in audio_exts:
            video_path = os.path.join(addon_source_folder, filename)
            subtitle_path = os.path.join(addon_source_folder, filename_base + ".srt")

            # extract subtitles if .srt doesnt exist
            if not os.path.exists(subtitle_path):
                extract_subtitle_files(video_path, subtitle_path)
                if not os.path.exists(subtitle_path):
                    print(f"Failed to extract subtitles from {video_path}")
                    continue

            with open(subtitle_path, 'r', encoding='utf-8') as f:
                blocks = f.read().strip().split('\n\n')

            for block in blocks:
                formatted_block = format_subtitle_block(block)
                if formatted_block and len(formatted_block) == 4:
                    subtitle_text = formatted_block[3]

                    if normalize_text(sentence_text) in normalize_text(subtitle_text):
                        return formatted_block, subtitle_path

    return None, None

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

    filename_base, _ = os.path.splitext(os.path.basename(subtitle_path))

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
    alt_names = [filename_base, filename_base.replace("_", " ")]
    for name in alt_names:
        for ext in set(video_exts):
            path = os.path.join(addon_source_folder, name + ext)
            if os.path.exists(path):
                return path
    return ""

def get_source_file(filename_base) -> str:
    mp3_path = os.path.join(addon_source_folder, filename_base + ".mp3")
    # if os.path.exists(mp3_path):
    #     return mp3_path
    # elif os.path.exists(mp3_path.replace("_", " ")):
    #     return mp3_path.replace("_", " ")

    alt_names = [filename_base, filename_base.replace("_", " ")]

    for name in alt_names:
        video_source_path = check_for_video_source(name)
        if video_source_path:
            return video_source_path

        for ext in set(audio_exts):
            path = os.path.join(addon_source_folder, name + ext)
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

    print("No image found, extracting from source.")

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
    timestamp = convert_to_default_time_notation(image_timestamp)
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

normalize_audio = True
lufs = -16
temp_file_extension = "mp3"


def create_ffmpeg_extract_audio_command(source_path, start_time, end_time, lufs, kbps, collection_path) -> list:
    ffmpeg_path, _ = get_ffmpeg_exe_path()

    start = convert_to_default_time_notation(start_time)
    end = convert_to_default_time_notation(end_time)
    duration_sec = time_to_seconds(end) - time_to_seconds(start)
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

    if normalize_audio and int(lufs) > 0:
        filters.append(f"loudnorm=I={lufs}:TP=-1.5:LRA=11")

    if filters:
        filter_str = ",".join(filters)
        cmd += ["-af", filter_str]

    cmd += ["-c:a", codec]

    if codec in ("libmp3lame", "libopus") and kbps:
        # For opus, bitrate can be specified in bps (e.g., 64000 for 64 kbps)
        bitrate = f"{kbps}k" if codec == "libmp3lame" else str(kbps * 1000)
        cmd += ["-b:a", bitrate]

    cmd.append(new_collection_path)

    return cmd


def create_just_normalize_audio_command(source_path, lufs, kbps) -> str:
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
        if kbps:
            cmd += ["-b:a", f"{kbps}k"]
    elif ext_no_dot == "opus":
        cmd += ["-c:a", "libopus"]
        if kbps:
            cmd += ["-b:a", str(kbps * 1000)]
    elif ext_no_dot == "flac":
        cmd += ["-c:a", "flac"]
    else:
        print(f"Unsupported audio format: {ext_no_dot}")
        return ""

    cmd.append(new_collection_path)
    return cmd



def convert_to_default_time_notation(t: str) -> str:
    hmsms_match = re.match(r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms", t)
    if hmsms_match:
        h, m, s, ms = hmsms_match.groups()
        return f"{h}:{m}:{s}.{ms}"

    parts = t.strip().split(".")
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"

    raise ValueError(f"Unrecognized timestamp format: {t}")

def time_to_seconds(t):
    h, m, s = t.split(':')
    s, ms = (s.split(',') if ',' in s else s.split('.'))
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def time_to_milliseconds(ts: str) -> int:
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

def milliseconds_to_anki_time_hmsms_format(ms: int) -> str:
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
        match = re.search(r"pts_time=([\d\.]+)", output)
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

kbps = 192
lufs = -16
def alter_sound_file_times(sound_line, start_ms, end_ms, relative_index) -> str:
    altered_data = get_altered_sound_data(sound_line, start_ms, end_ms, relative_index)
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
        f"{lufs}",
        f"{kbps}",
        altered_data["new_path"]
    )
    try:
        print("Running subprocess command:", cmd)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # print("Audio extraction succeeded.")
    except subprocess.CalledProcessError:
        print("FFmpeg failed.")
        return ""

    if os.path.exists(altered_data["new_path"]):
        return f"[sound:{altered_data['new_filename']}]"
    return ""

def convert_timestamp_dot_to_hmsms(ts: str) -> str:
    return re.sub(
        r"(\d{2})\.(\d{2})\.(\d{2})\.(\d{3})",
        r"\1h\2m\3s\4ms",
        ts
    )


def get_altered_sound_data(sound_line, lengthen_start_ms, lengthen_end_ms, relative_index) -> dict:
    data = extract_sound_line_data(sound_line)
    if not data:
        return {}

    # convert timestamps to ms
    orig_start_ms = time_to_milliseconds(data["start_time"])
    orig_end_ms = time_to_milliseconds(data["end_time"])

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

    new_start_time = milliseconds_to_anki_time_hmsms_format(new_start_ms)
    new_end_time = milliseconds_to_anki_time_hmsms_format(new_end_ms)

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

