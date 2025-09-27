import threading

from aqt import gui_hooks
from aqt.utils import showInfo
from aqt.editor import Editor
from PyQt6.QtCore import Qt
import json
from PyQt6.QtWidgets import QGroupBox, QLineEdit
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from aqt.utils import tooltip
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSpinBox, QCheckBox
)

import manage_database

try:
    from . import manage_files
    from . import button_actions
    from . import language_codes
    from . import constants
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import manage_files
    import button_actions
    import language_codes
    import constants


CONTAINER_MARGINS = constants.CONTAINER_MARGINS
CONTAINER_SPACING = constants.CONTAINER_SPACING

ROW_MARGINS = constants.ROW_MARGINS
ROW_SPACING = constants.ROW_SPACING

BUTTON_ROW_MARGINS = constants.BUTTON_ROW_MARGINS
BUTTON_ROW_SPACING = constants.BUTTON_ROW_SPACING

LABEL_MIN_WIDTH = constants.LABEL_MIN_WIDTH
SPINBOX_MIN_WIDTH = constants.SPINBOX_MIN_WIDTH
CHECKBOX_MIN_WIDTH = constants.CHECKBOX_MIN_WIDTH

BUTTON_PADDING = constants.BUTTON_PADDING
SHIFT_BUTTON_BG_COLOR = constants.SHIFT_BUTTON_BG_COLOR

_audio_tools_dialog_instance = None

from aqt import mw
from aqt.qt import *


def create_default_config():
    config_file_path = os.path.join(constants.addon_dir, "config.json")

    if not os.path.exists(config_file_path):
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(constants.default_settings, f, indent=2)
    return constants.default_settings

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.data = {"fields": [], "mapped_fields": {}}
        self.load()

    def load(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"fields": [], "mapped_fields": {}}
        else:
            self.data = {"fields": [], "mapped_fields": {}}
        return self.data

    def save(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)



    def getMappedFields(self, note_type_name):
        return self.data.get(note_type_name, {}).get("mapped_fields", {})

    def updateMapping(self, note_type_name, mapping):
        self.data.setdefault(note_type_name, {})["mapped_fields"] = mapping
        self.save()



class AudioToolsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.addon_id = "Audio-Card-Suite"
        config_file_path = os.path.join(constants.addon_dir, "config.json")
        self.configManager = ConfigManager(config_file_path)
        print("loading settings")
        self.settings = self.configManager.load()
        self.load_settings()
        self.initUI()
        self.apply_settings_to_ui()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setMinimumSize(546, 746)

    def load_settings(self):
        config_file_path = os.path.join(constants.addon_dir, "config.json")
        if not os.path.exists(config_file_path):
            print("No config.json found, creating default config.")
            config = create_default_config()
        else:
            try:
                with open(config_file_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Invalid config.json, resetting to defaults. Error: {e}")
                config = create_default_config()

        default_settings = create_default_config()

        # Treat only these keys as global defaults (kept at top level)
        GLOBAL_KEYS = [
            "default_model",
            "source_folder",
            "default_deck",
            "selected_tab_index",
            "autoplay",
        ]

        # Start with an empty dict, then copy global keys (from config if present, else defaults)
        self.settings = {}
        for k in GLOBAL_KEYS:
            if k in config:
                self.settings[k] = config[k]
            else:
                # only provide default for truly global keys
                if k in default_settings:
                    self.settings[k] = default_settings[k]

        # Copy any other keys from config (these will be per-model sections or legacy top-level keys)
        for key, value in config.items():
            if key in GLOBAL_KEYS:
                continue
            # keep whatever is in config (per-model dicts will be copied here)
            self.settings[key] = value

        print("Loaded settings from config:")
        print(json.dumps(self.settings, indent=2))
        print(f"normalize_audio in settings: {self.settings.get('normalize_audio')}")

    def save_settings(self):
        print("save_settings called")

        note_type_name = self.modelButton.text()

        if note_type_name not in self.settings:
            self.settings[note_type_name] = {}

        self.settings[note_type_name]["image_height"] = self.imageHeightEdit.value()
        self.settings[note_type_name]["pad_start_target"] = self.padStartEditTarget.value()
        self.settings[note_type_name]["pad_end_target"] = self.padEndEditTarget.value()
        self.settings[note_type_name]["pad_start_translation"] = self.padStartEditTranslation.value()
        self.settings[note_type_name]["pad_end_translation"] = self.padEndEditTranslation.value()
        self.settings[note_type_name]["audio_ext"] = self.audioExtCombo.currentText()
        self.settings[note_type_name]["bitrate"] = self.bitrateEdit.value()
        self.settings[note_type_name]["normalize_audio"] = self.normalize_checkbox.isChecked()
        self.settings[note_type_name]["lufs"] = self.lufsSpinner.value()
        self.settings["source_folder"] = self.sourceDirEdit.text()

        for i, key in enumerate([
            "target_audio_track",
            "target_subtitle_track",
            "translation_audio_track",
            "translation_subtitle_track",
            "target_timing_track",
            "translation_timing_track"
        ]):
            self.settings[note_type_name][key] = self.trackSpinners[i].value()

        self.settings[note_type_name]["timing_tracks_enabled"] = self.timingTracksCheckbox.isChecked()
        print(f"setting timing tracks to {self.timingTracksCheckbox.isChecked()} to model: {note_type_name}")

        # Save all 4 language code edits
        for i, key in enumerate(["target_language_code", "translation_language_code", "target_timing_code",
                                 "translation_timing_code"]):
            code = self.settings[note_type_name].get(key, "")
            language_name = language_codes.PyLangISO639_2.code_to_name(code)
            if language_name:
                self.langCodeCombos[i].setCurrentText(language_name)
            else:
                self.langCodeCombos[i].setCurrentText("None")

        config_path = os.path.join(constants.addon_dir, "config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            print("Settings saved successfully.")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def show_fields_menu(self):
        current_note_type_name = self.modelButton.text()
        model = mw.col.models.by_name(current_note_type_name)
        if not model:
            showInfo(f"Note type '{current_note_type_name}' not found.")
            return

        menu = QMenu(self.modelFieldsButton)
        for field in model['flds']:
            action = QAction(field['name'], menu)
            # Connect the action to some slot if needed, for example, print or store the field
            action.triggered.connect(lambda checked, f=field['name']: self.on_field_selected(f))
            menu.addAction(action)
        menu.exec(self.modelFieldsButton.mapToGlobal(self.modelFieldsButton.rect().bottomLeft()))

    def on_field_selected(self, field_name):
        # You can update your UI or settings with the selected field here
        print(f"Selected field: {field_name}")
        # For example, set the modelFieldsButton text to show selection (optional)
        self.modelFieldsButton.setText(field_name)

    def on_lang_code_changed(self, idx, language):
        code = self.language_to_code(language)
        edit = self.langCodeEdits[idx]
        edit.setText(code)
        note_type_name = self.modelButton.text()

        if idx == 0:
            self.settings[note_type_name]["target_language"] = language
            self.settings[note_type_name]["target_language_code"] = code
        elif idx == 1:
            self.settings[note_type_name]["translation_language"] = language
            self.settings[note_type_name]["translation_language_code"] = code
        elif idx == 2:
            self.settings[note_type_name]["target_timing_language"] = language
            self.settings[note_type_name]["target_timing_code"] = code
        elif idx == 3:
            self.settings[note_type_name]["translation_timing_language"] = language
            self.settings[note_type_name]["translation_timing_code"] = code

        self.save_settings()

    def language_to_code(self, language: str) -> str:
        return language_codes.PyLangISO639_2.name_to_code(language, bibliographic=True)

    def initUI(self):
        def confirm_conversion():
            msg_box = QMessageBox(mw)
            msg_box.setWindowTitle("Confirm Conversion")
            msg_box.setText(
                "This will extract the specified subtitle files and convert all video files in the source folder to the selected audio format to save space.\n\n"
                "The original video files will be deleted after conversion.\n\n"
                "After conversion, you will no longer be able to generate screenshots or switch tracks for existing cards.")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setIcon(QMessageBox.Icon.Question)

            if msg_box.exec() == QMessageBox.StandardButton.Yes:
                print("User confirmed conversion.")
                # insert actual conversion function here
            else:
                print("User cancelled conversion.")

        def confirm_bulk_generate():
            deck_id = mw.col.decks.get_current_id()
            deck = mw.col.decks.get(deck_id)
            all_note_types = mw.col.models.all()
            note_type = all_note_types[0]['name'] if all_note_types else ""

            dialog = QDialog(mw)
            dialog.setWindowTitle("Bulk Generate")

            layout = QVBoxLayout(dialog)

            message = QLabel(
                f"All cards in the deck '{deck['name']}' will have fields generated."
            )
            layout.addWidget(message)

            # Buttons
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
            )
            layout.addWidget(button_box)

            def on_accept():
                print("User confirmed conversion.")
                dialog.accept()
                button_actions.bulk_generate(
                    deck,
                    note_type,
                )

            def on_reject():
                print("User cancelled conversion.")
                dialog.reject()

            button_box.accepted.connect(on_accept)
            button_box.rejected.connect(on_reject)

            dialog.setLayout(layout)
            dialog.exec()

        def update_database_button():
            tooltip("Updating database...")
            threading.Thread(target=lambda: constants.timed_call(manage_database.update_database), daemon=True).start()


        self.setWindowTitle("Audio Card Suite")
        vbox = QVBoxLayout()
        importGroup = QGroupBox("Import Options")


        self.modelButton = QPushButton()
        default_model = self.settings.get("default_model")
        self.modelButton.setText(default_model)
        note_type_name = self.modelButton.text()

        self.modelButton.setAutoDefault(False)
        self.modelButton.clicked.connect(self.show_model_menu)


        self.modelFieldsButton = QPushButton("⚙️")
        self.modelFieldsButton.setFixedWidth(32)
        self.modelFieldsButton.clicked.connect(lambda: self.mapFields(self.modelButton.text()))

        grid = QGridLayout()
        grid.addWidget(QLabel("Note Type:"), 0, 0)
        grid.addWidget(self.modelButton, 0, 1)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self.modelFieldsButton, 0, 2)

        importGroup.setLayout(grid)
        vbox.addWidget(importGroup)

        # Editable input groups: Image, Pad Timings, Audio (new)
        hbox = QHBoxLayout()

        imageGroup = QGroupBox("Image")
        imageLayout = QGridLayout()
        imageLayout.addWidget(QLabel("Height:"), 0, 0)
        self.imageHeightEdit = QSpinBox()
        self.imageHeightEdit.setRange(1, 9999)

        self.imageHeightEdit.setValue(
            self.settings.get(note_type_name, {}).get("image_height", constants.default_settings["image_height"])
        )
        self.imageHeightEdit.setSuffix(" px")
        imageLayout.addWidget(self.imageHeightEdit, 0, 1)
        imageGroup.setLayout(imageLayout)
        hbox.addWidget(imageGroup)

        # Pad Timings group (Start and End)
        padGroup = QGroupBox("Pad Timings")
        padLayout = QGridLayout()
        padLayout.addWidget(QLabel("Target Start:"), 0, 0)
        padLayout.addWidget(QLabel("Target End:"), 1, 0)
        padLayout.addWidget(QLabel("Translation Start:"), 2, 0)
        padLayout.addWidget(QLabel("Translation End:"), 3, 0)

        self.padStartEditTarget = QSpinBox()
        self.padStartEditTarget.setRange(-10000000, 10000000)
        self.padStartEditTarget.setValue(
            self.settings.get(note_type_name, {}).get("pad_start_target", constants.default_settings["pad_start_target"]))
        self.padStartEditTarget.setSuffix(" ms")

        self.padEndEditTarget = QSpinBox()
        self.padEndEditTarget.setRange(-10000000, 10000000)
        self.padEndEditTarget.setValue(
            self.settings.get(note_type_name, {}).get("pad_end_target", constants.default_settings["pad_end_target"]))
        self.padEndEditTarget.setSuffix(" ms")

        self.padStartEditTranslation = QSpinBox()
        self.padStartEditTranslation.setRange(-10000000, 10000000)
        self.padStartEditTranslation.setValue(self.settings.get(note_type_name, {}).get("pad_start_translation", constants.default_settings["pad_start_translation"]))
        self.padStartEditTranslation.setSuffix(" ms")

        self.padEndEditTranslation = QSpinBox()
        self.padEndEditTranslation.setRange(-10000000, 10000000)
        self.padEndEditTranslation.setValue(self.settings.get(note_type_name, {}).get("pad_end_translation", constants.default_settings["pad_end_translation"]))
        self.padEndEditTranslation.setSuffix(" ms")

        padLayout.addWidget(self.padStartEditTarget, 0, 1)
        padLayout.addWidget(self.padEndEditTarget, 1, 1)
        padLayout.addWidget(self.padStartEditTranslation, 2, 1)
        padLayout.addWidget(self.padEndEditTranslation, 3, 1)

        padGroup.setLayout(padLayout)
        hbox.addWidget(padGroup)

        # Audio group (File ext and Bitrate)
        audioGroup = QGroupBox("Audio")
        audioLayout = QGridLayout()
        audioLayout.addWidget(QLabel("File Type:"), 0, 0)
        self.audioExtCombo = QComboBox()
        self.audioExtCombo.addItems(["opus", "mp3", "flac"])
        current_index = self.audioExtCombo.findText(
            self.settings.get(note_type_name, {}).get("audio_ext", constants.default_settings["audio_ext"])
        )
        if current_index >= 0:
            self.audioExtCombo.setCurrentIndex(current_index)
        self.audioExtCombo.currentTextChanged.connect(self.on_audio_ext_changed)
        audioLayout.addWidget(self.audioExtCombo, 0, 1)
        self.bitrateEdit = QSpinBox()
        self.bitrateEdit.setRange(8, 512)  # example range
        self.bitrateEdit.setValue(
            int(self.settings.get(note_type_name, {}).get("bitrate", constants.default_settings["bitrate"]))
        )
        self.kbps_label = QLabel("Quality:")
        self.bitrateEdit.setSuffix(" kbps")
        audioLayout.addWidget(self.kbps_label, 1, 0)
        audioLayout.addWidget(self.bitrateEdit, 1, 1)


        # LUFS spinner (hidden by default)
        self.lufsSpinner = QSpinBox()
        self.lufsSpinner.setRange(-70, 0)
        self.lufsSpinner.setValue(-16)
        self.lufsSpinner.setSuffix(" LUFS")
        self.lufsSpinner.setToolTip("Target loudness level")
        self.lufsSpinner.setValue(
            self.settings.get(note_type_name, {}).get("lufs", constants.default_settings["lufs"])
        )
        self.normalize_checkbox = QCheckBox("Normalize Audio")
        self.normalize_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
        self.normalize_checkbox.setChecked(
            self.settings.get(note_type_name, {}).get("normalize_audio", constants.default_settings["normalize_audio"])
        )

        self.normalize_checkbox.stateChanged.connect(lambda _: self.on_audio_ext_changed(self.audioExtCombo.currentText()))
        audioLayout.addWidget(self.normalize_checkbox, 2, 0, 1, 2)
        audioLayout.addWidget(self.lufsSpinner, 3, 0)
        self.lufsSpinner.hide()
        audioGroup.setLayout(audioLayout)
        hbox.addWidget(audioGroup)
        vbox.addLayout(hbox)

        # Subtitles group with tabs
        subsGroup = QGroupBox("Source Tracks")
        subsLayout = QVBoxLayout()
        self.timingTracksCheckbox = QCheckBox("Timing Tracks")
        self.timingTracksCheckbox.setChecked(
            self.settings.get(note_type_name, {}).get(
                "timing_tracks_enabled", constants.default_settings["timing_tracks_enabled"]
            )
        )
        self.timingTracksCheckbox.stateChanged.connect(self.on_timing_checkbox_changed)
        self.timingTracksCheckbox.setTristate(False)
        subsLayout.addWidget(self.timingTracksCheckbox)
        self.tabs = QTabWidget()

        from PyQt6.QtWidgets import QSizePolicy

        # language codes tab
        langCodesTab = QWidget()
        langGrid = QGridLayout()
        self.langCodeCombos = []
        self.langCodeEdits = []
        self.langCodeLabels = []

        codes_info_label = QLabel("Tracks will be used as a fallback if the Language Code cannot be found.")
        codes_info_label.setWordWrap(True)
        codes_label = QLabel()
        codes_label.setText(
            'If your language is not listed, enter its <a href="https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes">ISO 639-2 language code</a> in the text box.'
        )
        codes_label.setOpenExternalLinks(True)
        codes_label.setWordWrap(True)

        codes_info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        codes_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        langGrid.addWidget(codes_info_label, 0, 0, 1, 3)
        langGrid.addWidget(codes_label, 1, 0, 1, 3)

        labels = [
            "Target Language Code:",
            "Translation Language Code:",
            "Target Timing Code:",
            "Translation Timing Code:"
        ]

        combo_keys = [
            "target_language",
            "translation_language",
            "target_timing_language",
            "translation_timing_language"
        ]

        edit_keys = [
            "target_language_code",
            "translation_language_code",
            "target_timing_code",
            "translation_timing_code"
        ]

        hide_rows_start = 2
        start_row = 2

        for i, label_text in enumerate(labels):
            row = start_row + i
            label = QLabel(label_text)
            self.langCodeLabels.append(label)
            langGrid.addWidget(label, row, 0)

            combo = QComboBox()
            combo.addItems([
                "None", "Japanese", "Chinese", "English", "Korean", "Cantonese", "German", "Spanish"
            ])
            saved_combo_value = self.settings.get(note_type_name, {}).get(combo_keys[i], "None")
            if combo.findText(saved_combo_value) == -1:
                combo.addItem(saved_combo_value)
            combo.setCurrentText(saved_combo_value)
            self.langCodeCombos.append(combo)
            langGrid.addWidget(combo, row, 1)

            edit = QLineEdit()
            edit.setFixedWidth(35)
            edit.setStyleSheet("QLineEdit{background: #f4f3f4;}")
            edit.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            saved_edit_value = self.settings.get(note_type_name, {}).get(edit_keys[i], "")
            edit.setText(saved_edit_value)
            self.langCodeEdits.append(edit)
            langGrid.addWidget(edit, row, 2)

            note_type_name = self.modelButton.text()
            combo.currentTextChanged.connect(
                lambda text, idx=i, model=note_type_name: self.on_lang_code_changed(idx, str(text))
            )

        for i in range(hide_rows_start, len(labels)):
            self.langCodeCombos[i].hide()
            self.langCodeEdits[i].hide()
            self.langCodeLabels[i].hide()

        langCodesTab.setLayout(langGrid)
        self.tabs.addTab(langCodesTab, "Language Codes")

        # Tracks Tab
        tracksTab = QWidget()
        tracksGrid = QGridLayout()
        tracks_info_label = QLabel("Language Codes will be used as a fallback if the Track does not exist.")

        tracks_info_label.setWordWrap(True)
        tracksGrid.addWidget(tracks_info_label, 0, 0, 1, 2)



        track_keys = [
            "target_audio_track",
            "target_subtitle_track",
            "translation_audio_track",
            "translation_subtitle_track",
            "target_timing_track",
            "translation_timing_track"
        ]

        track_labels = [
            "Target Audio Track",
            "Target Subtitle Track",
            "Translation Audio Track",
            "Translation Subtitle Track",
            "Target Timing Subtitle Track",
            "Translation Timing Subtitle Track"
        ]

        self.trackSpinners = []
        self.trackLabels = []

        for i, (label_text, key) in enumerate(zip(track_labels, track_keys), start=1):
            label = QLabel(label_text + ":")
            spinner = QSpinBox()
            spinner.setMinimum(0)
            spinner.setMaximum(1000)
            spinner.setValue(self.settings.get(note_type_name, {}).get(key, 0))
            tracksGrid.addWidget(label, i, 0)
            tracksGrid.addWidget(spinner, i, 1)
            self.trackLabels.append(label)
            self.trackSpinners.append(spinner)

        tracksTab.setLayout(tracksGrid)
        self.tabs.addTab(tracksTab, "Tracks")
        self.trackSpinners[0].setValue(self.settings.get(note_type_name, {}).get("target_audio_track", 0))
        self.trackSpinners[1].setValue(self.settings.get(note_type_name, {}).get("target_subtitle_track", 0))
        self.trackSpinners[2].setValue(self.settings.get(note_type_name, {}).get("translation_audio_track", 0))
        self.trackSpinners[3].setValue(self.settings.get(note_type_name, {}).get("translation_subtitle_track", 0))
        self.trackSpinners[4].setValue(self.settings.get(note_type_name, {}).get("target_timing_track", 0))
        self.trackSpinners[5].setValue(self.settings.get(note_type_name, {}).get("translation_timing_track", 0))

        selected_tab_index = self.settings.get(note_type_name, {}).get("selected_tab_index", 0)
        self.tabs.setCurrentIndex(selected_tab_index)

        subsLayout.addWidget(self.tabs)
        subsGroup.setLayout(subsLayout)
        vbox.addWidget(subsGroup)
        sourceGroup = QGroupBox("Source")
        sourceLayout = QVBoxLayout()
        sourceGroup.setLayout(sourceLayout)
        sourceDirLayout = QHBoxLayout()

        # Load from config or fallback
        initial_source_folder = self.settings.get(note_type_name, {}).get(
            "source_folder", os.path.join(constants.addon_dir, "Sources")
        )

        self.sourceDirEdit = QLineEdit()
        self.sourceDirEdit.setPlaceholderText("Select source directory")
        self.sourceDirEdit.setText(initial_source_folder)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sourceDirEdit.setSizePolicy(policy)

        # Save on text change
        self.sourceDirEdit.textChanged.connect(
            lambda text: self.settings.update({"source_folder": text})
        )

        browseBtn = QPushButton("Open Folder")
        browseBtn.clicked.connect(
            lambda: (
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.sourceDirEdit.text()))
                if os.path.exists(self.sourceDirEdit.text())
                else showInfo("Folder not found")
            )
        )

        sourceDirLayout.addWidget(self.sourceDirEdit)
        sourceDirLayout.addWidget(browseBtn)
        sourceLayout.addLayout(sourceDirLayout)

        # todo implement
        # Convert button with confirmation dialog
        # convertBtn = QPushButton("Convert Source Videos to Audio")
        # convertBtn.clicked.connect(confirm_conversion)
        # sourceLayout.addWidget(convertBtn)

        # Add source group below subtitles group
        vbox.addWidget(sourceGroup)
        hbox2 = QHBoxLayout()

        self.bulkGenerateButton = QPushButton("Bulk Generate")
        self.bulkGenerateButton.setDefault(True)
        self.bulkGenerateButton.clicked.connect(confirm_bulk_generate)
        hbox2.addWidget(self.bulkGenerateButton)

        self.updateDatabaseButton = QPushButton("Update Database")
        self.updateDatabaseButton.setDefault(True)
        self.updateDatabaseButton.clicked.connect(update_database_button)
        hbox2.addWidget(self.updateDatabaseButton)

        hbox2.addStretch(4)

        # todo add mpv support
        # open file button
        # self.openFileButton = QPushButton("Open File")
        # self.openFileButton.setDefault(True)
        # self.openFileButton.clicked.connect(lambda: None)
        # hbox2.addWidget(self.openFileButton)

        vbox.addLayout(hbox2)
        self.setLayout(vbox)
        self.setWindowIcon(QIcon(":/icons/anki.png"))
        self.on_audio_ext_changed(self.audioExtCombo.currentText())


        # save settings any time a change is made
        self.sourceDirEdit.textChanged.connect(self.save_settings)
        self.imageHeightEdit.valueChanged.connect(self.save_settings)
        self.bitrateEdit.valueChanged.connect(self.save_settings)
        self.lufsSpinner.valueChanged.connect(self.save_settings)
        for spinner in self.trackSpinners:
            spinner.valueChanged.connect(self.save_settings)
        self.imageHeightEdit.valueChanged.connect(self.save_settings)
        self.padStartEditTarget.valueChanged.connect(self.save_settings)
        self.padEndEditTarget.valueChanged.connect(self.save_settings)
        self.padStartEditTranslation.valueChanged.connect(self.save_settings)
        self.padEndEditTranslation.valueChanged.connect(self.save_settings)

        self.normalize_checkbox.stateChanged.connect(self.save_settings)
        self.audioExtCombo.currentTextChanged.connect(self.save_settings)

        for i, edit in enumerate(self.langCodeEdits):
            edit.textChanged.connect(lambda text, idx=i: self.on_code_edit_changed(idx, text))

        for i, combo in enumerate(self.langCodeCombos):
            combo.currentTextChanged.connect(lambda text, idx=i: self.on_lang_code_changed(idx, text))

        self.timingTracksCheckbox.stateChanged.connect(self.save_settings)
        self.timingTracksCheckbox.stateChanged.connect(lambda s: print(f"Checkbox changed to {s}"))
        self.timingTracksCheckbox.stateChanged.connect(self.on_timing_checkbox_changed)
        self.apply_settings_to_ui()

    def select_model(self, model):
        self.selectedModel = model
        self.modelButton.setText(model["name"])
        self.settings["default_model"] = model["name"]
        self.apply_settings_to_ui()

    def show_model_menu(self):
        menu = QMenu(self)
        for model in mw.col.models.all():
            name = model["name"]
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, m=model: self.select_model(m))
            menu.addAction(action)
        menu.exec(self.modelButton.mapToGlobal(self.modelButton.rect().bottomLeft()))



    def mapFields(self, note_type_name):
        if note_type_name == constants.select_note_type_string:
            showInfo(f"Please select a note type.")
            return

        fm = FieldMapping(note_type_name, self.configManager, parent=self)
        fm.exec()

    def on_tab_changed(self, index):
        note_type_name = self.modelButton.text()
        self.settings[note_type_name]["selected_tab_index"] = index
        print(f"saving settings, tab change")
        self.save_settings()

    def apply_settings_to_ui(self):
        # Block signals on widgets that trigger save_settings
        widgets = [
            self.imageHeightEdit,
            self.padStartEditTarget,
            self.padEndEditTarget,
            self.padStartEditTranslation,
            self.padEndEditTranslation,
            self.audioExtCombo,
            self.bitrateEdit,
            self.normalize_checkbox,
            self.lufsSpinner,
            *self.trackSpinners,
            *self.langCodeEdits,
            self.timingTracksCheckbox,
            self.sourceDirEdit,
        ]
        for w in widgets:
            w.blockSignals(True)

        note_type_name = self.modelButton.text()

        self.imageHeightEdit.setValue(self.settings.get(note_type_name, {}).get("image_height", constants.default_settings["image_height"]))
        self.padStartEditTarget.setValue(self.settings.get(note_type_name, {}).get("pad_start_target", constants.default_settings["pad_start_target"]))
        self.padEndEditTarget.setValue(self.settings.get(note_type_name, {}).get("pad_end_target", constants.default_settings["pad_end_target"]))
        self.padStartEditTranslation.setValue(self.settings.get(note_type_name, {}).get("pad_start_translation", constants.default_settings["pad_start_translation"]))
        self.padEndEditTranslation.setValue(self.settings.get(note_type_name, {}).get("pad_end_translation", constants.default_settings["pad_end_translation"]))

        idx = self.audioExtCombo.findText(self.settings.get(note_type_name, {}).get("audio_ext", constants.default_settings["audio_ext"]))
        if idx >= 0:
            self.audioExtCombo.setCurrentIndex(idx)

        self.bitrateEdit.setValue(self.settings.get(note_type_name, {}).get("bitrate", constants.default_settings["bitrate"]))
        self.normalize_checkbox.setChecked(self.settings.get(note_type_name, {}).get("normalize_audio", constants.default_settings["normalize_audio"]))
        self.lufsSpinner.setValue(self.settings.get(note_type_name, {}).get("lufs", constants.default_settings["lufs"]))

        self.sourceDirEdit.setText(self.settings.get("source_folder", constants.default_settings.get("source_folder", "")))

        self.tabs.setCurrentIndex(self.settings.get(note_type_name, {}).get("selected_tab_index", constants.default_settings["selected_tab_index"]))


        tracks = [
            "target_audio_track",
            "target_subtitle_track",
            "translation_audio_track",
            "translation_subtitle_track",
            "target_timing_track",
            "translation_timing_track"
        ]

        for i, track in enumerate(tracks):
            self.trackSpinners[i].setValue(self.settings.get(note_type_name, {}).get(track, 0))

        self.timingTracksCheckbox.setChecked(self.settings.get(note_type_name, {}).get("timing_tracks_enabled", False))

        for w in widgets:
            w.blockSignals(False)

        self.on_audio_ext_changed(self.audioExtCombo.currentText())
        self.on_timing_checkbox_changed(self.timingTracksCheckbox.checkState())

    def on_code_edit_changed(self, idx, text):
        print(f"code edit changed")
        code = text.strip().lower()
        combo = self.langCodeCombos[idx]

        lang_name = language_codes.PyLangISO639_2.code_to_name(code)

        if lang_name:
            if combo.findText(lang_name) == -1:
                combo.insertItem(0, lang_name)
                combo.setCurrentIndex(0)
            else:
                combo.setCurrentText(lang_name)
        else:
            if combo.findText("None") >= 0:
                combo.setCurrentText("None")
            else:
                combo.setCurrentIndex(-1)

        self.save_settings()

    def on_audio_ext_changed(self, text):
        if text == "flac":
            self.bitrateEdit.hide()
            self.kbps_label.hide()
        else:
            self.bitrateEdit.show()
            self.kbps_label.show()

        show_lufs = self.normalize_checkbox.isChecked()
        self.lufsSpinner.setVisible(show_lufs)

    def on_timing_checkbox_changed(self, state):
        state_val = state.value if hasattr(state, "value") else state
        show = (state_val == Qt.CheckState.Checked.value)

        self.langCodeEdits[2].setVisible(show)
        self.langCodeEdits[3].setVisible(show)

        self.langCodeCombos[2].setVisible(show)
        self.langCodeCombos[3].setVisible(show)

        self.langCodeLabels[2].setVisible(show)
        self.langCodeLabels[3].setVisible(show)

        self.trackLabels[4].setVisible(show)
        self.trackSpinners[4].setVisible(show)
        self.trackLabels[5].setVisible(show)
        self.trackSpinners[5].setVisible(show)

        self.save_settings()


