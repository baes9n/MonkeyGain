#!/usr/bin/env python3
"""Install or remove MonkeyGain's local desktop integration."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from monkeygain.desktop import install, uninstall  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='MonkeyGain per-user desktop launcher')
    parser.add_argument('--uninstall', action='store_true', help='Remove the menu entry and launcher')
    args = parser.parse_args()
    if args.uninstall:
        removed = uninstall()
        print(f'Removed {len(removed)} installed file(s). Git source and settings are untouched.')
    else:
        paths = install(ROOT)
        print('MonkeyGain installed for the current user.')
        print(f'Application menu entry: {paths.entry}')
        print(f'Launcher: {paths.launcher}')
        print(f'Icon: {paths.icon}')
        print('If the menu does not update immediately, log out and back in.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
