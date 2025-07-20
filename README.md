
- [ ] read every sub folder in source folder, add folder it will ignore for easy management
- [ ] allow removing from end start times and batch normalization even without source files
- [ ] use showinfo when any button returns null
- [ ] run bulk generation in background, have a stop button, display info
- [ ] fix audio stopping when adjusting too fast 
- [ ] fix add/remove next line breaking using timing files, change name to be like jpn-eng to know which to take audio from
- [ ] add track to sound line so it doesnt have to search for the subtitle file
- [ ] make it so you can add the langauge code manually for your own subtitles
- [ ] only add media file info to database when used, and not on startup
- [ ] make context aware generation update sentence line
- [ ] only store subtitles in the database so you can overwrite them with files in the source folder


low priority
- [ ] implement 4 character sha code for file disambiguation, use few kilobytes from audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
- [ ] add next and previous lines without a source file, for just text sentence cards
- [ ] open mpv option
- [ ]  add/subtract 1db for each audio
- [ ]  generate waveform
- [ ]  allow square brackets in filenames

```
Generate Fields:
None - Generates all set fields if empty, plays target audio if full
Alt - Generates all set fields if empty, plays translation audio if full
Ctrl - Generates all set fields based on the target sentence, overwrites current fields
Ctrl + Alt - Regenerates translation fields, used when editing sound line after initial generation
```
