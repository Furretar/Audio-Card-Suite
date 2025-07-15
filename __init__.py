from aqt import gui_hooks

from . import manage_database
from . import menu

gui_hooks.profile_did_open.append(menu.on_profile_loaded)
manage_database.update_database()
