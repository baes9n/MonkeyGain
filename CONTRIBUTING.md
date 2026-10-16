# Contributing to MonkeyGain

Thanks for your interest in contributing! MonkeyGain is a small, independent GTK 4 project.

## Development environment

We target Python 3.12+, GTK 4, and rsgain 3.4 or newer. Linux packages supply PyGObject and GTK. Clone the project and open it in VS Code if you prefer working with an IDE.

## Before submitting a pull request

1. Keep application code, comments, documentation, and commit messages in **English**.
2. Prefer native GTK widgets and preserve accessibility and keyboard navigation.
3. Keep filesystem discovery, command generation, and parsing in `monkeygain/core.py` so they can be tested without a display.
4. Avoid shell interpolation; pass argument arrays to subprocesses.
5. Do not re-encode audio or silently overwrite tags. Keep a safe scan-only mode and explicit confirmation.
6. Run the tests:

   ```bash
   python3 -m unittest discover -s tests -v
   ```

7. Test the GTK interface on a Linux desktop, in both light and dark modes. Use disposable audio copies for any tag-writing tests.

## Reporting issues

Include your distribution, Python / GTK / rsgain versions, steps to reproduce, and relevant log output. **Remove private file paths and other personal information** before sharing logs publicly.

## Scope and roadmap

See [README.md](README.md) for existing functionality and planned enhancements. Keep changes focused and explain any changes to backend command-line flags.
