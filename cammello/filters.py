"""Filtering the file list by rating, colour label and channel (0.16.1).

Harald: "im Kopf der Bilderspalte noch Filtermoeglichkeiten nach Sternen,
Farben und Kanaelen", and on how they combine: "Sterne als und, farben als
oder, wie Lightroom".

So, exactly like Lightroom's filter bar:

  * STARS are a THRESHOLD, not a set of choices. A file has ONE rating, so
    picking "2" and "4" cannot mean "either" in any useful way - it means
    "2 and up", the way Lightroom's >= comparison works. Zero stars is the
    off position: everything passes.
  * COLOURS are a set, combined with OR. Picking red and green shows the
    red ones and the green ones. Nothing picked = colours do not filter.
  * CHANNELS are a set too, combined with OR - a file carries at most one
    mark, so OR is the only reading that lets you ask for two of them.
  * The three GROUPS combine with AND: three stars AND (red OR green).

Rejected files (rating -1) are a special case: Lightroom hides them behind
their own flag rather than sorting them below one star. Here a rejected file
never passes an active star filter, and passes the "off" position like any
unrated file - it is not the filter bar's job to hide them.

No Qt imports: this is plain logic, testable without a QApplication, the
same rule channels.py and workflows.py follow.
"""

# The "no colour label" bucket. A file with an unknown or custom label text
# (label_index() returns None for those) lands here rather than being
# unfilterable - the alternative would be a file that no colour choice can
# ever reach.
NO_COLOR = 'none'

# Same idea for files without a channel mark.
NO_CHANNEL = 'none'

MAX_STARS = 5


class FileFilter:
    """Which files the filter bar lets through.

    Attributes are plain data so the widget can set them directly and the
    tests can build one without any UI:

      min_rating  0 = off, 1..5 = "that many stars and up"
      colors      set of colour indices 0..4 and/or NO_COLOR; empty = off
      channels    set of channels.MARK_* and/or NO_CHANNEL; empty = off
    """

    __slots__ = ('min_rating', 'colors', 'channels')

    def __init__(self, min_rating=0, colors=None, channels=None):
        self.min_rating = int(min_rating or 0)
        self.colors = set(colors or ())
        self.channels = set(channels or ())

    # ── State ────────────────────────────────────────────────────────────
    @property
    def active(self):
        """Whether the filter narrows anything at all.

        The caller needs this for more than cosmetics: with no filter
        active, an empty selection means "all files" everywhere in the app,
        and that fallback must NOT apply while a filter is on.
        """
        return bool(self.min_rating or self.colors or self.channels)

    def clear(self):
        self.min_rating = 0
        self.colors = set()
        self.channels = set()

    # ── The test itself ──────────────────────────────────────────────────
    def matches(self, rating=0, color_index=None, mark=None):
        """Whether one file passes.

        rating       0..5, or -1 for rejected
        color_index  0..4, or None for no/unknown label
        mark         a channels.MARK_* value, or None
        """
        if self.min_rating:
            # A rejected file (-1) fails this by arithmetic, which is what
            # we want: asking for two stars should not turn up rejects.
            if (rating or 0) < self.min_rating:
                return False
        if self.colors:
            key = NO_COLOR if color_index is None else color_index
            if key not in self.colors:
                return False
        if self.channels:
            key = NO_CHANNEL if not mark else mark
            if key not in self.channels:
                return False
        return True

    def describe(self, translate=None):
        """A short human-readable summary for the status line and the log."""
        tr = translate or (lambda s: s)
        parts = []
        if self.min_rating:
            parts.append('%s%s' % ('\u2605' * self.min_rating, '+'))
        if self.colors:
            parts.append(tr('{n} colour(s)').format(n=len(self.colors)))
        if self.channels:
            parts.append(tr('{n} channel(s)').format(n=len(self.channels)))
        return ', '.join(parts)
