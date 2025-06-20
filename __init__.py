from .menu import add_custom_controls
from aqt import gui_hooks

gui_hooks.editor_did_init.append(add_custom_controls)
