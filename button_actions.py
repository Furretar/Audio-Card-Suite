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
from aqt.utils import tooltip

import manage_database


import manage_files
from manage_files import get_field_key_from_label, alter_sound_file_times, get_altered_sound_data, \
    extract_sound_line_data, extract_subtitle_path_data
import constants
from constants import (
    log_filename,
    log_error,
    log_image,
    log_database,
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



## manipulate and update fields

# finds the location of the current sentence field, then uses the selected text to find the next line that
# contains the selection and re-generates every field
def next_result_button(editor):
    if constants.database_updating.is_set():
        tooltip(f"Database updating, {constants.database_items_left} files left process.")

    config = constants.extract_config_data()
    fields = get_fields_from_editor_or_note(editor)
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
        return ""

    if not selected_text:
        selected_text = sentence_line

    if not sound_line:
        log_error(f"no sound line, called generate fields")
        generate_and_update_fields(editor, None, False)
        return ""

    log_filename(f"calling extract sound line data: {sound_line}")
    data = manage_files.extract_sound_line_data(sound_line)

    # gets next matching subtitle block using selected text and current fields
    block, subtitle_path = manage_files.get_next_matching_subtitle_block(sentence_line, selected_text, sound_line, config, data)

    if not block or not subtitle_path:
        log_error(f"didn't find another result for: {selected_text}")
        show_info_msg(f"No results found for: {selected_text}")
        return ""

    # generate new sound and sentence line using the block just retrieved
    next_sound_line, next_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block, subtitle_path, None, None, config)

    # Check if we've wrapped around to the same result
    new_data = manage_files.extract_sound_line_data(next_sound_line)
    if new_data:
        start_index = new_data["start_index"]
        end_index = new_data["end_index"]
        full_source_filename = new_data["full_source_filename"]

        old_data = manage_files.extract_sound_line_data(sound_line)
        if old_data:
            old_start_index = old_data["start_index"]
            old_end_index = old_data["end_index"]
            old_full_source_filename = old_data["full_source_filename"]

            if full_source_filename == old_full_source_filename and old_start_index >= start_index and old_end_index <= end_index:
                log_filename("Next result is the same as current result")
                show_info_msg(f"This is the only result for: {selected_text}")
                return ""

    # generate sound file using next sound line
    log_filename(f"calling extract sound line data: {next_sound_line}")
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
    if constants.database_updating.is_set():
        tooltip(f"Database updating, {constants.database_items_left} files left process.")

    fields = get_fields_from_editor_or_note(editor)
    config = constants.extract_config_data()
    modifiers = QApplication.keyboardModifiers()
    alt_pressed = modifiers & Qt.KeyboardModifier.AltModifier
    subtitle_database = manage_database.get_database()

    if alt_pressed:
        sound_idx = fields["translation_sound_idx"]
        sentence_idx = fields["translation_idx"]
        translation_idx = ""
        track = config.get("translation_subtitle_track")
        code = config.get("translation_language_code")
        pad_start = config["pad_start_translation"]
        pad_end = config["pad_end_translation"]

    else:
        sound_idx = fields["sound_idx"]
        sentence_idx = fields["sentence_idx"]
        translation_idx = fields["translation_idx"]
        track = config.get("target_subtitle_track")
        code = config.get("target_language_code")
        pad_start = config["pad_start_target"]
        pad_end = config["pad_end_target"]

    if add_to_start == 0:
        pad_start = 0
    if add_to_end == 0:
        pad_end = 0

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
        return ""

    start_index = data["start_index"]
    end_index = data["end_index"]
    timing_code = data["timing_lang_code"]
    print(f"timing code: {timing_code}, code: {code}")

    if not timing_code and not code:
        timing_code = "und"
        code = "und"
    elif not timing_code:
        timing_code = code

    # keep start and end times on opposite edges
    if add_to_end != 0:
        start_time = data["start_time"]
    else:
        start_time = None

    if add_to_start != 0:
        end_time = data["end_time"]
    else:
        end_time = None

    full_source_filename = data["full_source_filename"]
    print(f"2 sending code: {timing_code}")
    timing_subtitle_path = manage_files.get_subtitle_file_from_database(full_source_filename, track, timing_code, config, subtitle_database)

    if not timing_subtitle_path:
        aqt.utils.showInfo(f"No subtitle file found matching the source file '{full_source_filename}'.")

    log_filename(f"getting timing blocks, start_index {start_index}, add to start: {add_to_start}, end_index {end_index}, add to end: {add_to_end}, timing subtitle path: {timing_subtitle_path}")
    timing_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index - add_to_start, end_index + add_to_end, timing_subtitle_path, start_time, end_time)
    new_timing_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(timing_blocks, timing_subtitle_path, code, timing_code, config)

    if not timing_blocks:
        log_error(f"no timing blocks returned")
        return ""
    log_filename(f"timing blocks: {timing_blocks}")

    new_timing_data = manage_files.extract_sound_line_data(new_timing_sound_line)
    start_time = new_timing_data["start_time"]
    end_time = new_timing_data["end_time"]

    # get blocks for sentence line if applicable
    if timing_code != code:
        sentence_subtitle_path = manage_files.get_subtitle_file_from_database(full_source_filename, track, code, config, subtitle_database)
        log_filename(f"sentence_subtitle_path: {sentence_subtitle_path}")

        if not sentence_subtitle_path:
            aqt.utils.showInfo(f"No subtitle file found matching {full_source_filename}|`track_{track}`|code:'{code}'")

        sentence_blocks = manage_files.get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(sentence_subtitle_path, start_time, end_time)
        if not sentence_blocks:
            log_error(f"no sentence blocks returned")
            return ""
        _, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(sentence_blocks, timing_subtitle_path, code, timing_code, config)

    log_filename(f"new_sentence_line from blocks: {new_sentence_line}")

    # pad sound line if applicable
    pad_target_timings = (pad_start != 0 or pad_end != 0)
    if pad_target_timings:
        log_filename(f"padding timings for context line, pad start: {pad_start} | pad end: {pad_end}")
        data = manage_files.extract_sound_line_data(new_timing_sound_line)
        altered_data = get_altered_sound_data(new_timing_sound_line, pad_start, pad_end, config, data)
        if not altered_data:
            log_error(f"padded sound line is empty")
            return None
        new_timing_sound_line = altered_data["new_sound_line"]

    log_filename(f"getting sound line data from5: {new_timing_sound_line}")
    new_data = manage_files.extract_sound_line_data(new_timing_sound_line)
    altered_data = manage_files.get_altered_sound_data(new_timing_sound_line, 0, 0, config, new_data)
    new_timing_sound_line = manage_files.alter_sound_file_times(altered_data, new_timing_sound_line, config, alt_pressed)

    # generate new translation line
    if not alt_pressed:
        translation_line, _ = manage_files.get_translation_line_and_subtitle_from_target_sound_line(new_timing_sound_line, config, new_data)
        editor.note.fields[translation_idx] = str(translation_line or "")

    # update sound field with new sound line
    new_field = re.sub(r"\[sound:.*?]", new_timing_sound_line, sound_line)
    editor.note.fields[sound_idx] = str(new_field)
    editor.note.fields[sentence_idx] = str(new_sentence_line)

    # apply and save the changes to the note
    generate_and_update_fields(editor, None, False)

    def play_after_reload():
        if alt_pressed:
            play_sound = editor.note.fields[translation_sound_idx]
        else:
            play_sound = editor.note.fields[sound_idx]
        log_filename(f"playing sound: {play_sound}")
        match = re.search(r"\[sound:(.*?)]", play_sound)
        if match:
            sound_filename = match.group(1)
            QTimer.singleShot(0, lambda: play(sound_filename))

    editor.loadNote()

    autoplay = config["autoplay"]
    if not autoplay:
        QTimer.singleShot(0, play_after_reload)

