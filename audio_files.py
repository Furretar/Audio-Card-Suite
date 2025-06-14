
import os

from aqt.utils import showInfo
from send2trash import send2trash
from aqt import mw
addon_dir = os.path.dirname(os.path.abspath(__file__))
addon_source_folder = os.path.join(addon_dir, "Sources")
import re
from aqt.editor import Editor

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


def extract_sound_line_data(text: str):
    match = re.search(
        r"\[sound:(.+?)_(\d+\.\d+\.\d+\.\d+)-(\d+\.\d+\.\d+\.\d+)\.(\w+)\]",
        text,
        flags=re.UNICODE
    )

    if not match:
        return None

    filename_base = match.group(1).replace(" ", "_")
    start_time = match.group(2)
    end_time = match.group(3)
    file_extension = match.group(4)
    full_source_filename = f"{filename_base}.{file_extension}"
    timestamp_filename = f"{filename_base}_{start_time}-{end_time}.{file_extension}"
    audio_collection_path = os.path.join(collection_dir, timestamp_filename)
    screenshot_filename = f"{filename_base}_{start_time}.jpg"
    screenshot_collection_path = os.path.join(collection_dir, screenshot_filename)

    source_path = get_source_file(filename_base)
    return {
        "filename_base": filename_base,
        "start_time": start_time,
        "end_time": end_time,
        "file_extension": file_extension,
        "full_source_filename": full_source_filename,
        "timestamp_filename": timestamp_filename,
        "collection_path": audio_collection_path,
        "source_path": source_path,
        "screenshot_filename": screenshot_filename,
        "screenshot_collection_path": screenshot_collection_path,
    }

def format_timestamp_for_filename(timestamp: str) -> str:
    return timestamp.replace(':', '.').replace(',', '.')



def extract_first_subtitle_line(video_path, srt_output_path):
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

