
- [ ] button to open source folder
- [ ] read every sub folder in source folder, add folder it will ignore for easy management
- [ ] allow removing from end start times even without backtick filename
- [ ] PRE INDEXING
- [ ] store start and end offset every time its pushed, when user moves the whole line forward or backward it automatically adjusts the offset amount
- [ ] keep extension in sound line?

      refactor
      get_subtitle_path_from_full_filename_track_code, make it take sound line instead of path
      make only 2 ways to get sub path, one with just sentence line and one with sound line


low priority, might do after initial release
- [ ] implement 4 character sha code for file disambiguation, use few kilobytes from audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
- [ ] add next and previous lines without a source file, for just text sentence cards
- [ ] bulk convert my current underscore audios/subs2srs underscore files to use the actual file name with normal spaces
- [ ] open mpv option
- [ ]  add/subtract 1db for each audio
- [ ]  use timings from a different subtitle track but the text for the translation