def adjust_sound_tag(editor, start_delta: int, end_delta: int):
    if constants.database_updating.is_set():
        tooltip(f"Database updating, {constants.database_items_left} files left process.")

    # check for modifier keys
    config = constants.extract_config_data()
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        start_delta //= 2
        end_delta //= 2
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        start_delta *= 10
        end_delta *= 10

    fields = get_fields_from_editor_or_note(editor)
    alt_pressed = modifiers & Qt.KeyboardModifier.AltModifier
    if alt_pressed:
        sound_line = fields["translation_sound_line"]
        sound_idx = fields["translation_sound_idx"]
        sentence_line = fields["translation_line"]
    else:
        sound_line = fields["sound_line"]
        sound_idx = fields["sound_idx"]
        sentence_line = fields["sentence_line"]


    data = manage_files.extract_sound_line_data(sound_line)
    if not data:
        log_error(f"no valid sound line detected")
        generate_and_update_fields(editor, None, True)
        return

    log_filename(f"getting altered data from1: {sound_line}")
    altered_data = manage_files.get_altered_sound_data(sound_line, -start_delta, end_delta, config, data)
    if altered_data["new_sound_line"] == sound_line:
        return

    log_filename(f"sending data to alter sound file times: {altered_data}")
    new_sound_line = manage_files.alter_sound_file_times(altered_data, sound_line, config, alt_pressed)

    # generate a new sound line if first try failed
    if not new_sound_line:
        log_error("No new sound tag returned, checking database.")
        block, subtitle_path = manage_files.get_target_subtitle_block_and_subtitle_path_from_sentence_line(sentence_line, config)
        new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block, subtitle_path, None, None, config)
        if new_sound_line:
            new_sound_line_data = manage_files.extract_sound_line_data(new_sound_line)
            altered_data = manage_files.get_altered_sound_data(new_sound_line, -start_delta, end_delta, config, new_sound_line_data)
            if altered_data["new_sound_line"] == sound_line:
                return
            log_filename(f"sending data to alter sound file times: {altered_data}")
            new_sound_line = manage_files.alter_sound_file_times(altered_data, new_sound_line, config, alt_pressed)
        else:
            log_error(f"nothing found from sentence line {sentence_line}, returning")
            aqt.utils.showInfo(f"Could not find `{sentence_line}` in any subtitle file in '{os.path.basename(addon_source_folder)}',\n or any embedded subtitle file.")
            return

    print(f"sound line: {new_sound_line}")
    editor.note.fields[sound_idx] = new_sound_line
    editor.loadNote()

    autoplay = config["autoplay"]
    if not autoplay:
        QTimer.singleShot(100, lambda: on_note_loaded(editor, True))

