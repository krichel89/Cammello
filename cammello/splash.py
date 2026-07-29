"""The start screen (0.14.2). NEW MODULE - remember it when installing.

Cammello used to open on a black window while the main window was being
built; this replaces that with a drawn splash carrying both logos: the app
icon and the WikiPortraits wordmark it belongs to.

The pixmap is PAINTED, not a bundled image: it then adapts to the display's
device pixel ratio (crisp on Retina), picks up the version string, and can
show a progress line while the window is built.

No dependency on the rest of the app beyond constants/assets, so it can be
shown before anything heavy is imported. Qt only.
"""
import os
import time

from PyQt5.QtWidgets import QSplashScreen, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QFont
from PyQt5.QtCore import Qt, QRectF, QTimer

from .constants import APP_NAME, __version__, asset_path

WIDTH, HEIGHT = 620, 330
BAND_Y = 232            # top edge of the light WikiPortraits band

# The dark blue of the app icon, so the splash and the icon read as one.
BG_TOP = QColor(24, 42, 68)
BG_BOTTOM = QColor(12, 20, 34)
ACCENT = QColor(216, 161, 42)          # the amber used for active controls
TEXT = QColor(238, 242, 246)
MUTED = QColor(150, 170, 190)


def _draw_logo(painter, path, rect):
    """Draw an asset into `rect`, keeping its aspect ratio and centring it.
    Missing assets are skipped - the splash must never be the reason the
    application fails to start."""
    if not path or not os.path.exists(path):
        return False
    pm = QPixmap(path)
    if pm.isNull():
        return False
    scaled = pm.scaled(int(rect.width()), int(rect.height()),
                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = rect.x() + (rect.width() - scaled.width()) / 2
    y = rect.y() + (rect.height() - scaled.height()) / 2
    painter.drawPixmap(int(x), int(y), scaled)
    return True


def build_pixmap(ratio=1.0):
    """Paint the splash at `ratio` device pixels per point."""
    pm = QPixmap(int(WIDTH * ratio), int(HEIGHT * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(BG_BOTTOM)

    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                     | QPainter.TextAntialiasing)

    # 0.14.3: an OPAQUE rectangular card. The first version drew rounded
    # corners onto a transparent pixmap and asked for a translucent window
    # to keep them - and on macOS that combination can leave the splash
    # invisible altogether, which is exactly what happened. A splash that
    # is reliably THERE beats one with prettier corners.
    card = QRectF(0, 0, WIDTH, HEIGHT)
    grad = QLinearGradient(0, 0, 0, HEIGHT)
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(1.0, BG_BOTTOM)
    p.fillRect(card, grad)

    # App icon, top left. The rounded variant is used when it is present so
    # the splash matches the macOS dock icon.
    icon = asset_path('icon_rounded.png')
    if not os.path.exists(icon):
        icon = asset_path('icon.png')
    _draw_logo(p, icon, QRectF(38, 46, 108, 108))

    # Name, version, tagline.
    p.setPen(TEXT)
    f = QFont(p.font())
    f.setPointSizeF(34)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(168, 52, WIDTH - 200, 48),
               Qt.AlignLeft | Qt.AlignVCenter, APP_NAME)

    p.setPen(ACCENT)
    f.setPointSizeF(13)
    f.setBold(False)
    p.setFont(f)
    p.drawText(QRectF(170, 100, WIDTH - 200, 22),
               Qt.AlignLeft | Qt.AlignVCenter,
               f'Version {__version__}')

    p.setPen(MUTED)
    f.setPointSizeF(12)
    p.setFont(f)
    p.drawText(QRectF(170, 124, WIDTH - 200, 22),
               Qt.AlignLeft | Qt.AlignVCenter,
               'Batch upload for Wikimedia Commons')

    p.setPen(MUTED)
    f.setPointSizeF(10)
    p.setFont(f)
    p.drawText(QRectF(170, 150, WIDTH - 200, 20),
               Qt.AlignLeft | Qt.AlignVCenter, 'CC0 \u00b7 Harald Krichel')

    # The WikiPortraits wordmark sits on a LIGHT band: its lettering is
    # near-black and would disappear on the dark card. A band keeps the
    # logo itself untouched instead of recolouring someone's mark, and
    # gives the splash a clear two-part reading - app above, project below.
    band = QRectF(0, BAND_Y, WIDTH, HEIGHT - BAND_Y)
    p.fillRect(band, QColor(244, 246, 249))
    p.setPen(QColor(0, 0, 0, 40))
    p.drawLine(0, int(BAND_Y), WIDTH, int(BAND_Y))

    drawn = _draw_logo(p, asset_path('wikiportraits.png'),
                       band.adjusted(60, 16, -60, -16))
    if not drawn:
        p.setPen(QColor(40, 40, 40))
        f.setPointSizeF(19)
        f.setBold(True)
        p.setFont(f)
        p.drawText(band, Qt.AlignCenter, 'WikiPortraits')

    p.setPen(QColor(255, 255, 255, 46))
    p.drawRect(QRectF(0.5, 0.5, WIDTH - 1, HEIGHT - 1))

    p.end()
    return pm


MIN_VISIBLE_MS = 4000   # 0.15.0 (Harald): four seconds, was 1500


class Splash(QSplashScreen):
    """The start screen. Messages appear in the lower right, over the card."""

    def __init__(self):
        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        ratio = screen.devicePixelRatio() if screen else 1.0
        super().__init__(build_pixmap(ratio))
        # NO WA_TranslucentBackground and no custom window flags (0.14.3):
        # QSplashScreen already is a frameless, always-on-top window, and
        # re-setting the flags after construction can drop the window back
        # behind others on macOS. Both were in the first version; between
        # them the splash never became visible there.
        self._shown_at = None
        if screen is not None:
            # Centre it on the screen the user is actually looking at.
            geo = screen.availableGeometry()
            self.move(geo.center().x() - WIDTH // 2,
                      geo.center().y() - HEIGHT // 2)

    def showEvent(self, event):
        super().showEvent(event)
        if self._shown_at is None:
            self._shown_at = time.monotonic()

    def finish_after_minimum(self, window, minimum_ms=MIN_VISIBLE_MS):
        """Close the splash, but not before it has been on screen long
        enough to be seen (0.14.3).

        The first version called finish() the moment the main window was
        up. On a fast machine that is a few hundred milliseconds - the
        splash flickered past or never appeared at all, which reads exactly
        like "no splash screen".
        """
        elapsed_ms = 0.0
        if self._shown_at is not None:
            elapsed_ms = (time.monotonic() - self._shown_at) * 1000.0
        # 0.15.0 (Harald): once the main window is up, the splash sits in
        # front of it for the remaining seconds - so align it HORIZONTALLY
        # with the window's centre instead of the screen's, or it hangs
        # visibly off to one side of a window that is not screen-centred.
        # Vertical position stays as it is, only horizontal was asked for.
        try:
            frame = window.frameGeometry()
            if frame.width() > 0:
                self.move(frame.center().x() - WIDTH // 2, self.y())
        except (RuntimeError, AttributeError):
            pass                      # window half-built: keep screen centre
        remaining = int(max(0.0, minimum_ms - elapsed_ms))
        if remaining <= 0:
            self.finish(window)
            return 0
        QTimer.singleShot(remaining, lambda: self.finish(window))
        return remaining

    def note(self, text):
        """Progress line - purely cosmetic, safe to call at any time."""
        # Drawn over the dark part, not the light band: white on white
        # would be invisible.
        self.showMessage(text + '   ', Qt.AlignTop | Qt.AlignRight, MUTED)
        app = QApplication.instance()
        if app:
            app.processEvents()


LAST_ERROR = ''


def show_splash():
    """Create and show the splash, or return None if anything goes wrong -
    a decoration must never keep the application from starting.

    A failure is recorded in LAST_ERROR so that main() can put it in the
    log once logging exists; a silently missing start screen is otherwise
    impossible to diagnose from a distance (0.14.3).
    """
    global LAST_ERROR
    LAST_ERROR = ''
    try:
        s = Splash()
        s.show()
        s.raise_()
        s.activateWindow()
        app = QApplication.instance()
        if app:
            app.processEvents()
        return s
    except Exception as e:
        LAST_ERROR = f'{type(e).__name__}: {e}'
        return None
