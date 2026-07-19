## Cammello 0.12.5

Follow-up to Harald's screenshot: overlapping buttons, toolbars that never
actually got slimmer, and the menu entries that went missing.

### Overlapping buttons — root cause fixed
Long German labels in the narrow right-hand column squeezed fixed button
rows until the buttons painted over each other. Two changes:

- The caption buttons ("Add language" / "Information from caption") now sit
  in a wrapping row, like the settings import/export row.
- The wrapping layout itself had a flaw: it reserved only each button's
  *preferred* width, which can be less than the button actually paints
  (notably with the native macOS bezel). It now reserves the larger of
  preferred and minimum width, and keeps a bit more air between neighbours.

### Toolbars are really slim now
The previous attempt capped the control height - which Qt silently ignores,
because a widget never shrinks below its minimum size hint (29 px, more on
macOS). The compact controls are now marked and the stylesheet drops their
minimum height, so the fixed height takes effect. The MediaWiki toolbar also
lost its button row entirely: Add files, Remove selected, Bulk edit and
Clear all live in the File and Edit menus, so the bar carries just the login
status, the warnings switch and the upload button.

### Culling filter
- The minimum rating is shown as **stars** instead of a dropdown: click a
  star to show that rating and up, click the same star again for "all".
- The whole filter block is now **centred** in the toolbar, between the
  folder actions on the left and the hand-off actions on the right.

### Menus
- **About** and **Settings** are back where you can see them: Help > About
  Cammello and File > Settings. They previously carried the macOS "role"
  that moves such entries into the application menu - which is called
  "Python" when Cammello runs from source, so they looked lost.
- **Bulk edit selected** joined the Edit menu (Ctrl/Cmd+B).

### Editor
The **Suggest** button moved to the **Categories** row, where the category
it produces actually lands - the "created during" row is a plain field again.
