- [ ] add generate button, add blocks for every matching string in text field
- [ ] add a button to fetch next result for text if it matched something else
- [ ] store start and end offset every time its pushed, when user moves the whole line forward or backward it automatically adjusts the offset amount


mpv to anki tool
- [ ] hotkey to add and remove 50ms to subtitle line in mpv?
- [ ] hotkey to add to beginning or end of last edited card
- [ ] add other audio to backside for pure audio cards
- [ ] store source filename with hash, then add to filename if different video has the same name, ie 01_abcd.mkv, 01_(2)_efgh.mkv, dont use hash in mp3 file on the cards
- [ ] store source mp3 file on card when you create first card


edit already made cards
- [ ] add/subtract 1db for each audio
- [ ] move buttons to above audio field
- [ ] figure out a system to use language codes to always get the right audio track (box with order of priority?)
- [ ] equalize all audio in current deck, auto equalize when adding

remove text inside ()?


Spin boxes:
Target Audio Field | Target Sentence Field | Translation Audio Field | Translation Text Field |
Start offset | End offset | Subtitle Offset | (Translation variants)

Normal:
Add Previous Line | Start +50ms | Generate Fields | End +50ms | Add Next Line

Hold shift
Remove First Line | Start -50ms | Generate Translation Field? | End -50ms | Remove Last Line

ctrl and alt to adjust +- ms times
