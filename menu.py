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


def get_sound_and_sentence_from_editor(editor: Editor) -> tuple[str, int, str, int]:
    sound_line = ""
    sound_idx = 2

    for idx, field_text in enumerate(editor.note.fields):
        if "[sound:" in field_text:
            sound_line = field_text
            sound_idx = idx

    sentence_text = editor.note.fields[0]
    sentence_idx = 0
    return sound_line, sound_idx, sentence_text, sentence_idx




def remove_first_last_lines(editor, relative_index):
    sound_line, sound_idx, sentence_text, sentence_idx = get_sound_and_sentence_from_editor(editor)
    sentence_lines = [line for line in sentence_text.splitlines() if line.strip()]
    print(f"sentence lines: " + str(len(sentence_lines)))
    if len(sentence_lines) == 1:
        return
    edge_line = sentence_lines[-1] if relative_index == 1 else sentence_lines[0]
    new_end_beginning_line = audio_files.get_subtitle_sentence_text_from_relative_index(edge_line, -relative_index)
    cut_off_text = audio_files.get_subtitle_sentence_text_from_relative_index(new_end_beginning_line, relative_index)
    new_sentence_text = sentence_text
    print(f"remove text: {cut_off_text}")
    new_sentence_text = new_sentence_text.replace(cut_off_text, "")


    data = audio_files.extract_sound_line_data(sound_line)
    start_time = data["start_time"]
    end_time = data["end_time"]

    new_sound_line = audio_files.get_timestamps_from_sentence_text(new_end_beginning_line)

    target_data = audio_files.extract_sound_line_data(new_sound_line)
    target_start_time = target_data["start_time"]
    target_end_time = target_data["end_time"]

    start_ms = audio_files.time_to_milliseconds(start_time)
    end_ms = audio_files.time_to_milliseconds(end_time)
    target_start_ms = audio_files.time_to_milliseconds(target_start_time)
    target_end_ms = audio_files.time_to_milliseconds(target_end_time)

    if relative_index == 1:
        delta_end = target_end_ms - end_ms
        new_sound_tag = audio_files.alter_sound_file_times(sound_line, 0, delta_end)
    else:
        delta_start = target_start_ms - start_ms
        new_sound_tag = audio_files.alter_sound_file_times(sound_line, delta_start, 0)

    if new_sound_tag:
        new_text = re.sub(r"\[sound:.*?\]", new_sound_tag, sound_line)
        editor.note.fields[sound_idx] = new_text
        print(f"now playing {new_sound_tag}")
        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_tag).group(1)
        QTimer.singleShot(0, lambda: play(sound_filename))
    else:
        print("No new sound tag returned, field not updated.")

    editor.note.fields[sentence_idx] = new_sentence_text
    editor.loadNote()
    print(f"new line {new_sentence_text}")

    return

