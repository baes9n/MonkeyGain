# MonkeyGain release checklist

This guide is for maintainers. The GitHub workflow builds a test artifact; it
does **not** publish a GitHub Release automatically or deploy to any package
repository.

## 1. Review the source

- Update `monkeygain/__init__.py` and create a matching version entry in
  `CHANGELOG.md`.
- Keep the version in the README, tests and package metadata consistent.
- Check `git status` and `git diff` so personal files are not committed.
- Check that the application works in both light and dark appearance modes.
- Test importing a folder, switching pages, selecting albums, and read-only
  `Scan Selected` and `Scan All` before publishing.
- Test tag writing only on expendable copies of audio files. Keep a backup.

## 2. Run the release checks

On elementary OS / Ubuntu with `dpkg-deb` installed:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q monkeygain scripts run.py
python3 scripts/build_deb.py --output-dir dist
python3 scripts/verify_release.py dist/monkeygain_0.6.3_all.deb
(cd dist && sha256sum monkeygain_0.6.3_all.deb > SHA256SUMS)
```

Check that the `.deb` installs and the application starts on a real desktop.
For package upgrades on Debian/Ubuntu, use:

```bash
sudo apt install ./dist/monkeygain_0.6.3_all.deb
```

Never verify tag writing against your only copies of music. `apt remove
monkeygain` removes the packaged application but not your music, Git checkout
or user preferences.

## 3. Push to GitHub

```bash
git status
git add -A
git diff --cached --check
git commit -m "Refine MonkeyGain v0.6.3 interface"
git push origin main
```

The `Linux tests and Debian package` workflow should appear under **Actions**.
It runs on `main`, pull requests, manual dispatch and `v*` tags. A successful
run contains a `.deb` and `SHA256SUMS` as downloadable workflow artifacts.

## 4. Tag and publish only after manual desktop testing

```bash
git tag -a v0.6.3 -m "MonkeyGain v0.6.3"
git push origin v0.6.3
```

On GitHub, open **Releases → Draft a new release**, select `v0.6.3`, paste
release notes derived from `CHANGELOG.md`, and attach the verified `.deb` and
`SHA256SUMS`. Mark the release as a prerelease while platform testing is
incomplete. Do not describe the package as Flatpak, AppCenter or an official
Ubuntu package.

## 5. Installing from GitHub Releases

Users on compatible Debian-based distributions can download the `.deb` and
run `sudo apt install ./monkeygain_0.6.3_all.deb`. This delegates dependency
resolution to APT (including GTK 4, PyGObject, Mutagen and rsgain).

Users can verify the checksum from the same release with `sha256sum -c
SHA256SUMS` while both files are in the same directory.

The developer's per-user launcher created by `install_local.py` can shadow
an installed Debian package. Remove that launcher with
`python3 scripts/install_local.py --uninstall` before installing the `.deb`.
