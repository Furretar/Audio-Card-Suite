from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication
from aqt import gui_hooks
from aqt.sound import play
from aqt.utils import showInfo
import re
from aqt.editor import Editor
from aqt.sound import av_player
import os
from aqt import mw
import subprocess
from send2trash import send2trash


from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSpinBox, QCheckBox
)
import json
try:
    from . import manage_files
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import manage_files


ms_amount = 50

sound_idx = 2
sentence_idx = 0
image_idx = 3

addon_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(addon_dir, "config.json")

def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)

def get_field_key_from_label(note_type_name: str, label: str, config: dict) -> str:
    mapped_fields = config.get("mapped_fields", {}).get(note_type_name, {})
    for field_key, mapped_label in mapped_fields.items():
        if mapped_label == label:
            return field_key
    return ""

def get_sound_and_sentence_from_editor(editor: Editor):
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    note_type = editor.note.note_type()
    note_type_name = note_type["name"]
    fields = note_type["flds"]

    def index_of_field(field_name):
        for i, fld in enumerate(fields):
            if fld["name"] == field_name:
                return i
        return -1

    sentence_field = get_field_key_from_label(note_type_name, "Target Sub Line", config)
    sound_field = get_field_key_from_label(note_type_name, "Target Audio", config)
    translation_field = get_field_key_from_label(note_type_name, "Translation Sub Line", config)
    image_field = get_field_key_from_label(note_type_name, "Image", config)

    sentence_idx = index_of_field(sentence_field) if sentence_field else 0
    sound_idx = index_of_field(sound_field) if sound_field else 2
    translation_idx = index_of_field(translation_field) if translation_field else 4
    image_idx = index_of_field(image_field) if image_field else 3

    print(f"sentence_idx: {sentence_idx}")
    print(f"sound_idx: {sound_idx}")
    print(f"translation_idx: {translation_idx}")
    print(f"image_idx: {image_idx}")

    sound_line = editor.note.fields[sound_idx] if 0 <= sound_idx < len(editor.note.fields) else ""
    if "[sound:" not in sound_line:
        sound_line = ""

    image_line = editor.note.fields[image_idx] if 0 <= image_idx < len(editor.note.fields) else ""
    if "<img src=" not in image_line:
        image_line = ""

    sentence_text = editor.note.fields[sentence_idx] if 0 <= sentence_idx < len(editor.note.fields) else ""
    format = manage_files.detect_format(sound_line)
    if format != "backtick":
        selected_text = editor.web.selectedText().strip()
        if selected_text:
            sentence_text = selected_text
            print(f"using selected text: {sentence_text}")

    return (
        strip_html_tags(sound_line),
        sound_idx,
        strip_html_tags(sentence_text),
        sentence_idx,
        strip_html_tags(image_line),
        image_idx,
    )


def remove_edge_new_sentence_new_sound_file(sound_line, sentence_text, relative_index):
    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        print(f"no data extracted from {sound_line}")
        return None, None

    start_time = data["start_time"]
    end_time = data["end_time"]
    start_index = data["start_index"]
    end_index   = data["end_index"]

    filename_base = data["filename_base"]
    source_path = manage_files.get_source_file(filename_base)
    subtitle_path = os.path.splitext(source_path)[0] + ".srt"

    sentence_blocks = [b.strip() for b in sentence_text.split("\n\n") if b.strip()]
    if len(sentence_blocks) <= 1:
        print(f"no sentence blocks extracted from {sentence_text}")
        return None, None

    if relative_index == 1:
        # remove last block
        new_blocks = sentence_blocks[:-1]
        end_index -= 1
        new_edge_block = manage_files.get_subtitle_block_from_index_and_path(end_index - 1, subtitle_path)

    else:
        # remove first block
        new_blocks = sentence_blocks[1:]
        start_index += 1
        new_edge_block = manage_files.get_subtitle_block_from_index_and_path(start_index - 1, subtitle_path)

    print(f"edge block: {new_edge_block}")
    if abs(int(new_edge_block[0]) - start_index) > 10:
        print(f"\nblock from very far away\n")
    if not new_edge_block or len(new_edge_block) < 3:
        print(f"Could not locate boundary block: {new_edge_block}")
        return None, None

    new_start_time = start_time
    new_end_time = end_time
    if relative_index == 1:
        new_end_time = new_edge_block[2]

    else:
        new_start_time = new_edge_block[1]
    print(new_edge_block[3])
    orig_start_ms = manage_files.time_to_milliseconds(data["start_time"])
    orig_end_ms = manage_files.time_to_milliseconds(data["end_time"])
    new_start_ms = manage_files.time_to_milliseconds(new_start_time)
    new_end_ms = manage_files.time_to_milliseconds(new_end_time)

    lengthen_start = orig_start_ms - new_start_ms
    print(f"lengthen_start: {lengthen_start}")
    lengthen_end = new_end_ms - orig_end_ms
    print(f"lengthen_end: {lengthen_end}")

    new_sound_line = manage_files.alter_sound_file_times(
        sound_line,
        lengthen_start if relative_index == -1 else 0,
        lengthen_end if relative_index == 1 else 0,
        relative_index
    )

    if not new_sound_line:
        print("No new sound tag returned, field not updated.")
        return None, None

    new_sentence_text = "\n\n".join(new_blocks).strip()

    return new_sentence_text, new_sound_line

