from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication
import difflib
import os
import re
import html
from aqt import mw
import aqt
from aqt.sound import play, av_player
from aqt import gui_hooks
from anki.notes import Note
import manage_database


import manage_files
from manage_files import get_field_key_from_label
import constants
from constants import (
    log_filename,
    log_error,
    log_image,
    log_command, addon_source_folder,
)

# constants
ms_amount = constants.ms_amount
addon_dir = constants.addon_dir
config_dir = constants.config_dir

target_subtitle_line_string = constants.target_subtitle_line_string
target_audio_string = constants.target_audio_string
translation_subtitle_line_string = constants.translation_subtitle_line_string
translation_audio_string = constants.translation_audio_string
image_string = constants.image_string



# manipulate and update fields

# finds the location of the current sentence field, then uses the selected text to find the next line that
# contains the selection and re-generates every field
def next_result_button(editor):
    config = constants.extract_config_data()
    fields = get_fields_from_editor(editor)
    sentence_idx = fields["sentence_idx"]
    sound_idx = fields["sound_idx"]
    image_idx = fields["image_idx"]
    translation_idx = fields["translation_idx"]
    translation_sound_idx = fields["translation_sound_idx"]
    sentence_line = fields["sentence_line"]
    sound_line = fields["sound_line"]
    selected_text = fields["selected_text"]

    if not sentence_line and not selected_text:
        log_error(f"no text to search")
        return

    log_filename(f"calling extract sound line data: {sound_line}")
    data = manage_files.extract_sound_line_data(sound_line)

    # gets next matching subtitle block using selected text and current fields
    block, subtitle_path = manage_files.get_next_matching_subtitle_block(sentence_line, selected_text, sound_line, config, data)

    if not block or not subtitle_path:
        log_error(f"didn't find another result")
        return

    # generate new sound and sentence line using the block just retrieved
    next_sound_line, next_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block, subtitle_path, config)

    # generate sound file using next sound line
    log_filename(f"calling extract sound line data: {next_sound_line}")
    new_data = manage_files.extract_sound_line_data(next_sound_line)
    altered_data = manage_files.get_altered_sound_data(next_sound_line, 0, 0, config, new_data)
    next_sound_line = manage_files.alter_sound_file_times(altered_data, next_sound_line, config, False)


    if next_sound_line:
        # add tag and remove any previous tags
        filename_base = re.sub(r'^\[sound:|]$', '', next_sound_line.split("`", 1)[0].strip())
        prev_filename_base = re.sub(r'^\[sound:|]$', '', sound_line.split("`", 1)[0].strip())

        filename_base_underscore = filename_base.replace(" ", "_")
        prev_base_underscore = prev_filename_base.replace(" ", "_")

        if filename_base_underscore != prev_base_underscore:
            editor.note.remove_tag(prev_base_underscore)

        if filename_base_underscore not in editor.note.tags:
            editor.note.add_tag(filename_base_underscore)

    # set new values empty other fields to let generate_fields generate the rest
    editor.note.fields[sentence_idx] = next_sentence_line
    editor.note.fields[sound_idx] = next_sound_line
    editor.note.fields[image_idx] = ""
    editor.note.fields[translation_idx] = ""
    editor.note.fields[translation_sound_idx] = ""
    editor.loadNote()
    generate_fields_button(editor)

