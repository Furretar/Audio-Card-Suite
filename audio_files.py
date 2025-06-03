import re
import os
from aqt import mw

media_source_folder = os.path.join(os.getcwd(), "Sources")

def get_audio_from_text(audio_filename) -> str:
    pass

def get_audio_from_timestamps(audio_filename) -> str:
    text = audio_filename
    match = re.search(r"\[sound:(.+?)_(\d{2}\.\d{2}\.\d{2}\.\d{3})-(\d{2}\.\d{2}\.\d{2}\.\d{3})\.(\w+)\]", text)

    if not match:
        return ""

    filename_base = match.group(1)
    start_time = match.group(2)
    end_time = match.group(3)
    file_extension = match.group(4)
    print("Filename base:", filename_base)
    print("Start time:", start_time)
    print("End time:", end_time)
    print("File extension:", file_extension)

    if get_source_file(filename_base):
        if os.path.exists(os.path.join(mw.col.media.dir(), file_extension))



def get_source_file(filename_base) -> str:
    path = os.path.join(media_source_folder, filename_base + ".mp3")
    if os.path.exists(path):
        return path
    else:
        return ""

get_audio_from_timestamps("[sound:Yuru_Camp_S1E08_00.06.05.332-00.06.07.700.mp3]")