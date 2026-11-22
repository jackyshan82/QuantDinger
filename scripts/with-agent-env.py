#!/usr/bin/env python3
"""Run a command with private QuantDinger Agent Gateway credentials."""

import os
from pathlib import Path
import stat
import sys


def main():
    command = sys.argv[1:]
    if command and command[0] == "--":
        command = command[1:]
    if not command or command[0] in {"-h", "--help"}:
        print("Usage: python scripts/with-agent-env.py <command> [arguments ...]")
        return 0 if command else 2

    environment = os.environ.copy()
    keys = ("QUANTDINGER_BASE_URL", "QUANTDINGER_AGENT_TOKEN")
    if not all(environment.get(key) for key in keys):
        path = Path(environment.get(
            "QUANTDINGER_AGENT_ENV", "~/.config/quantdinger/agent.env",
        )).expanduser()
        try:
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ValueError("Private agent configuration must be a mode-0600 file.")
            if hasattr(os, "getuid") and info.st_uid != os.getuid():
                raise ValueError("Private agent configuration must belong to the current user.")
            for line in path.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key in keys and not environment.get(key):
                    environment[key] = value.strip()
        except (OSError, ValueError) as error:
            print(f"Cannot load private Agent Gateway configuration ({type(error).__name__}).", file=sys.stderr)
            return 2

    if not all(environment.get(key) for key in keys):
        print("Agent Gateway URL and token are required.", file=sys.stderr)
        return 2
    try:
        os.execvpe(command[0], command, environment)
    except OSError as error:
        print(f"Cannot launch the requested command ({type(error).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