def add_and_remove_edge_lines_update_note(editor, add_to_start, add_to_end):
    fields = get_fields_from_editor(editor)
    config = constants.extract_config_data()
    modifiers = QApplication.keyboardModifiers()
    alt_pressed = modifiers & Qt.KeyboardModifier.AltModifier

    if alt_pressed:
        sound_line = fields["translation_sound_line"]
    else:
        sound_line = fields["sound_line"]

    data = manage_files.extract_sound_line_data(sound_line)

    if not data:
        log_error(f"no data from sound line: {sound_line}, generating fields")
        generate_and_update_fields(editor, None, True)

        if alt_pressed:
            sound_line = fields["translation_sound_line"]
        else:
            sound_line = fields["sound_line"]

        data = manage_files.extract_sound_line_data(sound_line)

    if not data:
        log_error(f"still no data from sound line: {sound_line}, returning")
        return

    if alt_pressed:
        sound_line = fields["translation_sound_line"]
        sound_idx = fields["translation_sound_idx"]
        sentence_line = fields["translation_line"]
        sentence_idx = fields["translation_idx"]
        translation_idx = ""
        track = config.get("translation_subtitle_track")
        code = config.get("translation_language_code")
    else:
        sound_line = fields["sound_line"]
        sound_idx = fields["sound_idx"]
        sentence_line = fields["sentence_line"]
        sentence_idx = fields["sentence_idx"]
        translation_idx = fields["translation_idx"]
        track = config.get("target_subtitle_track")
        code = config.get("target_language_code")


    start_index = data["start_index"]
    end_index = data["end_index"]
    full_source_filename = data["full_source_filename"]
    subtitle_database = manage_database.get_database()
    subtitle_path = manage_files.get_subtitle_file_from_database(full_source_filename, track, code, config, subtitle_database)


    blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index - add_to_start, end_index + add_to_end, subtitle_path)
    new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(blocks, subtitle_path, config)

    if not new_sound_line or not new_sentence_line:
        log_error("No new sound line or sentence text returned.")
        block, subtitle_path = manage_files.get_target_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line, config)
        new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block, subtitle_path, config)
        if not new_sound_line:
            log_error(f"nothing found from sentence line {sentence_line}, returning")
            return

    log_filename(f"getting sound line data from5: {new_sound_line}")
    new_data = manage_files.extract_sound_line_data(new_sound_line)
    altered_data = manage_files.get_altered_sound_data(new_sound_line, 0, 0, config, new_data)
    manage_files.alter_sound_file_times(altered_data, new_sound_line, config, alt_pressed)

    # generate new translation line
    if not alt_pressed:
        translation_line, _ = manage_files.get_translation_line_and_subtitle_from_target_sound_line(new_sound_line, config, new_data)
        editor.note.fields[translation_idx] = translation_line

    new_field = re.sub(r"\[sound:.*?]", new_sound_line, sound_line)
    editor.note.fields[sound_idx] = new_field
    editor.note.fields[sentence_idx] = new_sentence_line
    generate_and_update_fields(editor, None, False)

    def play_after_reload():
        sound_filename = re.search(r"\[sound:(.*?)]", new_sound_line)
        if sound_filename:
            QTimer.singleShot(100, lambda: play(sound_filename.group(1)))

    editor.loadNote()
    QTimer.singleShot(50, play_after_reload)

def new_sound_sentence_line_from_sound_line_path_and_relative_index(sound_line, subtitle_path, relative_start, relative_end):
    config = constants.extract_config_data()
    log_filename(f"calling extract sound line data: {sound_line}")
    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        return "", ""

    start_index = data["start_index"]
    end_index = data["end_index"]

    blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index - relative_start, end_index + relative_end, subtitle_path)
    log_filename(f"blocks: {blocks}")
    new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(blocks, subtitle_path, config)
    return new_sound_line, new_sentence_line

def  adjust_sound_tag(editor, start_delta: int, end_delta: int):
    # check for modifier keys
    config = constants.extract_config_data()
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        start_delta //= 2
        end_delta //= 2
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        start_delta *= 10
        end_delta *= 10

    fields = get_fields_from_editor(editor)
    alt_pressed = modifiers & Qt.KeyboardModifier.AltModifier
    if alt_pressed:
        sound_line = fields["translation_sound_line"]
        sound_idx = fields["translation_sound_idx"]
        sentence_line = fields["translation_line"]
    else:
        sound_line = fields["sound_line"]
        sound_idx = fields["sound_idx"]
        sentence_line = fields["sentence_line"]


    log_filename(f"calling extract sound line data: {sound_line}")
    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        log_error(f"no valid sound line detected")
        generate_and_update_fields(editor, None, True)
        return

    log_filename(f"getting altered data from1: {sound_line}")
    altered_data = manage_files.get_altered_sound_data(sound_line, -start_delta, end_delta, config, data)
    log_filename(f"sending data to alter sound file times: {altered_data}")
    new_sound_line = manage_files.alter_sound_file_times(altered_data, sound_line, config, alt_pressed)

    # generate a new sound line if first try failed
    if not new_sound_line:
        log_error("No new sound tag returned, checking database.")
        block, subtitle_path = manage_files.get_target_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line, config)
        new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block, subtitle_path, config)
        if not new_sound_line:
            log_error(f"nothing found from sentence line {sentence_line}, returning")

    editor.note.fields[sound_idx] = new_sound_line
    editor.loadNote()

    if new_sound_line.startswith("[sound:") and new_sound_line.endswith("]"):
        filename = new_sound_line[len("[sound:"):-1]
        media_path = os.path.join(mw.col.media.dir(), filename)

        def wait_and_play():
            if os.path.exists(media_path) and os.path.getsize(media_path) > 0:
                log_command(f"Playing sound from field {sound_idx}: {filename}")
                play(filename)
            else:
                log_error("File not ready, retrying...")
                QTimer.singleShot(50, wait_and_play)

        QTimer.singleShot(50, wait_and_play)

