from PyQt6.QtCore import Qt, QTimer
import difflib
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
from manage_files import get_subtitle_path_from_filename_track_code, get_field_key_from_label
try:
    from . import manage_files
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import manage_files

# constants
ms_amount = 50
addon_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(addon_dir, "config.json")

# get data
def get_fields_from_editor(editor: Editor):
    config = manage_files.extract_config_data()

    mapped_fields = config["mapped_fields"]
    if not mapped_fields:
        showInfo("fields not mapped")
        return {}

    note_type_name = list(config["mapped_fields"].keys())[0]
    note_type = editor.note.note_type()

    fields = note_type["flds"]

    sentence_field = manage_files.get_field_key_from_label(note_type_name, "Target Sub Line", config)
    sound_field = manage_files.get_field_key_from_label(note_type_name, "Target Audio", config)
    translation_field = manage_files.get_field_key_from_label(note_type_name, "Translation Sub Line", config)
    translation_sound_field = manage_files.get_field_key_from_label(note_type_name, "Translation Audio", config)
    image_field = manage_files.get_field_key_from_label(note_type_name, "Image", config)

    sentence_idx = index_of_field(sentence_field, fields) if sentence_field else -1
    sound_idx = index_of_field(sound_field, fields) if sound_field else -1
    translation_idx = index_of_field(translation_field, fields) if translation_field else -1
    image_idx = index_of_field(image_field, fields) if image_field else -1

    sound_line = editor.note.fields[sound_idx] if 0 <= sound_idx < len(editor.note.fields) else ""
    if "[sound:" not in sound_line:
        sound_line = ""

    image_line = editor.note.fields[image_idx] if 0 <= image_idx < len(editor.note.fields) else ""
    if "<img src=" not in image_line:
        print("no valid image detected")
        image_line = ""

    sentence_line = editor.note.fields[sentence_idx] if 0 <= sentence_idx < len(editor.note.fields) else ""
    translation_line = editor.note.fields[translation_idx] if 0 <= translation_idx < len(editor.note.fields) else ""
    selected_text = editor.web.selectedText().strip()
    translation_sound_idx = index_of_field(translation_sound_field, fields) if translation_sound_field else -1
    translation_sound_line = editor.note.fields[translation_sound_idx] if 0 <= translation_sound_idx < len(editor.note.fields) else ""

    return {
        "sound_line": sound_line,
        "sound_idx": sound_idx,
        "sentence_line": sentence_line,
        "sentence_idx": sentence_idx,
        "image_line": image_line,
        "image_idx": image_idx,
        "translation_line": translation_line,
        "translation_idx": translation_idx,
        "translation_sound_line": translation_sound_line,
        "translation_sound_idx": translation_sound_idx,
        "selected_text": selected_text,
    }


# format and detect
def index_of_field(field_name, fields):
    for i, fld in enumerate(fields):
        if fld["name"] == field_name:
            return i
    return -1


def next_result_button(editor):
    fields = get_fields_from_editor(editor)
    sentence_idx = fields["sentence_idx"]
    sound_idx = fields["sound_idx"]
    image_idx = fields["image_idx"]
    translation_idx = fields["translation_idx"]

    sentence_line = fields["sentence_line"]
    sound_line = fields["sound_line"]
    selected_text = fields["selected_text"]
    print(f"detected selected txt: {selected_text}")


    block, subtitle_path = manage_files.get_next_matching_subtitle_block(sentence_line, selected_text, sound_line)
    if not block or not subtitle_path:
        print(f"didnt find another result")
        return

    next_sentence_line = block[3]
    next_sound_line = manage_files.get_sound_line_from_subtitle_block_and_path(block, subtitle_path)

    # generate file using next sound line
    altered_data = manage_files.get_altered_sound_data(next_sound_line, 0, 0, 0)
    next_sound_line = manage_files.alter_sound_file_times(altered_data, next_sound_line)
    print(f"next sentence: {next_sentence_line}, next sound: {next_sound_line}")

    editor.note.fields[sentence_idx] = next_sentence_line
    editor.note.fields[sound_idx] = next_sound_line
    editor.note.fields[image_idx] = ""
    editor.note.fields[translation_idx] = ""
    editor.loadNote()
    generate_fields_button(editor)


