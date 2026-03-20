# About
Audio Card Suite was made to provide a suite of tools for creating and editing audio cards in Anki. To use Audio Card Suite you must have video files and their corresponding subtitle files. 
 
# Usage
## Sources and Subtitles
Put all of your source video and subtitle files in the `Sources` folder. This folder can be opened by clicking `Audio Tools` in the main Anki screen, then clicking `Open Folder`. Audio Card Suite will read through every video file in the `Sources` folder, storing the contents of every embedded subtitle file and its [language code](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes) in the database. If the language is `undefined`, the language will be automatically detected using [fastText](https://github.com/facebookresearch/fastText). External subtitle files in the same directory with the same name will also be added, for example, `video.mkv` and `video.srt`. The language code can also be manually set by adding its [639-2 language code](https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes) before the extension, like this: `video.mkv` and `video.jpn.srt`. Subtitles without a matching video file will be automatically removed from the database. Since the contents of the subtitle file are read into the database on startup, you must either: click `Reload Database` in the settings, or, remove the subtitle file, click `Update Database`, then add it back.

## Generation
### Hotkeys for `Generate Fields`
None - Plays target audio if all fields are full, otherwise generates all set fields that are currently empty.

`Alt` - Plays translation audio if all fields are full, otherwise generates all set fields that are currently empty.

`Ctrl` - Generates all set fields, overwrites all current fields

`Ctrl + Alt` - Overwrites translation fields using current target fields


## Settings


# To-Do
- [ ] check if image for audiobooks already exists for optimal batch generation
- [ ] save config and log somewhere to help with bug reports
- [ ] if theres only 1 audio track then dont worry about the user set track
- [ ] make it possible to put (()) in filenames/fix unsafe characters better
- [ ] console window at the bottom of settings to show source reading progress
- [ ] if there are the same number of audio and subtitle tracks with the same language with matches indices, use the corresponding tracks (ie audio - 1:mainland chi, 2:taiwan chi, subs - 1:mainland chi, 2:taiwan chi)

low priority/after initial release?
- [ ] add checkbox to allow trimming audio and batch normalization even without source files
- [ ] hash subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
- [ ] option to stop subtitle search, useful if you know you want something in the first subtitle but it didn't match immediately.
- [ ] functionality to cycle tracks if there are multiple audio/subtitle tracks of the same language?
- [ ] checkbox to prioritize auto detected audio language, if tracks were set wrong initially