def context_aware_sentence_sound_line_generate(sentence_line, new_sentence_line, sound_line, subtitle_path):
    if sentence_line == new_sentence_line:
        log_error(f"sentence line and new sentence line are the same: {sentence_line}")
        return sound_line, sentence_line

    if (not sentence_line) or (not new_sentence_line):
        log_error(f"sentence line or new sentence line are null: {sentence_line}|{new_sentence_line}")
        return None, None

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

    new_sound_line = sound_line
    while before_removed or after_removed:
        if not subtitle_path:
            break

        log_filename(f"calling extract sound line data: {new_sound_line}")
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
            before_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index - 1, start_index - 1, subtitle_path)
            before_block = before_blocks[0] if before_blocks else None
            before_line = before_block[3]
            before_line_clean = before_line.replace('\n', '').strip()

            # check if previous line is in leftover line, or if leftover line is in previous line, and add previous line if it is
            if before_line_clean in before_removed:
                before_removed = before_removed.replace(before_line_clean, "").strip()
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 1, 0)
            elif before_line in before_removed:
                before_removed = before_removed.replace(before_line, "").strip()
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 1, 0)
            elif before_removed in before_line:
                before_removed = ""
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 1, 0)
            elif before_removed in before_line_clean:
                before_removed = ""
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 1, 0)
            else:
                before_removed = ""

        log_filename(f"calling extract sound line data: {new_sound_line}")
        data = manage_files.extract_sound_line_data(new_sound_line)
        if not data:
            break
        end_index = data.get("end_index")

        if after_removed:
            after_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(end_index + 1, end_index + 1, subtitle_path)
            after_block = after_blocks[0] if after_blocks else None
            after_line = after_block[3]
            after_line_clean = after_line.replace('\n', '').strip()

            if after_line_clean in after_removed:
                after_removed = after_removed.replace(after_line_clean, "").strip()
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 0, 1)
            elif after_line in after_removed:
                after_removed = after_removed.replace(after_line, "").strip()
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 0, 1)
            elif after_removed in after_line:
                after_removed = ""
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 0, 1)
            elif after_removed in after_line_clean:
                after_removed = ""
                new_sound_line, new_sentence_line = new_sound_sentence_line_from_sound_line_path_and_relative_index(new_sound_line, subtitle_path, 0, 1)
            else:
                after_removed = ""

    return new_sound_line, new_sentence_line

