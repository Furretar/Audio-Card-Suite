






- [ ] make ffmpeg commands run in the background, try to fix audio cutting off when spamming the button
- [ ] figure out why some files arent deleted from collection
- [ ] figure out why database doesn't go to 0 when all files are removed
- [ ] make it not call the japanese audio chinese, remove language code?
- [ ] checkbox to remove buttons at the top
- [ ] make it search and add files in folders correctly
- [ ] sort subtitles by date used, allows user to keep all media in source folder without micromanaging
- [ ] option to auto detect languages for subs with no language code
- [ ] check if image for audiobooks already exists for optimal batch generation 




low priority
- [ ] add checkbox to allow trimming audio and batch normalization even without source files
om audio track for hash, add hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
- [ ] different source folders for each note type




```
Generate Fields:
None - Generates all set fields if empty, plays target audio if full
Alt - Generates all set fields if empty, plays translation audio if full
Ctrl - Generates all set fields based on the target sentence, overwrites current fields
Ctrl + Alt - Overwrites translation fields using current target fields
```