# play sound hooks and buttons
def generate_fields_button(editor):
    if constants.database_updating.is_set():
        tooltip(f"Database updating, {constants.database_items_left} files left process.")

    sound_filename, updated = generate_and_update_fields(editor, None, False)
    if sound_filename and not updated:
        log_command(f"Playing sound filename: {sound_filename}")
        QTimer.singleShot(0, lambda: play(sound_filename))

# uses current fields to generate all missing fields
def generate_and_update_fields(editor, note, should_overwrite):
    config = constants.extract_config_data()

    # Determine current_note and fields dict depending on whether note or editor is provided
    if note is not None:
        current_note = note
        fields = get_fields_from_editor_or_note(note)  # Make sure this function handles both editor and note
    elif editor is not None:
        current_note = editor.note
        fields = get_fields_from_editor_or_note(editor)
    else:
        log_error("No editor or note provided")
        return None, None

    note_type_name = current_note.model()["name"]

    if not fields:
        log_error(f"No fields set for the note type '{note_type_name}'.")
        aqt.utils.showInfo(f"No fields set for the note type '{note_type_name}'.")

        return None, None

    sentence_idx = fields["sentence_idx"]
    sound_idx = fields["sound_idx"]
    image_idx = fields["image_idx"]
    translation_idx = fields["translation_idx"]
    translation_sound_idx = fields["translation_sound_idx"]
    sound_line = fields["sound_line"]

    modifiers = QApplication.keyboardModifiers()
    overwrite = bool(modifiers & Qt.KeyboardModifier.ControlModifier) or should_overwrite
    alt_pressed = bool(modifiers & Qt.KeyboardModifier.AltModifier)

    data = manage_files.extract_sound_line_data(sound_line)
    print(f"fields: {fields}")
    should_generate = should_generate_fields(fields, note_type_name, overwrite, data, config)

    fields_status = {
        "sound_line": not should_generate["sound_line"],
        "sentence_line": not should_generate["image_line"],
        "image_line": not should_generate["image_line"],
        "translation_line": not should_generate["translation_line"],
        "translation_sound_line": not should_generate["translation_sound_line"],
    }

    updated = False
    if all(fields_status.values()) and not overwrite:
        log_filename("All fields are filled, returning.")
        current_sound_line = current_note.fields[translation_sound_idx if alt_pressed else sound_idx]
        match = re.search(r"\[sound:(.*?)]", current_sound_line)
        return (match.group(1), updated) if match else (None, updated)

    new_result = get_generate_fields_sound_sentence_image_translation(
        note_type_name, fields, overwrite, alt_pressed, data
    )
    log_filename(f"new result: {new_result}")

    if not new_result:
        log_error("generate_fields_sound_sentence_image failed to return valid values.")
        return None, None

    new_sound_line, new_sentence_line, new_image_line, new_translation_line, new_translation_sound_line = new_result
    print(f"after new sentence line: {new_sentence_line}")

    def update_field(idx, new_val):
        nonlocal updated
        if new_val and current_note.fields[idx] != new_val:
            print(f"Updating field {idx} from {current_note.fields[idx]!r} to {new_val!r}")
            current_note.fields[idx] = new_val
            updated = True
        else:
            print(f"No update needed for field {idx}")

    should_generate = should_generate_fields(fields, note_type_name, overwrite, data, config)

    if should_generate["sentence_line"] and new_sentence_line:
        update_field(sentence_idx, new_sentence_line)

    if should_generate["translation_line"]:
        update_field(translation_idx, new_translation_line)

    if should_generate["sound_line"]:
        log_filename(f"getting altered data from3: {new_sound_line}")
        data = manage_files.extract_sound_line_data(new_sound_line)
        altered_data = manage_files.get_altered_sound_data(new_sound_line, 0, 0, config, data)
        if new_sound_line != current_note.fields[sound_idx] and altered_data:
            new_sound_line = manage_files.alter_sound_file_times(altered_data, new_sound_line, config, False)
            current_note.fields[sound_idx] = new_sound_line
            updated = True

    if should_generate["translation_sound_line"]:
        log_filename(f"getting sound data from translation: {new_translation_sound_line}")
        data = manage_files.extract_sound_line_data(new_translation_sound_line)
        altered_data = manage_files.get_altered_sound_data(new_translation_sound_line, 0, 0, config, data)
        if new_translation_sound_line != current_note.fields[translation_sound_idx] and altered_data:
            new_translation_sound_line = manage_files.alter_sound_file_times(altered_data, new_translation_sound_line, config, True)
            if not new_translation_sound_line:
                new_translation_sound_line = ""
            current_note.fields[translation_sound_idx] = new_translation_sound_line
            updated = True

    if should_generate["image_line"]:
        generated_img = manage_files.get_image_line_from_sound_line("", new_sound_line)
        log_image(f"new image: {generated_img}")
        if generated_img and isinstance(generated_img, str):
            current_note.fields[image_idx] = generated_img
            updated = True
    else:
        update_field(image_idx, new_image_line)

    # Only call editor.loadNote() if editor is not None
    if editor is not None:
        editor.loadNote()
    else:
        note.col.update_note(current_note)

    # Use editor.note.fields if editor is present, else current_note.fields
    sound_field_idx = translation_sound_idx if alt_pressed else sound_idx
    sound_field_val = None
    if editor is not None:
        sound_field_val = editor.note.fields[sound_field_idx]
    else:
        sound_field_val = current_note.fields[sound_field_idx]

    match = re.search(r"\[sound:(.*?)]", sound_field_val)
    log_filename(f"playing sound2: {match.group(1)}" if match else "No sound match")

    if match:
        path = os.path.join(mw.col.media.dir(), match.group(1))
        return (match.group(1), updated) if os.path.exists(path) else (None, updated)
    return None, updated