def generate_fields_button(editor):
    sound_filename = generate_fields_helper(editor, None)
    if sound_filename:
        print(f"Playing sound filename: {sound_filename}")
        QTimer.singleShot(100, lambda: play(sound_filename))

def get_idx(label):
    field_key = manage_files.get_field_key_from_label(note_type_name, label, config)
    return index_of_field(field_key, fields) if field_key else -1

def generate_fields_helper(editor, note):
    if note:
        config = manage_files.extract_config_data()
        mapped_fields = config["mapped_fields"]
        note_type_name = list(mapped_fields.keys())[0]
        fields = note.note_type()["flds"]

        sentence_idx = get_idx("Target Sub Line")
        sound_idx = get_idx("Target Audio")
        image_idx = get_idx("Image")
        translation_idx = get_idx("Translation Sub Line")
        translation_sound_idx = fields["translation_sound_idx"]

        sentence_line = note.fields[sentence_idx] if 0 <= sentence_idx < len(note.fields) else ""
        sound_line = note.fields[sound_idx] if 0 <= sound_idx < len(note.fields) else ""
        image_line = note.fields[image_idx] if 0 <= image_idx < len(note.fields) else ""
        translation_line = note.fields[translation_idx] if 0 <= translation_idx < len(note.fields) else ""
        selected_text = ""

        field_obj = note
    else:
        fields = get_fields_from_editor(editor)
        sentence_idx = fields["sentence_idx"]
        sound_idx = fields["sound_idx"]
        image_idx = fields["image_idx"]
        translation_idx = fields["translation_idx"]
        translation_sound_idx = fields["translation_sound_idx"]

        sentence_line = fields["sentence_line"]
        sound_line = fields["sound_line"]
        image_line = fields["image_line"]
        translation_line = fields["translation_line"]
        translation_sound_line = fields["translation_sound_line"]
        selected_text = fields["selected_text"]
        print(f"detected selected txt: {selected_text}")

        field_obj = editor.note

    updated = False
    # generate fields using sentence line
    new_result = generate_fields_sound_sentence_image_translation(
        sound_line, sentence_line, selected_text, image_line, translation_line, translation_sound_line
    )

    if not new_result:
        print("generate_fields_sound_sentence_image failed to return valid values.")
        if new_result:
            for i, val in enumerate(new_result):
                print(f"  Field {i}: {val!r}")
        else:
            print("  new_result is None or empty.")
        return None

    new_sound_line, new_sentence_line, new_image_line, new_translation_line, new_translation_sound_line = new_result


    def update_field(idx, new_val):
        nonlocal updated
        current_field = field_obj.fields[idx]
        if new_val and current_field != new_val:
            field_obj.fields[idx] = new_val
            updated = True

    update_field(sentence_idx, new_sentence_line)
    update_field(translation_idx, new_translation_line)

    altered_data = manage_files.get_altered_sound_data(new_sound_line, 0, 0, 0)
    if new_sound_line and new_sound_line != field_obj.fields[sound_idx]:
        new_sound_line = manage_files.alter_sound_file_times(altered_data, new_sound_line)
        field_obj.fields[sound_idx] = new_sound_line
        updated = True

    altered_data = manage_files.get_altered_sound_data(new_translation_sound_line, 0, 0, 0)
    if new_translation_sound_line and new_translation_sound_line != field_obj.fields[translation_sound_idx]:
        new_translation_sound_line = manage_files.alter_sound_file_times(altered_data, new_translation_sound_line)
        field_obj.fields[translation_sound_idx] = new_translation_sound_line
        updated = True

    if not image_line:
        generated_img = manage_files.get_image_if_empty_helper("", new_sound_line)
        if generated_img and isinstance(generated_img, str):
            field_obj.fields[image_idx] = generated_img
            updated = True
        else:
            print("Image generation failed or result was not a string.")
    else:
        update_field(image_idx, new_image_line)

    if updated:
        if note:
            mw.col.update_note(note)
        else:
            editor.loadNote()

    current_sound_line = field_obj.fields[sound_idx]
    match = re.search(r"\[sound:(.*?)\]", current_sound_line)
    return match.group(1) if match else None

