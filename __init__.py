from aqt import gui_hooks
import time
from . import manage_database
from . import menu
import threading

def timed_call(func, *args, **kwargs):
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    print(f"{func.__name__} took {elapsed:.4f} seconds")
    return result


gui_hooks.profile_did_open.append(menu.on_profile_loaded)
threading.Thread(target=lambda: timed_call(manage_database.update_database), daemon=True).start()
