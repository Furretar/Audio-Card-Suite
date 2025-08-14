
- [ ] make ffmpeg commands run in the background, try to fix audio cutting off when spamming the button
- [ ] figure out why some files arent deleted from collection
- [ ] figure out why database doesn't go to 0 when all files are removed
- [ ] crashes when adding new note type
- [ ] different profiles with language codes and tracks for every note type
- [ ] checkbox to remove buttons at the top
- [ ] make it search and add files in folders correctly

low priority
- [ ] add checkbox to allow trimming audio and batch normalization even without source files
- [ ] add checkbox to use just subtitle file without a source file to make text sentence cards
- [ ] optimize next result by starting search from last found subtitle file
- [ ] add track to sound line so it doesnt have to search for the subtitle file
- [ ] open mpv option
- [ ]  generate waveform
- [ ] implement 4 character sha code for file disambiguation, use few kilobytes from audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc


```
Generate Fields:
None - Generates all set fields if empty, plays target audio if full
Alt - Generates all set fields if empty, plays translation audio if full
Ctrl - Generates all set fields based on the target sentence, overwrites current fields
Ctrl + Alt - Overwrites translation fields using current target fields
```