class FieldMapping(QDialog):
    def __init__(self, name, configManager, parent=None):
        QDialog.__init__(self, parent)
        self.configManager = configManager


        self.mappedFields = self.configManager.getMappedFields(name)
        print(f"self.configManager.getMappedFields({name}): {self.configManager.getMappedFields(name)}")
        self.name = name

        self.initUI()

    def initUI(self):
        if not self.name or self.name == constants.select_note_type_string:
            showInfo(f"Please select a note type.")
            return

        self.setWindowTitle(self.name)
        vbox = QVBoxLayout()
        self.fields = []

        groupBox = QGroupBox("Map Fields")

        m = mw.col.models.by_name(self.name)
        fields = mw.col.models.field_names(m)
        grid = QGridLayout()

        for index, field in enumerate(fields):
            line = QLineEdit(field)
            line.setReadOnly(True)
            grid.addWidget(line, index, 0)

            comboBox = QComboBox()
            comboBox.currentIndexChanged.connect(self.update_comboboxes)
            comboBox.addItem("None")
            comboBox.addItem("Target Subtitle Line")
            comboBox.addItem("Target Audio")
            comboBox.addItem("Image")
            comboBox.addItem("Translation Subtitle Line")
            comboBox.addItem("Translation Audio")
            if field in self.mappedFields:
                comboBox.setCurrentIndex(comboBox.findText(self.mappedFields[field]))
            else:
                comboBox.setCurrentIndex(0)
            grid.addWidget(comboBox, index, 1)

            self.fields.append((field, comboBox))

        groupBox.setLayout(grid)
        vbox.addWidget(groupBox)

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttonBox.setOrientation(Qt.Orientation.Horizontal)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        vbox.addWidget(self.buttonBox)

        self.setLayout(vbox)

    def accept(self):
        m = {}
        for field, box in self.fields:
            if box.currentText() != "None":
                m[field] = box.currentText()
        self.configManager.updateMapping(self.name, m)
        self.close()

    def update_comboboxes(self):
        selected = set()
        for _, combo in self.fields:
            text = combo.currentText()
            if text != "None":
                selected.add(text)

        for _, combo in self.fields:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("None")

            for option in ["Target Subtitle Line", "Target Audio", "Image", "Translation Subtitle Line",
                           "Translation Audio"]:
                if option == current or option not in selected:
                    combo.addItem(option)

            combo.setCurrentText(current)
            combo.blockSignals(False)