def remove_edge_lines_helper(editor, relative_index):
    print(f"got here")
    generate_fields_helper(editor)
    sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx = get_sound_and_sentence_from_editor(editor)


    new_sentence_text, new_sound_line = remove_edge_new_sentence_new_sound_file(sound_line, sentence_text, relative_index)

    if not new_sound_line or not new_sentence_text:
        print("No new sound line or sentence text returned.")
        return

    new_field = re.sub(r"\[sound:.*?\]", new_sound_line, sound_line)
    editor.note.fields[sound_idx] = new_field
    editor.note.fields[sentence_idx] = new_sentence_text

    def play_after_reload():
        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_line)
        if sound_filename:
            QTimer.singleShot(100, lambda: play(sound_filename.group(1)))

    editor.loadNote()
    QTimer.singleShot(50, play_after_reload)

    if not image_line.strip():
        generated_img = manage_files.get_image_if_empty_helper(image_line, sound_line)
        if generated_img and isinstance(generated_img, str):
            editor.note.fields[image_idx] = generated_img
        else:
            print("Image generation failed or result was not a string.")

    print(f"Removed {'last' if relative_index==1 else 'first'} block, new text:\n{new_sentence_text}")

def add_context_line_helper(editor: Editor, relative_index):
    generate_fields_helper(editor)
    sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx = get_sound_and_sentence_from_editor(editor)


    print(f"sound_line from editor: {sound_line}")
    new_sound_tag, context_sentence_text = get_context_line_data(sound_line, sentence_text, relative_index)

    if relative_index == 1:
        new_sentence_text = f"{sentence_text}\n\n{context_sentence_text}"
    else:
        new_sentence_text = f"{context_sentence_text}\n\n{sentence_text}"

    if new_sound_tag and new_sentence_text:
        editor.note.fields[sound_idx] = re.sub(r"\[sound:.*?\]", new_sound_tag, sound_line)
        editor.note.fields[sentence_idx] = new_sentence_text

        match = re.search(r"\[sound:(.*?)\]", new_sound_tag)
        sound_filename = match.group(1) if match else None

        def play_after_reload():
            if sound_filename:
                QTimer.singleShot(100, lambda: play(sound_filename))

        QTimer.singleShot(0, play_after_reload)
        editor.loadNote()

        if not image_line.strip():
            generated_img = manage_files.get_image_if_empty_helper(image_line, sound_line)
            if generated_img and isinstance(generated_img, str):
                editor.note.fields[image_idx] = generated_img
            else:
                print("Image generation failed or result was not a string.")

        print(f"new line {new_sentence_text}")

def get_context_line_data(sound_line, sentence_text, relative_index):

    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        return "", ""


    edge_index = data["end_index"] if relative_index == 1 else data["start_index"]

    filename_base = data["filename_base"]
    source_path = manage_files.get_source_file(filename_base)
    subtitle_path = os.path.splitext(source_path)[0] + ".srt"

    target_block = manage_files.get_subtitle_block_from_relative_index(relative_index, edge_index, subtitle_path)
    if not target_block or len(target_block) < 4:
        return "", ""

    target_line = target_block[3]
    new_sound_line = manage_files.get_sound_line_from_subtitle_block_and_path(target_block, subtitle_path)

    target_data = manage_files.extract_sound_line_data(new_sound_line)
    if not target_data:
        return "", ""

    start_ms = manage_files.time_to_milliseconds(data["start_time"])
    end_ms = manage_files.time_to_milliseconds(data["end_time"])
    target_start_ms = manage_files.time_to_milliseconds(target_data["start_time"])
    target_end_ms = manage_files.time_to_milliseconds(target_data["end_time"])

    if relative_index == 1:
        delta = target_end_ms - end_ms
        new_sound_line = manage_files.alter_sound_file_times(sound_line, 0, delta, relative_index)
        new_sentence_text = f"{target_line}"
    else:
        delta = start_ms - target_start_ms
        new_sound_line = manage_files.alter_sound_file_times(sound_line, delta, 0, relative_index)
        new_sentence_text = f"{target_line}"

    if not new_sound_line:
        return "", ""

    return new_sound_line.strip(), new_sentence_text.strip()

