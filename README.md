
- [ ] read every sub folder in source folder, add folder it will ignore for easy management
- [ ] allow removing from end start times and batch normalization even without source files
- [ ] use showinfo when any button returns null
- [ ] run bulk generation in background, have a stop button, display info
- [ ] make it so you can add the language code manually for your own subtitles
- [ ] make ffmpeg commands run in the background, try to fix audio cutting off when spamming the button


low priority
- [ ] implement 4 character sha code for file disambiguation, use few kilobytes from audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
- [ ] add next and previous lines without a source file, for just text sentence cards
- [ ] open mpv option
- [ ]  add/subtract 1db for each audio
- [ ]  generate waveform
- [ ]  allow square brackets in filenames
- [ ]  add track to sound line so it doesnt have to search for the subtitle file

```
Generate Fields:
None - Generates all set fields if empty, plays target audio if full
Alt - Generates all set fields if empty, plays translation audio if full
Ctrl - Generates all set fields based on the target sentence, overwrites current fields
Ctrl + Alt - Regenerates translation fields, used when editing sound line after initial generation
```