def generate_fields_sound_sentence_image_translation(sound_line, sentence_line, selected_text, image_line, translation_line, translation_sound_line):
    # checks each field, generating and updating if needed. Returns each field, empty if not needed
    sentence_line = sentence_line or ""
    sentence_blocks = [line for line in str(sentence_line).splitlines() if line.strip()]
    if not sentence_line:
        showInfo("sentence field empty")
        return

    # dont overwrite if sound line already formatted
    new_sentence_line = sentence_line
    format = manage_files.detect_format(sound_line)
    if format != "backtick":
        # check selected text first
        if selected_text:
            sound_line, target_block, subtitle_path = manage_files.get_valid_backtick_sound_line_and_block(sound_line, selected_text)
            print(f"getting sound line from selected text, sub path: {subtitle_path}")
        else:
            if len(sentence_blocks) > 1:
                print("formatting sound line from first line of multiple")
            else:
                print("formatting sound line from sentence line")
            sound_line, target_block, subtitle_path = manage_files.get_valid_backtick_sound_line_and_block(sound_line, sentence_line)
            print(f"sub path from line: {subtitle_path}")
        if not target_block or len(target_block) < 4:
            print(
                f"Invalid or incomplete block: {target_block}, length: {len(target_block) if target_block else 'N/A'}")
            new_sentence_line = ""
        else:
            new_sentence_line = target_block[3]
    else:
        print("already formatted")
        target_block, subtitle_path = manage_files.get_subtitle_block_from_sound_line_and_sentence_line(sound_line, sentence_line)

    new_sound_line, new_sentence_line = context_aware_sentence_sound_line_generate(sentence_line, new_sentence_line, sound_line, subtitle_path)

    config = manage_files.extract_config_data()
    note_type_name = list(config["mapped_fields"].keys())[0]
    generate_image = get_field_key_from_label(note_type_name, "Image", config)
    generate_translation_line = get_field_key_from_label(note_type_name, "Translation Sub Line", config)
    generate_translation_audio = get_field_key_from_label(note_type_name, "Translation Audio", config)

    if not image_line and generate_image:
        new_image_line = manage_files.get_image_if_empty_helper(image_line, new_sound_line)
    else:
        new_image_line = image_line

    if not translation_line and generate_translation_line:
        new_translation_line = manage_files.get_translation_line_from_target_sound_line(new_sound_line)
    else:
        new_translation_line = ""

    if not translation_sound_line and generate_translation_audio:
        print(f"\ngenerating translation audio\n")
        new_translation_sound_line = manage_files.get_translation_sound_line_from_target_sound_line(new_sound_line)
        print(f"new_translation_sound_line: {new_translation_sound_line} ")
    else:
        new_translation_sound_line = ""

    return new_sound_line, new_sentence_line, new_image_line, new_translation_line, new_translation_sound_line

def remove_edge_new_sentence_new_sound_file(sound_line, sentence_line, relative_index):
    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        print(f"no data extracted from {sound_line}")
        return None, None

    start_time = data["start_time"]
    end_time = data["end_time"]
    start_index = data["start_index"]
    end_index   = data["end_index"]

    filename_base = data["filename_base"]
    config = manage_files.extract_config_data()
    track = config["target_subtitle_track"]
    code = config["target_language_code"]
    subtitle_path = manage_files.get_subtitle_path_from_filename_track_code(filename_base, track, code)

    sentence_blocks = [b.strip() for b in sentence_line.split("\n\n") if b.strip()]
    if len(sentence_blocks) <= 1:
        print(f"no sentence blocks extracted from {sentence_line}")
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
    orig_start_ms = manage_files.time_hmsms_to_milliseconds(data["start_time"])
    orig_end_ms = manage_files.time_hmsms_to_milliseconds(data["end_time"])
    new_start_ms = manage_files.time_hmsms_to_milliseconds(new_start_time)
    new_end_ms = manage_files.time_hmsms_to_milliseconds(new_end_time)

    lengthen_start = orig_start_ms - new_start_ms
    print(f"lengthen_start: {lengthen_start}")
    lengthen_end = new_end_ms - orig_end_ms
    print(f"lengthen_end: {lengthen_end}")

    altered_data = manage_files.get_altered_sound_data(
        sound_line,
        lengthen_start if relative_index == -1 else 0,
        lengthen_end if relative_index == 1 else 0,
        relative_index
    )
    new_sound_line = manage_files.alter_sound_file_times(altered_data, sound_line)

    if not new_sound_line:
        print("No new sound tag returned, field not updated.")
        return None, None

    new_sentence_line = "\n\n".join(new_blocks).strip()

    return new_sentence_line, new_sound_line

