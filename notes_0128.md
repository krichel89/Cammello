## Cammello 0.12.8

One door instead of two.

### Signing in
- **The link on the MediaWiki page and the button in Settings now open the
  same window.** Until now they did different things: the link called the
  login routine, which fell through to the BOT PASSWORD dialog whenever no
  OAuth token was stored - so the more prominent of the two entry points
  sent a first-time user down the fallback path, while Settings offered the
  browser authorization.
- **The bot password lives inside that window** as a small fallback at the
  bottom. Settings keeps what belongs there: whether you are authorized,
  the button to remove the authorization, and an entry to edit the stored
  bot-password credentials (that button now says what it does - it edits,
  it does not sign in).
- **Authorizing signs you in right away.** Previously the browser round-trip
  left you authorized but not logged in, and you had to press Login again.
- **Nothing changed when you are already authorized**: the link signs you in
  silently, without a window in the way. The Settings button always opens
  the window, since pressing it is the request to see it - to re-authorize
  or to switch account.
- **The two option boxes always start unchecked.** "Show the link only" and
  "confirm manually" used to remember their last setting, so one manual
  sign-in left the window in manual mode for good - the normal one-click
  path stayed hidden behind a box ticked once, days ago. They are exception
  switches: the default is the normal way in, and reaching for the
  exception is a deliberate act each time.

### Two corrections after testing
- **The section headings needed contrast, not size.** 0.12.7 quietened them
  into a mid blue that nearly vanished on the dark background. The accent
  colour is now picked per colour scheme and is much stronger, and the size
  sits one step above the body text. It stays a FACTOR of the UI font, not
  a fixed point size, so headings follow the font when you change it.
- **The wheel no longer changes the language fields.** Scrolling the
  MediaWiki page with the touchpad kept landing on "Other (ISO code)…" and
  opening the code dialog - Qt's default is that the wheel over a combo box
  changes its value instead of scrolling the page. The language combos now
  pass the wheel on. Clicking, the keyboard and the wheel inside the open
  dropdown all still work; only the accidental path is closed.
- **IPTC: creator / rights / contact moved into the right column.** It used
  to be a full-width band across the top of the page, which pushed the file
  list and the field editor down and read like a header rather than what it
  is. It now sits next to the file list, above the per-file fields -
  settings that apply to every image, right beside the images.
- **The collapse arrows are visible.** They were the platform style's small
  grey triangle, whose size the style decides; they are now a glyph in the
  heading text, so they take the heading's colour and size and can actually
  be found.
- **Headings are white** (near-black on the light scheme - white on a light
  background would be invisible; the point is a neutral, maximal-contrast
  heading rather than a coloured one).
- **The FTP / Flickr sections match the rest of the app**: same heading,
  same arrow, and they fold away. They start expanded, and that state is
  not remembered - this tab is entered rarely, and a section folded away
  weeks ago would just look like a missing feature.
