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
import os, json
from aqt.gui_hooks import editor_did_load_note, editor_did_focus_field


from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSpinBox, QCheckBox
)
try:
    from . import manage_files
    from . import button_actions
    from . import language_codes
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import manage_files
    import button_actions
    import language_codes

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

    def getMappedFields(self, model_name):
        return self.data.get("mapped_fields", {}).get(model_name, {})

    def updateMapping(self, model_name, mapping):
        self.data.setdefault("mapped_fields", {})[model_name] = mapping
        self.save()



class AudioToolsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.addon_id = "Audio-Card-Suite"
        config_file_path = os.path.join(addon_dir, "config.json")
        self.configManager = ConfigManager(config_file_path)
        print("loading settings")
        self.settings = self.configManager.load()
        self.load_settings()
        self.initUI()
        self.apply_settings_to_ui()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setMinimumSize(546, 746)

    def load_settings(self):
        self.settings = self.configManager.load()
        print("Loaded settings from config:")
        print(json.dumps(self.settings, indent=2))
        config_file_path = os.path.join(addon_dir, "config.json")

        default_settings = {
            "default_model": "Basic",
            "default_deck": "Default",
            "audio_ext": "mp3",
            "bitrate": 192,
            "image_height": 1080,
            "pad_start": 0,
            "pad_end": 0,
            "target_language": "",
            "translation_language": "",
            "target_language_code": "",
            "translation_language_code": "",
            "normalize_audio": False,
            "lufs": -16,
            "target_audio_track": 1,
            "target_subtitle_track": 1,
            "translation_audio_track": 2,
            "translation_subtitle_track": 2,
            "target_timing_code": "",
            "translation_timing_code": "",
            "target_timing_track": 0,
            "translation_timing_track": 0,
            "timing_tracks_enabled": False
        }

        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Invalid config.json, resetting to defaults. Error: {e}")
                config = default_settings.copy()
                with open(config_file_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
        else:
            print("No config.json found, creating default config.")
            config = default_settings.copy()
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

        self.settings = default_settings.copy()
        self.settings.update(config)
        print(f"normalize_audio in settings: " + str(config["normalize_audio"]))

    def save_settings(self):
        print("save_settings called")
        self.settings["image_height"] = self.imageHeightEdit.value()
        self.settings["pad_start"] = self.padStartEdit.value()
        self.settings["pad_end"] = self.padEndEdit.value()
        self.settings["audio_ext"] = self.audioExtCombo.currentText()
        self.settings["bitrate"] = self.bitrateEdit.value()
        self.settings["normalize_audio"] = self.normalize_checkbox.isChecked()
        self.settings["lufs"] = self.lufsSpinner.value()

        for i, key in enumerate([
            "target_audio_track",
            "target_subtitle_track",
            "translation_audio_track",
            "translation_subtitle_track",
            "target_timing_track",
            "translation_timing_track"
        ]):
            self.settings[key] = self.trackSpinners[i].value()

        self.settings["timing_tracks_enabled"] = self.timingTracksCheckbox.isChecked()

        # Save all 4 language code edits
        for i, key in enumerate(["target_language_code", "translation_language_code", "target_timing_code",
                                 "translation_timing_code"]):
            code = self.settings.get(key, "")
            language_name = language_codes.PyLangISO639_2.code_to_name(code)
            if language_name:
                self.langCodeCombos[i].setCurrentText(language_name)
            else:
                self.langCodeCombos[i].setCurrentText("None")

        config_path = os.path.join(addon_dir, "config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            print("Settings saved successfully.")
        except Exception as e:
            print(f"Error saving settings: {e}")

    def show_fields_menu(self):
        current_model_name = self.modelButton.text()
        model = mw.col.models.by_name(current_model_name)
        if not model:
            showInfo(f"Note type '{current_model_name}' not found.")
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

        if idx == 0:
            self.settings["target_language"] = language
            self.settings["target_language_code"] = code
        elif idx == 1:
            self.settings["translation_language"] = language
            self.settings["translation_language_code"] = code
        elif idx == 2:
            self.settings["target_timing_language"] = language
            self.settings["target_timing_code"] = code
        elif idx == 3:
            self.settings["translation_timing_language"] = language
            self.settings["translation_timing_code"] = code

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
            config = manage_files.extract_config_data()

            deck_id = mw.col.decks.get_current_id()
            deck = mw.col.decks.get(deck_id)
            all_note_types = mw.col.models.all()
            note_type = all_note_types[0]['name'] if all_note_types else ""

            dialog = QDialog(mw)
            dialog.setWindowTitle("Bulk Generate")

            layout = QVBoxLayout(dialog)

            message = QLabel(
                f"All cards of note type '{note_type}' in the deck '{deck['name']}' will have fields generated."
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
        # self.deckButton = QPushButton(self.settings["default_deck"])
        # self.deckButton.clicked.connect(lambda: None)

        self.modelFieldsButton = QPushButton()
        self.modelFieldsButton.setText("⚙️")
        self.modelFieldsButton.setFixedWidth(32)
        self.modelFieldsButton.clicked.connect(lambda: self.mapFields(self.modelButton.text()))


        grid = QGridLayout()
        grid.addWidget(QLabel("Note Type:"), 0, 0)
        grid.addWidget(self.modelButton, 0, 1)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self.modelFieldsButton, 0, 2)
        # grid.addWidget(QLabel("Deck:"), 0, 3)
        # grid.addWidget(self.deckButton, 0, 4)
        # grid.setColumnStretch(4, 1)

        importGroup.setLayout(grid)
        vbox.addWidget(importGroup)

        # Editable input groups: Image, Pad Timings, Audio (new)
        hbox = QHBoxLayout()

        imageGroup = QGroupBox("Image")
        imageLayout = QGridLayout()
        imageLayout.addWidget(QLabel("Height:"), 0, 0)
        self.imageHeightEdit = QSpinBox()
        self.imageHeightEdit.setRange(1, 9999)
        self.imageHeightEdit.setValue(self.settings["image_height"])
        self.imageHeightEdit.setSuffix(" px")
        imageLayout.addWidget(self.imageHeightEdit, 0, 1)
        imageGroup.setLayout(imageLayout)
        hbox.addWidget(imageGroup)

        # Pad Timings group (Start and End)
        padGroup = QGroupBox("Pad Timings")
        padLayout = QGridLayout()
        padLayout.addWidget(QLabel("Start:"), 0, 0)
        padLayout.addWidget(QLabel("End:"), 1, 0)

        self.padStartEdit = QSpinBox()
        self.padStartEdit.setRange(-10000000, 10000000)  # Adjust max as needed
        self.padStartEdit.setValue(self.settings["pad_start"])
        self.padStartEdit.setSuffix(" ms")

        self.padEndEdit = QSpinBox()
        self.padEndEdit.setRange(-10000000, 10000000)  # Adjust max as needed
        self.padEndEdit.setValue(self.settings["pad_end"])
        self.padEndEdit.setSuffix(" ms")

        padLayout.addWidget(self.padStartEdit, 0, 1)
        padLayout.addWidget(self.padEndEdit, 1, 1)
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
        self.lufsSpinner.setValue(-16)
        self.lufsSpinner.setSuffix(" LUFS")
        self.lufsSpinner.setToolTip("Target loudness level")
        self.lufsSpinner.setValue(self.settings.get("lufs", -16))
        self.normalize_checkbox = QCheckBox("Normalize Audio")
        self.normalize_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
        self.normalize_checkbox.setChecked(self.settings.get("normalize_audio"))

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
        info_label = QLabel("The currently selected tab will have its settings preferred. Tracks will be used if the Language Code cannot be found.")
        info_label.setWordWrap(True)
        subsLayout.addWidget(info_label)
        self.timingTracksCheckbox = QCheckBox("Timing Tracks")
        self.timingTracksCheckbox.setChecked(self.settings.get("timing_tracks_enabled", False))
        self.timingTracksCheckbox.stateChanged.connect(self.on_timing_checkbox_changed)
        self.timingTracksCheckbox.setTristate(False)
        subsLayout.addWidget(self.timingTracksCheckbox)
        self.tabs = QTabWidget()

        langCodesTab = QWidget()
        langGrid = QGridLayout()
        self.langCodeCombos = []
        self.langCodeEdits = []
        self.langCodeLabels = []

        labels = [
            "Target Language Code:",
            "Translation Language Code:",
            "Target Timing Code:",
            "Translation Timing Code:"
        ]

        combo_keys = [
            "target_language",
            "translation_language",
            "target_timing_code",
            "translation_timing_code"
        ]

        edit_keys = [
            "target_language_code",
            "translation_language_code",
            "target_timing_code",
            "translation_timing_code"
        ]

        hide_rows_start = 2

        for i, label_text in enumerate(labels):
            label = QLabel(label_text)
            self.langCodeLabels.append(label)
            langGrid.addWidget(label, i + 1, 0)

            combo = QComboBox()
            combo.addItems([
                "None", "Japanese", "Chinese", "English", "Korean", "Cantonese", "German", "Spanish"
            ])
            saved_combo_value = self.settings.get(combo_keys[i], "None")
            combo.setCurrentText(saved_combo_value)
            self.langCodeCombos.append(combo)
            langGrid.addWidget(combo, i + 1, 1)

            edit = QLineEdit()
            edit.setFixedWidth(30)
            edit.setStyleSheet("QLineEdit{background: #f4f3f4;}")
            edit.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            saved_edit_value = self.settings.get(edit_keys[i], "")
            edit.setText(saved_edit_value)
            self.langCodeEdits.append(edit)
            langGrid.addWidget(edit, i + 1, 2)

            combo.currentTextChanged.connect(lambda text, idx=i: self.on_lang_code_changed(idx, str(text)))

        for i in range(hide_rows_start, len(labels)):
            self.langCodeCombos[i].hide()
            self.langCodeEdits[i].hide()
            self.langCodeLabels[i].hide()

        langCodesTab.setLayout(langGrid)
        self.tabs.addTab(langCodesTab, "Language Codes")

        # Tracks Tab
        tracksTab = QWidget()
        tracksGrid = QGridLayout()

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

        for i, (label_text, key) in enumerate(zip(track_labels, track_keys)):
            label = QLabel(label_text + ":")
            spinner = QSpinBox()
            spinner.setMinimum(0)
            spinner.setMaximum(1000)
            spinner.setValue(self.settings.get(key, 0))

            tracksGrid.addWidget(label, i, 0)
            tracksGrid.addWidget(spinner, i, 1)

            self.trackLabels.append(label)
            self.trackSpinners.append(spinner)

        tracksTab.setLayout(tracksGrid)
        self.tabs.addTab(tracksTab, "Tracks")
        self.trackSpinners[0].setValue(self.settings.get("target_audio_track", 0))
        self.trackSpinners[1].setValue(self.settings.get("target_subtitle_track", 0))
        self.trackSpinners[2].setValue(self.settings.get("translation_audio_track", 0))
        self.trackSpinners[3].setValue(self.settings.get("translation_subtitle_track", 0))
        self.trackSpinners[4].setValue(self.settings.get("target_timing_track", 0))
        self.trackSpinners[5].setValue(self.settings.get("translation_timing_track", 0))
        subsLayout.addWidget(self.tabs)
        subsGroup.setLayout(subsLayout)
        codes_label = QLabel()
        codes_label.setText(
            'If your language is not listed, enter its <a href="https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes">ISO 639-2 language code</a> in the text box.'
        )
        codes_label.setOpenExternalLinks(True)
        codes_label.setWordWrap(True)
        subsLayout.addWidget(codes_label)
        vbox.addWidget(subsGroup)

        # source folder
        addon_source_folder = os.path.join(addon_dir, "Sources")
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
        convertBtn.clicked.connect(confirm_conversion)
        sourceLayout.addWidget(convertBtn)

        # Add source group below subtitles group
        vbox.addWidget(sourceGroup)
        hbox2 = QHBoxLayout()

        self.bulkGenerateButton = QPushButton("Bulk Generate")
        self.bulkGenerateButton.setDefault(True)
        self.bulkGenerateButton.clicked.connect(confirm_bulk_generate)
        hbox2.addWidget(self.bulkGenerateButton)
        hbox2.addStretch(4)

        # open file button
        # self.openFileButton = QPushButton("Open File")
        # self.openFileButton.setDefault(True)
        # self.openFileButton.clicked.connect(lambda: None)
        # hbox2.addWidget(self.openFileButton)

        vbox.addLayout(hbox2)
        self.setLayout(vbox)
        self.setWindowIcon(QIcon(":/icons/anki.png"))
        self.on_audio_ext_changed(self.audioExtCombo.currentText())


        # save settings anytime a change is made
        self.imageHeightEdit.valueChanged.connect(self.save_settings)
        self.bitrateEdit.valueChanged.connect(self.save_settings)
        self.lufsSpinner.valueChanged.connect(self.save_settings)
        for spinner in self.trackSpinners:
            spinner.valueChanged.connect(self.save_settings)
        self.imageHeightEdit.valueChanged.connect(self.save_settings)
        self.padStartEdit.valueChanged.connect(self.save_settings)
        self.padEndEdit.valueChanged.connect(self.save_settings)
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



    def mapFields(self, model_name):
        fm = FieldMapping(model_name, self.configManager, parent=self)
        fm.exec()

    def on_tab_changed(self, index):
        self.settings["selected_tab_index"] = index
        print(f"saving settings, tab change")
        self.save_settings()

    def apply_settings_to_ui(self):
        # Block signals on widgets that trigger save_settings
        widgets = [
            self.imageHeightEdit,
            self.padStartEdit,
            self.padEndEdit,
            self.audioExtCombo,
            self.bitrateEdit,
            self.normalize_checkbox,
            self.lufsSpinner,
            *self.trackSpinners,
            *self.langCodeEdits,
            self.timingTracksCheckbox,
        ]
        for w in widgets:
            w.blockSignals(True)

        self.imageHeightEdit.setValue(self.settings["image_height"])
        self.padStartEdit.setValue(self.settings["pad_start"])
        self.padEndEdit.setValue(self.settings["pad_end"])

        idx = self.audioExtCombo.findText(self.settings["audio_ext"])
        if idx >= 0:
            self.audioExtCombo.setCurrentIndex(idx)

        self.bitrateEdit.setValue(self.settings["bitrate"])
        self.normalize_checkbox.setChecked(self.settings["normalize_audio"])
        self.lufsSpinner.setValue(self.settings.get("lufs", -16))

        tracks = [
            "target_audio_track",
            "target_subtitle_track",
            "translation_audio_track",
            "translation_subtitle_track",
            "target_timing_track",
            "translation_timing_track"
        ]
        for i, track in enumerate(tracks):
            self.trackSpinners[i].setValue(self.settings.get(track, 0))

        self.timingTracksCheckbox.setChecked(self.settings.get("timing_tracks_enabled", False))

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
        self.name = name
        self.initUI()

    def initUI(self):
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
            comboBox.addItem("None")
            comboBox.addItem("Target Subtitle Line")
            comboBox.addItem("Target Audio")
            comboBox.addItem("Translation Subtitle Line")
            comboBox.addItem("Translation Audio")
            comboBox.addItem("Image")
            if field in self.mappedFields:
                comboBox.setCurrentIndex(comboBox.findText(self.mappedFields[field]))
            else:
                comboBox.setCurrentIndex(0)
            grid.addWidget(comboBox, index, 1)

            self.fields.append((field, comboBox))

        groupBox.setLayout(grid)
        vbox.addWidget(groupBox)

        infoLabel = QLabel("Field mappings each for note type will be saved.")
        infoLabel.setWordWrap(True)
        vbox.addWidget(infoLabel)

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
    add_remove_layout.addWidget(make_button("Add Previous Line", lambda: button_actions.add_and_remove_edge_lines_update_note(editor, 1, 0)))
    add_remove_layout.addWidget(make_button("Remove First Line", lambda: button_actions.add_and_remove_edge_lines_update_note(editor, -1, 0), danger=True))
    add_remove_layout.addWidget(make_button("Remove Last Line", lambda: button_actions.add_and_remove_edge_lines_update_note(editor, 0, -1), danger=True))
    add_remove_layout.addWidget(make_button("Add Next Line", lambda: button_actions.add_and_remove_edge_lines_update_note(editor, 0, 1)))
    buttons_layout.addWidget(add_remove_row)

    generate_btn_row = QWidget()
    generate_btn_layout = QHBoxLayout(generate_btn_row)
    generate_btn_layout.setContentsMargins(*BUTTON_ROW_MARGINS)
    generate_btn_layout.setSpacing(BUTTON_ROW_SPACING)
    generate_btn_layout.addWidget(make_button("Generate Fields", lambda: button_actions.generate_fields_button(editor)))
    generate_btn_layout.addWidget(make_button("Next Result", lambda: button_actions.next_result_button(editor)))

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

    # Row 4: Checkboxes row (autoplay + track menu)
    checkboxes_row = QWidget()
    checkboxes_layout = QHBoxLayout(checkboxes_row)
    checkboxes_layout.setContentsMargins(*ROW_MARGINS)
    checkboxes_layout.setSpacing(ROW_SPACING)

    autoplay_checkbox = QCheckBox("Autoplay")
    autoplay_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
    autoplay_checkbox.setChecked(getattr(editor, "_auto_play_enabled", False))
    autoplay_checkbox.clicked.connect(lambda _: handle_autoplay_checkbox_toggle(_, editor))
    checkboxes_layout.addWidget(autoplay_checkbox)

    show_track_menu_checkbox = QCheckBox("Track Menu")
    show_track_menu_checkbox.setMinimumWidth(CHECKBOX_MIN_WIDTH)
    checkboxes_layout.addWidget(show_track_menu_checkbox)

    def toggle_track_visibility(state):
        visible = state == 2
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
