#!/usr/bin/env python3
"""Read-only audit of a built MonkeyGain Debian package before publication.

This is not an installed-app or GTK integration test. It checks package
metadata and the exact files shipped to end users, without invoking rsgain.
"""
from __future__ import annotations

import argparse
import ast
import gzip
from pathlib import Path
import struct
import subprocess
import tempfile

APP_ID = 'io.github.baes9n.MonkeyGain'
ICON_SIZES = (32, 48, 64, 128, 256, 512)
REQUIRED_DEPENDENCIES = (
    'python3', 'python3-gi', 'python3-gi-cairo',
    'gir1.2-gtk-4.0', 'python3-mutagen', 'rsgain',
)


class PackageError(RuntimeError):
    """Package is incomplete, unexpected, or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def _version_from_module(package_dir: Path) -> str:
    code = (package_dir / 'usr/lib/monkeygain/monkeygain/__init__.py').read_text(encoding='utf-8')
    module = ast.parse(code)
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == '__version__'
            for target in node.targets
        ) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    raise PackageError('Python application version is absent')


def verify(package: Path) -> str:
    """Validate a .deb; return its version or raise PackageError."""
    _require(package.is_file(), f'Package does not exist: {package}')
    fields: dict[str, str] = {}
    for field in ('Package', 'Version', 'Architecture', 'Depends'):
        completed = subprocess.run(['dpkg-deb', '--field', str(package), field],
                                   check=True, text=True, capture_output=True)
        fields[field] = completed.stdout.strip()
    _require(fields['Package'] == 'monkeygain', 'Unexpected Debian package name')
    _require(fields['Architecture'] == 'all', 'Expected architecture-independent package')
    _require(bool(fields['Version']), 'Missing Debian package version')
    for dep in REQUIRED_DEPENDENCIES:
        _require(any(part.strip().split(' ')[0] == dep for part in fields['Depends'].split(',')),
                 f'Missing required Debian dependency: {dep}')

    with tempfile.TemporaryDirectory(prefix='monkeygain-verify-') as tmp:
        root = Path(tmp)
        subprocess.run(['dpkg-deb', '--extract', str(package), str(root)], check=True)
        binary = root / 'usr/bin/monkeygain'
        _require(binary.is_file() and bool(binary.stat().st_mode & 0o111),
                 'Missing or non-executable launcher')
        launcher = binary.read_text(encoding='utf-8')
        _require('exec /usr/bin/python3 /usr/lib/monkeygain/run.py "$@"' in launcher,
                 'Launcher does not use packaged code or pass files safely')
        _require('/data/Projects' not in launcher and '/home/' not in launcher,
                 'Launcher contains a development-specific path')

        entry = root / f'usr/share/applications/{APP_ID}.desktop'
        _require(entry.is_file(), 'Missing desktop entry')
        desktop = entry.read_text(encoding='utf-8')
        _require(f'Icon={APP_ID}' in desktop, 'Desktop icon identity mismatch')
        _require('Exec=/usr/bin/monkeygain %F' in desktop,
                 'Desktop entry does not invoke the packaged launcher')
        for size in ICON_SIZES:
            icon = root / f'usr/share/icons/hicolor/{size}x{size}/apps/{APP_ID}.png'
            _require(icon.is_file(), f'Missing {size}px icon')
            with icon.open('rb') as f:
                header = f.read(24)
            _require(header[:8] == b'\x89PNG\r\n\x1a\n' and len(header) == 24,
                     f'Invalid {size}px PNG')
            _require(struct.unpack('>II', header[16:24]) == (size, size),
                     f'Wrong pixel dimensions in {size}px PNG')
        app_root = root / 'usr/lib/monkeygain'
        _require((app_root / 'run.py').is_file(), 'Missing startup script')
        _require((app_root / 'monkeygain/app.py').is_file(), 'Missing GUI module')
        _require((app_root / 'monkeygain/core.py').is_file(), 'Missing ReplayGain engine module')
        _require((app_root / 'assets/style.css').is_file(), 'Missing GTK styles')
        installed_version = _version_from_module(root)
        _require(installed_version == fields['Version'],
                 'Debian package and Python code version do not match')
        changelog = root / 'usr/share/doc/monkeygain/changelog.gz'
        _require(changelog.is_file(), 'Missing packaged changelog')
        _require(f'[{installed_version}]' in gzip.decompress(changelog.read_bytes()).decode('utf-8'),
                 'Changelog does not include packaged version')
    return fields['Version']


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify a built MonkeyGain .deb before release')
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    try:
        version = verify(args.package.resolve())
    except (OSError, subprocess.CalledProcessError, PackageError, UnicodeError) as exc:
        parser.exit(1, f'Package verification failed: {exc}\n')
    print(f'MonkeyGain {version}: Debian package verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
