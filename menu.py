import subprocess
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication
from aqt.gui_hooks import editor_did_load_note
from aqt import gui_hooks
from aqt.editor import Editor
from aqt.sound import play
from aqt.utils import showInfo
import re


try:
    from . import audio_files
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import audio_files

ms_amount = 50
const_screenshot_index = 3
const_sound_index = 2
const_sentence_index = 0

def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)

def get_sound_and_sentence_from_editor(editor: Editor) -> tuple[str, int, str, int]:
    sound_line = ""
    sound_idx = const_sound_index

    for idx, field_text in enumerate(editor.note.fields):
        if "[sound:" in field_text:
            sound_line = field_text
            sound_idx = idx

    selected_text = editor.web.selectedText().strip()
    if selected_text:
        sentence_text = selected_text
        sentence_idx = const_sentence_index
    else:
        sentence_text = editor.note.fields[const_sentence_index]
        sentence_idx = const_sentence_index

    sound_line = strip_html_tags(sound_line)
    sentence_text = strip_html_tags(sentence_text)

    if not sound_line:
        block, subtitle_path = audio_files.get_block_and_subtitle_file_from_sentence_text(sentence_text)
        sound_line = audio_files.get_sound_line_from_block_and_path(block, subtitle_path)

    return sound_line, sound_idx, sentence_text, sentence_idx


def remove_edge_new_sentence_new_sound_file(sound_line, sentence_text, relative_index):
    data = audio_files.extract_sound_line_data(sound_line)
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
        new_edge_text = new_blocks[-1]
        end_index -= 1
    else:
        # remove first block
        new_blocks = sentence_blocks[1:]
        new_edge_text = new_blocks[0]
        start_index += 1

    new_edge_block = audio_files.get_block_from_subtitle_path_and_sentence_text(subtitle_path, new_edge_text)
    if not new_edge_block or len(new_edge_block) < 3:
        print(f"Could not locate boundary block: {new_edge_block}")
        return None, None

    new_start_time = start_time
    new_end_time = end_time
    if relative_index == 1:
        new_end_time = new_edge_block[2]
    else:
        new_start_time = new_edge_block[1]

    orig_start_ms = audio_files.time_to_milliseconds(data["start_time"])
    orig_end_ms = audio_files.time_to_milliseconds(data["end_time"])
    new_start_ms = audio_files.time_to_milliseconds(new_start_time)
    new_end_ms = audio_files.time_to_milliseconds(new_end_time)

    lengthen_start = orig_start_ms - new_start_ms
    lengthen_end = new_end_ms - orig_end_ms


    new_sound_line = audio_files.alter_sound_file_times(
        sound_line,
        lengthen_start if relative_index == -1 else 0,
        lengthen_end if relative_index == 1 else 0,
        relative_index
    )

    if not new_sound_line:
        print("No new sound tag returned, field not updated.")
        return

    new_sentence_text = "\n\n".join(new_blocks).strip()
    return new_sentence_text, new_sound_line

def remove_edge_lines_helper(editor, relative_index):
    sound_line, sound_idx, sentence_text, sentence_idx = get_sound_and_sentence_from_editor(editor)

    new_sentence_text, new_sound_line = remove_edge_new_sentence_new_sound_file(sound_line, sentence_text, relative_index)

    new_field = re.sub(r"\[sound:.*?\]", new_sound_line, sound_line)
    editor.note.fields[sound_idx] = new_field
    editor.note.fields[sentence_idx] = new_sentence_text
    editor.loadNote()

    sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_line).group(1)
    QTimer.singleShot(0, lambda: play(sound_filename))

    data = audio_files.add_image_if_empty_data(new_sound_line)
    if data:
        audio_files.add_image_if_empty_helper(editor, const_screenshot_index, data, new_sound_line)

    print(f"Removed {'last' if relative_index==1 else 'first'} block, new text:\n{new_sentence_text}")


def add_context_line_helper(editor: Editor, relative_index):
    sound_line, sound_idx, sentence_text, sentence_idx = get_sound_and_sentence_from_editor(editor)
    print(f"sound_line from editor: {sound_line}")
    new_sound_tag, new_sentence_text = add_context_line_data(sound_line, sentence_text, relative_index)


    if new_sound_tag and new_sentence_text:
        editor.note.fields[sound_idx] = re.sub(r"\[sound:.*?\]", new_sound_tag, sound_line)
        editor.note.fields[sentence_idx] = new_sentence_text
        editor.loadNote()

        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_tag).group(1)
        QTimer.singleShot(0, lambda: play(sound_filename))

        data = audio_files.add_image_if_empty_data(new_sound_tag)
        if data:
            audio_files.add_image_if_empty_helper(editor, const_screenshot_index, data, new_sound_tag)

        print(f"new line {new_sentence_text}")

