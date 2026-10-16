# Changelog

All notable changes to MonkeyGain are documented here. Versions follow the `MAJOR.MINOR.PATCH` convention.

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
