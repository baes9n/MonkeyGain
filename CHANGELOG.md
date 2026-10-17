# Changelog

## [0.5.5] — 2026-10-16

- Added GitHub Actions tests and Debian package builds for pushes, pull requests and release tags.
- Added a read-only Debian package audit for dependencies, packaged version, launcher, desktop entry and all app icon sizes.
- Added release instructions, SHA-256 checksum generation and updated install/version references in English.
- No changes to the GTK interface, audio analysis or ReplayGain tag-writing behavior.


## [0.5.4] — 2026-10-16

### Changed
- Removed the About dialog, diagnostic export control, and manual rsgain executable picker from the workspace.
- Removed the technical engine status label from the footer.
- Kept user-facing ReplayGain, appearance, and notification options.
- Automatically checks Mutagen and the rsgain executable before opening the main workspace.
- The Debian package continues to resolve Python, GTK 4, Mutagen, and rsgain through APT dependencies.
- Kept existing audio processing, tag writing, album navigation, and the single progress region unchanged.

## [0.5.3] — 2026-10-16

### Changed
- Removed the Analysis Activity/Raw output mini-console from the main window.
- Combined importing and scanning into one footer progress area with one elapsed-time display.
- Added Save Diagnostic Log in Settings so full rsgain output remains available.
- Retained album rows and scroll position instead of recreating the list at scan start.
- Highlighted and followed the active album, suspending auto-follow on manual navigation.
- Revealed completed results without jumping to the top of the album list.
- Kept lazy track loading, paging, multi-album selection and all ReplayGain settings.

## [0.5.2] — 2026-10-16

### Fixed
- The album details control now uses a list icon rather than a right-pointing triangle that resembles a Play button.
- The button retains its explicit **Show tracks / Hide tracks** and **View results / Hide results** labels.
- No changes to scan execution, tag handling, album expansion, or performance.

## [0.5.1] — 2026-10-16

### Fixed
- Restore immediate per-track analysis visibility: automatically expand up to
  two visible albums with completed measurements when a scan finishes.
- Replace the inconspicuous arrow-only expansion control with explicit
  **Show tracks / Hide tracks** and **View results / Hide results** labels.
- Preserve lazy construction, per-page limits and manual expansion for other albums.

### Unchanged
- ReplayGain calculation and metadata writing, existing tag detection, the
  activity console, album selection, read-only scans, the dark/light themes,
  the application icon and Debian package installation locations.

## [0.5.0] — 2026-10-16

### Added
- Reproducible native Debian package builder (`scripts/build_deb.py`) and
  `monkeygain_0.5.0_all.deb` for elementary OS 8 / Ubuntu 24.04.
- APT dependency declarations for Python, GTK 4, Mutagen and rsgain.
- System-level desktop launcher, the selected MonkeyGain icons, and MIT license.
- A small GTK About dialog with version, license and GitHub repository.
- Headless packaging tests for install paths, launcher arguments and `.deb` layout.

### Fixed
- Pass command-line file arguments through `Gtk.Application.run()` so an
  installed launcher's `%F` file list can reach GApplication's open handler.

### Preserved
- No changes to the ReplayGain command, audio tag handling, import queue,
  selected-album scanning, activity progress, LUFS display or app icon.
- User-level source installation still works independently of the `.deb`.
- The package never touches user music, configuration or source Git history.



## [0.4.2] — 2026-10-16

### Changed
- Removed all artwork discovery, decoding, background image work, and cached thumbnails. Album rows now use a small symbolic audio icon.
- Compact album rows and kept bounded pagination / lazy track expansion.
- Album checkboxes persist across search, tag-status filters, and pagination.
- Added **Select Matches**, **Clear Selection**, **Scan Selected**, and **Scan All** actions.
- Scan Selected processes only explicitly checked albums. Scan All processes the full import queue regardless of filters.
- Write Tags confirmation now includes the exact job scope, measured in albums and files.
- Scan callbacks map results and progress to a stable snapshot of the selected jobs, not the complete library.

### Preserved
- Existing ReplayGain command options, tag reading/writing, read-only scan mode, 
  live activity, import progress, cancellation, search and filter semantics.
- Missing measured LUFS still displays as an em dash (`—`); no LUFS estimation.
- The selected MonkeyGain desktop icon is unchanged.

### Migration
- Remove the obsolete `monkeygain/artwork.py` and `tests/test_artwork.py`
  when upgrading an existing checkout (see README).


## [0.4.1] — 2026-10-16

### Added
- Background import runner with live discovery counts and real per-file metadata progress.
- Dedicated **Cancel Import** control that retains already processed files.
- Paginated collection view: up to 40 albums per page, with Previous/Next navigation.
- Tag-status filter for fully tagged, needing tags, or unreadable metadata.
- Lazy creation of album details with **Show next tracks** for large album folders.
- On-demand background cover loading with bounded in-memory artwork caching.
- Stress-oriented headless tests covering 5,000 files, streaming batches, and cancellation.

### Changed
- Search input is debounced and filters only the visible page source, not the scan queue.
- Album cards are collapsed initially to reduce unnecessary GTK widget allocation.
- The backend scan still runs all imported albums even when only some are visible.
- Existing ReplayGain options, tag formats, and missing-loudness dash remain unchanged.

### Notes
- Pagination is used instead of a fully virtualized GTK ListView for a smaller,
  safer upgrade of the existing GTK 4 application. Actual GTK responsiveness
  still requires testing on the target Linux desktop.


