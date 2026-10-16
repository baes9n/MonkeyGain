# Changelog

All notable changes to MonkeyGain are documented here. Versions follow the `MAJOR.MINOR.PATCH` convention.

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
