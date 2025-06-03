# File: Audio-Card-Suite/__init__.py
from aqt import gui_hooks
from . import menu  # Import your menu module (which defines init_editor_buttons)

def start_addon() -> None:
    """Called once the main window is ready, sets up editor buttons etc."""
    menu.init_editor_buttons()

# Append your start_addon to main_window_did_init hook
gui_hooks.main_window_did_init.append(start_addon)
