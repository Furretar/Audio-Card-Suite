from aqt import gui_hooks
from aqt.editor import Editor
from aqt.utils import showInfo
import re
from . import audio_files

ms_amount = 50

def adjust_sound_tag(editor: Editor, start_delta: int, end_delta: int) -> None:
    # finds first field with "[sound:" tag
    for idx, field_text in enumerate(editor.note.fields):
        if "[sound:" in field_text:
            new_sound_tag = audio_files.alter_sound_file_times(field_text, start_delta, end_delta)
            print("new_sound_tag:", new_sound_tag)

            if new_sound_tag:
                new_text = re.sub(r"\[sound:.*?\]", new_sound_tag, field_text)
                editor.note.fields[idx] = new_text
                editor.loadNote()
            else:
                print("No new sound tag returned, field not updated.")
            return

    showInfo("No [sound:] tag found in any field.")


def add_custom_editor_button(html_buttons: list[str], editor: Editor) -> None:
    # Avoid adding the button multiple times per editor
    if getattr(editor, "_my_button_added", False):
        return
    editor._my_button_added = True

    buttons = [
        (f"S+{ms_amount}", lambda ed=editor: adjust_sound_tag(ed, -ms_amount, 0), f"Add {ms_amount}ms to start", f"S+{ms_amount}"),
        (f"S-{ms_amount}", lambda ed=editor: adjust_sound_tag(ed, ms_amount, 0), f"Remove {ms_amount}ms from start", f"S-{ms_amount}"),
        (f"E+{ms_amount}", lambda ed=editor: adjust_sound_tag(ed, 0, ms_amount), f"Add {ms_amount}ms to end", f"E+{ms_amount}"),
        (f"E-{ms_amount}", lambda ed=editor: adjust_sound_tag(ed, 0, -ms_amount), f"Remove {ms_amount}ms from end", f"E-{ms_amount}"),    ]

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


# def on_focus_field(obj, field_index: int) -> None:
#     note = obj
#     field_text = note.fields[field_index]
#     print("on_focus_field - field text:", field_text)
#     matches = re.findall(r"\[([^\]]+)\]", field_text)
#     if matches:
#         for match in matches:
#             print(f"Found bracketed text: [{match}]")

def init_editor_buttons() -> None:
    gui_hooks.editor_did_init_buttons.append(add_custom_editor_button)
    # gui_hooks.editor_did_focus_field.append(on_focus_field)

init_editor_buttons()
