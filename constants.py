import json
import re
import os
import inspect
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

from aqt.utils import showInfo
import html

# logging functions
DEBUG_FILENAME = True
DEBUG_COMMAND = True
DEBUG_ERROR = True
DEBUG_IMAGE = False
DEBUG_DATABASE = True

# integers
ms_amount = 50

# files
addon_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(addon_dir, "config.json")

database_updating = threading.Event()
database_items_left = 0


temp_ffmpeg_folder = os.path.join(addon_dir, "ffmpeg")
temp_ffmpeg_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffmpeg.exe")
temp_ffprobe_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffprobe.exe")

# strings
target_subtitle_line_string = "Target Subtitle Line"
target_audio_string = "Target Audio"
translation_subtitle_line_string = "Translation Subtitle Line"
translation_audio_string = "Translation Audio"
image_string = "Image"

audio_extensions = [
    ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"
]

video_extensions = [
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4b"
]

subtitle_extensions = {".srt", ".vtt", ".ass", ".ssa"}

BACKTICK_PATTERN = re.compile(
    r'^(?:\[sound:)?'
    r'(?P<filename_base>[^`.]+)'
    r'(?P<source_file_extension>\.[^`]+)?'
    r'(?:`(?P<lang_code>[a-z]{3})(?:-(?P<timing_lang_code>[a-z]{3}))?)?'
    r'`(?P<start_time>\d{2}h\d{2}m\d{2}s\d{3}ms)-'
    r'(?P<end_time>\d{2}h\d{2}m\d{2}s\d{3}ms)`'
    r'(?P<subtitle_range>\d+-\d+)'
    r'(?:`(?P<normalize_tag>[^`]+))?'
    r'\.(?P<sound_file_extension>\w+)'
    r'(?:\])?$',
    re.IGNORECASE
)


addon_dir = addon_dir
default_source_dir = os.path.join(addon_dir, "Sources")
select_note_type_string = "Please Select a Note Type"

default_settings = {
    "default_model": f"{select_note_type_string}",
    "source_folder": f"{default_source_dir}",
    "default_deck": "Default",
    "audio_ext": "mp3",
    "bitrate": 192,
    "image_height": 1080,
    "pad_start_target": 0,
    "pad_end_target": 0,
    "pad_start_translation": 0,
    "pad_end_translation": 0,
    "target_language": "",
    "translation_language": "",
    "target_language_code": "",
    "translation_language_code": "",
    "normalize_audio": True,
    "lufs": -16,
    "target_audio_track": 1,
    "target_subtitle_track": 1,
    "translation_audio_track": 2,
    "translation_subtitle_track": 2,
    "target_timing_code": "",
    "translation_timing_code": "",
    "target_timing_track": 3,
    "translation_timing_track": 3,
    "timing_tracks_enabled": False,
    "selected_tab_index": 0,
    "autoplay": False,
    "show_buttons": True,
}

# menu
CONTAINER_MARGINS = (2, 2, 2, 2)
CONTAINER_SPACING = 8
ROW_MARGINS = (0, 0, 0, 0)
ROW_SPACING = 10
BUTTON_ROW_MARGINS = (0, 0, 0, 0)
BUTTON_ROW_SPACING = 12
LABEL_MIN_WIDTH = 120
SPINBOX_MIN_WIDTH = 60
CHECKBOX_MIN_WIDTH = 150
BUTTON_PADDING = "padding: 1px 4px;"
SHIFT_BUTTON_BG_COLOR = "#f0d0d0"



def log_filename(message):
    if DEBUG_FILENAME:
        frame = inspect.stack()[1]
        func = frame.function
        file = os.path.basename(frame.filename)
        line = frame.lineno
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {file}:{line} in {func}:\n{message.strip()}\n")

def log_command(message):
    if DEBUG_COMMAND:
        frame = inspect.stack()[1]
        func = frame.function
        file = os.path.basename(frame.filename)
        line = frame.lineno
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {file}:{line} in {func}:\n[command] {message.strip()}\n")

