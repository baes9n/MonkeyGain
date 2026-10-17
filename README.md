# 🐒 MonkeyGain

![MonkeyGain icon](assets/icons/256.png)

**MonkeyGain** is a lightweight, native GTK 4 desktop application for scanning music with [rsgain](https://github.com/complexlogic/rsgain). Inspired by the simplicity of elementary OS, it offers a compact scan queue with album selection and real ReplayGain analysis results without re-encoding audio.

**Current version: 0.6.3 — restored reliable album list.** The Python core is covered by automated tests. The GTK UI should be tested on an actual Linux desktop before relying on it for valuable music. **Back up your files before enabling tag writing.**

## Features

- Native GTK 4 layout with **Dark**, **Light**, and **System** appearance modes.
- **Simplified album rows** with compact details controls, clearer keyboard focus and a narrower options panel.
- **Compact search and selection toolbar**: keep album searching and tag filtering visible; use the Selection menu for Select Matches / Clear Selection.
- **Contextual activity**: import and scan progress appears only while operations are active, and the completion summary remains visible without a full progress bar.
- **Keyboard shortcuts**: Ctrl+O files, Ctrl+Shift+O folders, Ctrl+F search, Ctrl+R refresh tags, Ctrl+Enter scan selected, Ctrl+Shift+Enter scan all; Esc clears the focused search field. Album rows can be expanded with keyboard activation.
- Drag and drop audio files or folders into the window, or open supported files via the desktop launcher.
- Remembers the most recently imported folder for subsequent file dialogs.
- Optional desktop notification when each scan queue finishes.
- Import individual songs or entire directories, including recursively discovered albums.
- **Responsive large imports**: folder discovery and ReplayGain-tag inspection run away from the GTK main thread. Discovery displays a busy indicator and a live discovered-file count; metadata inspection displays actual processed/total file progress.
- The **Cancel** button in the shared footer stops an import safely; already inspected files stay in the import queue.
- **Bounded scan queue**: shows at most 40 compact album rows per page, instead of constructing the whole collection at once. Previous/Next and filters help locate albums and select them for scanning. This uses pagination, not complete GTK ListView virtualization.
- **Stable album position**: opening a track list remembers the current scroll position; closing it returns to that position without a height animation or stealing mouse focus.
- **Lazy track details**: albums initially appear collapsed. The most recently analyzed album is expanded automatically when auto-follow is active. Use **View results** (list icon, not playback) on any other album, loading up to 60 track rows; use Show next tracks for unusually large albums.
- **Expandable compact album rows** with track names and formats, without artwork decoding or thumbnail caching. Search matches album names, artist folder names and track names.
- **Multi-album selection** with checkboxes, the **Selection** menu containing **Select Matches** (across all matching pages) and **Clear Selection**. Selection is retained while changing pages and filters.
- **Scan Selected** processes exactly the checked albums; **Scan All** processes all imported albums regardless of search and filters. The confirmation for writing tags states the actual number of files to be modified.
- Album cards retain their expanded/collapsed state when the library refreshes.
- **Existing metadata detection**: automatically reads already-written ReplayGain tags when importing audio, without launching an analysis or modifying any file. Shows "Already tagged", "Not tagged", "Partly tagged", or "Tags unknown" where appropriate.
- **Refresh Tags** in the header re-reads the files if their tags have changed outside MonkeyGain (read-only; no scan).
- **Per-track results**: measured loudness (LUFS), calculated Track Gain (dB), and peak (dB), or existing stored gain/peak values when no scan has been performed.
- **Album results**: measured loudness, calculated Album Gain, and album peak, when album analysis is enabled.
- Uses `rsgain custom --output` to read structured **tab-separated results directly from rsgain**, not guessed from text or metadata.
- Configurable target loudness, True Peak, clipping protection, maximum peak, Album Gain, and ReplayGain tag writing.
- A scan-only option (`--tagmode=s`) that does not write ReplayGain tags; confirmation before writing tags (`--tagmode=i`).
- Background scanning with **one progress area** in the footer, showing album counts and elapsed time alongside the active album, plus cancellation. No on-screen terminal, duplicated progress indicators, or periodic heartbeat messages.
- A single unobtrusive footer progress area is shared by import and ReplayGain scans. The interface does not display a technical console.
- Detects the installed rsgain engine automatically; no executable path configuration is required.
- Supports filenames containing spaces and Unicode characters; subprocesses never run through a shell.
- Automatically saves preferences in `~/.config/monkeygain/settings.json` (outside the Git repository).

## Requirements

- Linux with GTK 4 and PyGObject; developed with **elementary OS 8.1**, **Python 3.12**, **GTK 4.14**, and **rsgain 3.4** in mind.
- `rsgain` installed by the package manager (automatically when installing the `.deb`).
- **Mutagen** (`python3-mutagen`) for safe, read-only import of existing ReplayGain/R128 metadata. The app checks for it before opening the workspace.

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

The installer creates a launcher, a desktop entry, and multiple PNG icons in your **user account**:

- `~/.local/bin/monkeygain` — a tiny launcher that points to the existing `run.py`.
- `~/.local/share/applications/io.github.baes9n.MonkeyGain.desktop` — the application menu entry.
- `~/.local/share/icons/hicolor/{size}x{size}/apps/io.github.baes9n.MonkeyGain.png` — the MonkeyGain icon at six sizes (32–512 px).

No system files are changed and no project files are moved. Re-running the installer updates the icons and removes the original MonkeyGain SVG icon if it matches the version bundled in older releases. You can still develop in VS Code and push changes to GitHub normally. **If you move or rename the project folder, run the installer again** so the launcher points to the new path. If the launcher has not appeared in the application menu, try logging out and back in.

To run the installed launcher from a terminal:

```bash
~/.local/bin/monkeygain
```

To uninstall the desktop integration, while keeping the source, Git history and preferences:

```bash
python3 scripts/install_local.py --uninstall
```

This is a **per-user source-based launcher**, not the separately built Debian package. It still relies on Python, GTK 4 and rsgain installed on your computer. It does not require administrator privileges.

## How to use MonkeyGain

1. Choose **Add Folder** or **Add Files**, or drag audio files and folders onto the application window. Folders are scanned recursively **in the background**. The shared footer progress bar shows discovery and metadata-reading progress, and **Cancel** stops new work while retaining batches already loaded. Importing does **not change your audio**.
2. Navigate with **Previous/Next**, search by album/artist/track, or filter by tag status. Click the checkbox beside any album you want to analyze. **Selection → Select Matches** adds every album currently matching the search and status filter, including other pages. **Selection → Clear Selection** deselects all albums. Use **Show tracks** (or **View results** after a scan) to expand track details. When a scan finishes, the most recently analyzed album expands automatically if auto-follow is still active. Use **Refresh Tags** after editing tags in another application.
3. Review the **Settings** panel; the default profile matches:

   ```bash
   rsgain custom --album --true-peak --loudness=-18 --clip-mode=p --max-peak=-1 --tagmode=i file1.flac file2.flac
   ```

   MonkeyGain additionally passes **`--output`**, which emits tab-separated results to standard output. Files are passed as individual arguments, not expanded with `*.flac`.
4. For a first test, **turn off Write Tags**. The resulting scan uses `--tagmode=s` and does not modify metadata.
5. Click **Scan Selected** to process checked albums, or **Scan All** to process the entire imported queue. Search/filter alone does not change the selection or scope. If Write Tags is enabled, confirm the metadata change dialog after checking its actual album/file count.
6. Check **Album Gain**, **Loudness**, and **Album Peak** in the expanded album summary, and each track's **Loudness**, **Gain**, and **Peak** in the rows below it.
7. Watch the **single progress area** at the bottom of the window: it shows the active album, the completed-album count and one elapsed-time readout. The album row stays in place and is highlighted; auto-follow pauses if you scroll, change pages or search. A notification can announce completion.
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
- A **Completed** status means the backend returned success, **not** that every ReplayGain field has been read back from the file. If scanning fails, the album and footer display a failure status.

### Album grouping and progress

An **album is one parent folder**, not a metadata-based album grouping. When scanning a directory containing several album subfolders, each subfolder becomes its own scan job. If two albums share a folder, separate them before Album Gain scanning. Multidisc albums stored in separate folders are treated as separate jobs.

The progress bar counts **completed album jobs**, not elapsed playback time or audio frames. The animated pulse indicates that the backend is running. The footer shows elapsed time in one place and never invents per-track percentages. On rsgain 3.4, `--output` automatically suppresses normal scanning progress messages, so MonkeyGain **cannot display a live per-track percentage** without changing the analysis workflow. Track measurements appear whenever rsgain emits them, generally at the end of the album scan. No additional audio decoding pass is performed.

### Supported formats

For rsgain 3.4, MonkeyGain recognizes these extensions:

`.flac`, `.mp3`, `.mp2`, `.m4a` (AAC/ALAC), `.mp4`, `.ogg`, `.oga`, `.spx`, `.opus`, `.wav`, `.aif`, `.aiff`, `.snd`, `.wv`, `.ape`, `.mpc`, `.tak`, `.wma`.

The actual codec support is determined by the **installed build of rsgain / FFmpeg**. Newer extensions (`.mka`, `.mkv`, `.webm`, `.dsf`) are intentionally not advertised for rsgain 3.4. Mixed file formats in one album folder are supported when the backend can process them.

### Automatic dependency handling

The `.deb` lists GTK 4, PyGObject, Mutagen and `rsgain` as required APT
packages. Installing it with `sudo apt install ./monkeygain_<version>_all.deb`
resolves these requirements before launch. MonkeyGain then verifies that
Mutagen and a working `rsgain` executable are available **before opening the
main window**. If the environment is damaged or an optional development run
is missing a dependency, the app displays a clear startup error instead of
exposing an executable-path selector. It does not download or silently install
software during execution. On Debian-based systems, repair the installation
with `sudo apt install --reinstall monkeygain python3-mutagen rsgain`.

## Debian package (Ubuntu / elementary OS)

MonkeyGain 0.5.0 introduced a reproducible, architecture-independent **`.deb`**
build for elementary OS 8 / Ubuntu 24.04 and compatible systems. It installs
MonkeyGain in `/usr/lib/monkeygain`, creates `/usr/bin/monkeygain`, and installs
the desktop launcher and chosen icon under `/usr/share`. **It does not move,
modify or delete a Git checkout**. The package depends on distribution-provided
Python, GTK 4, Mutagen and rsgain (3.4 or later); it does **not** bundle a
private copy of these components. See the terminal and GTK tests before
publishing binaries: installing on elementary OS must still be validated.

Build from the repository, without administrator privileges:

```bash
cd /data/Projects/MonkeyGain
python3 -m unittest discover -s tests -v
python3 scripts/build_deb.py
# Output: dist/monkeygain_0.6.3_all.deb
```

**If you previously used the per-user desktop installer** (`install_local.py`),
first remove **only its launcher and icon files** while the Git checkout still
exists. Otherwise the user-level `.desktop` file shadows the system-wide one
and opens the development copy instead of the `.deb` installation:

```bash
python3 scripts/install_local.py --uninstall
sudo apt install ./dist/monkeygain_0.6.3_all.deb
```

You can then launch `MonkeyGain` from the Applications menu or run
`monkeygain`. APT will install missing dependencies (if enabled in your APT
sources, including the Ubuntu `universe` component for `rsgain`). On
Ubuntu 24.04, the repository ships `rsgain 3.4`.

Check the installed version and binary paths:

```bash
dpkg-query -W monkeygain rsgain
command -v monkeygain
```

For removal, run `sudo apt remove monkeygain`. This leaves music files, the
Git repository, and configuration in `~/.config/monkeygain` untouched.
You may reactivate the development launcher by running
`python3 scripts/install_local.py` in your repository **after** removing the
Debian package (do not keep both launchers installed).

**Development versus packaged application:** editing files under
`/data/Projects/MonkeyGain` affects `python3 run.py`, but not the version
installed from `.deb`. Rebuild and reinstall the package after source edits.
Do not run the system package and the development checkout simultaneously
against the same audio files.

This first Debian build is intended for systems with distro-compatible
Python / GTK dependencies. Flatpak is planned separately and is **not yet
provided**. Do not describe this archive as a standalone binary or an
official AppCenter package.

## Continuous integration and release checks

Every push to `main`, pull request, and `v*` tag triggers the GitHub Actions
[Linux tests and Debian package](.github/workflows/ci.yml) workflow. The job
runs automated tests, checks Python syntax, builds the `.deb`, and verifies
that the package includes the correct launcher, icons, system dependencies,
GTK styles and a matching version. It uploads a downloadable `.deb` and
`SHA256SUMS` on successful runs; **it does not publish a release automatically**.

Maintainers should follow [docs/RELEASING.md](docs/RELEASING.md) for the manual
GTK smoke test and GitHub release checklist. CI tests cannot prove that an
installed application works on every Linux desktop or audio codec.

## Development and tests

```bash
cd /data/Projects/MonkeyGain
python3 -m unittest discover -s tests -v
python3 -m compileall -q monkeygain
```

The test suite covers multi-album selection and scan scopes, recursive multiformat discovery, per-folder job creation, safe `rsgain custom` command generation, executable detection, parsing TSV Track/Album Gain results, a mocked subprocess scan, and read-only ReplayGain/R128 metadata extraction (including real ID3 metadata). It does **not** replace manual GTK desktop testing.

## Repository structure

```text
MonkeyGain/
├── monkeygain/
│   ├── __init__.py
│   ├── app.py                 # GTK 4 application, scan queue, album selection
│   ├── desktop.py             # Safe per-user desktop integration
│   ├── importer.py            # Background batch import, paging, search
│   ├── selection.py           # Album selection and scan-scope planning
│   ├── activity.py            # Live scan activity journal
│   ├── metadata.py            # Read-only ReplayGain/R128 tag detection
│   └── core.py                # Discovery, rsgain invocation, TSV parser
├── scripts/
│   ├── build_deb.py            # Build .deb from this checkout
│   ├── verify_release.py       # Audit package contents and dependencies
│   └── install_local.py        # User-level installation and removal
├── assets/
│   ├── icons/               # App icon PNGs (32–1024 px)
│   └── style.css             # Light/dark appearance, compact rows
├── tests/
│   ├── test_core.py
│   ├── test_desktop.py
│   ├── test_metadata.py
│   ├── test_importer.py
│   ├── test_selection.py
│   └── test_results.py
├── docs/RELEASING.md          # Manual release checklist
├── .github/workflows/ci.yml  # Linux test/build artifact workflow
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
git commit -m "Refine MonkeyGain v0.6.3 interface"
git push origin main
```

The repository README, comments, interface messages, contributing guide, and changelog are written in **English**. Previous Git commit messages retain their original language unless you explicitly rewrite Git history; history rewriting is neither required nor recommended just to translate a repository.

## Roadmap

- More manual GTK accessibility testing with assistive technologies and narrow windows.
- Optional metadata-based album grouping for multidisc releases.
- Persistent scan history, result export to CSV, and Flatpak distribution.
- Broader metadata support for less common tag containers, with stronger post-write verification.
- Dynamic file format detection based on the installed rsgain version.

## License

Original MonkeyGain source code is licensed under the MIT License; see [LICENSE](LICENSE). Third-party components, including rsgain and GTK, retain their own licenses. Not affiliated with the rsgain project or elementary OS.

## Large-collection performance notes (v0.4.1)

- Discovery progress is indeterminate because the total number of supported files is not known until traversal completes. The discovered-file count is real.
- Tag reading progresses with actual inspected/total file counts in batches of 64. The library becomes navigable as batches arrive, though many files may still be processing. In-memory album grouping does not repeat filesystem stat calls on the GTK thread.
- Only **40 album rows per page** and **60 track rows per expansion batch** are created, keeping UI widget counts bounded even when the imported queue contains thousands of albums. Switching pages and applying filters never removes albums from the scan queue.
- Album artwork is not loaded, decoded, cached, or displayed. This keeps import and navigation focused on ReplayGain.
- The one **Cancel** button stops whichever operation is active (import or scan). Cancelling an import preserves batches already imported.
- For an initial test, turn **Write Tags** off. Test with your actual collection, since responsiveness depends on storage speed, codecs, metadata sizes, and desktop hardware. Automated importer tests use mock metadata instead of timing real disks.

## Album selection in v0.4.2

- **Scan All** deliberately ignores checkboxes and filters and scans every imported album.
- **Scan Selected** requires at least one checked album. Checked albums remain selected if you change pages or search terms.
- **Select Matches** adds all albums matching the current text and tag-status filters, not merely the visible 40. Previously checked albums remain checked.
- **Clear Selection** resets checkboxes but leaves all imported files untouched.
- Removing an album or clearing the queue removes its selection.
- Importing more files preserves selections of already-imported albums; newly imported albums are unchecked until you select them.
- With **Write Tags** enabled, the confirmation dialog states how many audio files are in the **actual scan scope**. With it disabled, the scan only reads and reports loudness.

### Upgrade from v0.4.1

When extracting this release on top of a prior checkout, remove two obsolete
artwork-only source files, which are no longer shipped in the archive:

```bash
cd /data/Projects/MonkeyGain
rm -f monkeygain/artwork.py tests/test_artwork.py
python3 -m unittest discover -s tests -v
```

This does not touch any music, icon, preferences or Git history.

### Visible results after scanning (0.5.3)

When a scan finishes and automatic following is still enabled, MonkeyGain
expands the most recently scanned album containing measurements. This preserves
immediate access to per-track Loudness, Gain and Peak without expanding the
whole library or changing pages unexpectedly. Each album has an explicit
**View results / Hide results** control. Existing tracks can be displayed before
scanning with **Show tracks**. Results remain available in the imported queue
until the album is removed or cleared. A scanned album hidden by a filter or on
another page can be viewed by navigating to it and using **View results**.

From v0.5.3, the visible console panel is removed. The main interface is focused on scan status and track results. Per-track results remain available
in expanded album rows. Nothing changed in the `rsgain` command or tag writing.


## Focus and progress in v0.5.3

- MonkeyGain uses **one progress area in the footer** for both music import and ReplayGain scanning. Import discovery is indeterminate; tag reading shows actual inspected files, while scans show completed album counts with an animated busy indicator. No per-track percentage is fabricated.
- **Analysis Activity** and the raw console have been removed from the main view. Technical output is kept out of the interface.
- Scanning updates existing album rows **in place** rather than rebuilding the list at scan start. Expanded track details, search, selection and scroll position are retained.
- During a scan, the current album is highlighted and followed across visible pages. Manual searching, paging or scrolling suspends automatic following so the app does not fight your navigation. The last scanned album is expanded when results are ready, provided auto-follow remained enabled.
- The library remains bounded to 40 albums per page and 60 track rows per expansion batch. This release does not change ReplayGain computation, tag-writing semantics, or existing LUFS behavior.