def add_context_line_data(sound_line, sentence_text, relative_index):
    sentence_lines = [line for line in sentence_text.splitlines() if line.strip()]
    if relative_index == 1:
        edge_line = sentence_lines[-1]
        print(f"relative index is 1, {edge_line}")
    else:
        edge_line = sentence_lines[0]
        print(f"relative index is -1, {edge_line}")

    sound_line, block = audio_files.get_valid_backtick_sound_line_and_block(sound_line, edge_line)
    print(f"block {block}")

    if block:
        sentence_text = block[3]


    data = audio_files.extract_sound_line_data(sound_line)
    if not data:
        return "", ""


    edge_index = data["end_index"] if relative_index == 1 else data["start_index"]
    subtitle_path = data["subtitle_path"]

    target_block = audio_files.get_subtitle_block_from_relative_index(relative_index, edge_index, subtitle_path)
    if not target_block or len(target_block) < 4:
        return "", ""

    target_line = target_block[3]
    new_sound_line = audio_files.get_sound_line_from_block_and_path(target_block, subtitle_path)

    target_data = audio_files.extract_sound_line_data(new_sound_line)
    if not target_data:
        return "", ""

    start_ms = audio_files.time_to_milliseconds(data["start_time"])
    end_ms = audio_files.time_to_milliseconds(data["end_time"])
    target_start_ms = audio_files.time_to_milliseconds(target_data["start_time"])
    target_end_ms = audio_files.time_to_milliseconds(target_data["end_time"])

    if relative_index == 1:
        delta = target_end_ms - end_ms
        new_sound_line = audio_files.alter_sound_file_times(sound_line, 0, delta, relative_index)
        new_sentence_text = f"{sentence_text}\n\n{target_line}"
    else:
        delta = start_ms - target_start_ms
        new_sound_line = audio_files.alter_sound_file_times(sound_line, delta, 0, relative_index)
        new_sentence_text = f"{target_line}\n\n{sentence_text}"

    if not new_sound_line:
        return "", ""

    return new_sound_line.strip(), new_sentence_text.strip()

def adjust_sound_tag(editor, start_delta: int, end_delta: int) -> None:
    sound_line, sound_idx, sentence_text, sentence_idx = get_sound_and_sentence_from_editor(editor)
    print(f"editor sound line: {sound_line}")
    print(f"editor sentence text: {sentence_text}")


    # check for modifier keys
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        start_delta //= 2
        end_delta //= 2
    elif modifiers & Qt.KeyboardModifier.ControlModifier:
        start_delta *= 5
        end_delta *= 5

    fixed_sound_line, block = audio_files.get_valid_backtick_sound_line_and_block(sound_line, sentence_text)
    print(f"fixed sound line: {fixed_sound_line}")
    print(f"block {block}")

    sentence_blocks = [b.strip() for b in sentence_text.split("\n\n") if b.strip()]

    if len(sentence_blocks) == 1:
        sentence_text = block[3]
        editor.note.fields[sentence_idx] = sentence_text

    new_sound_line = audio_files.alter_sound_file_times(fixed_sound_line, -start_delta, end_delta, None)

    if new_sound_line:
        editor.note.fields[sound_idx] = new_sound_line
        editor.loadNote()

        data = audio_files.add_image_if_empty_data(new_sound_line)
        if data:
            audio_files.add_image_if_empty_helper(editor, const_screenshot_index, data, new_sound_line)


        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_line).group(1)
        QTimer.singleShot(0, lambda: play(sound_filename))

    else:
        print("No new sound tag returned, field not updated.")
    return

    showInfo("No [sound:] tag found in any field.")

def on_note_loaded(editor: Editor):
    if getattr(editor, "_auto_play_enabled", False):
        for field_text in editor.note.fields:
            match = re.search(r"\[sound:([^\]]+)\]", field_text)
            if match:
                filename = match.group(1)
                print(f"Playing sound: {filename}")
                QTimer.singleShot(0, lambda fn=filename: play(fn))
                break

def toggle_auto_play_audio(editor: Editor):
    current = getattr(editor, "_auto_play_enabled", False)
    editor._auto_play_enabled = not current
    state = "enabled" if editor._auto_play_enabled else "disabled"
    print(f"Auto-play {state} for editor {id(editor)}")

editor_did_load_note.append(on_note_loaded)

def add_custom_editor_button(html_buttons: list[str], editor: Editor) -> None:
    # avoid adding the button multiple times per editor
    if getattr(editor, "_my_button_added", False):
        return
    editor._my_button_added = True

    buttons = [
        (f"Prev Line", lambda ed=editor: add_context_line_helper(editor, -1), f"Add previous line to card", f"Prev Line"),
        (f"Rem First Line", lambda ed=editor: remove_edge_lines_helper(editor, -1), f"Remove first line from card", f"Rem First Line"),

        (f"S+{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, -ms_amount, 0), f"Add {ms_amount}ms to start", f"S+{ms_amount}"),
        (f"S-{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, ms_amount, 0), f"Remove {ms_amount}ms from start", f"S-{ms_amount}"),
        (f"E+{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, 0, ms_amount), f"Add {ms_amount}ms to end", f"E+{ms_amount}"),
        (f"E-{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, 0, -ms_amount), f"Remove {ms_amount}ms from end", f"E-{ms_amount}"),

        (f"Rem Last Line", lambda ed=editor: remove_edge_lines_helper(editor, 1), f"Removes last line from card", f"Rem Last Line"),
        (f"Next Line", lambda ed=editor: add_context_line_helper(editor, 1), f"Add next line to card", f"Next Line"),
        (f"Autoplay", lambda ed=editor: toggle_auto_play_audio(ed), f"Autoplay Audio", f"Autoplay"),
    ]

    for cmd, func, tip, label in buttons:
        html_buttons.append(
            editor.addButton(
                icon=None,
                cmd=cmd,
                func=func,
                tip=tip,
                label=label
            )
        )

    print("Custom editor button added.")

def init_editor_buttons() -> None:
    gui_hooks.editor_did_init_buttons.append(add_custom_editor_button)
    # gui_hooks.editor_did_focus_field.append(on_focus_field)

init_editor_buttons()

