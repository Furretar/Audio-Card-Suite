
- [ ] button to open source folder
- [ ] read every sub folder in source folder, add folder it will ignore for easy management
- [ ] allow removing from end start times even without backtick filename
- [ ] store start and end offset every time its pushed, when user moves the whole line forward or backward it automatically adjusts the offset amount
- [ ] fix audio not playing if you edit the times too quickly in a row
- [ ] run bulk generation in background, have a stop button
- [ ] make config global, only update when changed
- [ ] using different timings files breaks the add/remove next/previous lines, so add a check where if the index and start times dont match the current file, search all of subtitle files with the same basename, and use another one if it matches exactly
- [ ] make it so you can add the langauge code manually for your own subtitles
- [ ] only add media file info to database when used and not on startup?



low priority, might do after initial release
- [ ] implement 4 character sha code for file disambiguation, use few kilobytes from audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
- [ ] add next and previous lines without a source file, for just text sentence cards
- [ ] open mpv option
- [ ]  add/subtract 1db for each audio