def open_audio_tools_dialog(isEditor):
    global _audio_tools_dialog_instance

    # If the dialog is already open and visible, bring it to front
    if _audio_tools_dialog_instance and _audio_tools_dialog_instance.isVisible():
        _audio_tools_dialog_instance.raise_()
        _audio_tools_dialog_instance.activateWindow()
        return

    # Otherwise, create and show a new one
    dlg = AudioToolsDialog()
    if isEditor:
        dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    # Store reference and clear it when the dialog is closed
    _audio_tools_dialog_instance = dlg
    dlg.destroyed.connect(lambda: _clear_audio_tools_reference())

    dlg.show()

def _clear_audio_tools_reference():
    global _audio_tools_dialog_instance
    _audio_tools_dialog_instance = None

def add_audio_tools_menu():
    menu_bar = mw.form.menubar
    for action in menu_bar.actions():
        if action.text() == "Audio Tools":
            return
    action = QAction("Audio Tools", mw)
    action.triggered.connect(lambda: open_audio_tools_dialog(False))
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

    create_default_config()

    # === BUTTONS ===
    buttons_container = QWidget()
    buttons_layout = QVBoxLayout(buttons_container)
    buttons_layout.setContentsMargins(*CONTAINER_MARGINS)
    buttons_layout.setSpacing(CONTAINER_SPACING)

    timing_btn_row = QWidget()
    timing_btn_layout = QHBoxLayout(timing_btn_row)
    timing_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    timing_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    timing_btn_layout.addWidget(
        make_button("Start +50ms", lambda: constants.timed_call(button_actions.adjust_sound_tag, editor, -ms_amount, 0)))
    timing_btn_layout.addWidget(
        make_button("Start -50ms", lambda: constants.timed_call(button_actions.adjust_sound_tag, editor, ms_amount, 0),
                    danger=True))
    timing_btn_layout.addWidget(
        make_button("End -50ms", lambda: constants.timed_call(button_actions.adjust_sound_tag, editor, 0, -ms_amount),
                    danger=True))
    timing_btn_layout.addWidget(
        make_button("End +50ms", lambda: constants.timed_call(button_actions.adjust_sound_tag, editor, 0, ms_amount)))
    buttons_layout.addWidget(timing_btn_row)

    add_remove_row = QWidget()
    add_remove_layout = QHBoxLayout(add_remove_row)
    add_remove_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    add_remove_layout.setSpacing(BUTTON_ROW_SPACING)
    add_remove_layout.addWidget(make_button("Add Previous Line",
                                            lambda: constants.timed_call(button_actions.add_and_remove_edge_lines_update_note,
                                                               editor, 1, 0)))
    add_remove_layout.addWidget(make_button("Remove First Line",
                                            lambda: constants.timed_call(button_actions.add_and_remove_edge_lines_update_note,
                                                               editor, -1, 0), danger=True))
    add_remove_layout.addWidget(make_button("Remove Last Line",
                                            lambda: constants.timed_call(button_actions.add_and_remove_edge_lines_update_note,
                                                               editor, 0, -1), danger=True))
    add_remove_layout.addWidget(make_button("Add Next Line",
                                            lambda: constants.timed_call(button_actions.add_and_remove_edge_lines_update_note,
                                                               editor, 0, 1)))
    buttons_layout.addWidget(add_remove_row)

    generate_btn_row = QWidget()
    generate_btn_layout = QHBoxLayout(generate_btn_row)
    generate_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    generate_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    generate_btn_layout.addWidget(
        make_button("Generate Fields", lambda: constants.timed_call(button_actions.generate_fields_button, editor)))
    generate_btn_layout.addWidget(
        make_button("Next Result", lambda: constants.timed_call(button_actions.next_result_button, editor)))


    buttons_layout.addWidget(generate_btn_row)

    main_layout.insertWidget(0, buttons_container)
    editor._custom_controls_container_buttons = buttons_container

    # === SPINBOXES + CHECKBOXES ===
    spinboxes_container = QWidget()
    spinboxes_layout = QVBoxLayout(spinboxes_container)
    spinboxes_layout.setContentsMargins(*CONTAINER_MARGINS)
    spinboxes_layout.setSpacing(CONTAINER_SPACING)

    # Row 4: Checkboxes row (autoplay + track menu)
    checkboxes_row = QWidget()
    checkboxes_layout = QHBoxLayout(checkboxes_row)
    checkboxes_layout.setContentsMargins(*ROW_MARGINS)
    checkboxes_layout.setSpacing(ROW_SPACING)

    config = constants.extract_config_data()
    autoplay_checkbox = QCheckBox("Autoplay")
    autoplay_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
    autoplay_checkbox.setChecked(config["autoplay"])
    set_auto_play_audio(editor, config.get("autoplay", False))
    autoplay_checkbox.clicked.connect(lambda _: handle_autoplay_toggle_and_save(editor))
    checkboxes_layout.addWidget(autoplay_checkbox)

    # Push everything to the left before adding the button on the right
    checkboxes_layout.addStretch()

    # Add "Main Menu" button
    settings_menu_button = QPushButton("Settings")
    settings_menu_button.clicked.connect(lambda: open_audio_tools_dialog(True))
    checkboxes_layout.addWidget(settings_menu_button)

    # Add the row to the layout
    spinboxes_layout.addWidget(checkboxes_row)
    main_layout.addWidget(spinboxes_container)
    editor._custom_controls_container_spinboxes = spinboxes_container
gui_hooks.editor_did_init.append(add_custom_controls)

def on_profile_loaded():
    def wrapped(editor):
        button_actions.on_note_loaded(editor, override=False)
    gui_hooks.editor_did_load_note.append(wrapped)

def save_config(cfg: dict) -> None:
    path = os.path.join(constants.addon_dir, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def handle_autoplay_toggle_and_save(editor: Editor):
    # flip editor state
    new_state = not getattr(editor, "_auto_play_enabled", False)
    set_auto_play_audio(editor, new_state)

    # persist
    cfg = constants.extract_config_data()
    cfg["autoplay"] = new_state
    save_config(cfg)