def log_error(message):
    if DEBUG_ERROR:
        frame = inspect.stack()[1]
        func = frame.function
        file = os.path.basename(frame.filename)
        line = frame.lineno
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {file}:{line} in {func}:\n[error] {message.strip()}\n")

def log_image(message):
    if DEBUG_IMAGE:
        frame = inspect.stack()[1]
        func = frame.function
        file = os.path.basename(frame.filename)
        line = frame.lineno
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {file}:{line} in {func}:\n[image] {message.strip()}\n")

def log_database(message):
    if DEBUG_DATABASE:
        frame = inspect.stack()[1]
        func = frame.function
        file = os.path.basename(frame.filename)
        line = frame.lineno
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {file}:{line} in {func}:\n[database] {message.strip()}\n")


def get_ffmpeg_exe_path():
    exe_path = shutil.which("ffmpeg")
    probe_path = shutil.which("ffprobe")
    if exe_path:
        return exe_path, probe_path

    if os.path.exists(temp_ffmpeg_exe):
        return temp_ffmpeg_exe, temp_ffprobe_exe

    log_error("FFmpeg executable not found in PATH or addon folder.")
    showInfo("FFmpeg is not installed or could not be found.\n\n"
             "Either install FFmpeg globally and add it to your system PATH,\n"
             "or place ffmpeg.exe in the addon folder under: ffmpeg/bin/ffmpeg.exe")
    return None, None

def normalize_text(s):
    s = html.unescape(s)
    s = re.sub(r'<.*?>', '', s)
    s = re.sub(r'（.*?）|\(.*?\)', '', s)
    s = s.replace('\xa0', '')  # Non-breaking space
    s = re.sub(r'[\u2000-\u200B\u3000\s]+', '', s)
    s = re.sub(r'[‐‑‒–—―─]+', '-', s)
    return s.strip()

def get_audio_start_time_ms_for_track(source_path, audio_stream_index):
    try:
        ffmpeg_path, ffprobe_path = get_ffmpeg_exe_path()

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", f"a:{audio_stream_index}",
            "-show_entries", "stream=start_time",
            "-of", "json",
            source_path
        ]
        result = silent_run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)

        info = json.loads(result.stdout)

        streams = info.get("streams", [])
        if not streams:
            return 0

        start_time_str = streams[0].get("start_time", "0")
        start_time_sec = float(start_time_str)
        delay_ms = int(start_time_sec * 1000)

        return max(delay_ms, 0)

    except Exception as e:
        log_error(f"Failed to get audio start time for track {audio_stream_index} in {source_path}: {e}")
        return 0

def extract_config_data():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")

    if not os.path.exists(config_path):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_settings, f, indent=2)
        config = default_settings.copy()
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # Fill in any missing keys with defaults
    for key, value in default_settings.items():
        if key not in config:
            config[key] = value

    # Save back any missing defaults to file
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return config

config = extract_config_data()
addon_source_folder = config["source_folder"]

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

def format_timestamp_for_filename(timestamp: str) -> str:
    return timestamp.replace(':', '.').replace(',', '.')


def silent_run(*args, **kwargs):
    log_command(f"silent_run called with: {args[0]}")
    if sys.platform.startswith("win"):
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return subprocess.run(*args, **kwargs)

def timed_call(func, *args, **kwargs):
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    print(f"{func.__name__} took {elapsed:.4f} seconds")
    return result

# returns collection directory
def get_collection_dir():
    from aqt import mw
    if not mw or not mw.col:
        print("Collection is not loaded yet.")
    return mw.col.media.dir()

def is_add_editor(editor):
    from aqt.addcards import AddCards
    return isinstance(editor.parentWindow, AddCards)

def format_anki_safe_filename(text, revert):
    unsafe_chars = {'꞉', '～'}
    found = [c for c in text if c in unsafe_chars]
    if found:
        unique_found = sorted(set(found))
        showInfo(f"Incompatible characters detected in filename:\n"
                 f"{text}\n"
                 f"Please remove or replace: '{' '.join(unique_found)}'")
        return ""

    if not revert:
        text = text.replace('[', '((').replace(']', '))')
    else:
        text = text.replace('((', '[').replace('))', ']')

    return text