# 🐒 MonkeyGain

**MonkeyGain** is a lightweight, native GTK 4 desktop application for scanning music with [rsgain](https://github.com/complexlogic/rsgain). Inspired by the simplicity of elementary OS, it offers a clean interface, an expandable album library, and real ReplayGain analysis results without re-encoding audio.

**Current version: 0.3.4 — early preview.** The Python core is covered by automated tests. The GTK UI should be tested on an actual Linux desktop before relying on it for valuable music. **Back up your files before enabling tag writing.**

## Features

- Native GTK 4 layout with **Dark**, **Light**, and **System** appearance modes.
- Drag and drop audio files or folders into the window, or open supported files via the desktop launcher.
- Remembers the most recently imported folder for subsequent file dialogs.
- Optional desktop notification when each scan queue finishes.
- Import individual songs or entire directories, including recursively discovered albums.
- **Expandable album cards** with track names and formats.
- **Existing metadata detection**: automatically reads already-written ReplayGain tags when importing audio, without launching an analysis or modifying any file. Shows "Already tagged", "Not tagged", "Partly tagged", or "Tags unknown" where appropriate.
- **Refresh Tags** in the header re-reads the files if their tags have changed outside MonkeyGain (read-only; no scan).
- **Per-track results**: measured loudness (LUFS), calculated Track Gain (dB), and peak (dB), or existing stored gain/peak values when no scan has been performed.
- **Album results**: measured loudness, calculated Album Gain, and album peak, when album analysis is enabled.
- Uses `rsgain custom --output` to read structured **tab-separated results directly from rsgain**, not guessed from text or metadata.
- Configurable target loudness, True Peak, clipping protection, maximum peak, Album Gain, and ReplayGain tag writing.
- A scan-only option (`--tagmode=s`) that does not write ReplayGain tags; confirmation before writing tags (`--tagmode=i`).
- Background scanning, an animated activity bar with elapsed time and completed-album counts, cancellation, and a **live Activity feed** with scan-start and per-album status, periodic real-time heartbeat messages, and final summaries.
- A **Raw output** switch shows the exact subprocess command and TSV output for troubleshooting. **Export raw** always saves the complete unmodified scanner output.
- Automatically locates the rsgain executable, with a manual path option.
- Supports filenames containing spaces and Unicode characters; subprocesses never run through a shell.
- Automatically saves preferences in `~/.config/monkeygain/settings.json` (outside the Git repository).

## Requirements

- Linux with GTK 4 and PyGObject; developed with **elementary OS 8.1**, **Python 3.12**, **GTK 4.14**, and **rsgain 3.4** in mind.
- `rsgain` installed and accessible either via `PATH` or an absolute path selected in Settings.
- **Mutagen** (`python3-mutagen`) for safe, read-only import of existing ReplayGain/R128 metadata; if missing, audio scanning still works but tag-detection status is unknown.

On elementary OS 8.1 / Ubuntu 24.04:

```bash
sudo apt update
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 python3-mutagen rsgain
```

Verify the dependencies:

```bash
rsgain --version
python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print(Gtk.get_major_version(), Gtk.get_minor_version())"
```

The application uses system-provided PyGObject and Mutagen. A `pip` environment is not required. To verify tag-reading support:

```bash
python3 -c "import mutagen; print('Mutagen available')"
```

## Install from source / run in VS Code

Clone the repository or unpack a release archive. For example:

```bash
cd /data/Projects/MonkeyGain
code .
python3 run.py
```

A VS Code launch configuration is included in `.vscode/launch.json` for debugging with F5.

## Install as a desktop application (without sudo)

Keep the Git checkout in its desired location (for example, `/data/Projects/MonkeyGain`) and run:

```bash
cd /data/Projects/MonkeyGain
python3 scripts/install_local.py
```

The installer creates three files in your **user account**:

- `~/.local/bin/monkeygain` — a tiny launcher that points to the existing `run.py`.
- `~/.local/share/applications/io.github.baes9n.MonkeyGain.desktop` — the application menu entry.
- `~/.local/share/icons/hicolor/scalable/apps/io.github.baes9n.MonkeyGain.svg` — the MonkeyGain icon.

No system files are changed and no project files are moved. You can still develop in VS Code and push changes to GitHub normally. **If you move or rename the project folder, run the installer again** so the launcher points to the new path. If the launcher has not appeared in the application menu, try logging out and back in.

To run the installed launcher from a terminal:

```bash
~/.local/bin/monkeygain
```

To uninstall the desktop integration, while keeping the source, Git history and preferences:

```bash
python3 scripts/install_local.py --uninstall
```

This is a **local source-based installation**, not yet a standalone `.deb` or Flatpak package. It still relies on Python, GTK 4 and rsgain installed on your computer. It does not require administrator privileges.

## How to use MonkeyGain

1. Choose **Add Folder** or **Add Files**, or drag audio files and folders onto the application window. Folders are scanned recursively. Existing metadata is read immediately and **does not change your audio**.
2. Expand an album with the arrow on the left. A green checkmark beside a track indicates recognized existing gain metadata; the album status shows whether all, some, or none have tags. Use **Refresh Tags** after editing tags in another application.
3. Review the **Settings** panel; the default profile matches:

   ```bash
   rsgain custom --album --true-peak --loudness=-18 --clip-mode=p --max-peak=-1 --tagmode=i file1.flac file2.flac
   ```

   MonkeyGain additionally passes **`--output`**, which emits tab-separated results to standard output. Files are passed as individual arguments, not expanded with `*.flac`.
4. For a first test, **turn off Write Tags**. The resulting scan uses `--tagmode=s` and does not modify metadata.
5. Click **Start Scan**. If Write Tags is enabled, confirm the metadata change dialog.
6. Check **Album Gain**, **Loudness**, and **Album Peak** in the expanded album summary, and each track's **Loudness**, **Gain**, and **Peak** in the rows below it.
7. Watch **Analysis Activity** for a live spinner, elapsed time and a heartbeat every 10 seconds while an album is being analyzed. If needed, switch to **Raw output** for the full TSV table and command; **Export raw** saves the technical log. If enabled, a desktop notification announces scan completion.
8. MonkeyGain remembers the last imported directory and uses it as the initial location in future import dialogs.

### Understanding the results

- **Loudness** is the measured integrated loudness in LUFS, not your target setting.
- **Gain** is the ReplayGain adjustment recommended by rsgain in dB. Positive or negative values are possible.
- **Peak** is a dB value; when True Peak is enabled it is a true-peak measurement, otherwise a sample peak. Hover over a track's Peak result to see the underlying linear peak and peak mode.
- **Album Gain / Album Peak** appear only when `Album Gain` is enabled **and** the scanner supplies an album result.
- Existing **ReplayGain gain and peak** fields are loaded from tags when present. Stored peaks are **linear** and converted to dB for display; the tags do not indicate whether a peak is sample or true peak. The tags do **not** store measured integrated LUFS, so the **Loudness** column remains `—` until a scan provides it.
- Opus **R128** gain tags are recognized separately (Q7.8 dB, reference -23 LUFS) and are identified in tooltips, not silently treated as a result for the app's -18 LUFS target.
- Album gain/peak are displayed from existing tags only when the stored album values do not disagree; conflicting values display **Mixed**.
- The dash (`—`) means **no result was provided**, which is normal for missing fields (such as loudness in tags). For unreadable formats, MonkeyGain reports **Tags unknown**, not **Not tagged**.
- Yellow gain tooltip indicates an adjustment to prevent clipping when reported by rsgain.
- A **Completed** status means the backend returned success, **not** that every ReplayGain field has been read back from the file. Review the log for details.

### Album grouping and progress

An **album is one parent folder**, not a metadata-based album grouping. When scanning a directory containing several album subfolders, each subfolder becomes its own scan job. If two albums share a folder, separate them before Album Gain scanning. Multidisc albums stored in separate folders are treated as separate jobs.

The progress bar counts **completed album jobs**, not elapsed playback time or audio frames. The animated pulse and spinner indicate that the backend is still running. The Activity panel publishes the elapsed time and a heartbeat every 10 seconds; **these are not made-up percentages or track measurements**. On rsgain 3.4, `--output` automatically suppresses normal scanning progress messages, so MonkeyGain **cannot display a live per-track percentage** without changing the analysis workflow. Track measurements appear whenever rsgain emits them, generally at the end of the album scan. No additional audio decoding pass is performed.

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

The test suite covers recursive multiformat discovery, per-folder job creation, safe `rsgain custom` command generation, executable detection, parsing TSV Track/Album Gain results, a mocked subprocess scan, and read-only ReplayGain/R128 metadata extraction (including real ID3 metadata). It does **not** replace manual GTK desktop testing.

## Repository structure

```text
MonkeyGain/
├── monkeygain/
│   ├── __init__.py
│   ├── app.py                 # GTK 4 application, drag and drop, library
│   ├── desktop.py             # Safe per-user desktop integration
│   ├── metadata.py            # Read-only ReplayGain/R128 tag detection
│   └── core.py                # Discovery, rsgain invocation, TSV parser
├── scripts/
│   └── install_local.py        # User-level installation and removal
├── assets/
│   ├── monkeygain.svg        # App icon
│   └── style.css             # Light/dark appearance and album cards
├── tests/
│   ├── test_core.py
│   ├── test_desktop.py
│   ├── test_metadata.py
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
git commit -m "Fix detection of existing ReplayGain tags in v0.3.1"
git push origin main
```

The repository README, comments, interface messages, contributing guide, and changelog are written in **English**. Previous Git commit messages retain their original language unless you explicitly rewrite Git history; history rewriting is neither required nor recommended just to translate a repository.

## Roadmap

- Improved layouts for narrow windows and keyboard accessibility.
- Optional metadata-based album grouping for multidisc releases.
- Persistent scan history, result export to CSV, and independently packaged `.deb` / Flatpak builds.
- Broader metadata support for less common tag containers, with stronger post-write verification.
- Dynamic file format detection based on the installed rsgain version.

## License

Original MonkeyGain source code is licensed under the MIT License; see [LICENSE](LICENSE). Third-party components, including rsgain and GTK, retain their own licenses. Not affiliated with the rsgain project or elementary OS.
