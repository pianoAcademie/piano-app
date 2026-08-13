#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


NGINX_CONFIG = Path("/etc/nginx/nginx.conf")
SNIPPET_TARGET = Path("/etc/nginx/snippets/piano-redacted-log.conf")
SNIPPET_SOURCE = Path(__file__).with_name("piano-redacted-log.conf")
INCLUDE_LINE = "\tinclude /etc/nginx/snippets/piano-redacted-log.conf;"
ACCESS_LINE = "\taccess_log /var/log/nginx/access.log piano_redacted;"


def install() -> None:
    original = NGINX_CONFIG.read_text(encoding="utf-8")
    updated = original
    if INCLUDE_LINE not in updated:
        marker = "\t# Logging Settings\n\t##\n"
        if marker not in updated:
            raise RuntimeError("Nginx logging section was not found")
        updated = updated.replace(marker, f"{marker}\n{INCLUDE_LINE}\n", 1)

    default_access_line = "\taccess_log /var/log/nginx/access.log;"
    if default_access_line in updated:
        updated = updated.replace(default_access_line, ACCESS_LINE, 1)
    elif ACCESS_LINE not in updated:
        raise RuntimeError("Nginx access_log directive was not found")

    SNIPPET_TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SNIPPET_SOURCE, SNIPPET_TARGET)
    if updated != original:
        NGINX_CONFIG.write_text(updated, encoding="utf-8")

    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)


if __name__ == "__main__":
    try:
        install()
    except Exception as exc:
        print(f"Unable to install redacted Nginx logging: {exc}", file=sys.stderr)
        raise
