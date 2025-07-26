
- [ ] read every sub folder in source folder, add folder it will ignore for easy management
- [ ] allow removing from end start times and batch normalization even without source files
- [ ] run bulk generation in background, have a stop button, display info
- [ ] show database update progress, add update database button to menu
- [ ] make ffmpeg commands run in the background, try to fix audio cutting off when spamming the button
- [ ] figure out why some files arent deleted from collection
- [ ]  figure out why database doesn't go to 0 when all files are removed
- [ ] add next and previous lines without a source file, for just text sentence cards



low priority
- [ ]  different language codes and tracks for different note types
- [ ] open mpv option
- [ ]  add/subtract 1db for each audio
- [ ]  generate waveform
- [ ]  add track to sound line so it doesnt have to search for the subtitle file
- [ ] implement 4 character sha code for file disambiguation, use few kilobytes from audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc


```
Generate Fields:
None - Generates all set fields if empty, plays target audio if full
Alt - Generates all set fields if empty, plays translation audio if full
Ctrl - Generates all set fields based on the target sentence, overwrites current fields
Ctrl + Alt - Regenerates translation fields, used when editing sound line after initial generation
```