## get and format data
def context_aware_sound_sentence_line_generate(sentence_line, new_sentence_line, sound_line, subtitle_path, config):
    if sentence_line == new_sentence_line:
        log_error(f"sentence line and new sentence line are the same: {sentence_line}")
        return sound_line, sentence_line

    if (not sentence_line) or (not new_sentence_line):
        log_error(f"sentence line or new sentence line are null: {sentence_line}|{new_sentence_line}")
        return None, None

    # check before and after selected text for more lines to add
    leftover_sentence = manage_files.normalize_text(sentence_line)

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

        data = manage_files.extract_sound_line_data(new_sound_line)
        if not data:
            break
        start_index = data.get("start_index")
        if start_index is None:
            break
        end_index = data.get("end_index")
        if end_index is None:
            break
        lang_code = data["lang_code"]
        timing_lang_code = None
        timing_tracks_enabled = config["timing_tracks_enabled"]
        if timing_tracks_enabled:
            timing_lang_code = data["timing_lang_code"]

        # get the previous block if there's still text left over before the current sentence line
        if before_removed:
            before_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index - 1, start_index - 1, subtitle_path, None, None)
            if not before_blocks:
                log_error(f"no blocks extracted from: {subtitle_path}")
                return None, None
            before_block = before_blocks[0] if before_blocks else None
            before_line = before_block[3]
            before_line_clean = before_line
            # and add the previous line if the previous line is in leftover line, or if leftover line is in previous line
            if (
                before_line_clean in before_removed
                or before_line in before_removed
                or before_removed in before_line
                or before_removed in before_line_clean
            ):
                before_removed = before_removed.replace(before_line_clean, "", 1).replace(before_line, "", 1).strip()
                sentence_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index - 1, end_index, subtitle_path, None, None)
                new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(sentence_blocks, subtitle_path, lang_code, timing_lang_code, config)

            else:
                before_removed = ""
        data = manage_files.extract_sound_line_data(new_sound_line)
        if not data:
            break
        start_index = data.get("start_index")
        end_index = data.get("end_index")


        # get the next block if there's still text left over after the current sentence line
        if after_removed:
            after_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(end_index + 1, end_index + 1, subtitle_path, None, None)
            if not after_blocks:
                log_error(f"no blocks extracted from: {subtitle_path}")
                return None, None
            after_block = after_blocks[0] if after_blocks else None
            after_line = after_block[3]
            after_line_clean = after_line.replace('\n', '').strip()
            # and add the next line if the next line is in leftover line, or if leftover line is in next line
            if (
                after_line_clean in after_removed
                or after_line in after_removed
                or after_removed in after_line
                or after_removed in after_line_clean
            ):
                after_removed = after_removed.replace(after_line_clean, "", 1).replace(after_line, "", 1).strip()
                sentence_blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index, end_index + 1, subtitle_path, None, None)
                new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(sentence_blocks, subtitle_path, lang_code, timing_lang_code, config)
            else:
                after_removed = ""

    log_filename(f"new context sentence line: {new_sentence_line}")
    return new_sound_line, new_sentence_line

