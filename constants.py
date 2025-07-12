
import os


# integers
ms_amount = 50

# files
addon_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(addon_dir, "config.json")
addon_source_folder = os.path.join(addon_dir, "Sources")
temp_ffmpeg_folder = os.path.join(addon_dir, "ffmpeg")
temp_ffmpeg_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffmpeg.exe")
temp_ffprobe_exe = os.path.join(temp_ffmpeg_folder, "bin", "ffprobe.exe")

# strings
target_subtitle_line_string = "Target Subtitle Line"
target_audio_string = "Target Audio"
translation_subtitle_line_string = "Translation Subtitle Line"
translation_audio_string = "Translation Audio"
image_string = "Image"

# menu
CONTAINER_MARGINS = (2, 2, 2, 2)
CONTAINER_SPACING = 8
ROW_MARGINS = (0, 0, 0, 0)
ROW_SPACING = 10
BUTTON_ROW_MARGINS = (0, 0, 0, 0)
BUTTON_ROW_SPACING = 12
LABEL_MIN_WIDTH = 120
SPINBOX_MIN_WIDTH = 60
CHECKBOX_MIN_WIDTH = 150
BUTTON_PADDING = "padding: 1px 4px;"
SHIFT_BUTTON_BG_COLOR = "#f0d0d0"