from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication
from aqt import gui_hooks
from aqt.sound import play
from aqt.utils import showInfo
import re
from aqt.editor import Editor
from aqt.sound import av_player
import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QCheckBox
)


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

addon_dir = os.path.dirname(os.path.abspath(__file__))

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

from aqt import mw
from aqt.qt import *

class AudioToolsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.settings = {
            "default_model": "Basic",
            "default_deck": "Default",
            "audio_ext": "mp3",
            "bitrate": "192",
            "image_height": 1080,
            "pad_start": 0,
            "pad_end": 0,
            "subs_target_language": "",
            "subs_native_language": "",
            "subs_target_language_code": "",
            "subs_native_language_code": "",
        }
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Audio Card Suite')

        vbox = QVBoxLayout()

        importGroup = QGroupBox("Import Options")
        self.modelButton = QPushButton()
        if mw.col.models.by_name(self.settings["default_model"]):
            self.modelButton.setText(self.settings["default_model"])
        else:
            self.modelButton.setText(mw.col.models.current()['name'])
        self.modelButton.setAutoDefault(False)
        self.modelButton.clicked.connect(lambda: None)
        self.modelFieldsButton = QPushButton()
        self.modelFieldsButton.clicked.connect(lambda: None)
        self.deckButton = QPushButton(self.settings["default_deck"])
        self.deckButton.clicked.connect(lambda: None)

        self.modelFieldsButton.setText("⚙️")
        self.modelFieldsButton.setFixedWidth(32)

        grid = QGridLayout()
        grid.addWidget(QLabel("Type:"), 0, 0)
        grid.addWidget(self.modelButton, 0, 1)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self.modelFieldsButton, 0, 2)
        grid.addWidget(QLabel("Deck:"), 0, 3)
        grid.addWidget(self.deckButton, 0, 4)
        grid.setColumnStretch(4, 1)

        importGroup.setLayout(grid)
        vbox.addWidget(importGroup)

        # Editable input groups: Image, Pad Timings, Audio (new)
        hbox = QHBoxLayout()

        # Image group (Height only)
        imageGroup = QGroupBox("Image")
        imageLayout = QGridLayout()
        imageLayout.addWidget(QLabel("Height:"), 0, 0)
        self.imageHeightEdit = QLineEdit(str(self.settings["image_height"]))
        imageLayout.addWidget(self.imageHeightEdit, 0, 1)
        imageLayout.addWidget(QLabel("px"), 0, 2)
        imageGroup.setLayout(imageLayout)
        hbox.addWidget(imageGroup)

        # Pad Timings group (Start and End)
        padGroup = QGroupBox("Pad Timings")
        padLayout = QGridLayout()
        padLayout.addWidget(QLabel("Start:"), 0, 0)
        padLayout.addWidget(QLabel("End:"), 1, 0)
        self.padStartEdit = QLineEdit(str(self.settings["pad_start"]))
        self.padEndEdit = QLineEdit(str(self.settings["pad_end"]))
        padLayout.addWidget(self.padStartEdit, 0, 1)
        padLayout.addWidget(QLabel("ms"), 0, 2)
        padLayout.addWidget(self.padEndEdit, 1, 1)
        padLayout.addWidget(QLabel("ms"), 1, 2)
        padLayout.addWidget(QLabel(""), 1, 2)  # empty for alignment
        padGroup.setLayout(padLayout)
        hbox.addWidget(padGroup)

        # Audio group (File ext and Bitrate)
        audioGroup = QGroupBox("Audio")
        audioLayout = QGridLayout()
        audioLayout.addWidget(QLabel("File Type:"), 0, 0)

        self.audioExtCombo = QComboBox()
        self.audioExtCombo.addItems(["opus", "mp3", "flac"])
        current_index = self.audioExtCombo.findText(self.settings["audio_ext"])
        if current_index >= 0:
            self.audioExtCombo.setCurrentIndex(current_index)
        self.audioExtCombo.currentTextChanged.connect(self.on_audio_ext_changed)
        audioLayout.addWidget(self.audioExtCombo, 0, 1)

        self.normalize_checkbox = QCheckBox("Normalize Audio")
        self.normalize_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
        self.normalize_checkbox.stateChanged.connect(lambda _: self.on_audio_ext_changed(self.audioExtCombo.currentText()))

        self.bitrateEdit = QSpinBox()
        self.bitrateEdit.setRange(8, 512)  # example range
        self.bitrateEdit.setValue(int(self.settings["bitrate"]))
        self.kbps_label = QLabel("Quality:")
        self.bitrateEdit.setSuffix(" kbps")
        audioLayout.addWidget(self.kbps_label, 1, 0)
        audioLayout.addWidget(self.bitrateEdit, 1, 1)


        # LUFS spinner (hidden by default)
        self.lufsSpinner = QSpinBox()
        self.lufsSpinner.setRange(-70, 0)
        self.lufsSpinner.setValue(-14)
        self.lufsSpinner.setSuffix(" LUFS")
        self.lufsSpinner.setToolTip("Target loudness level")

        audioLayout.addWidget(self.normalize_checkbox, 2, 0, 1, 2)
        audioLayout.addWidget(self.lufsSpinner, 3, 0)

        self.lufsSpinner.hide()



        audioGroup.setLayout(audioLayout)
        hbox.addWidget(audioGroup)

        vbox.addLayout(hbox)

        # Subtitles group with tabs
        subsGroup = QGroupBox("Mpv Tracks")
        subsLayout = QVBoxLayout()

        info_label = QLabel("The currently selected tab will have its settings used.")
        subsLayout.addWidget(info_label)

        tabs = QTabWidget()

        # Language Codes Tab
        langCodesTab = QWidget()
        langGrid = QGridLayout()

        lang_labels = [
            "Target Audio Code",
            "Target subtitle code",
            "Translation Audio Code",
            "Translation subtitle code",
        ]

        self.langCodeCombos = []
        self.langCodeEdits = []

        for i, label_text in enumerate(lang_labels):
            langGrid.addWidget(QLabel(label_text + ":"), i, 0)
            combo = QComboBox()
            edit = QLineEdit("")
            edit.setFixedWidth(24)
            edit.setReadOnly(True)
            edit.setStyleSheet("QLineEdit{background: #f4f3f4;}")
            edit.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

            self.langCodeCombos.append(combo)
            self.langCodeEdits.append(edit)

            langGrid.addWidget(combo, i, 1)
            langGrid.addWidget(edit, i, 2)

        langCodesTab.setLayout(langGrid)
        tabs.addTab(langCodesTab, "Language Codes")

        # Tracks Tab
        tracksTab = QWidget()
        tracksGrid = QGridLayout()

        track_labels = [
            "Target Audio Track Number",
            "Target Subtitle Track Number",
            "Translation Audio Track Number",
            "Translation Subtitle Track Number",
        ]

        self.trackSpinners = []

        for i, label_text in enumerate(track_labels):
            tracksGrid.addWidget(QLabel(label_text + ":"), i, 0)
            spinner = QSpinBox()
            spinner.setMinimum(0)
            spinner.setMaximum(1000)
            self.trackSpinners.append(spinner)
            tracksGrid.addWidget(spinner, i, 1)

        tracksTab.setLayout(tracksGrid)
        tabs.addTab(tracksTab, "Tracks")

        subsLayout.addWidget(tabs)
        subsGroup.setLayout(subsLayout)

        # Add subtitles group first (full width)
        vbox.addWidget(subsGroup)

        # Set default source directory path
        addon_source_folder = os.path.join(addon_dir, "Sources")

        # Source group with horizontal row for sourceDirEdit + browseBtn
        sourceGroup = QGroupBox("Source")
        sourceLayout = QVBoxLayout()
        sourceGroup.setLayout(sourceLayout)

        sourceDirLayout = QHBoxLayout()
        self.sourceDirEdit = QLineEdit()
        self.sourceDirEdit.setPlaceholderText("Select source directory")
        self.sourceDirEdit.setText(addon_source_folder)

        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sourceDirEdit.setSizePolicy(policy)

        browseBtn = QPushButton("Browse")
        sourceDirLayout.addWidget(self.sourceDirEdit)
        sourceDirLayout.addWidget(browseBtn)
        sourceLayout.addLayout(sourceDirLayout)

        # Convert button with confirmation dialog
        convertBtn = QPushButton("Convert Source Videos to Audio")

        def confirm_conversion():
            msg_box = QMessageBox(mw)
            msg_box.setWindowTitle("Confirm Conversion")
            msg_box.setText(
                "This will convert all video files in the source folder to the selected audio format to save space.\n\n"
                "The original video files will be deleted after conversion.\n\n"
                "After conversion, you will no longer be able to generate screenshots or switch audio tracks for existing cards.")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setIcon(QMessageBox.Icon.Question)

            if msg_box.exec() == QMessageBox.StandardButton.Yes:
                print("User confirmed conversion.")
                # insert actual conversion function here
            else:
                print("User cancelled conversion.")

        convertBtn.clicked.connect(confirm_conversion)
        sourceLayout.addWidget(convertBtn)



        # Add source group below subtitles group
        vbox.addWidget(sourceGroup)

        # Bottom buttons
        hbox2 = QHBoxLayout()
        hbox2.addStretch(1)
        self.openFileButton = QPushButton("Open File")
        self.openFileButton.setDefault(True)
        self.openFileButton.clicked.connect(lambda: None)
        hbox2.addWidget(self.openFileButton)
        vbox.addLayout(hbox2)

        self.setLayout(vbox)
        self.setWindowIcon(QIcon(":/icons/anki.png"))

        self.on_audio_ext_changed(self.audioExtCombo.currentText())

    def on_audio_ext_changed(self, text):
        if text == "flac":
            self.bitrateEdit.hide()
            self.kbps_label.hide()
        else:
            self.bitrateEdit.show()
            self.kbps_label.show()

        show_lufs = self.normalize_checkbox.isChecked()
        self.lufsSpinner.setVisible(show_lufs)


