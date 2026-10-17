#!/usr/bin/env python3
"""Start MonkeyGain with its system-provided GTK dependencies."""
import sys


def main() -> int:
    try:
        from monkeygain.app import main as start
    except (ImportError, ValueError) as exc:
        print('MonkeyGain requires GTK 4, PyGObject and its system dependencies.\n'
              'Install the MonkeyGain .deb with APT or restore the packages listed in README.md.\n'
              f'Details: {exc}', file=sys.stderr)
        return 1
    return start()


if __name__ == '__main__':
    raise SystemExit(main())
