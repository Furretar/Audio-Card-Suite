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
    from . import audio_files
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import audio_files

ms_amount = 50

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
    format = audio_files.detect_format(sound_line)
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
        end_index -= 1
        new_edge_block = audio_files.get_subtitle_block_from_index_and_path(end_index - 1, subtitle_path)

    else:
        # remove first block
        new_blocks = sentence_blocks[1:]
        start_index += 1
        new_edge_block = audio_files.get_subtitle_block_from_index_and_path(start_index - 1, subtitle_path)

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
    orig_start_ms = audio_files.time_to_milliseconds(data["start_time"])
    orig_end_ms = audio_files.time_to_milliseconds(data["end_time"])
    new_start_ms = audio_files.time_to_milliseconds(new_start_time)
    new_end_ms = audio_files.time_to_milliseconds(new_end_time)

    lengthen_start = orig_start_ms - new_start_ms
    print(f"lengthen_start: {lengthen_start}")
    lengthen_end = new_end_ms - orig_end_ms
    print(f"lengthen_end: {lengthen_end}")

    new_sound_line = audio_files.alter_sound_file_times(
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
        generated_img = audio_files.get_image_if_empty_helper(image_line, sound_line)
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
            generated_img = audio_files.get_image_if_empty_helper(image_line, sound_line)
            if generated_img and isinstance(generated_img, str):
                editor.note.fields[image_idx] = generated_img
            else:
                print("Image generation failed or result was not a string.")

        print(f"new line {new_sentence_text}")


def get_context_line_data(sound_line, sentence_text, relative_index):

    data = audio_files.extract_sound_line_data(sound_line)
    if not data:
        return "", ""


    edge_index = data["end_index"] if relative_index == 1 else data["start_index"]
    subtitle_path = data["subtitle_path"]

    target_block = audio_files.get_subtitle_block_from_relative_index(relative_index, edge_index, subtitle_path)
    if not target_block or len(target_block) < 4:
        return "", ""

    target_line = target_block[3]
    new_sound_line = audio_files.get_sound_line_from_subtitle_block_and_path(target_block, subtitle_path)

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
        new_sentence_text = f"{target_line}"
    else:
        delta = start_ms - target_start_ms
        new_sound_line = audio_files.alter_sound_file_times(sound_line, delta, 0, relative_index)
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

    fixed_sound_line, block = audio_files.get_valid_backtick_sound_line_and_block(sound_line, sentence_text)


    new_sound_line = audio_files.alter_sound_file_times(fixed_sound_line, -start_delta, end_delta, None)

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
        QTimer.singleShot(0, lambda: play(sound_filename))


def generate_fields_helper(editor):
    sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx = get_sound_and_sentence_from_editor(editor)

    updated = False

    if not image_line.strip():
        generated_img = audio_files.get_image_if_empty_helper(image_line, sound_line)
        if generated_img and isinstance(generated_img, str):
            if editor.note.fields[image_idx] != generated_img:
                editor.note.fields[image_idx] = generated_img
                updated = True
        else:
            print("Image generation failed or result was not a string.")

    new_result = generate_fields_sound_sentence_image(sound_line, sound_idx, sentence_text, sentence_idx, image_line, image_idx)
    if not new_result or not all(new_result):
        print("generate_fields_sound_sentence_image failed to return valid values.")
        return None

    new_sound_line, new_sentence_text = new_result

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
        format = audio_files.detect_format(sound_line)
        if format != "backtick":
            print(f'formatting sound line')
            first_sound_line, first_block = audio_files.get_valid_backtick_sound_line_and_block(sound_line, first_line)
            return first_sound_line, sentence_text
        else:
            print(f"already formatted")
            return sound_line, sentence_text

    print(f"not formatted, formatting")


    first_sound_line, first_block = audio_files.get_valid_backtick_sound_line_and_block(sound_line, first_line)

    if not first_block or len(first_block) < 4:
        print(f"Invalid or incomplete block: {first_block}")
        return None

    sentence_text = first_block[3]

    first_sound_line = audio_files.alter_sound_file_times(first_sound_line, 0, 0, 0)
    return first_sound_line, sentence_text


def on_note_loaded(editor: Editor):
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

def set_auto_play_audio(editor: Editor, enabled: bool) -> None:
    editor._auto_play_enabled = enabled
    state = "enabled" if enabled else "disabled"
    print(f"Autoplay {state} for editor {id(editor)}")

def handle_autoplay_checkbox_toggle(_, editor):
    # flip the current state
    current = getattr(editor, "_auto_play_enabled", False)
    new_state = not current
    editor._auto_play_enabled = new_state
    print(f"Autoplay {'enabled' if new_state else 'disabled'} for editor {id(editor)}")

def add_custom_controls(editor: Editor) -> None:

    if not hasattr(editor, "widget") or editor.widget is None:
        return

    main_layout = editor.widget.layout()
    if main_layout is None:
        return

    # prevent duplicate buttons
    if hasattr(editor, "_custom_controls_container_buttons"):
        return

    ms_amount = 50

    def make_button(label, on_click, danger=False):
        btn = QPushButton(label)
        style = BUTTON_PADDING
        if danger:
            style = f"background-color: {SHIFT_BUTTON_BG_COLOR}; {BUTTON_PADDING}"
        btn.setStyleSheet(style)
        btn.clicked.connect(on_click)
        return btn

    def make_labeled_spinbox(text, min_val, max_val, default):
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(*ROW_MARGINS)
        layout.setSpacing(4)
        label = QLabel(text)
        label.setMinimumWidth(LABEL_MIN_WIDTH)
        spin = QSpinBox()
        spin.setMinimum(min_val)
        spin.setMaximum(max_val)
        spin.setValue(default)
        spin.setMinimumWidth(SPINBOX_MIN_WIDTH)
        layout.addWidget(label)
        layout.addWidget(spin)
        return w, spin

    # top buttons container
    buttons_container = QWidget()
    buttons_layout = QVBoxLayout(buttons_container)
    buttons_layout.setContentsMargins(*CONTAINER_MARGINS)
    buttons_layout.setSpacing(CONTAINER_SPACING)

    # timing buttons
    timing_btn_row = QWidget()
    timing_btn_layout = QHBoxLayout(timing_btn_row)
    timing_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    timing_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    timing_btn_layout.addWidget(make_button("Start +50ms", lambda: adjust_sound_tag(editor, -ms_amount, 0)))
    timing_btn_layout.addWidget(make_button("Start -50ms", lambda: adjust_sound_tag(editor, ms_amount, 0), danger=True))
    timing_btn_layout.addWidget(make_button("End -50ms", lambda: adjust_sound_tag(editor, 0, -ms_amount), danger=True))
    timing_btn_layout.addWidget(make_button("End +50ms", lambda: adjust_sound_tag(editor, 0, ms_amount)))
    buttons_layout.addWidget(timing_btn_row)

    # add and remove line buttons
    add_remove_row = QWidget()
    add_remove_layout = QHBoxLayout(add_remove_row)
    add_remove_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    add_remove_layout.setSpacing(BUTTON_ROW_SPACING)
    add_remove_layout.addWidget(make_button("Add Previous Line", lambda: add_context_line_helper(editor, -1)))
    add_remove_layout.addWidget(make_button("Remove First Line", lambda: remove_edge_lines_helper(editor, -1), danger=True))
    add_remove_layout.addWidget(make_button("Remove Last Line", lambda: remove_edge_lines_helper(editor, 1), danger=True))
    add_remove_layout.addWidget(make_button("Add Next Line", lambda: add_context_line_helper(editor, 1)))
    buttons_layout.addWidget(add_remove_row)

    # generate button
    generate_btn_row = QWidget()
    generate_btn_layout = QHBoxLayout(generate_btn_row)
    generate_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    generate_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    generate_btn_layout.addWidget(make_button("Generate Fields", lambda: generate_fields_button(editor)))
    buttons_layout.addWidget(generate_btn_row)




    main_layout.insertWidget(0, buttons_container)
    editor._custom_controls_container_buttons = buttons_container

    # spinboxes container

    target_fields = [
        # ("Target Audio Track", 1, 99, 1),
        # ("Target Sentence Track", 1, 99, 1),
    ]
    translation_fields = [
        # ("Translation Audio Track", 1, 99, 1),
        # ("Translation Text Track", 1, 99, 1),
    ]
    other_fields = [
        # ("Start offset", -999999, 999999, 0),
        # ("End offset", -999999, 999999, 0),
        # ("Subtitle Offset", -999999, 999999, 0),
    ]

    spinboxes_container = QWidget()
    spinboxes_layout = QVBoxLayout(spinboxes_container)
    spinboxes_layout.setContentsMargins(*CONTAINER_MARGINS)
    spinboxes_layout.setSpacing(CONTAINER_SPACING)

    # target fields row
    row_target = QWidget()
    row_target_layout = QHBoxLayout(row_target)
    row_target_layout.setContentsMargins(*ROW_MARGINS)
    row_target_layout.setSpacing(ROW_SPACING)

    for label, mn, mx, default in target_fields:
        widget, spin = make_labeled_spinbox(label, mn, mx, default)
        row_target_layout.addWidget(widget)

        if "Audio" in label:
            editor._audio_field_index_spinbox = spin
        elif "Sentence" in label:
            editor._sentence_field_index_spinbox = spin

    spinboxes_layout.addWidget(row_target)

    # translation fields row
    row_trans = QWidget()
    row_trans_layout = QHBoxLayout(row_trans)
    row_trans_layout.setContentsMargins(*ROW_MARGINS)
    row_trans_layout.setSpacing(ROW_SPACING)

    for label, mn, mx, default in translation_fields:
        widget, spin = make_labeled_spinbox(label, mn, mx, default)
        row_trans_layout.addWidget(widget)

        if "Audio" in label:
            editor._translation_audio_index_spinbox = spin
        elif "Text" in label:
            editor._translation_text_index_spinbox = spin

    spinboxes_layout.addWidget(row_trans)

    # offsets and autoplay
    row_other = QWidget()
    row_other_layout = QHBoxLayout(row_other)
    row_other_layout.setContentsMargins(*ROW_MARGINS)
    row_other_layout.setSpacing(ROW_SPACING)
    for label, mn, mx, default in other_fields:
        widget, _ = make_labeled_spinbox(label, mn, mx, default)
        row_other_layout.addWidget(widget)

        if "Start offset" in label:
            editor._start_offset_spinbox = spin
        elif "End offset" in label:
            editor._end_offset_spinbox = spin
        elif "Subtitle Offset" in label:
            editor._subtitle_offset_spinbox = spin

    autoplay_checkbox = QCheckBox("Autoplay")
    autoplay_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)

    autoplay_checkbox.blockSignals(True)
    autoplay_checkbox.setChecked(getattr(editor, "_auto_play_enabled", False))
    autoplay_checkbox.blockSignals(False)

    autoplay_checkbox.clicked.connect(lambda _: handle_autoplay_checkbox_toggle(_, editor))

    row_other_layout.addWidget(autoplay_checkbox)
    spinboxes_layout.addWidget(row_other)

    main_layout.addWidget(spinboxes_container)
    editor._custom_controls_container_spinboxes = spinboxes_container

    print("Custom editor control buttons, spinboxes, and autoplay checkbox added.")

gui_hooks.editor_did_init.append(add_custom_controls)

def on_profile_loaded():
    gui_hooks.editor_did_load_note.append(on_note_loaded)