def open_audio_tools_dialog():
    dlg = AudioToolsDialog()
    dlg.show()


def add_audio_tools_menu():
    menu_bar = mw.form.menubar
    for action in menu_bar.actions():
        if action.text() == "Audio Tools":
            return
    action = QAction("Audio Tools", mw)
    action.triggered.connect(open_audio_tools_dialog)
    menu_bar.addAction(action)

add_audio_tools_menu()







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
    if main_layout is None or hasattr(editor, "_custom_controls_container_buttons"):
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

    # === BUTTONS ===
    buttons_container = QWidget()
    buttons_layout = QVBoxLayout(buttons_container)
    buttons_layout.setContentsMargins(*CONTAINER_MARGINS)
    buttons_layout.setSpacing(CONTAINER_SPACING)

    timing_btn_row = QWidget()
    timing_btn_layout = QHBoxLayout(timing_btn_row)
    timing_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    timing_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    timing_btn_layout.addWidget(make_button("Start +50ms", lambda: button_actions.adjust_sound_tag(editor, -ms_amount, 0)))
    timing_btn_layout.addWidget(make_button("Start -50ms", lambda: button_actions.adjust_sound_tag(editor, ms_amount, 0), danger=True))
    timing_btn_layout.addWidget(make_button("End -50ms", lambda: button_actions.adjust_sound_tag(editor, 0, -ms_amount), danger=True))
    timing_btn_layout.addWidget(make_button("End +50ms", lambda: button_actions.adjust_sound_tag(editor, 0, ms_amount)))
    buttons_layout.addWidget(timing_btn_row)

    add_remove_row = QWidget()
    add_remove_layout = QHBoxLayout(add_remove_row)
    add_remove_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    add_remove_layout.setSpacing(BUTTON_ROW_SPACING)
    add_remove_layout.addWidget(make_button("Add Previous Line", lambda: button_actions.add_context_line_helper(editor, -1)))
    add_remove_layout.addWidget(make_button("Remove First Line", lambda: button_actions.remove_edge_lines_helper(editor, -1), danger=True))
    add_remove_layout.addWidget(make_button("Remove Last Line", lambda: button_actions.remove_edge_lines_helper(editor, 1), danger=True))
    add_remove_layout.addWidget(make_button("Add Next Line", lambda: button_actions.add_context_line_helper(editor, 1)))
    buttons_layout.addWidget(add_remove_row)

    generate_btn_row = QWidget()
    generate_btn_layout = QHBoxLayout(generate_btn_row)
    generate_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    generate_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    generate_btn_layout.addWidget(make_button("Generate Fields", lambda: button_actions.generate_fields_button(editor)))
    buttons_layout.addWidget(generate_btn_row)

    main_layout.insertWidget(0, buttons_container)
    editor._custom_controls_container_buttons = buttons_container

    # === SPINBOXES + CHECKBOXES ===
    spinboxes_container = QWidget()
    spinboxes_layout = QVBoxLayout(spinboxes_container)
    spinboxes_layout.setContentsMargins(*CONTAINER_MARGINS)
    spinboxes_layout.setSpacing(CONTAINER_SPACING)

    # Row 1: Target track spinboxes
    track_row_1 = QWidget()
    track_row_1_layout = QHBoxLayout(track_row_1)
    track_row_1_layout.setContentsMargins(*ROW_MARGINS)
    track_row_1_layout.setSpacing(ROW_SPACING)
    for label in ["Target Audio Track Number", "Target Subtitle Track Number"]:
        widget, spin = make_labeled_spinbox(label, 0, 1000, 0)
        track_row_1_layout.addWidget(widget)
        if "Audio" in label:
            editor._target_audio_track_spinbox = spin
        elif "Subtitle" in label:
            editor._target_subtitle_track_spinbox = spin

    # Row 2: Translation track spinboxes
    track_row_2 = QWidget()
    track_row_2_layout = QHBoxLayout(track_row_2)
    track_row_2_layout.setContentsMargins(*ROW_MARGINS)
    track_row_2_layout.setSpacing(ROW_SPACING)
    for label in ["Translation Audio Track Number", "Translation Subtitle Track Number"]:
        widget, spin = make_labeled_spinbox(label, 0, 1000, 0)
        track_row_2_layout.addWidget(widget)
        if "Audio" in label:
            editor._translation_audio_track_spinbox = spin
        elif "Subtitle" in label:
            editor._translation_subtitle_track_spinbox = spin

    # Row 3: Offset spinboxes
    offset_spinboxes_row = QWidget()
    offset_spinboxes_layout = QHBoxLayout(offset_spinboxes_row)
    offset_spinboxes_layout.setContentsMargins(*ROW_MARGINS)
    offset_spinboxes_layout.setSpacing(ROW_SPACING)
    for label in ["Start offset", "End offset", "Subtitle Offset"]:
        widget, spin = make_labeled_spinbox(label, -999999, 999999, 0)
        offset_spinboxes_layout.addWidget(widget)
        if "Start" in label:
            editor._start_offset_spinbox = spin
        elif "End" in label:
            editor._end_offset_spinbox = spin
        elif "Subtitle" in label:
            editor._subtitle_offset_spinbox = spin

    # Row 4: Checkboxes row (autoplay + show track menu)
    checkboxes_row = QWidget()
    checkboxes_layout = QHBoxLayout(checkboxes_row)
    checkboxes_layout.setContentsMargins(*ROW_MARGINS)
    checkboxes_layout.setSpacing(ROW_SPACING)

    autoplay_checkbox = QCheckBox("Autoplay")
    autoplay_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
    autoplay_checkbox.setChecked(getattr(editor, "_auto_play_enabled", False))
    autoplay_checkbox.clicked.connect(lambda _: handle_autoplay_checkbox_toggle(_, editor))
    checkboxes_layout.addWidget(autoplay_checkbox)

    show_track_menu_checkbox = QCheckBox("Show Track Menu")
    show_track_menu_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
    checkboxes_layout.addWidget(show_track_menu_checkbox)

    def toggle_track_visibility(state):
        visible = state == 2  # Qt.Checked == 2
        track_row_1.setVisible(visible)
        track_row_2.setVisible(visible)
        offset_spinboxes_row.setVisible(visible)

    show_track_menu_checkbox.stateChanged.connect(toggle_track_visibility)
    toggle_track_visibility(0)

    spinboxes_layout.addWidget(track_row_1)
    spinboxes_layout.addWidget(track_row_2)
    spinboxes_layout.addWidget(offset_spinboxes_row)
    spinboxes_layout.addWidget(checkboxes_row)
    main_layout.addWidget(spinboxes_container)
    editor._custom_controls_container_spinboxes = spinboxes_container


gui_hooks.editor_did_init.append(add_custom_controls)

def on_profile_loaded():
    gui_hooks.editor_did_load_note.append(button_actions.on_note_loaded)