def remove_edge_lines_helper(editor, relative_index):
    fields = get_fields_from_editor(editor)
    sound_line = fields["sound_line"]
    sound_idx = fields["sound_idx"]
    sentence_line = fields["sentence_line"]
    sentence_idx = fields["sentence_idx"]
    translation_idx = fields["translation_idx"]


    new_sentence_line, new_sound_line = remove_edge_new_sentence_new_sound_file(sound_line, sentence_line, relative_index)

    if not new_sound_line or not new_sentence_line:
        print("No new sound line or sentence text returned.")
        return

    # generate new translation line
    translation_line = manage_files.get_translation_line_from_target_sound_line(new_sound_line)
    editor.note.fields[translation_idx] = translation_line

    new_field = re.sub(r"\[sound:.*?\]", new_sound_line, sound_line)
    editor.note.fields[sound_idx] = new_field
    editor.note.fields[sentence_idx] = new_sentence_line
    generate_fields_helper(editor, None)

    def play_after_reload():
        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_line)
        if sound_filename:
            QTimer.singleShot(100, lambda: play(sound_filename.group(1)))

    editor.loadNote()
    QTimer.singleShot(50, play_after_reload)


    print(f"Removed {'last' if relative_index==1 else 'first'} block, new text:\n{new_sentence_line}")

def add_context_line_helper(editor: Editor, relative_index):
    fields = get_fields_from_editor(editor)
    sound_line = fields["sound_line"]
    sound_idx = fields["sound_idx"]
    sentence_line = fields["sentence_line"]
    sentence_idx = fields["sentence_idx"]
    translation_idx = fields["translation_idx"]


    print(f"sound_line from editor: {sound_line}")

    filename_base = re.sub(r'^\[sound:|\]$', '', sound_line.split("`", 1)[0].strip())

    config = manage_files.extract_config_data()
    track = config["target_subtitle_track"]
    code = config["target_language_code"]
    subtitle_path = manage_files.get_subtitle_path_from_filename_track_code(filename_base, track, code)
    new_sound_tag, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(sound_line, subtitle_path, relative_index)

    # generate new translation line
    translation_line = manage_files.get_translation_line_from_target_sound_line(new_sound_tag)
    print(f"translation line: {translation_line}, from new_sound_tag: {new_sound_tag}")
    editor.note.fields[translation_idx] = translation_line

    if relative_index == 1:
        new_sentence_line = f"{sentence_line}\n\n{context_sentence_line}"
    else:
        new_sentence_line = f"{context_sentence_line}\n\n{sentence_line}"

    if new_sound_tag and new_sentence_line:
        editor.note.fields[sound_idx] = re.sub(r"\[sound:.*?\]", new_sound_tag, sound_line)
        editor.note.fields[sentence_idx] = new_sentence_line

        match = re.search(r"\[sound:(.*?)\]", new_sound_tag)
        sound_filename = match.group(1) if match else None

        def play_after_reload():
            if sound_filename:
                QTimer.singleShot(100, lambda: play(sound_filename))

        QTimer.singleShot(0, play_after_reload)
        editor.loadNote()

    print(f"riunning generate fields helper")
    generate_fields_helper(editor, None)

def get_context_sound_and_sentence_line():
    pass

