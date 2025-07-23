from aqt import gui_hooks
import time
from . import manage_database
from . import constants

from . import menu
import threading




gui_hooks.profile_did_open.append(menu.on_profile_loaded)
threading.Thread(target=lambda: constants.timed_call(manage_database.update_database), daemon=True).start()
