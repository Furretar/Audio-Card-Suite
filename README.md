

- [ ] figure out why some files arent deleted from collection
- [ ] figure out why database doesn't go to 0 when all files are removed

- [ ] check if image for audiobooks already exists for optimal batch generation
- [ ] save config and log somewhere to help me debug reports
- [ ] if theres only 1 audio track then dont worry about the user set track
- [ ] make it possible to put (()) in filenames/fix unsafe characters better
- [ ] fix ffmpeg not found error





low priority
- [ ] add checkbox to allow trimming audio and batch normalization even without source files
hash to subtitle files to link them to file, this will allow files with the same name to remain unchanged, allowing torrent seeding etc
rrent fields
- [ ] option to auto detect languages for subs with no language code
- [ ] option to stop subtitle search, useful if you know you want something in the first subtitle but it didn't match immediately.
- [ ] dynamically resize search window to always be slightly larger than search string



```
Generate Fields:
None - Generates all set fields if empty, plays target audio if full
Alt - Generates all set fields if empty, plays translation audio if full
Ctrl - Generates all set fields based on the target sentence, overwrites current fields
Ctrl + Alt - Overwrites translation fields using current target fields
```
