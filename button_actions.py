from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication
from aqt import gui_hooks
from aqt.sound import play
from aqt.utils import showInfo
import re
from aqt.editor import Editor
from aqt.sound import av_player
import os


from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSpinBox, QCheckBox
)

try:
    from . import manage_files
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import manage_files


ms_amount = 50

def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)

def get_sound_and_sentence_from_editor(editor: Editor):
    sound_idx = 2
    sentence_idx = 0
    image_idx = 3

    sound_line = ""
    if sound_idx < len(editor.note.fields):
        field_text_at_sound_idx = editor.note.fields[sound_idx]
        if "[sound:" in field_text_at_sound_idx:
            sound_line = field_text_at_sound_idx

    image_line = ""
    if image_idx < len(editor.note.fields):
        field_text_at_image_idx = editor.note.fields[image_idx]
        if "<img src=" in field_text_at_image_idx:
            image_line = field_text_at_image_idx

    # only use selected text if sentence_text has no blocks
    sentence_text = editor.note.fields[sentence_idx]
    format = manage_files.detect_format(sound_line)
    if format != "backtick":
        selected_text = editor.web.selectedText().strip()
        if selected_text:
            sentence_text = selected_text
            print(f"using selected text: {sentence_text}")
    else:
        print("format is backtick, using normal field")

    sound_line = strip_html_tags(sound_line)
    sentence_text = strip_html_tags(sentence_text)
    image_line = strip_html_tags(image_line)

    return sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx

def remove_edge_new_sentence_new_sound_file(sound_line, sentence_text, relative_index):
    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        print(f"no data extracted from {sound_line}")
        return None, None

    start_time = data["start_time"]
    end_time = data["end_time"]
    start_index = data["start_index"]
    end_index   = data["end_index"]
    subtitle_path = data["subtitle_path"]

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
    subtitle_path = data["subtitle_path"]

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

        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_line)
        if sound_filename:
            sound_filename = sound_filename.group(1)
            QTimer.singleShot(150, lambda: play(sound_filename))

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