def should_generate_fields(fields, note_type_name, overwrite, data, config):
    sound_line = fields["sound_line"]
    image_line = fields["image_line"]
    translation_line = fields["translation_line"]
    translation_sound_line = fields["translation_sound_line"]

    should_generate_sentence_line = True
    should_generate_sound_line = True
    should_generate_translation_line = True
    should_generate_translation_sound_line = True
    should_generate_image_line = True

    # don't generate if the field isn't set, or if there is already text in the field, unless overwrite is true
    if (sound_line and not overwrite) or (not get_field_key_from_label(note_type_name, target_audio_string, config)):
        should_generate_sound_line = False

    if (translation_line and not overwrite) or not get_field_key_from_label(note_type_name, translation_subtitle_line_string, config):
        should_generate_translation_line = False

    if (translation_sound_line and not overwrite) or not get_field_key_from_label(note_type_name, translation_audio_string, config):
        should_generate_translation_sound_line = False

    if (image_line and not overwrite) or not get_field_key_from_label(note_type_name, image_string, config):
        should_generate_image_line = False

    if data:
        # don't try to generate image if the source is an audio file
        if should_generate_image_line:
            source_file_extension = data["source_file_extension"]
            audio_extensions = constants.audio_extensions
            print(f"source file extension: {source_file_extension}")
            if source_file_extension in audio_extensions:
                should_generate_image_line = False

        # don't try to generate translation lines if only 1 subtitle is found
        if should_generate_translation_line or should_generate_translation_sound_line:
            full_source_filename = data["full_source_filename"]
            conn = manage_database.get_database()
            print(f"searching for subtitle files with name: {full_source_filename}")
            cursor = conn.execute('''
                                  SELECT COUNT(*)
                                  FROM subtitles
                                  WHERE filename LIKE ? || '%'
                                  ''', (full_source_filename,))
            count = cursor.fetchone()[0]
            if count < 2:
                log_database(f"{full_source_filename} has {count} subtitle in the database.")
                should_generate_translation_line = False
                should_generate_translation_sound_line = False

    should_generate = {
        "sentence_line": should_generate_sentence_line,
        "sound_line": should_generate_sound_line,
        "image_line": should_generate_image_line,
        "translation_line": should_generate_translation_line,
        "translation_sound_line": should_generate_translation_sound_line,
    }
    log_filename(f"should_generate: {should_generate}")

    return should_generate

