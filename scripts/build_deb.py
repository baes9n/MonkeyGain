#!/usr/bin/env python3
"""Build a dependency-managed Debian package without modifying this checkout.

Requires dpkg-deb (part of dpkg). The package installs into /usr rather than
linking to the developer's home directory or the current Git checkout.
"""
from __future__ import annotations

import argparse
import gzip
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
APP_ID = 'io.github.baes9n.MonkeyGain'
SIZES = (32, 48, 64, 128, 256, 512)
MODULES = ('__init__.py', 'activity.py', 'app.py', 'core.py', 'desktop.py',
           'importer.py', 'metadata.py', 'selection.py', 'startup.py')


def read_version(root: Path = ROOT) -> str:
    import ast
    tree = ast.parse((root / 'monkeygain/__init__.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == '__version__'
            for target in node.targets
        ) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise ValueError('Missing __version__ in monkeygain/__init__.py')


def _install_file(src: Path, dst: Path, *, mode: int = 0o644) -> None:
    if not src.is_file() or src.is_symlink():
        raise FileNotFoundError(f'Missing regular source file: {src}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    dst.chmod(mode)


def stage(root: Path, package_root: Path) -> None:
    """Stage an architecture-independent Debian filesystem for dpkg-deb."""
    from sys import path
    path.insert(0, str(root))
    try:
        from monkeygain.desktop import DesktopPaths, desktop_contents
    finally:
        path.pop(0)

    version = read_version(root)
    lib = package_root / 'usr/lib/monkeygain'
    for source in MODULES:
        _install_file(root / 'monkeygain' / source, lib / 'monkeygain' / source)
    _install_file(root / 'run.py', lib / 'run.py')
    _install_file(root / 'assets/style.css', lib / 'assets/style.css')

    for size in SIZES:
        _install_file(root / 'assets/icons' / f'{size}.png',
                      package_root / f'usr/share/icons/hicolor/{size}x{size}/apps/{APP_ID}.png')

    binary = package_root / 'usr/bin/monkeygain'
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text('#!/bin/sh\n# MonkeyGain system package launcher\n'
                      'exec /usr/bin/python3 /usr/lib/monkeygain/run.py "$@"\n',
                      encoding='utf-8')
    binary.chmod(0o755)

    entry = package_root / f'usr/share/applications/{APP_ID}.desktop'
    entry.parent.mkdir(parents=True, exist_ok=True)
    paths = DesktopPaths(Path('/usr/bin/monkeygain'), entry,
                         package_root / f'usr/share/icons/hicolor/256x256/apps/{APP_ID}.png')
    entry.write_text(desktop_contents(paths), encoding='utf-8')
    entry.chmod(0o644)

    doc = package_root / 'usr/share/doc/monkeygain'
    _install_file(root / 'LICENSE', doc / 'copyright')
    changelog = (root / 'CHANGELOG.md').read_bytes()
    (doc / 'changelog.gz').write_bytes(gzip.compress(changelog, compresslevel=9, mtime=0))
    (doc / 'changelog.gz').chmod(0o644)

    # All packaged files are interpreted Python, metadata, or architecture-
    # independent images. External native libraries come from apt dependencies.
    size_kib = (sum(p.stat().st_size for p in package_root.rglob('*') if p.is_file()) + 1023) // 1024
    control_dir = package_root / 'DEBIAN'
    control_dir.mkdir(parents=True, exist_ok=True)
    control = '\n'.join([
        'Package: monkeygain',
        f'Version: {version}',
        'Section: sound',
        'Priority: optional',
        'Architecture: all',
        'Maintainer: MonkeyGain contributors <baes9n@users.noreply.github.com>',
        f'Installed-Size: {size_kib}',
        'Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, python3-mutagen, rsgain (>= 3.4)',
        'Homepage: https://github.com/baes9n/MonkeyGain',
        'Description: GTK 4 frontend for ReplayGain audio analysis',
        ' Analyze album and track loudness with rsgain, inspect ReplayGain tags,',
        ' and select specific albums for read-only scans or metadata updates.',
        ' Uses the system GTK and rsgain packages; does not re-encode audio.',
        '',
    ])
    (control_dir / 'control').write_text(control, encoding='utf-8')
    (control_dir / 'control').chmod(0o644)


def build(root: Path, output: Path) -> Path:
    if not shutil.which('dpkg-deb'):
        raise RuntimeError('dpkg-deb is required to build a Debian package')
    output.mkdir(parents=True, exist_ok=True)
    target = (output / f'monkeygain_{read_version(root)}_all.deb').resolve()
    with tempfile.TemporaryDirectory(prefix='monkeygain-deb-') as tmp:
        package_dir = Path(tmp) / 'package'
        stage(root, package_dir)
        subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(package_dir),
                        str(target)], check=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description='Build the MonkeyGain Debian package')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    target = build(ROOT, args.output_dir.resolve())
    print(f'Built: {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
