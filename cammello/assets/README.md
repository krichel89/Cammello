# Bundled assets

## icon.png

The Cammello application icon: a white dromedary on a dark navy tile,
512×512 RGBA PNG. This one file is the single source for every icon the
project needs:

- **In the app** — loaded via `constants.asset_path('icon.png')` for the
  window/dock icon (`app.setWindowIcon`) and the logo shown in the UI. The
  code guards every use with `os.path.exists`, so a missing icon degrades
  to the platform default rather than crashing.
- **macOS build** — `.github/workflows/build.yml` pads it with a
  transparent margin (dock icons expect ~80% content) and builds
  `icon.icns` through `sips`/`iconutil`.
- **Windows build** — the same workflow derives `icon.ico`
  (16/32/48/128/256 px) with Pillow.

The derived `icon.icns` and `icon.ico` are build artefacts and are **not**
checked in; only `icon.png` is versioned. Replacing the icon means
replacing this one file — the build regenerates the rest.