def generate_and_update_fields(editor, note, should_overwrite):
    config = constants.extract_config_data()
    if note:
        mapped_fields = config["mapped_fields"]
        note_type_name = list(mapped_fields.keys())[0]
        fields = note.note_type()["flds"]
        sentence_idx = get_idx(f"{target_subtitle_line_string}", note_type_name, config, fields)
        sound_idx = get_idx(f"{target_audio_string}", note_type_name, config, fields)
        image_idx = get_idx(f"{image_string}", note_type_name, config, fields)
        translation_idx = get_idx(f"{translation_subtitle_line_string}", note_type_name, config, fields)
        translation_sound_idx = get_idx(f"{translation_audio_string}", note_type_name, config, fields)
        sentence_line = note.fields[sentence_idx] if 0 <= sentence_idx < len(note.fields) else ""
        sound_line = note.fields[sound_idx] if 0 <= sound_idx < len(note.fields) else ""
        image_line = note.fields[image_idx] if 0 <= image_idx < len(note.fields) else ""
        translation_line = note.fields[translation_idx] if 0 <= translation_idx < len(note.fields) else ""
        translation_sound_line = note.fields[translation_sound_idx] if 0 <= translation_sound_idx < len(note.fields) else ""
        selected_text = ""
        field_obj = note
    else:
        fields = get_fields_from_editor(editor)
        if not fields:
            log_error(f"fields is null, fields are not set in menu")
            return
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
        field_obj = editor.note

    modifiers = QApplication.keyboardModifiers()
    overwrite = bool(modifiers & Qt.KeyboardModifier.ControlModifier) or should_overwrite
    alt_pressed = bool(modifiers & Qt.KeyboardModifier.AltModifier)

    fields_status = {
        "sound_line": bool(sound_line),
        "sentence_line": bool(sentence_line),
        "image_line": bool(image_line),
        "translation_line": bool(translation_line),
        "translation_sound_line": bool(translation_sound_line)
    }

    if all(fields_status.values()) and not overwrite:
        log_filename("All fields are filled, returning.")
        if alt_pressed:
            current_sound_line = field_obj.fields[translation_sound_idx]
            match = re.search(r"\[sound:(.*?)]", current_sound_line)
            return match.group(1) if match else None
        else:
            current_sound_line = field_obj.fields[sound_idx]
            match = re.search(r"\[sound:(.*?)]", current_sound_line)
            return match.group(1) if match else None
    else:
        for name, is_present in fields_status.items():
            if not is_present:
                log_filename(f"Missing: {name}")



    updated = False


    # generate fields using sentence line
    new_result = get_generate_fields_sound_sentence_image_translation(
        sound_line, sentence_line, selected_text, image_line, translation_line, translation_sound_line, overwrite, alt_pressed
    )

    log_filename(f"new result: {new_result}")

    if not new_result:
        log_error("generate_fields_sound_sentence_image failed to return valid values.")
        if new_result:
            for i, val in enumerate(new_result):
                log_error(f"  Field {i}: {val!r}")
        else:
            log_error("  new_result is None or empty.")
        return None

    new_sound_line, new_sentence_line, new_image_line, new_translation_line, new_translation_sound_line = new_result

    def update_field(idx, new_val):

        nonlocal updated
        current_field = field_obj.fields[idx]
        if new_val and current_field != new_val:
            field_obj.fields[idx] = new_val
            updated = True

    note_type_name = list(config["mapped_fields"].keys())[0]

    should_generate_sentence_line = get_field_key_from_label(note_type_name, target_subtitle_line_string, config)
    should_generate_translation_line = get_field_key_from_label(note_type_name, translation_subtitle_line_string, config)
    should_generate_sound_line = get_field_key_from_label(note_type_name, target_audio_string, config)
    should_generate_translation_sound_line = get_field_key_from_label(note_type_name, translation_audio_string, config)
    should_generate_image_line = get_field_key_from_label(note_type_name, image_string, config)

    # update sentence line
    if should_generate_sentence_line and ((not sentence_line) or overwrite):
        update_field(sentence_idx, new_sentence_line)

    # update translation line
    if should_generate_translation_line and ((not translation_line) or overwrite):
        update_field(translation_idx, new_translation_line)

    # update sound line
    log_filename(f"calling extract sound line data: {new_sound_line}")
    data = manage_files.extract_sound_line_data(new_sound_line)
    if should_generate_sound_line:
        log_filename(f"getting altered data from3: {new_sound_line}")
        altered_data = manage_files.get_altered_sound_data(new_sound_line, 0, 0, config, data)
        if new_sound_line != field_obj.fields[sound_idx] and altered_data:
            new_sound_line = manage_files.alter_sound_file_times(altered_data, new_sound_line, config, False)
            field_obj.fields[sound_idx] = new_sound_line
            updated = True

    # update translation sound line
    if should_generate_translation_sound_line and ((not translation_sound_line) or overwrite):
        log_filename(f"getting sound data from translation: {new_translation_sound_line}")
        data = manage_files.extract_sound_line_data(new_translation_sound_line)
        altered_data = manage_files.get_altered_sound_data(new_translation_sound_line, 0, 0, config, data)
        if new_translation_sound_line != field_obj.fields[translation_sound_idx] and altered_data:
            new_translation_sound_line = manage_files.alter_sound_file_times(altered_data, new_translation_sound_line, config, True)
            field_obj.fields[translation_sound_idx] = new_translation_sound_line
            updated = True

    # update image line
    if should_generate_image_line and ((not image_line) or overwrite):
        generated_img = manage_files.get_image_line_from_sound_line("", new_sound_line)
        log_image(f"new image: {generated_img}")
        if generated_img and isinstance(generated_img, str):
            field_obj.fields[image_idx] = generated_img
            updated = True
        else:
            log_image("Image generation failed or result was not a string.")
    else:
        update_field(image_idx, new_image_line)

    if updated:
        if note:
            mw.col.update_note(note)
        else:
            editor.loadNote()

    current_sound_line = field_obj.fields[sound_idx]
    match = re.search(r"\[sound:(.*?)]", current_sound_line)
    return match.group(1) if match else None