def adjust_sound_tag(editor, start_delta: int, end_delta: int) -> None:
    sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx = get_sound_and_sentence_from_editor(editor)

    # check for modifier keys
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        start_delta //= 2
        end_delta //= 2
    elif modifiers & Qt.KeyboardModifier.ControlModifier:
        start_delta *= 5
        end_delta *= 5

    print(f"current sound line: {sound_line}")
    fixed_sound_line, block = manage_files.get_valid_backtick_sound_line_and_block(sound_line, sentence_text)
    print(f"fixed sound line: {fixed_sound_line}")


    new_sound_line = manage_files.alter_sound_file_times(fixed_sound_line, -start_delta, end_delta, None)
    print(f"new sound line: {new_sound_line}")

    if new_sound_line:
        editor.note.fields[sound_idx] = new_sound_line
        editor.loadNote()


        if new_sound_line.startswith("[sound:") and new_sound_line.endswith("]"):
            filename = new_sound_line[len("[sound:"):-1]
            media_path = os.path.join(mw.col.media.dir(), filename)

            def wait_and_play():
                if os.path.exists(media_path) and os.path.getsize(media_path) > 0:
                    print(f"Playing sound from field {sound_idx}: {filename}")
                    play(filename)
                else:
                    print("File not ready, retrying...")
                    QTimer.singleShot(50, wait_and_play)

            QTimer.singleShot(50, wait_and_play)

    else:
        print("No new sound tag returned, field not updated.")
    return

def generate_fields_button(editor):
    sound_filename = generate_fields_helper(editor)
    if sound_filename:
        print(f"Playing sound filename: {sound_filename}")
        QTimer.singleShot(100, lambda: play(sound_filename))

def generate_fields_helper(editor):
    sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx = get_sound_and_sentence_from_editor(editor)
    print(f"current sound line: {sound_line}")

    updated = False

    new_result = generate_fields_sound_sentence_image(
        sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx
    )
    
    if not new_result or not all(new_result):
        print("generate_fields_sound_sentence_image failed to return valid values.")
        return None
    
    new_sound_line, new_sentence_text = new_result
    print(f"new sound line: {new_sound_line}")

    generated_img = None
    if not editor.note.fields[image_idx].strip():
        generated_img = manage_files.get_image_if_empty_helper("", new_sound_line)
        if generated_img and isinstance(generated_img, str):
            editor.note.fields[image_idx] = generated_img
            updated = True
        else:
            print("Image generation failed or result was not a string.")

    if new_sound_line and editor.note.fields[sound_idx] != new_sound_line:
        editor.note.fields[sound_idx] = new_sound_line
        updated = True

    if new_sentence_text and editor.note.fields[sentence_idx] != new_sentence_text:
        editor.note.fields[sentence_idx] = new_sentence_text
        updated = True

    if updated:
        editor.loadNote()

    current_sound_line = editor.note.fields[sound_idx]
    match = re.search(r"\[sound:(.*?)\]", current_sound_line)
    return match.group(1) if match else None

def generate_fields_sound_sentence_image(sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx):
    sentence_blocks = [line for line in sentence_text.splitlines() if line.strip()]

    sentence_lines = [line for line in sentence_text.split(" ") if line.strip()]
    print(f"sentence lines: {sentence_lines}")
    first_line = sentence_lines[0]
    if first_line == "-":
        first_line += sentence_lines[1]

    if len(sentence_blocks) > 1:
        format = manage_files.detect_format(sound_line)
        if format != "backtick":
            print(f'formatting sound line')
            first_sound_line, first_block = manage_files.get_valid_backtick_sound_line_and_block(sound_line, first_line)
            return first_sound_line, sentence_text
        else:
            print(f"already formatted")
            return sound_line, sentence_text

    print(f"not formatted, formatting")


    first_sound_line, first_block = manage_files.get_valid_backtick_sound_line_and_block(sound_line, first_line)

    if not first_block or len(first_block) < 4:
        print(f"Invalid or incomplete block: {first_block}")
        return None

    sentence_text = first_block[3]

    first_sound_line = manage_files.alter_sound_file_times(first_sound_line, 0, 0, 0)
    return first_sound_line, sentence_text

