## Cammello 0.12.4

Interface round based on Harald's list: slimmer toolbars, the menus in the
right places, and channel marks that set themselves.

### Channel marks
- The Commons mark is **teal** now instead of green: green was too close to
  the green colour label (1-5), so a channel mark could be mistaken for a
  rating. Commercial stays orange.
- **Uploading now sets the mark automatically.** Sending files to Commons
  marks them as the CC/Commons channel; sending them by FTP or to Flickr
  marks them commercial. Uploading *is* the decision, so you no longer have
  to remember to right-click first. The mark is set when the run starts, so
  an interrupted upload still records where the files went.

### Menus
- **Fullscreen is F**, grid is **G**, loupe view is **E** - plain keys, no
  modifier, matching the culling keyboard. Typing those letters into a text
  field still types them.
- **View** now lists only the working sections (Cmd/Ctrl+1…n) plus the three
  view modes and the zoom.
- **About** and the **Log** moved to **Help**, without shortcuts. Settings
  lives in the application/File menu (macOS files it under Cammello).
- Login and Test connection moved into the **Upload** menu.

### Toolbars
- Both toolbars (Culling and MediaWiki) are noticeably **shorter** - the
  images and the file table get the space back.
- The culling **filter block** is now set apart by thin separators.
- The Grid button left the culling toolbar (View menu / G key own it).

### MediaWiki tab
- The upload button reads **"Upload all"** with nothing selected and
  **"Upload selected"** with a selection.
- Pressing it while **not logged in opens the login** instead of a dead-end
  warning.
- "Clear all" is simply **"Clear"**.
- The buttons in the right-hand column no longer overlap: the settings
  import/export row wraps onto a second line when the column is narrow.
- The **Suggest** buttons moved into the left half, directly behind the
  "Categories:" and "Created during:" captions, so the input fields get the
  full width of the right column.
