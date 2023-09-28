#!/usr/bin/env python
"""A simple script to update the version embedded in the source."""

import argparse
import pathlib
import re

from packaging.version import Version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', type=Version, help='version number to embed in source files')
    args = parser.parse_args()
    version: Version = args.version

    major_minor_version = f'{version.major}.{version.minor}'
    version_info = ', '.join(map(repr, get_version_info(version)))

    updates: list[tuple[str, re.Pattern, str | Version]] = [
        ('doc/source/conf.py', re.compile(r"^(version = ')[^']*(')$", flags=re.MULTILINE), major_minor_version),
        ('doc/source/conf.py', re.compile(r"^(release = ')[^']*(')$", flags=re.MULTILINE), version),
        ('setup.py', re.compile(r"^( +version=')[^']*(',)$", flags=re.MULTILINE), version),
        ('src/c/_cffi_backend.c', re.compile(r'^(#define CFFI_VERSION +")[^"]*(")$', flags=re.MULTILINE), version),
        ('src/c/test_c.py', re.compile(r'^(assert __version__ == ")[^"]*(", .*)$', flags=re.MULTILINE), version),
        ('src/cffi/__init__.py', re.compile(r'^(__version__ = ")[^"]*(")$', flags=re.MULTILINE), version),
        ('src/cffi/__init__.py', re.compile(r'^(__version_info__ = \()[^)]*(\))$', flags=re.MULTILINE), version_info),
        ('src/cffi/_embedding.h', re.compile(r'^( +"\\ncompiled with cffi version: )[^"]*(")$', flags=re.MULTILINE), version),
    ]

    repo_root = pathlib.Path(__file__).parent.parent

    for relative_path, pattern, replacement in updates:
        path = repo_root / relative_path
        original_content = path.read_text()

        if not pattern.search(original_content):
            raise RuntimeError(f'{relative_path}: no match found for pattern: {pattern.pattern}')

        updated_content = pattern.sub(rf'\g<1>{replacement}\g<2>', original_content)

        if updated_content == original_content:
            print(f'{relative_path}: unchanged')
        else:
            path.write_text(updated_content)
            print(f'{relative_path}: updated')


def get_version_info(version: Version) -> tuple:
    """Return a tuple representing the given version."""
    version_info = list(version.release)

    if version.pre is not None:
        version_info.append(''.join(map(str, version.pre)))

    if version.post is not None:
        version_info.append(f'post{version.post}')

    if version.dev is not None:
        version_info.append(f'dev{version.dev}')

    if version.local is not None:
        version_info.append(f'+{version.local}')

    return tuple(version_info)


if __name__ == '__main__':
    main()
