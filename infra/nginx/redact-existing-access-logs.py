#!/usr/bin/env python3
from __future__ import annotations

import gzip
import os
from pathlib import Path
import re
import shutil
import tempfile


LOG_DIR = Path("/var/log/nginx")
REQUEST_LINE = re.compile(
    r'^(?P<prefix>.*?"[A-Z]+ )(?P<target>\S+)(?P<protocol> HTTP/[0-9.]+"\s+\d+\s+\d+\s+)'
    r'"(?P<referrer>[^"]*)"(?P<tail>\s+".*)$'
)


def redact_line(line: str) -> tuple[str, bool]:
    match = REQUEST_LINE.match(line.rstrip("\n"))
    if match is None:
        return line, False
    target = match.group("target").split("?", 1)[0]
    redacted = (
        f'{match.group("prefix")}{target}{match.group("protocol")}'
        f'"-"{match.group("tail")}\n'
    )
    return redacted, redacted != line


def rewrite(path: Path) -> tuple[int, int]:
    compressed = path.suffix == ".gz"
    opener = gzip.open if compressed else open
    read_kwargs = {"mode": "rt", "encoding": "utf-8", "errors": "replace"}
    write_kwargs = {"mode": "wt", "encoding": "utf-8"}
    total = 0
    changed = 0
    with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with opener(path, **read_kwargs) as source, opener(temporary, **write_kwargs) as destination:
            for line in source:
                total += 1
                value, was_changed = redact_line(line)
                changed += int(was_changed)
                destination.write(value)
        shutil.copystat(path, temporary)
        os.chown(temporary, path.stat().st_uid, path.stat().st_gid)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return total, changed


def main() -> None:
    paths = sorted(
        path for path in LOG_DIR.glob("access.log.*")
        if path.is_file()
    )
    total_lines = 0
    changed_lines = 0
    for path in paths:
        total, changed = rewrite(path)
        total_lines += total
        changed_lines += changed
    print(f"Sanitized {changed_lines} of {total_lines} archived Nginx access-log lines across {len(paths)} files")


if __name__ == "__main__":
    main()