def get_generate_fields_sound_sentence_image_translation(sound_line, sentence_line, selected_text, image_line, translation_line, translation_sound_line, overwrite, alt_pressed):
    # checks each field, generating and updating if needed. Returns each field, empty if not needed
    if not sentence_line:
        log_error(f"sentence field empty")
        return None

    if overwrite:
        if not alt_pressed:
            sound_line = ""


    config = constants.extract_config_data()
    log_filename(f"calling extract sound line data: {sound_line}")
    data = manage_files.extract_sound_line_data(sound_line)
    subtitle_path = ""
    new_sound_line = ""
    new_sentence_line = ""

    track = config["target_subtitle_track"]
    code = config["target_language_code"]

    note_type_name = list(config["mapped_fields"].keys())[0]
    should_generate_image = get_field_key_from_label(note_type_name, "Image", config)
    should_generate_translation_line = get_field_key_from_label(note_type_name, f"{translation_subtitle_line_string}", config)
    should_generate_translation_sound = get_field_key_from_label(note_type_name, f"{translation_audio_string}", config)

    # get sound and sentence line
    if data:
        full_source_filename = data["full_source_filename"]
        subtitle_database = manage_database.get_database()
        subtitle_path = manage_files.get_subtitle_file_from_database(full_source_filename, track, code, config, subtitle_database)

        if not subtitle_path:
            log_error(f"subtitle path null1")
            aqt.utils.showInfo(f"Could not find `{sentence_line}` in any subtitle file with the code `{code}` or track `{track}` in {addon_source_folder}.")
            return None

        start_index = data["start_index"]
        end_index = data["end_index"]
        blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index, end_index, subtitle_path)
        if blocks:
            new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(blocks, subtitle_path, config)
        else:
            data = None

    # generate sound line if doesn't exist
    if not data:
        log_error(f"no data extracted from sound line: {sound_line}")
        block, subtitle_path = manage_files.get_target_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line, config)
        if not subtitle_path:
            log_error(f"subtitle path null2")
            aqt.utils.showInfo(f"Could not find `{sentence_line}` in any subtitle file with the code `{code}` or track `{track}`.")
            return None
        new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block, subtitle_path, config)
    if selected_text:
        new_sound_line, new_sentence_line = context_aware_sentence_sound_line_generate(sentence_line, selected_text, new_sound_line, subtitle_path)
    else:
        new_sound_line, new_sentence_line = context_aware_sentence_sound_line_generate(sentence_line, new_sentence_line, new_sound_line, subtitle_path)
    if new_sentence_line:
        new_sentence_line = constants.format_text(new_sentence_line)

    # get timing line from other sound line
    timing_tracks_enabled = config["timing_tracks_enabled"]
    if timing_tracks_enabled:
        subtitle_data = manage_files.extract_subtitle_path_data(subtitle_path)
        if not subtitle_data:
            log_error(f"subtitle_data null")
            return None
        subtitle_file_code = subtitle_data["code"]
        new_sound_line = manage_files.get_new_timing_sound_line_from_target_sound_line(new_sound_line, config, subtitle_file_code, False)
    else:
        new_sound_line = ""

    # get image line
    if should_generate_image and ((not image_line) or overwrite):
        log_image(f"image line empty, generating new one")
        new_image_line = manage_files.get_image_line_from_sound_line(image_line, new_sound_line)
        log_image(f"generated image line: {new_image_line}")
    else:
        new_image_line = ""

    # get translation line
    if not new_sound_line:
        log_error(f"Target Audio not detected, cannot generate Translation or Translation Audio.")
        aqt.utils.showInfo(f"Target Audio not detected, cannot generate Translation or Translation Audio.")

    if (should_generate_translation_line and ((not translation_line) or overwrite)) or should_generate_translation_sound:
        log_filename(f"calling extract sound line data: {new_sound_line}")
        new_data = manage_files.extract_sound_line_data(new_sound_line)
        new_translation_line, translation_subtitle_path = manage_files.get_translation_line_and_subtitle_from_target_sound_line(new_sound_line, config, new_data)
        if new_translation_line:
            new_translation_line = constants.format_text(new_translation_line)
    else:
        new_translation_line = ""

    # get translation sound line
    if should_generate_translation_sound and ((not translation_sound_line) or overwrite):
        subtitle_data = manage_files.extract_subtitle_path_data(translation_subtitle_path)
        if not subtitle_data:
            log_error(f"subtitle_data null")
            return None
        subtitle_file_code = subtitle_data["code"]
        new_translation_sound_line = manage_files.get_new_timing_sound_line_from_target_sound_line(new_sound_line, config, subtitle_file_code, True)
    else:
        new_translation_sound_line = ""


    log_filename(f"generated fields:\n"
                          f"new_sound_line: {new_sound_line}\n"
                          f"new_sentence_line: {new_sentence_line}\n"
                          f"new_image_line: {new_image_line}\n"
                          f"new_translation_line: {new_translation_line}\n"
                          f"new_translation_sound_line: {new_translation_sound_line}\n")

    return new_sound_line, new_sentence_line, new_image_line, new_translation_line, new_translation_sound_line


