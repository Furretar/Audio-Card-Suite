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
    from . import button_actions
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import manage_files
    import button_actions

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
    timing_btn_layout.addWidget(make_button("Start +50ms", lambda: button_actions.adjust_sound_tag(editor, -ms_amount, 0)))
    timing_btn_layout.addWidget(make_button("Start -50ms", lambda: button_actions.adjust_sound_tag(editor, ms_amount, 0), danger=True))
    timing_btn_layout.addWidget(make_button("End -50ms", lambda: button_actions.adjust_sound_tag(editor, 0, -ms_amount), danger=True))
    timing_btn_layout.addWidget(make_button("End +50ms", lambda: button_actions.adjust_sound_tag(editor, 0, ms_amount)))
    buttons_layout.addWidget(timing_btn_row)

    # add and remove line buttons
    add_remove_row = QWidget()
    add_remove_layout = QHBoxLayout(add_remove_row)
    add_remove_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    add_remove_layout.setSpacing(BUTTON_ROW_SPACING)
    add_remove_layout.addWidget(make_button("Add Previous Line", lambda: button_actions.add_context_line_helper(editor, -1)))
    add_remove_layout.addWidget(make_button("Remove First Line", lambda: button_actions.remove_edge_lines_helper(editor, -1), danger=True))
    add_remove_layout.addWidget(make_button("Remove Last Line", lambda: button_actions.remove_edge_lines_helper(editor, 1), danger=True))
    add_remove_layout.addWidget(make_button("Add Next Line", lambda: button_actions.add_context_line_helper(editor, 1)))
    buttons_layout.addWidget(add_remove_row)

    # generate button
    generate_btn_row = QWidget()
    generate_btn_layout = QHBoxLayout(generate_btn_row)
    generate_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    generate_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    generate_btn_layout.addWidget(make_button("Generate Fields", lambda: button_actions.generate_fields_button(editor)))
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
    gui_hooks.editor_did_load_note.append(button_actions.on_note_loaded)