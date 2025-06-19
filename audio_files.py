
import os

from aqt.utils import showInfo
from send2trash import send2trash
from aqt import mw
addon_dir = os.path.dirname(os.path.abspath(__file__))
addon_source_folder = os.path.join(addon_dir, "Sources")
from aqt.editor import Editor
import subprocess
import re

# temp for testing outside of anki
if mw is not None and mw.col is not None and mw.col.media is not None:
    collection_dir = mw.col.media.dir()
else:
    # fallback path when running outside Anki
    collection_dir = r"C:\Users\wyatt\AppData\Roaming\Anki2\Furretar\collection.media"

audio_exts = [
    ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus", ".m4b"
]

video_exts = [
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4b"
]

def extract_sound_line_data(sound_line):
    regex_backtick = re.compile(
        r"""\[sound:
        (?P<filename_base>.+?)`                        # filename base
        (?P<sha>[a-zA-Z0-9]{4})`                       # 4-character SHA
        (?P<start_time>\d{2}h\d{2}m\d{2}s\d{3}ms)-     # start time
        (?P<end_time>\d{2}h\d{2}m\d{2}s\d{3}ms)`       # end time
        (?P<subtitle_range>\d+-\d+)                    # subtitle range
        (?:`(?P<normalize_tag>[a-z]{2}))?              # optional normalize tag
        \.(?P<file_extension>\w+)                      # file extension
        \]""",
        re.VERBOSE | re.UNICODE
    )

    regex_subs2srs = re.compile(
        r"""\[sound:
        (?P<filename_base>.+?)_                           # base
        (?P<start_time>\d{2}\.\d{2}\.\d{2}\.\d{3})-       # start time
        (?P<end_time>\d{2}\.\d{2}\.\d{2}\.\d{3})          # end time
        \.(?P<file_extension>\w+)\]                       # extension
        """,
        re.VERBOSE | re.UNICODE
    )

    def convert_timestamp_hmsms_to_dot(ts):
        return re.sub(
            r"(\d{2})h(\d{2})m(\d{2})s(\d{3})ms",
            r"\1.\2.\3.\4",
            ts
        )

    match = regex_backtick.search(sound_line)
    if match:
        groups = match.groupdict()
        filename_base = groups["filename_base"].replace(" ", "_")
        sha = groups["sha"]
        start_time_raw = groups["start_time"]
        end_time_raw = groups["end_time"]
        start_time = convert_timestamp_hmsms_to_dot(groups["start_time"])
        end_time = convert_timestamp_hmsms_to_dot(groups["end_time"])
        subtitle_range = groups["subtitle_range"]
        normalize_tag = groups["normalize_tag"]
        file_extension = groups["file_extension"]

        timestamp_filename = (
            f"{filename_base}`{sha}`{start_time_raw}`{end_time_raw}"
            f"`{subtitle_range}`{normalize_tag}.{file_extension}"
        )
    elif (match := regex_subs2srs.search(sound_line)):
        groups = match.groupdict()
        filename_base = groups["filename_base"].replace(" ", "_")
        sha = ""
        start_time_raw = groups["start_time"]
        end_time_raw = groups["end_time"]
        start_time = convert_timestamp_hmsms_to_dot(groups["start_time"])
        end_time = convert_timestamp_hmsms_to_dot(groups["end_time"])
        subtitle_range = ""
        normalize_tag = ""
        file_extension = groups["file_extension"]

        timestamp_filename = (
            f"{filename_base}_{start_time_raw}-{end_time_raw}.{file_extension}"
        )
    else:
        return None

    if subtitle_range:
        try:
            start_index, end_index = map(int, subtitle_range.split("-"))
        except ValueError:
            start_index, end_index = None, None
    else:
        start_index, end_index = None, None

    audio_collection_path = os.path.join(collection_dir, timestamp_filename)
    screenshot_filename = f"{filename_base}`{start_time}.jpg"
    screenshot_collection_path = os.path.join(collection_dir, screenshot_filename)
    source_path = get_source_file(filename_base)
    subtitle_path = os.path.splitext(source_path)[0] + ".srt"

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
        "screenshot_filename": screenshot_filename,
        "screenshot_collection_path": screenshot_collection_path,
        "source_path": source_path,
        "subtitle_path": subtitle_path,
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

def extract_first_subtitle_file(video_path, srt_output_path):
    try:
        print(f"Extracting first subtitle for {video_path}")
        subprocess.run([
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-map", "0:s:0",
            srt_output_path
        ])
    except subprocess.CalledProcessError as e:
        print(f"Failed to extract subtitles from {video_path}: {e}")