def show_info_msg(msg):
    import aqt
    aqt.utils.showInfo(msg)

# get and format data
def get_fields_from_editor(editor):
    config = constants.extract_config_data()
    if config is None:
        log_error("Config missing required fields, cannot proceed.")
        return {}

    mapped_fields = config.get("mapped_fields", {})
    if not mapped_fields:
        print("mapped_fields is empty or missing")
        aqt.utils.showInfo(f"No fields are mapped")
        return {}

    note_type = editor.note.note_type()
    note_type_name = list(mapped_fields.keys())[0]
    field_map = mapped_fields[note_type_name]

    required_labels = [
        target_subtitle_line_string,
        target_audio_string,
        image_string,
        translation_subtitle_line_string,
        translation_audio_string,
    ]


    lookup = {}
    missing = []
    for lbl in required_labels:
        # find the field whose mapped label equals lbl
        fld = next((f for f, lab in field_map.items() if lab == lbl), None)
        log_error(f"looking for '{lbl}' → field: {fld!r}")
        if fld:
            lookup[lbl] = fld
        else:
            missing.append(lbl)

    if missing:
        aqt.utils.showInfo(f"The following labels are not mapped for note type '{note_type_name}':\n" + "\n".join(missing))

        return {}


    fields = note_type["flds"]

    sentence_field = manage_files.get_field_key_from_label(note_type_name, f"{target_subtitle_line_string}", config)
    sentence_idx = index_of_field(sentence_field, fields) if sentence_field else -1
    if not sentence_field:
        log_error(f"Sentence field at index {sentence_idx} is empty.")
        return None

    sound_field = manage_files.get_field_key_from_label(note_type_name, f"{target_audio_string}", config)
    sound_idx = index_of_field(sound_field, fields) if sound_field else -1

    translation_field = manage_files.get_field_key_from_label(note_type_name, f"{translation_subtitle_line_string}", config)
    translation_idx = index_of_field(translation_field, fields) if translation_field else -1

    translation_sound_field = manage_files.get_field_key_from_label(note_type_name, f"{translation_audio_string}", config)
    translation_sound_idx = index_of_field(translation_sound_field, fields) if translation_sound_field else -1

    image_field = manage_files.get_field_key_from_label(note_type_name, f"{image_string}", config)
    image_idx = index_of_field(image_field, fields) if image_field else -1


    sound_line = editor.note.fields[sound_idx] if 0 <= sound_idx < len(editor.note.fields) else ""
    if "[sound:" not in sound_line:
        sound_line = ""

    image_line = editor.note.fields[image_idx] if 0 <= image_idx < len(editor.note.fields) else ""
    if "<img src=" not in image_line:
        log_image("no valid image detected")
        image_line = ""

    sentence_line = editor.note.fields[sentence_idx] if 0 <= sentence_idx < len(editor.note.fields) else ""
    translation_line = editor.note.fields[translation_idx] if 0 <= translation_idx < len(editor.note.fields) else ""
    translation_sound_line = editor.note.fields[translation_sound_idx] if 0 <= translation_sound_idx < len(editor.note.fields) else ""

    selected_text = editor.web.selectedText().strip()

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


def index_of_field(field_name, fields):
    for i, fld in enumerate(fields):
        if fld["name"] == field_name:
            return i
    return -1

