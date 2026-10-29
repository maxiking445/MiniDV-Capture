#!/usr/bin/env python3
"""Keep Python package, UI and Arch package versions in sync for releases."""
from pathlib import Path
import re
import sys


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', sys.argv[1]):
        raise SystemExit('Usage: set-version.py MAJOR.MINOR.PATCH')
    version = sys.argv[1]
    changes = {
        Path('pyproject.toml'): (r'(?m)^version = "[^"]+"$', f'version = "{version}"'),
        Path('minidv_capture/__init__.py'): (r'(?m)^__version__ = "[^"]+"$', f'__version__ = "{version}"'),
        Path('packaging/PKGBUILD'): (r'(?m)^pkgver=[^\n]+$', f'pkgver={version}'),
    }
    for path, (pattern, replacement) in changes.items():
        text = path.read_text()
        updated, count = re.subn(pattern, replacement, text)
        if count != 1:
            raise SystemExit(f'Expected exactly one version in {path}, found {count}')
        path.write_text(updated)


if __name__ == '__main__':
    main()