# uses current fields to generate and return update field data
def get_generate_fields_sound_sentence_image_translation(note_type_name, fields, overwrite, alt_pressed, data):
    # checks each field, generating and updating if needed. Returns each field, empty if not needed
    log_error(f"\n\n\n\n-------------------------------------------------------------------------------------------------------------------------------\n\n\n\n")
    sentence_line = fields["sentence_line"]
    sound_line = ""
    image_line = fields["image_line"]
    selected_text = fields["selected_text"]

    if not sentence_line:
        log_error(f"sentence field empty")
        return None

    if overwrite:
        if not alt_pressed:
            log_filename(f"overwriting sound line")
            sound_line = ""
            data = None

    config = constants.extract_config_data()
    log_filename(f"calling extract sound line data: {sound_line}")
    subtitle_path = ""
    new_sound_line = ""
    new_sentence_line = ""
    track = config["target_subtitle_track"]
    code = config["target_language_code"]
    pad_start_target = config["pad_start_target"]
    pad_end_target = config["pad_end_target"]
    pad_start_translation = config["pad_start_translation"]
    pad_end_translation = config["pad_end_translation"]

    # get sound and sentence line
    if data:
        full_source_filename = data["full_source_filename"]
        subtitle_database = manage_database.get_database()
        subtitle_path = manage_files.get_subtitle_file_from_database(full_source_filename, track, code, config, subtitle_database)
        log_filename(f"subtitle path from database1: {subtitle_path}")

        # return if subtitle path could not be found
        if not subtitle_path:
            log_error(f"subtitle path null1")
            aqt.utils.showInfo(f"No subtitles found with the track `{track}`, code `{code}`, and base name '{full_source_filename}'.")
            return None

        start_index = data["start_index"]
        end_index = data["end_index"]
        blocks = manage_files.get_subtitle_blocks_from_index_range_and_path(start_index, end_index, subtitle_path, None, None)
        if blocks:
            new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(blocks, subtitle_path, None, None, config)
        else:
            data = None

    # generate sound line if it doesn't exist
    if not data:
        log_error(f"no data extracted from sound line: {sound_line}")

        # Get target block and subtitle path using selected_text if available, otherwise sentence_line
        search_text = selected_text if selected_text else sentence_line
        block, subtitle_path = constants.timed_call(
            manage_files.get_target_subtitle_block_and_subtitle_path_from_sentence_line,
            search_text,
            config
        )

        log_filename(f"subtitle path from database2: {subtitle_path}")

        if not subtitle_path:
            log_error(f"subtitle path null2")
            aqt.utils.showInfo(f"Could not find `{sentence_line}` in any subtitle file in '{os.path.basename(addon_source_folder)}',\n or any embedded subtitle file with the code `{code}` or track `{track}`.")
            return None

        new_sound_line, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(block,subtitle_path,None,None,config)

    # always call context_aware_sentence_sound_line_generate
    log_filename(f"calling context_aware_sentence_sound_line_generate with sentence_line: {sentence_line}" + (f", new sentence line: {new_sentence_line}" if selected_text else ""))
    new_sound_line, new_sentence_line = context_aware_sound_sentence_line_generate(sentence_line, new_sentence_line, new_sound_line, subtitle_path, config)

    if new_sentence_line:
        new_sentence_line = constants.format_text(new_sentence_line)

    # get new timed sound line from target sound line
    timing_tracks_enabled = config["timing_tracks_enabled"]
    if timing_tracks_enabled:
        subtitle_data = manage_files.extract_subtitle_path_data(subtitle_path)
        if not subtitle_data:
            log_error(f"subtitle_data null")
            return None
        subtitle_file_code = subtitle_data["code"]
        new_timed_sound_line = manage_files.get_new_timing_sound_line_from_target_sound_line(new_sound_line, config, subtitle_file_code, False)
    else:
        new_timed_sound_line = new_sound_line
    data = manage_files.extract_sound_line_data(new_timed_sound_line)
    if not data:
        log_error(f"data is none")
        return None

    # if using a timing track, generate sentence line from sound line so it matches
    if timing_tracks_enabled:
        timing_code = data["timing_lang_code"]
        if timing_code:
            start_time = data["start_time"]
            end_time = data["end_time"]
            overlapping_blocks = manage_files.get_overlapping_blocks_from_subtitle_path_and_hmsms_timings(subtitle_path, start_time, end_time)
            _, new_sentence_line = manage_files.get_sound_sentence_line_from_subtitle_blocks_and_path(overlapping_blocks, subtitle_path, None, timing_code,config)

    # pad target sound line if applicable
    pad_target_timings = (
            pad_start_target != 0 or
            pad_end_target != 0)
    if pad_target_timings:
        altered_data = get_altered_sound_data(new_timed_sound_line, pad_start_target, pad_end_target, config, data)
        if not altered_data:
            log_error(f"padded sound line is empty")
            return None
        new_timed_sound_line = altered_data["new_sound_line"]
    log_filename(f"sound after after padding: {new_timed_sound_line}")

    should_generate = should_generate_fields(fields, note_type_name, overwrite, data, config)
    should_generate_image = should_generate["image_line"]
    should_generate_translation_line = should_generate["translation_line"]
    should_generate_translation_sound_line = should_generate["translation_sound_line"]

    # get image line
    if should_generate_image:
        log_image(f"image line empty, generating new one")
        new_image_line = manage_files.get_image_line_from_sound_line(image_line, new_timed_sound_line)
        log_image(f"generated image line: {new_image_line}")
    else:
        new_image_line = ""

    # get translation line
    if not new_sound_line:
        log_error(f"Target Audio not detected, cannot generate Translation or Translation Audio.")
        aqt.utils.showInfo(f"Target Audio not detected, cannot generate Translation or Translation Audio.")
        return ""
    if should_generate_translation_line or should_generate_translation_sound_line:
        log_filename(f"calling extract sound line data: {new_sound_line}")
        new_data = manage_files.extract_sound_line_data(new_sound_line)
        new_translation_line, translation_subtitle_path = manage_files.get_translation_line_and_subtitle_from_target_sound_line(new_sound_line, config, new_data)
        if new_translation_line:
            new_translation_line = constants.format_text(new_translation_line)
    else:
        new_translation_line = ""
        translation_subtitle_path = ""

    # get translation sound line
    if should_generate_translation_sound_line:
        subtitle_data = manage_files.extract_subtitle_path_data(translation_subtitle_path)
        if not subtitle_data:
            log_error(f"subtitle_data null")
            return None
        subtitle_file_code = subtitle_data["code"]
        new_translation_sound_line = manage_files.get_new_timing_sound_line_from_target_sound_line(new_sound_line, config, subtitle_file_code, True)
    else:
        new_translation_sound_line = ""

    # pad translation sound line if applicable
    pad_translation_timings = (pad_start_translation != 0 or pad_end_translation != 0)
    if pad_translation_timings:
        data = extract_sound_line_data(new_translation_sound_line)
        altered_data = get_altered_sound_data(new_translation_sound_line, pad_start_translation, pad_end_translation, config, data)
        if altered_data:
            new_translation_sound_line = altered_data["new_sound_line"]

    # don't regenerate sound line if holding alt and ctrl
    log_filename(f"alt being held, setting sound line to null")
    if alt_pressed:
        new_timed_sound_line = ""

    log_filename(f"generated fields:\n"
                          f"new_sound_line: {new_timed_sound_line}\n"
                          f"new_sentence_line: {new_sentence_line}\n"
                          f"new_image_line: {new_image_line}\n"
                          f"new_translation_line: {new_translation_line}\n"
                          f"new_translation_sound_line: {new_translation_sound_line}\n")

    return new_timed_sound_line, new_sentence_line, new_image_line, new_translation_line, new_translation_sound_line