def format_subtitle_block(subtitle_block):
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

    formatted_block = []
    for block in blocks:
        formatted_block = format_subtitle_block(block)

    target_index = subtitle_index + relative_index
    if 0 <= target_index < len(formatted_block):
        return formatted_block[target_index]
    else:
        print(f"Relative index {relative_index} goes out of range at position {subtitle_index}")
        return ""

def get_block_and_subtitle_file_from_sentence_text(sentence_text) -> tuple[str, list[str]]:
    for filename in os.listdir(addon_source_folder):
        filename_base, file_extension = os.path.splitext(filename)
        if file_extension.lower() in video_exts:
            video_path = os.path.join(addon_source_folder, filename)
            subtitle_path = os.path.join(addon_source_folder, filename_base + ".srt")

            # extract subtitles if .srt doesnt exist
            if not os.path.exists(subtitle_path):
                extract_first_subtitle_file(video_path, subtitle_path)
                if not os.path.exists(subtitle_path):
                    print(f"Failed to extract subtitles from {video_path}")
                    continue

            with open(subtitle_path, 'r', encoding='utf-8') as f:
                content = f.read()

            blocks = content.strip().split('\n\n')
            for block in blocks:
                formatted_block = format_subtitle_block(block)
                if not formatted_block:
                    continue
                text = formatted_block[3]
                if normalize_text(sentence_text) in normalize_text(text):
                    return formatted_block, subtitle_path

    return "", []

def normalize_text(s):
    return ''.join(s.strip().split())


def convert_timestamp_dot_to_hmsms(ts: str) -> str:
    parts = ts.split('.')
    if len(parts) != 4:
        raise ValueError(f"Invalid timestamp format: {ts}")
    hours, minutes, seconds, milliseconds = parts
    return f"{hours}h{minutes}m{seconds}s{milliseconds}ms"


def get_sound_line_from_block_and_path(block, subtitle_path) -> str:
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
            print("now checking: ", path)
            if os.path.exists(path):
                return path
    return ""

def get_source_file(filename_base) -> str:
    mp3_path = os.path.join(addon_source_folder, filename_base + ".mp3")
    if os.path.exists(mp3_path):
        return mp3_path
    elif os.path.exists(mp3_path.replace("_", " ")):
        return mp3_path.replace("_", " ")

    alt_names = [filename_base, filename_base.replace("_", " ")]

    print("Mp3 Source file not found, attempting extraction:", mp3_path)
    for name in alt_names:
        video_source_path = check_for_video_source(name)
        if video_source_path:
            mp3_path = ffmpeg_extract_full_audio(video_source_path)
            return mp3_path

        for ext in set(audio_exts):
            path = os.path.join(addon_source_folder, name + ext)
            print("now checking: ", path)
            if os.path.exists(path):
                mp3_path = ffmpeg_extract_full_audio(path)
                return mp3_path

    print(f"No source file found for base name: {filename_base}")
    return ""

def get_video_duration_seconds(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print("Failed to get duration:", e)
        return 0

def add_image_if_empty(editor: Editor, screenshot_index, new_sound_tag: str):
    # check if any field already has an image
    for idx, field_text in enumerate(editor.note.fields):
        if ".jpg" in field_text or ".png" in field_text:
            return ""

    print(f"no image found, extracting from source")

    print("extracting data from: " + new_sound_tag)
    data = extract_sound_line_data(new_sound_tag)
    start_time = data["start_time"]
    filename_base = data["filename_base"]
    source_path = data["source_path"]
    screenshot_collection_path = data["screenshot_collection_path"]
    screenshot_filename = data["screenshot_filename"]
    video_source_path = check_for_video_source(filename_base)
    if not video_source_path:
        print(f"No video source found for {filename_base}")
        return ""

    screenshot_path = run_ffmpeg_extract_screenshot_command(video_source_path, start_time, screenshot_collection_path)

    if screenshot_path:
        embed_screenshot = f'<img src="{screenshot_filename}">'
        print(f"add screenshot: {embed_screenshot}")
        editor.note.fields[screenshot_index] = embed_screenshot
        editor.loadNote()
    else:
        showInfo("Could not add screenshot")

def run_ffmpeg_extract_screenshot_command(source_path, screenshot_timestamp, screenshot_collection_path) -> str:
    if source_path.lower().endswith(".m4b"):
        cmd = [
            "ffmpeg", "-y",
            "-i", source_path,
            "-an",
            "-vcodec", "copy",
            "-loglevel", "error",
            screenshot_collection_path
        ]
        try:
            print(f"Extracting cover from m4b: {cmd}")
            subprocess.run(cmd, check=True)
            if os.path.exists(screenshot_collection_path):
                print(f"Extracted cover: {screenshot_collection_path}")
                return screenshot_collection_path
            else:
                print("Cover extraction failed: file not found")
                return ""
        except subprocess.CalledProcessError as e:
            print("FFmpeg cover extraction failed:", e)
            return ""


    timestamp = convert_to_default_time_notation(screenshot_timestamp)

    cmd = [
        "ffmpeg", "-y",
        "-ss", timestamp,
        "-i", source_path,
        "-frames:v", "1",
        "-q:v", "15",
        screenshot_collection_path
    ]

    try:
        print(f"running command: {cmd}")
        subprocess.run(cmd, check=True)
        print(f"extracted screenshot: {screenshot_collection_path}")
        return screenshot_collection_path
    except subprocess.CalledProcessError as e:
        print("FFmpeg failed:", e)
        return ""

def create_ffmpeg_extract_audio_command(source_path, start_time, end_time, kbps, collection_path) -> str:
    start = convert_to_default_time_notation(start_time)
    end = convert_to_default_time_notation(end_time)
    duration_sec = time_to_seconds(end) - time_to_seconds(start)
    if duration_sec <= 0:
        print(f"End time must be after start time, {start}, {end}")
        return ""

    delay_ms = get_audio_start_time_ms(source_path)
    base, _ = os.path.splitext(collection_path)
    collection_path = f"{base}.mp3"


    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-i", source_path,
        "-map", "0:a:0",
        "-t", str(duration_sec),
    ]

    if delay_ms > 0:
        adelay = f"{delay_ms}|{delay_ms}"
        cmd += ["-af", f"adelay={adelay}"]

    cmd += [
        "-c:a", "libmp3lame",
        "-b:a", f"{kbps}k",
        collection_path
    ]

    return cmd

