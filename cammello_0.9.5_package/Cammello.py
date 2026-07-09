"""Cammello - Batch upload tool for Wikimedia Commons.

The implementation now lives in the ``cammello/`` package. This module re-exports
its public names so that existing imports (``import Cammello``) and the existing
PyInstaller build (``pyinstaller ... Cammello.py``) keep working unchanged.

See CHANGELOG.md for the version history. Requirements: PyQt5, requests, Pillow.
License: CC0.
"""
from cammello.constants import *          # noqa: F401,F403
from cammello.logging_setup import *      # noqa: F401,F403
from cammello.sdc import *                # noqa: F401,F403
from cammello.exif import *               # noqa: F401,F403
from cammello.api import *                # noqa: F401,F403
from cammello.workers import *            # noqa: F401,F403
from cammello.wikidata import *           # noqa: F401,F403
from cammello.widgets import *            # noqa: F401,F403
from cammello.editors import *            # noqa: F401,F403
from cammello.main_window import *        # noqa: F401,F403
from cammello.main_window import main

# Names starting with "_" (and dunders) are skipped by "import *"; re-export the
# ones that tests / tooling reference explicitly.
from cammello.constants import __version__, _WD_SINGLE_RE, _WD_LIST_RE
from cammello.sdc import _strip_sd_lines
from cammello.wikidata import _style_wd_field
from cammello.widgets import _VGrip

if __name__ == '__main__':
    main()