def get_subtitle_sentence_text_from_relative_index(sentence_text, relative_index) -> str:
    subtitle_path = get_subtitle_file_from_sentence_text(sentence_text)
    with open(subtitle_path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    i = 0
    while i < len(lines):
        if lines[i] != "" and sentence_text in lines[i]:
            target_index = i + (4 * relative_index)
            if 0 <= target_index < len(lines):
                target_line = lines[i + (4 * relative_index)]
                return target_line
            else:
                print(f"Index {target_index} out of bounds for lines of length {len(lines)}")
                return ""
        i += 1
    return ""



def get_subtitle_file_from_sentence_text(sentence_text) -> str:
    for filename in os.listdir(addon_source_folder):
        filename_base, file_extension = os.path.splitext(filename)
        if file_extension.lower() in video_exts:
            video_path = os.path.join(addon_source_folder, filename)
            subtitle_path = os.path.join(addon_source_folder, filename_base + ".srt")

            if not os.path.exists(subtitle_path):
                extract_first_subtitle_line(video_path, subtitle_path)
                if not os.path.exists(subtitle_path):
                    print(f"Failed to extract subtitles from {video_path}")
                    continue

            with open(subtitle_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()

            i = 0
            # print(f"reading file: {filename_base}" + ".srt")

            while i < len(lines):
                if lines[i] != "" and sentence_text in lines[i]:
                    return subtitle_path
                i += 1
    return ""

def get_timestamps_from_sentence_text(sentence_text) -> str:
    subtitle_path = get_subtitle_file_from_sentence_text(sentence_text)
    if not subtitle_path:
        print(f"No subtitle file found containing sentence: {sentence_text}")
        return ""

    filename_base, file_extension = os.path.splitext(os.path.basename(subtitle_path))
    filename = os.path.basename(subtitle_path)
    with open(subtitle_path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    # print(f"reading file: {filename_base}" + ".srt")
    for i in range(1, len(lines)):
        if lines[i] != "" and sentence_text in lines[i]:
            timestamp_line = lines[i - 1]
            try:
                start_srt, end_srt = [t.strip() for t in timestamp_line.split('-->')]
                start_time = format_timestamp_for_filename(start_srt)
                end_time = format_timestamp_for_filename(end_srt)
                filename_base, _ = os.path.splitext(filename)
                return f"[sound:{filename_base}_{start_time}-{end_time}.mp3]"
            except Exception as e:
                print(f"Error parsing timestamp near line {i}: {e}")
                return ""

    print(f"Sentence not found in subtitle file: {subtitle_path}")
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
        print("End time must be after start time")
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

def time_to_milliseconds(t: str) -> int:
    parts = t.split('.')
    if len(parts) != 4:
        raise ValueError("Time string must be in HH.MM.SS.mmm format")

    h, m, s, ms = parts
    total_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    return total_ms

def milliseconds_to_anki_time_format(ms: int) -> str:
    hours = ms // (3600 * 1000)
    ms %= (3600 * 1000)
    minutes = ms // (60 * 1000)
    ms %= (60 * 1000)
    seconds = ms // 1000
    millis = ms % 1000
    return f"{hours:02d}.{minutes:02d}.{seconds:02d}.{millis:03d}"

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

def alter_sound_file_times(filename, start_ms, end_ms) -> str:
    print("received filename:", filename)
    data = extract_sound_line_data(filename)
    if not data:
        return ""
    filename_base = data["filename_base"]
    start_time = data["start_time"]
    end_time = data["end_time"]
    file_extension = data["file_extension"]
    full_source_filename = data["full_source_filename"]
    old_timestamp_path = data["collection_path"]
    source_path = data["source_path"]

    if not source_path or not os.path.isfile(source_path):
        print(f"Missing source file for base name: {filename_base}")
        return ""


    # recycle original file
    print(f"checking for old file to delete: {old_timestamp_path}")
    if os.path.exists(old_timestamp_path):
        send2trash(old_timestamp_path)
        print(f"Moved existing file {old_timestamp_path} to recycle bin.")

    # initialize times in milliseconds
    start_milliseconds = time_to_milliseconds(start_time)
    end_milliseconds = time_to_milliseconds(end_time)

    # apply adjustments, ensure not negative
    if start_ms != 0:
        start_milliseconds = max(0, start_milliseconds + start_ms)
    if end_ms != 0:
        end_milliseconds = max(0, end_milliseconds + end_ms)

    # validate times
    if end_milliseconds <= start_milliseconds:
        print("Invalid time range: end time must be after start time")
        return ""

    # convert back to anki time format
    new_start_time = milliseconds_to_anki_time_format(start_milliseconds)
    new_end_time = milliseconds_to_anki_time_format(end_milliseconds)
    print(f"new_start_time: {new_start_time}")
    print(f"new_end_time: {new_end_time}")


    new_timestamp_filename = f"{filename_base}_{new_start_time}-{new_end_time}.{file_extension}"
    old_timestamp_filename = f"{filename_base}_{start_time}-{end_time}.{file_extension}"
    print(f"new_timestamp_filename: {new_timestamp_filename}")
    new_timestamp_path = os.path.join(collection_dir, new_timestamp_filename)

    ffmpeg_command = create_ffmpeg_extract_audio_command(source_path, new_start_time, new_end_time, "192", new_timestamp_path)
    try:
        print(f"running command: {ffmpeg_command}")
        subprocess.run(ffmpeg_command, check=True)
        print(f"Created extracted audio: {new_timestamp_path}")
    except subprocess.CalledProcessError as e:
        print("FFmpeg failed:", e)
        return ""



    if os.path.exists(new_timestamp_path):
        return f"[sound:{new_timestamp_filename}]"
    else:
        print(f"file not found: {new_timestamp_path}")
        print(f"using old path: {old_timestamp_path}")
        return f"[sound:{old_timestamp_filename}]"

import subprocess
import re


#
#
# print(get_timestamps_from_sentence_text("這樣根本就不能露營嘛"))

# print(change_filename_start_time("[sound:Yuru_Camp_S1E01_00.17.38.583-00.17.40.084.mp3]", -5000))


# print("results: " + alter_sound_file_times("[sound:jìnjī_de_jùrén_s1_1-5_5_0.21.02.887-0.21.07.283.mp3]", 50, 50))