def new_sound_line_from_sound_line_path_and_relative_index(sound_line, subtitle_path, relative_index):
    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        return "", ""

    edge_index = data["end_index"] if relative_index == 1 else data["start_index"]

    target_block = manage_files.get_subtitle_block_from_relative_index(relative_index, edge_index, subtitle_path)
    if not target_block or len(target_block) < 4:
        return "", ""

    target_line = target_block[3]
    new_sound_line = manage_files.get_sound_line_from_subtitle_block_and_path(target_block, subtitle_path)

    target_data = manage_files.extract_sound_line_data(new_sound_line)
    if not target_data:
        return "", ""

    start_ms = manage_files.time_hmsms_to_milliseconds(data["start_time"])
    end_ms = manage_files.time_hmsms_to_milliseconds(data["end_time"])
    target_start_ms = manage_files.time_hmsms_to_milliseconds(target_data["start_time"])
    target_end_ms = manage_files.time_hmsms_to_milliseconds(target_data["end_time"])

    if relative_index == 1:
        delta = target_end_ms - end_ms
        altered_data = manage_files.get_altered_sound_data(sound_line, 0, delta, relative_index)
        new_sound_line = altered_data["new_sound_line"]
        new_sentence_line = f"{target_line}"
    else:
        delta = start_ms - target_start_ms
        altered_data = manage_files.get_altered_sound_data(sound_line, delta, 0, relative_index)
        new_sound_line = altered_data["new_sound_line"]
        new_sentence_line = f"{target_line}"

    if not new_sound_line:
        return "", ""

    return new_sound_line.strip(), new_sentence_line.strip()

def adjust_sound_tag(editor, start_delta: int, end_delta: int) -> None:
    fields = get_fields_from_editor(editor)
    sound_line = fields["sound_line"]
    sound_idx = fields["sound_idx"]
    sentence_line = fields["sentence_line"]

    # check for modifier keys
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        start_delta //= 2
        end_delta //= 2
    elif modifiers & Qt.KeyboardModifier.ControlModifier:
        start_delta *= 5
        end_delta *= 5

    print(f"current sound line: {sound_line}")
    fixed_sound_line, block, subtitle_path = manage_files.get_valid_backtick_sound_line_and_block(sound_line, sentence_line)
    print(f"fixed sound line: {fixed_sound_line}")

    altered_data = manage_files.get_altered_sound_data(fixed_sound_line, -start_delta, end_delta, None)
    new_sound_line = manage_files.alter_sound_file_times(altered_data, fixed_sound_line)

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

def context_aware_sentence_sound_line_generate(sentence_line, new_sentence_line, sound_line, subtitle_path):
    # check before and after selected text for more lines to add
    leftover_sentence = sentence_line.strip()

    # try to find the longest matching block between the two strings
    matcher = difflib.SequenceMatcher(None, leftover_sentence, new_sentence_line)
    match = matcher.find_longest_match(0, len(leftover_sentence), 0, len(new_sentence_line))
    if match.size > 0:
        before_removed = leftover_sentence[:match.a].strip()
        after_removed = leftover_sentence[match.a + match.size:].strip()
    else:
        before_removed = ""
        after_removed = leftover_sentence.strip()

    if before_removed or after_removed:
        print(f"leftover sentence before: {before_removed}")
        print(f"leftover sentence after: {after_removed}")
    else:
        print("no leftover sentence")

    new_sound_line = sound_line
    while before_removed or after_removed:
        if not subtitle_path:
            break

        data = manage_files.extract_sound_line_data(new_sound_line)
        if not data:
            break
        start_index = data.get("start_index")
        if start_index is None:
            break
        end_index = data.get("end_index")
        if end_index is None:
            break




        if before_removed:
            relative_index = -1
            before_block = manage_files.get_subtitle_block_from_relative_index(relative_index, start_index, subtitle_path)
            before_line = before_block[3]
            before_line_clean = before_line.replace('\n', '').strip()
            print(f"before_line_clean: {before_line_clean}, before_removed: {before_removed}")

            # check if previous line is in leftover line, or if leftover line is in previous line, and add previous line if it is
            if before_line_clean in before_removed:
                before_removed = before_removed.replace(before_line_clean, "").strip()
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line = f"{context_sentence_line}\n\n" + new_sentence_line
                print(f"before line found")
            elif before_line in before_removed:
                before_removed = before_removed.replace(before_line, "").strip()
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line = f"{context_sentence_line}\n\n" + new_sentence_line
                print(f"before line found")
            elif before_removed in before_line:
                before_removed = ""
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line = f"{context_sentence_line}\n\n" + new_sentence_line
                print(f"before line found")
            elif before_removed in before_line_clean:
                before_removed = ""
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line = f"{context_sentence_line}\n\n" + new_sentence_line
                print(f"before line found")
            else:
                print(f"didnt match before removed to anything")
                before_removed = ""

        data = manage_files.extract_sound_line_data(new_sound_line)
        if not data:
            break
        end_index = data.get("end_index")

        if after_removed:
            relative_index = 1
            after_block = manage_files.get_subtitle_block_from_relative_index(relative_index, end_index, subtitle_path)
            after_line = after_block[3]
            after_line_clean = after_line.replace('\n', '').strip()
            print(f"after_line_clean: {after_line_clean}, after_removed: {after_removed}")

            if after_line_clean in after_removed:
                after_removed = after_removed.replace(after_line_clean, "").strip()
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line += f"\n\n{context_sentence_line}"
                print(f"after line found1")
            elif after_line in after_removed:
                after_removed = after_removed.replace(after_line, "").strip()
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line += f"\n\n{context_sentence_line}"
                print(f"after line found2")
            elif after_removed in after_line:
                after_removed = ""
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line += f"\n\n{context_sentence_line}"
                print(f"after line found3")
            elif after_removed in after_line_clean:
                after_removed = ""
                new_sound_line, context_sentence_line = new_sound_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, relative_index)
                new_sentence_line += f"\n\n{context_sentence_line}"
                print(f"after line found4")
            else:
                print(f"didnt match after removed to anything")
                after_removed = ""

    altered_data = manage_files.get_altered_sound_data(new_sound_line, 0, 0, None)
    manage_files.alter_sound_file_times(altered_data, new_sound_line)
    return new_sound_line, new_sentence_line

