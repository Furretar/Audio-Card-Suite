from aqt import gui_hooks
from aqt.editor import Editor
from aqt.utils import showInfo
import re

def my_button_action(editor: Editor) -> None:
    showInfo("Button clicked!")

def add_custom_editor_button(html_buttons: list[str], editor: Editor) -> None:
    # Avoid adding the button multiple times per editor
    if getattr(editor, "_my_button_added", False):
        return
    # editor._my_button_added = True

    html_buttons.append(
        editor.addButton(
            icon=None,
            cmd="custom_btn",
            func=my_button_action,
            tip="Click to show a message",
            label="MyBtn"
        )
    )
    print("Custom editor button added.")


def on_focus_field(obj, field_index: int) -> None:
    note = obj
    field_text = note.fields[field_index]
    print("on_focus_field - field text:", field_text)
    matches = re.findall(r"\[([^\]]+)\]", field_text)
    if matches:
        for match in matches:
            print(f"Found bracketed text: [{match}]")
    gui_hooks.editor_did_init_buttons.append(add_custom_editor_button)


def init_editor_buttons() -> None:
    gui_hooks.editor_did_init_buttons.append(add_custom_editor_button)
    gui_hooks.editor_did_focus_field.append(on_focus_field)

init_editor_buttons()
