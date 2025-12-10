import os

from aqt import gui_hooks
from . import manage_database
from . import constants

from . import menu
import threading




gui_hooks.profile_did_open.append(menu.on_profile_loaded)
threading.Thread(target=lambda: constants.timed_call(manage_database.update_database), daemon=True).start()

if constants.addon_source_folder and not os.path.exists(constants.addon_source_folder):
    os.mkdir(constants.addon_source_folder)
if not os.path.exists(constants.ignore_dir):
    os.mkdir(constants.ignore_dir)