def on_note_loaded(editor: Editor):
    editor.web.eval("window.getSelection().removeAllRanges();")
    print(f"note loaded")
    av_player.stop_and_clear_queue()
    if getattr(editor, "_auto_play_enabled", False):
        fields = get_fields_from_editor(editor)
        sound_idx = fields["sound_idx"]

        if sound_idx < len(editor.note.fields):
            field_text = editor.note.fields[sound_idx]
            match = re.search(r"\[sound:([^\]]+)\]", field_text)
            if match:
                filename = match.group(1)
                print(f"Playing sound from field {sound_idx}: {filename}")
                QTimer.singleShot(0, lambda fn=filename: play(fn))

def get_fields_from_note(note):
    config = manage_files.extract_config_data()
    mapped_fields = config.get("mapped_fields", {})

    if not mapped_fields:
        showInfo("fields not mapped")
        return {}

    note_type_name = list(mapped_fields.keys())[0]
    note_type = note.note_type()
    fields = note_type["flds"]

    def get_index(label):
        key = manage_files.get_field_key_from_label(note_type_name, label, config)
        return index_of_field(key, fields) if key else -1

    sentence_idx = get_index("Target Sub Line")
    sound_idx = get_index("Target Audio")
    translation_idx = get_index("Translation Sub Line")
    translation_sound_idx = get_index("Translation Audio")
    image_idx = get_index("Image")

    sound_line = note.fields[sound_idx] if 0 <= sound_idx < len(note.fields) else ""
    if "[sound:" not in sound_line:
        sound_line = ""

    translation_sound_line = note.fields[translation_sound_idx] if 0 <= translation_sound_idx < len(note.fields) else ""
    if "[sound:" not in translation_sound_line:
        translation_sound_line = ""

    image_line = note.fields[image_idx] if 0 <= image_idx < len(note.fields) else ""
    if "<img src=" not in image_line:
        print("no valid image detected")
        image_line = ""

    sentence_line = note.fields[sentence_idx] if 0 <= sentence_idx < len(note.fields) else ""
    translation_line = note.fields[translation_idx] if 0 <= translation_idx < len(note.fields) else ""

    return {
        "sound_line": sound_line,
        "sound_idx": sound_idx,
        "sentence_line": sentence_line,
        "sentence_idx": sentence_idx,
        "image_line": image_line,
        "image_idx": image_idx,
        "translation_line": translation_line,
        "translation_idx": translation_idx,
        "translation_sound_line": translation_sound_line,
        "translation_sound_idx": translation_sound_idx,
    }


# bulk generation
def is_normalized(sound_line):
    return bool(re.search(r'`-\d+LUFS\.\w+$', sound_line))

def bulk_generate(deck, note_type, overwrite):
    current_deck_name = deck["name"]

    print("Running bulk_generate...")
    print("Deck:", current_deck_name)
    print("Overwrite Fields:", overwrite)

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
        generate_fields_helper(None, note)




