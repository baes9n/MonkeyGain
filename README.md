# 🐒 MonkeyGain

**MonkeyGain** is a lightweight, native GTK 4 desktop application for scanning music with [rsgain](https://github.com/complexlogic/rsgain). Inspired by the simplicity of elementary OS, it offers a clean interface, an expandable album library, and real ReplayGain analysis results without re-encoding audio.

**Current version: 0.2.0 — early preview.** The Python core is covered by automated tests. The GTK UI should be tested on an actual Linux desktop before relying on it for valuable music. **Back up your files before enabling tag writing.**

## Features

- Native GTK 4 layout with **Dark**, **Light**, and **System** appearance modes.
- Import individual songs or entire directories, including recursively discovered albums.
- **Expandable album cards** with track names and formats.
- **Per-track results**: measured loudness (LUFS), calculated Track Gain (dB), and peak (dB).
- **Album results**: measured loudness, calculated Album Gain, and album peak, when album analysis is enabled.
- Uses `rsgain custom --output` to read structured **tab-separated results directly from rsgain**, not guessed from text or metadata.
- Configurable target loudness, True Peak, clipping protection, maximum peak, Album Gain, and ReplayGain tag writing.
- A scan-only option (`--tagmode=s`) that does not write ReplayGain tags; confirmation before writing tags (`--tagmode=i`).
- Background scanning, cancellation, completed-album progress, and an exportable diagnostic log.
- Automatically locates the rsgain executable, with a manual path option.
- Supports filenames containing spaces and Unicode characters; subprocesses never run through a shell.
- Automatically saves preferences in `~/.config/monkeygain/settings.json` (outside the Git repository).

## Requirements

- Linux with GTK 4 and PyGObject; developed with **elementary OS 8.1**, **Python 3.12**, **GTK 4.14**, and **rsgain 3.4** in mind.
- `rsgain` installed and accessible either via `PATH` or an absolute path selected in Settings.

On elementary OS 8.1 / Ubuntu 24.04:

```bash
sudo apt update
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 rsgain
```

Verify the dependencies:

```bash
rsgain --version
python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print(Gtk.get_major_version(), Gtk.get_minor_version())"
```

The application uses system-provided PyGObject. A `pip` environment is not required.

## Install from source / run in VS Code

Clone the repository or unpack a release archive. For example:

```bash
cd /data/Projects/MonkeyGain
code .
python3 run.py
```

A VS Code launch configuration is included in `.vscode/launch.json` for debugging with F5.

## How to use MonkeyGain

1. Choose **Add Folder** or **Add Files**. Folders are scanned recursively.
2. Expand an album with the arrow on the left to see the files queued for that album.
3. Review the **Settings** panel; the default profile matches:

   ```bash
   rsgain custom --album --true-peak --loudness=-18 --clip-mode=p --max-peak=-1 --tagmode=i file1.flac file2.flac
   ```

   MonkeyGain additionally passes **`--output`**, which emits tab-separated results to standard output. Files are passed as individual arguments, not expanded with `*.flac`.
4. For a first test, **turn off Write Tags**. The resulting scan uses `--tagmode=s` and does not modify metadata.
5. Click **Start Scan**. If Write Tags is enabled, confirm the metadata change dialog.
6. Check **Album Gain**, **Loudness**, and **Album Peak** in the expanded album summary, and each track's **Loudness**, **Gain**, and **Peak** in the rows below it.
7. Use **Export** to save the full analysis log.

### Understanding the results

- **Loudness** is the measured integrated loudness in LUFS, not your target setting.
- **Gain** is the ReplayGain adjustment recommended by rsgain in dB. Positive or negative values are possible.
- **Peak** is a dB value; when True Peak is enabled it is a true-peak measurement, otherwise a sample peak. Hover over a track's Peak result to see the underlying linear peak and peak mode.
- **Album Gain / Album Peak** appear only when `Album Gain` is enabled **and** the scanner supplies an album result.
- The dash (`—`) means **no result was provided**. This can happen before scanning, for skipped tracks, on failure, or with older/different backend behavior.
- Yellow gain tooltip indicates an adjustment to prevent clipping when reported by rsgain.
- A **Completed** status means the backend returned success, **not** that every ReplayGain field has been read back from the file. Review the log for details.

### Album grouping and progress

An **album is one parent folder**, not a metadata-based album grouping. When scanning a directory containing several album subfolders, each subfolder becomes its own scan job. If two albums share a folder, separate them before Album Gain scanning. Multidisc albums stored in separate folders are treated as separate jobs.

The progress bar counts **completed album jobs**, not elapsed playback time or audio frames. On rsgain 3.4, `--output` automatically suppresses normal scanning progress messages, so MonkeyGain **cannot display a live per-track percentage**. Track measurements appear when rsgain emits its results at the end of the album scan.

### Supported formats

For rsgain 3.4, MonkeyGain recognizes these extensions:

`.flac`, `.mp3`, `.mp2`, `.m4a` (AAC/ALAC), `.mp4`, `.ogg`, `.oga`, `.spx`, `.opus`, `.wav`, `.aif`, `.aiff`, `.snd`, `.wv`, `.ape`, `.mpc`, `.tak`, `.wma`.

The actual codec support is determined by the **installed build of rsgain / FFmpeg**. Newer extensions (`.mka`, `.mkv`, `.webm`, `.dsf`) are intentionally not advertised for rsgain 3.4. Mixed file formats in one album folder are supported when the backend can process them.

### Troubleshooting rsgain detection

If MonkeyGain shows that rsgain is unavailable, run:

```bash
command -v rsgain
readlink -f "$(command -v rsgain)"
```

Enter the resolved executable path under **Settings → rsgain Executable** and select **Check**. The exact path is used for scanning. If `--version` succeeds but doesn't expose a recognizable version number, the status reads **rsgain · Ready**. This is not a failure.

## Development and tests

```bash
cd /data/Projects/MonkeyGain
python3 -m unittest discover -s tests -v
python3 -m compileall -q monkeygain
```

The test suite covers recursive multiformat discovery, per-folder job creation, safe `rsgain custom` command generation, executable detection, parsing TSV Track/Album Gain results, and a mocked subprocess scan. It does **not** replace manual GTK desktop testing.

## Repository structure

```text
MonkeyGain/
├── monkeygain/
│   ├── __init__.py
│   ├── app.py                 # GTK 4 application and expandable library
│   └── core.py                # Discovery, rsgain invocation, TSV parser
├── assets/
│   ├── monkeygain.svg        # App icon
│   └── style.css             # Light/dark appearance and album cards
├── tests/
│   ├── test_core.py
│   └── test_results.py
├── .vscode/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
└── run.py
```

## Updating an existing GitHub repository

If you already have a local Git repository, **do not run `git init` or add the remote again**. Update the source files in your working directory, then run:

```bash
cd /data/Projects/MonkeyGain
python3 -m unittest discover -s tests -v
git status
git add .
git commit -m "Release MonkeyGain v0.2.0: expandable library and structured results"
git push origin main
```

The repository README, comments, interface messages, contributing guide, and changelog are written in **English**. Previous Git commit messages retain their original language unless you explicitly rewrite Git history; history rewriting is neither required nor recommended just to translate a repository.

## Roadmap

- Drag-and-drop importing and more responsive layouts on narrow windows.
- Optional metadata-based album grouping for multidisc releases.
- Persistent scan history, result export to CSV, and an installer / Flatpak build.
- Detailed validation of the ReplayGain tags after writing, including special Opus conventions.
- Dynamic file format detection based on the installed rsgain version.

## License

Original MonkeyGain source code is licensed under the MIT License; see [LICENSE](LICENSE). Third-party components, including rsgain and GTK, retain their own licenses. Not affiliated with the rsgain project or elementary OS.