def convert_to_default_time_notation(t):
    parts = t.split('.')
    return f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"

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
    base, _ = os.path.splitext(source_file_path)
    output_path = base + ".mp3"

    delay_ms = get_audio_start_time_ms(source_file_path)

    cmd = [
        "ffmpeg", "-y",
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
    try:
        result = subprocess.run(
            [
                "ffprobe",
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
            print(f"delay time: {delay_ms}")
            return delay_ms
        else:
            print("No pts_time found in packets output.")
            return 0
    except Exception as e:
        print(f"Could not get pts_time from packets: {e}")
        return 0

def alter_sound_file_times(sound_line, start_ms, end_ms) -> str:
    altered_data = get_altered_sound_data(sound_line, start_ms, end_ms)
    print(f"altered data: {altered_data}")
    if not altered_data:
        return ""

    if os.path.exists(altered_data["old_path"]):
        send2trash(altered_data["old_path"])
        print(f"Moved existing file {altered_data['old_path']} to recycle bin.")

    cmd = create_ffmpeg_extract_audio_command(
        altered_data["source_path"],
        altered_data["new_start_time"],
        altered_data["new_end_time"],
        "192",
        altered_data["new_path"]
    )
    print("running command:", cmd)
    try:
        subprocess.run(cmd, check=True)
        print("Created extracted audio:", altered_data["new_path"])
    except subprocess.CalledProcessError as e:
        print("FFmpeg failed:", e)
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


def get_altered_sound_data(sound_line, start_ms, end_ms) -> dict:
    data = extract_sound_line_data(sound_line)
    print(f"getting altered sound data: {data}")
    if not data:
        return {}

    # convert timestamps to ms
    orig_start_ms = time_to_milliseconds(data["start_time"])
    orig_end_ms = time_to_milliseconds(data["end_time"])

    new_start_ms = max(0, orig_start_ms + start_ms)
    new_end_ms = max(0, orig_end_ms + end_ms)

    if new_end_ms <= new_start_ms:
        print(f"Invalid time range: {new_start_ms}-{new_end_ms}")
        return {}

    new_start_time = milliseconds_to_anki_time_hmsms_format(new_start_ms)
    new_end_time = milliseconds_to_anki_time_hmsms_format(new_end_ms)

    start_index = data["start_index"]
    end_index = data["end_index"]
    subtitle_range = f"{start_index}-{end_index}" if start_index is not None and end_index is not None else ""
    normalize_tag = "nm" if data.get("normalize_tag") else ""

    time_range = f"{new_start_time}-{new_end_time}"

    filename_parts = [data["filename_base"], "ABCD", time_range]
    if subtitle_range:
        filename_parts.append(subtitle_range)
    if normalize_tag:
        filename_parts.append(normalize_tag)

    new_filename = "`".join(filename_parts) + f".{data['file_extension']}"
    new_path = os.path.join(collection_dir, new_filename)

    return {
        "new_start_time": new_start_time,
        "new_end_time": new_end_time,
        "new_filename": new_filename,
        "new_path": new_path,
        "source_path": data["source_path"],
        "old_path": data["collection_path"]
    }