def get_idx(label, note_type_name, config, fields):
    field_key = manage_files.get_field_key_from_label(note_type_name, label, config)
    return index_of_field(field_key, fields) if field_key else -1

def get_fields_from_note(note):
    config = constants.extract_config_data()
    mapped_fields = config.get("mapped_fields", {})

    note_type_name = note.model()["name"]
    if note_type_name not in mapped_fields:
        log_error(f"fields not mapped for note type '{note_type_name}'")
        return {}

    note_type = note.note_type()
    fields = note_type["flds"]

    def get_index(label):
        key = manage_files.get_field_key_from_label(note_type_name, label, config)
        return index_of_field(key, fields) if key else -1

    sentence_idx = get_index(f"{target_subtitle_line_string}")
    sound_idx = get_index(f"{target_audio_string}")
    translation_idx = get_index(f"{translation_subtitle_line_string}")
    translation_sound_idx = get_index(f"{translation_audio_string}")
    image_idx = get_index("Image")

    sound_line = note.fields[sound_idx] if 0 <= sound_idx < len(note.fields) else ""
    if "[sound:" not in sound_line:
        sound_line = ""

    translation_sound_line = note.fields[translation_sound_idx] if 0 <= translation_sound_idx < len(note.fields) else ""
    if "[sound:" not in translation_sound_line:
        translation_sound_line = ""

    image_line = note.fields[image_idx] if 0 <= image_idx < len(note.fields) else ""
    if "<img src=" not in image_line:
        log_image("no valid image detected")
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

def is_normalized(sound_line):
    return bool(re.search(r'`-\d+LUFS\.\w+$', sound_line))


# play sound hooks and buttons
def generate_fields_button(editor):
    sound_filename = generate_and_update_fields(editor, None, False)
    if sound_filename:
        log_command(f"Playing sound filename: {sound_filename}")
        QTimer.singleShot(100, lambda: play(sound_filename))

def on_editor_field_focused_minimal(note: Note, field_name: str) -> None:
    model_fields = note.note_type()["flds"]
    focused_idx = next((i for i, f in enumerate(model_fields) if f["name"] == field_name), -1)
    sound_idx = next((i for i, f in enumerate(model_fields) if f["name"] == "Target Audio"), -1)
    translation_sound_idx = next((i for i, f in enumerate(model_fields) if f["name"] == "Translation Audio"), -1)

    if focused_idx in (sound_idx, translation_sound_idx):
        log_command(f"Field focused: {field_name}")

def on_note_loaded(editor):
    editor.web.eval("window.getSelection().removeAllRanges();")
    av_player.stop_and_clear_queue()
    if getattr(editor, "_auto_play_enabled", False):
        fields = get_fields_from_editor(editor)
        sound_idx = fields.get("sound_idx")

        if sound_idx is not None and sound_idx < len(editor.note.fields):
            field_text = editor.note.fields[sound_idx]
            match = re.search(r"\[sound:([^]]+)]", field_text)
            if match:
                filename = match.group(1)
                log_command(f"Playing sound from field {sound_idx}: {filename}")
                QTimer.singleShot(0, lambda fn=filename: play(fn))

gui_hooks.editor_did_focus_field.append(on_editor_field_focused_minimal)


# bulk generation
def suppress_showInfo(*args, **kwargs):
    pass

def bulk_generate(deck, note_type):
    original_showInfo = aqt.utils.showInfo
    aqt.utils.showInfo = suppress_showInfo
    try:
        current_deck_name = deck["name"]

        log_command("Running bulk_generate...")
        log_command(f"Deck: {current_deck_name}")

        note_ids = mw.col.find_notes(f'deck:"{current_deck_name}"')

        if not note_ids:
            all_decks = [d["name"] for d in mw.col.decks.all()]
            log_command(f"Available decks: {all_decks}")

            log_command("Available decks:")
            for deck in mw.col.decks.all():
                log_command(f"  ID: {deck['id']}, Name: {deck['name']}")

            log_command("\nAvailable note types:")
            for model in mw.col.models.all():
                log_command(f"  Name: {model['name']}, ID: {model['id']}")

        log_command(f"note ids: {note_ids}")
        for note_id in note_ids:
            note = mw.col.get_note(note_id)
            generate_and_update_fields(None, note, False)
    finally:
        aqt.utils.showInfo = original_showInfo