All notable changes to MonkeyGain are documented here. Versions follow the `MAJOR.MINOR.PATCH` convention.

## [0.4.0] — 2026-10-16

### Added
- A search field that filters imported album cards by artist folder, album, or track name; it does **not** modify the scan queue.
- Album cover thumbnails from `cover.jpg`, `folder.jpg`, `front.png` and similar image files, with embedded art support for FLAC, MP3, MP4/M4A, Ogg and Opus when available.
- Remember expanded/collapsed album cards when the library view refreshes.
- Clear feedback when a library search returns no matching albums.

### Unchanged
- The selected MonkeyGain app icon, ReplayGain commands, settings, activity progress, existing metadata detection, and missing-LUFS display (`—`) are unchanged.
- Album art reading is read-only. No audio files are edited by the artwork or search features.

## 0.3.5 — App icon refresh

- Replaced the original MonkeyGain icon with the selected warm-toned monkey and waveform design.
- Added PNG application icons at six resolutions (32, 48, 64, 128, 256 and 512 pixels).
- Updated the per-user desktop installer to install and remove the new icons, while retaining the existing launcher and desktop entry.
- Automatically cleans up the original SVG icon only when it matches MonkeyGain's previously shipped artwork.
- No changes to audio scanning, ReplayGain metadata or the analysis interface.

## [0.3.4] — 2026-10-16

### Improved
- Replaced the noisy default scanner console with a **live Analysis Activity** feed. It reports scan start, the active album, elapsed time, a heartbeat every 10 seconds while analysis is running, and completion/error summaries.
- Added a live spinner and elapsed timer beside the activity feed. The animated progress bar remains indeterminate during the active album, with real completed-album counts.
- Added a **Raw output** toggle for the original rsgain command and TSV measurements; **Export raw** always saves the unmodified technical output, regardless of the selected view.
- Improved activity readability with distinct status styling for light and dark themes.

### Unchanged
- Uses a single `rsgain custom --output` pass per album with exactly the same ReplayGain settings and cancel behavior as v0.3.3.
- No fabricated per-track percentages, no LUFS estimation, no loudness cache, and no "Not stored" labels. Existing tags still load on import, and missing measured LUFS remains `—`.
- rsgain 3.4 generally publishes TSV track measurements at the end of the album; the live feed reports **real elapsed time and backend state**, not simulated measurements.

## [0.3.3] — 2026-10-16

### Fixed
- Scans now display an animated activity bar immediately, together with elapsed time and the number of completed albums.
- The animation is explicitly indeterminate; rsgain 3.4 with `--output` does not expose a live completion percentage.
- Loudness display is unchanged from v0.3.1: when only existing ReplayGain tags are available, the measured LUFS field remains `—` until a fresh scan is performed.

## [0.3.1] — 2026-10-16

### Fixed
- Imported files now display existing ReplayGain gain and peak tags without requiring a scan.
- Tagged, partially tagged, untagged, and unreadable files are distinguished accurately.
- Existing ReplayGain peak values are converted from linear amplitudes to dB; original peak type is not assumed.
- Opus R128 gain values are recognized separately from conventional ReplayGain.
- Added a read-only **Refresh Tags** action for externally changed files.

### Changed
- Added the `python3-mutagen` dependency for read-only metadata detection.
- A previous scan measurement takes precedence until **Refresh Tags**, which explicitly loads on-disk values.
- Existing tag reading occurs in a background worker so the window stays responsive.

## [0.3.0] — 2026-10-16

### Added
- Drag-and-drop import for local files and folders using GTK 4's native file drop target.
- A per-user application-menu installer (`python3 scripts/install_local.py`) with an icon, desktop entry, and launcher.
- Reversible desktop integration (`--uninstall`) that preserves Git history, source files, and preferences.
- Support for opening audio files supplied to the desktop launcher.
- Optional desktop notifications on scan completion or cancellation.
- Recently used folder persistence for GTK file selection dialogs.
- Installation tests for paths containing spaces and reversible per-user installation.

### Changed
- Application ID aligned with the GitHub namespace: `io.github.baes9n.MonkeyGain`.
- The README and all new interface messages remain in English.

## [0.2.0] — 2026-10-16

### Added
- Expandable album cards with individual track rows and file-format labels.
- Structured per-track loudness, ReplayGain, and peak readings obtained from rsgain's `--output` option.
- Album Gain, measured loudness, and peak summary cards, when supported by the selected scan options.
- Album-level scan progress, with structured results displayed after each album completes.
- Regression tests for structured output, silent tracks, invalid rows, and the subprocess event flow.
- English contributing guide and documentation.

### Changed
- Refined spacing and visual hierarchy in both light and dark modes.
- Correct singular/plural album and track counts.
- Unknown backend version is displayed as `rsgain · Ready`, not a misleading error.
- Preserve user profile defaults: -18 LUFS, True Peak, Album Gain, positive-gain clipping protection, and -1 dB maximum peak.

### Notes
- Album folders are still grouped by filesystem directory rather than audio metadata.
- A dash in result fields indicates no scanner measurements received.
- Desktop UI must be tested on Linux with GTK 4.

## [0.1.1] — 2026-10-16

- Switched the interface and documentation to English.
- Removed the duplicate centered title from the app header.
- Improved detection of the rsgain executable and added a manual path selector.

## [0.1.0] — 2026-10-16

- Initial GTK 4 application with album queues, configurable ReplayGain scans, cancel support, and a log viewer.
