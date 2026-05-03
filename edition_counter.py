# edition_counter.py — auto-increment edition number
from __future__ import annotations

import os
from pathlib import Path

EDITION_FILE = Path(os.getenv("INTEL_EDITION_FILE", "edition.txt"))


def get_next_edition() -> int:
    if EDITION_FILE.exists():
        try:
            return int(EDITION_FILE.read_text().strip()) + 1
        except ValueError:
            pass
    return 1


def save_edition(n: int) -> None:
    EDITION_FILE.write_text(str(n))


def main() -> None:
    edition = get_next_edition()
    save_edition(edition)
    # Print so run_weekly.sh can capture it
    print(edition)


if __name__ == "__main__":
    main()