def show_info_msg(msg):
    import aqt
    aqt.utils.showInfo(msg)

def get_fields_from_editor_or_note(editor_or_note):

    if hasattr(editor_or_note, "note"):
        note = editor_or_note.note
    else:
        note = editor_or_note

    # determine model / model name (minimal addition)
    if hasattr(note, "model"):
        note_type_name = note.model()['name'] if callable(note.model) else note.model['name']
    elif hasattr(note, "modelName"):
        note_type_name = note.modelName
    else:
        aqt.utils.showInfo("Cannot determine note type/model.")
        return {}


    config = constants.extract_config_data()
    if config is None:
        log_error("Config missing required fields, cannot proceed.")
        return {}

    mapped_fields = config[note_type_name].get("mapped_fields", {})
    print(f"mapped_fields: {mapped_fields}")
    if not mapped_fields:
        print("mapped_fields is empty or missing")
        aqt.utils.showInfo(f"No fields are mapped")
        return {}

    note = editor_or_note.note if hasattr(editor_or_note, "note") else editor_or_note
    note_type = note.note_type()
    note_type_name = note_type['name']
    if not mapped_fields:
        log_error(f"No field map found for note type '{note_type_name}'")
        return {}

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
        fld = next((f for f, lab in mapped_fields.items() if lab == lbl), None)
        if fld:
            lookup[lbl] = fld
        else:
            missing.append(lbl)

    if missing:
        log_error(f"The following labels are not mapped for note type '{note_type_name}':\n" + "\n".join(missing))

    fields = note_type["flds"]

    def field_index(label_string):
        field_name = manage_files.get_field_key_from_label(note_type_name, label_string, config)
        return index_of_field(field_name, fields) if field_name else -1

    sentence_idx = field_index(target_subtitle_line_string)
    sound_idx = field_index(target_audio_string)
    image_idx = field_index(image_string)
    translation_idx = field_index(translation_subtitle_line_string)
    translation_sound_idx = field_index(translation_audio_string)

    def safe_field(idx):
        return str(note.fields[idx]) if 0 <= idx < len(note.fields) else ""

    sound_line = safe_field(sound_idx)
    if "[sound:" not in sound_line:
        sound_line = ""

    image_line = safe_field(image_idx)
    if "<img src=" not in image_line:
        log_image("no valid image detected")
        image_line = ""

    sentence_line = safe_field(sentence_idx)
    translation_line = safe_field(translation_idx)
    translation_sound_line = safe_field(translation_sound_idx)

    if not sentence_line or sentence_line == "":
        log_error(f"Target Sentence field is empty.")

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
        "selected_text": str(editor_or_note.web.selectedText().strip()) if hasattr(editor_or_note, "web") else "",
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

    if not sentence_line or sentence_line == "":
        aqt.utils.showInfo(f"Target Sentence field is empty.")

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

def on_note_loaded(editor, override=False):
    editor.web.eval("window.getSelection().removeAllRanges();")
    av_player.stop_and_clear_queue()

    modifiers = QApplication.keyboardModifiers()
    alt_pressed = modifiers & Qt.KeyboardModifier.AltModifier

    if getattr(editor, "_auto_play_enabled", False) or override:
        fields = get_fields_from_editor_or_note(editor)
        if alt_pressed:
            sound_idx = fields["translation_sound_idx"]
        else:
            sound_idx = fields.get("sound_idx")

        if sound_idx is not None and sound_idx < len(editor.note.fields):
            field_text = editor.note.fields[sound_idx]
            match = re.search(r"\[sound:([^]]+)]", field_text)
            if match:
                filename = match.group(1)
                log_command(f"Playing sound from field {sound_idx}: {filename}")
                QTimer.singleShot(50, lambda fn=filename: play(fn))


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