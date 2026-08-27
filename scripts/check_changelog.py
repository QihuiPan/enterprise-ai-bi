from __future__ import annotations

import argparse
import subprocess
import sys


def changed_files(base: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Require an English changelog update in each PR.")
    parser.add_argument("--base", required=True, help="Git base reference, for example origin/main")
    args = parser.parse_args()

    files = changed_files(args.base)
    meaningful = {path for path in files if path != "CHANGELOG.md"}
    if meaningful and "CHANGELOG.md" not in files:
        print("CHANGELOG.md must be updated in English with every meaningful pull request.")
        return 1
    print("Changelog policy satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