def add_context_line(editor, relative_index):
    sound_line, sound_idx, sentence_text, sentence_idx = get_sound_and_sentence_from_editor(editor)
    sentence_lines = [line for line in sentence_text.splitlines() if line.strip()]
    first_line = sentence_lines[0]
    last_line = sentence_lines[-1]

    if relative_index == 1:
        target_line = audio_files.get_subtitle_sentence_text_from_relative_index(last_line, relative_index)
        if target_line is None or target_line == "":
            showInfo(f"This is the last line of the file: {target_line}")
            return

    else:
        target_line = audio_files.get_subtitle_sentence_text_from_relative_index(first_line, relative_index)
        if target_line is None or target_line == "":
            showInfo(f"This is the first line of the file: {target_line}")
            return


    new_sound_line = audio_files.get_timestamps_from_sentence_text(target_line)
    print(f"getting new sound line from target line: {target_line}, new sound line: {new_sound_line}")

    print(f"extracting data from sound line {sound_line}")
    data = audio_files.extract_sound_line_data(sound_line)
    start_time = data["start_time"]
    end_time = data["end_time"]

    print(f"extracting data from new sound line: {new_sound_line}")
    target_data = audio_files.extract_sound_line_data(new_sound_line)
    target_start_time = target_data["start_time"]
    target_end_time = target_data["end_time"]

    if "jidoujisho-" in sound_line:
        sound_line = audio_files.get_timestamps_from_sentence_text(sentence_text)
        print(f"detect jidoujisho, new sound line: {sound_line}")

    start_ms = audio_files.time_to_milliseconds(start_time)
    end_ms = audio_files.time_to_milliseconds(end_time)
    target_start_ms = audio_files.time_to_milliseconds(target_start_time)
    target_end_ms = audio_files.time_to_milliseconds(target_end_time)
    if relative_index == 1:
        end_difference = target_end_ms - end_ms

        new_sound_tag = audio_files.alter_sound_file_times(sound_line, 0, end_difference)
        print(f"end_difference: {end_difference}, {target_end_ms} - {end_ms}")
        print(f"new start end, {start_time} - {target_end_time}")
        print(f"index 1, new sound tag: {new_sound_tag}")
    elif relative_index == -1:
        start_difference = target_start_ms - start_ms

        new_sound_tag = audio_files.alter_sound_file_times(sound_line, start_difference, 0)
        print(f"start_difference: {start_difference}")
        print(f"new start end, {target_start_time} - {end_time}")
        print(f"index -1, new sound tag: {new_sound_tag}")
    else:
        new_sound_tag = ""

    if new_sound_tag:
        new_text = re.sub(r"\[sound:.*?\]", new_sound_tag, sound_line)
        editor.note.fields[sound_idx] = new_text
        print(f"now playing {new_sound_tag}")
        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_tag).group(1)
        QTimer.singleShot(0, lambda: play(sound_filename))
    else:
        print("No new sound tag returned, field not updated.")

    if relative_index == 1:
        new_sentence_text = f"{sentence_text}\n{target_line}"
    else:
        new_sentence_text = f"{target_line}\n{sentence_text}"

    editor.note.fields[sentence_idx] = new_sentence_text
    editor.loadNote()
    print(f"new line {new_sentence_text}")

    return



def adjust_sound_tag(editor, start_delta: int, end_delta: int) -> None:
    sound_line, sound_idx, sentence_text, sentence_idx = get_sound_and_sentence_from_editor(editor)

    # check for modifier keys
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        start_delta //= 2
        end_delta //= 2
    elif modifiers & Qt.KeyboardModifier.ControlModifier:
        start_delta *= 5
        end_delta *= 5



    if "jidoujisho-" in sound_line or sound_line == "":
        new_sound_name = audio_files.get_timestamps_from_sentence_text(sentence_text)
        new_sound_tag = audio_files.alter_sound_file_times(new_sound_name, start_delta, end_delta)
    else:
        new_sound_tag = audio_files.alter_sound_file_times(sound_line, start_delta, end_delta)
    print("new_sound_tag:", new_sound_tag)

    if new_sound_tag:
        print("extracted text: ", new_sound_tag)
        editor.note.fields[sound_idx] = new_sound_tag
        editor.loadNote()
        print(f"now playing {new_sound_tag}")

        # 3 is temporary screenshot index
        audio_files.add_image_if_empty(editor, 3, new_sound_tag)
        sound_filename = re.search(r"\[sound:(.*?)\]", new_sound_tag).group(1)
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
        (f"Prev Line", lambda ed=editor: add_context_line(editor, -1), f"Add previous line to card", f"Prev Line"),
        (f"Rem First Line", lambda ed=editor: remove_first_last_lines(editor, -1), f"Remove first line from card", f"Rem First Line"),

        (f"S+{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, -ms_amount, 0), f"Add {ms_amount}ms to start", f"S+{ms_amount}"),
        (f"S-{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, ms_amount, 0), f"Remove {ms_amount}ms from start", f"S-{ms_amount}"),
        (f"E+{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, 0, ms_amount), f"Add {ms_amount}ms to end", f"E+{ms_amount}"),
        (f"E-{ms_amount}", lambda ed=editor: adjust_sound_tag(editor, 0, -ms_amount), f"Remove {ms_amount}ms from end", f"E-{ms_amount}"),

        (f"Rem Last Line", lambda ed=editor: remove_first_last_lines(editor, 1), f"Removes last line from card",f"Rem Last Line"),
        (f"Next Line", lambda ed=editor: add_context_line(editor, 1), f"Add next line to card", f"Next Line"),
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

