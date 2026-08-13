# edition_counter.py — auto-increment edition number
from __future__ import annotations

import os
from pathlib import Path
import sys

EDITION_FILE = Path(os.getenv("INTEL_EDITION_FILE", "edition.txt"))


def get_next_edition() -> int:
    if EDITION_FILE.exists():
        try:
            return int(EDITION_FILE.read_text().strip()) + 1
        except ValueError:
            pass
    return 1


def save_edition(n: int) -> None:
    temporary = EDITION_FILE.with_suffix(EDITION_FILE.suffix + ".tmp")
    temporary.write_text(str(n), encoding="utf-8")
    temporary.replace(EDITION_FILE)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "next"
    if command == "--peek":
        print(get_next_edition())
        return
    if command == "--commit":
        if len(sys.argv) != 3 or not sys.argv[2].isdigit() or int(sys.argv[2]) < 1:
            raise SystemExit("usage: edition_counter.py --commit NUMBER")
        save_edition(int(sys.argv[2]))
        return
    if command != "next":
        raise SystemExit("usage: edition_counter.py [--peek | --commit NUMBER]")

    edition = get_next_edition()
    save_edition(edition)
    print(edition)


if __name__ == "__main__":
    main()