def on_note_loaded(editor: Editor):
    editor.web.eval("window.getSelection().removeAllRanges();")
    print(f"note loaded")
    av_player.stop_and_clear_queue()
    if getattr(editor, "_auto_play_enabled", False):
        sound_line, sound_idx, _, _, _, _ = get_sound_and_sentence_from_editor(editor)
        if sound_idx < len(editor.note.fields):
            field_text = editor.note.fields[sound_idx]
            match = re.search(r"\[sound:([^\]]+)\]", field_text)
            if match:
                filename = match.group(1)
                print(f"Playing sound from field {sound_idx}: {filename}")
                QTimer.singleShot(0, lambda fn=filename: play(fn))


# bulk generation
def is_normalized(sound_line):
    return bool(re.search(r'`\-\d+LUFS\.\w+$', sound_line))

def bulk_generate(deck, note_type, overwrite, normalize, lufs, kbps):


    current_deck_name = deck["name"]

    print("Running bulk_generate...")
    print("Deck:", current_deck_name)
    print("Overwrite Fields:", overwrite)
    print("Normalize Audio:", normalize)

    deck_id = mw.col.decks.id(current_deck_name)
    note_ids = mw.col.find_notes(f'deck:"{current_deck_name}"')

    if not note_ids:
        all_decks = [d["name"] for d in mw.col.decks.all()]
        print("Available decks:", all_decks)

        print("Available decks:")
        for deck in mw.col.decks.all():
            print(f"  ID: {deck['id']}, Name: {deck['name']}")

        # Print all note types
        print("\nAvailable note types:")
        for model in mw.col.models.all():
            print(f"  Name: {model['name']}, ID: {model['id']}")

    print(f"note ids: {note_ids}")
    for note_id in note_ids:
        note = mw.col.get_note(note_id)
        if note.note_type()['name'] != note_type:
            continue

        print("Processing note:", note.id, note.note_type()['name'])

        sound_line = note.fields[sound_idx]
        print("Sound line:", sound_line)

        if normalize:
            m = re.search(r'`(-\d+)LUFS', sound_line)
            if m:
                print(f"m: {m.group(1)}")
                if int(m.group(1)) == lufs:
                    print(f"Skipping normalization for note {note.id}, LUFS already matches {m.group(1)}")
                    continue
            else:
                print("No LUFS tag found in sound line")

        format = manage_files.detect_format(sound_line)
        if "[sound:" in sound_line:
            if overwrite:
                data = manage_files.extract_sound_line_data(sound_line)
                if not data:
                    continue
                collection_path = data["collection_path"]
                print(f"Collection path: {collection_path}")

                if normalize and not is_normalized(sound_line):
                    base, file_extension = os.path.splitext(collection_path)
                    print(f"base name: {base}, extension: {file_extension}, og soiund line: {sound_line}, collection path: {collection_path}")
                    if format == "backtick":
                        timestamp_filename_no_normalize = data["timestamp_filename_no_normalize"]
                        print(f"timestamp_filename_no_normalize: {timestamp_filename_no_normalize}")
                        filename = f"{timestamp_filename_no_normalize}`{lufs}LUFS{file_extension}"
                    else:
                        print(f"not backtick, {sound_line}")
                        base_name = os.path.splitext(os.path.basename(collection_path))[0]
                        filename = f"{base_name}`{lufs}LUFS{file_extension}"

                    print(f"filename: {filename}")

                    folder = os.path.dirname(collection_path)
                    new_collection_path = os.path.join(folder, filename)

                    cmd = manage_files.create_just_normalize_audio_command(collection_path, lufs, kbps)

                    try:
                        subprocess.run(cmd, check=True)
                        print(f"running command: {cmd}")
                    except subprocess.CalledProcessError as e:
                        print(f"ffmpeg command failed: {e}")
                        continue

                    if os.path.exists(new_collection_path):
                        print(f"trashing: {collection_path}")
                        send2trash(collection_path)
                    else:
                        print(f"Error: new file not found after ffmpeg: {new_collection_path}")
                        continue

                    new_filename = os.path.basename(new_collection_path)
                    note.fields[sound_idx] = f"[sound:{new_filename}]"
                    mw.col.update_note(note)




