# About
Audio Card Suite was made to provide a suite of tools for creating and editing audio cards in Anki. To use Audio Card Suite you must have video files and their corresponding subtitle files. 
 
# Usage
## Sources and Subtitles
Put all of your source video and subtitle files in the `Sources` folder. This folder can be opened by clicking `Audio Tools` in the main Anki screen, then clicking `Open Folder`. Audio Card Suite will read through every video file in the `Sources` folder, storing the contents of every embedded subtitle file and its [language code](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes) in the database. If the language is `undefined`/`und`, the subtitle file must be chosen using the `Tracks` menu, unless it is the only subtitle file for its source file. External subtitle files in the same directory with the same name will also be added, for example, `video.mkv` and `video.srt`. The language code can also be manually set by adding its [639-2 language code](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes) before the extension, like this: `video.mkv` and `video.jpn.srt`.

Subtitles without a matching video file will be automatically removed from the database. Since the contents of the subtitle file are read into the database on startup, you must either: click `Reload Database` in the settings, or, remove the subtitle file, click `Update Database`, then add it back.

## Generation
### Hotkeys for `Generate Fields`
None - Plays target audio if all fields are full, otherwise generates all set fields that are currently empty.

`Alt` - Plays translation audio if all fields are full, otherwise generates all set fields that are currently empty.

`Ctrl` - Generates all set fields, overwrites all current fields

`Ctrl + Alt` - Overwrites translation fields using current target fields

## Multiple Tracks With Same Code
Some files contain multiple audio and subtitle tracks sharing the same language code. For example, a file might have:

| Track | Type | Code | Name | Track | Type | Code | Name |
|-------|------|------|------|-------|------|------|------|
| 1 | Audio | `chi` | Mainland | 1 | Subtitle | `chi` | Mainland CHS |
| 2 | Audio | `yue` | Cantonese | 2 | Subtitle | `chi` | SWC Cantonese |
| 3 | Audio | `chi` | Taiwanese | 3 | Subtitle | `chi` | Taiwan CHT |
| | | | | 4 | Subtitle | `chi` | Chinese |

When Audio Card Suite will try to match the 1st `chi` subtitle track with the 1st `chi` audio track, 2nd with the 2nd, etc. It will default to the last `chi` track if there are more subtitle tracks than audio tracks.

<img width="475" height="156" alt="multipletracks" src="https://github.com/user-attachments/assets/4acc0b98-143f-4559-82bf-b29214707e7e" />


## Settings


# To-Do
- [ ] save config and log somewhere to help with bug reports
- [ ] console window at the bottom of settings to show source reading progress

low priority/after initial release?
- [ ] add checkbox to allow trimming audio and batch normalization even without source files
- [ ] hash subtitle files to link them to file, this will allow files in subdirectories with the same name to remain unchanged, allowing torrent seeding etc
- [ ] option to stop subtitle search, useful if you know you want something in the first subtitle but it didn't match immediately.
- [ ] functionality to cycle tracks if there are multiple audio/subtitle tracks of the same language?
- [ ] auto detect audio language using faster whisper tiny, sample multiple sections of video
- [ ] option to prioritize auto detected languages, if codes were set wrong in the files
- [ ] store original and sanitized filenames in the database, no need to ban (( and )) in filenames


