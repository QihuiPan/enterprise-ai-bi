from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_ENGLISH_WORD = re.compile(r"\b[A-Za-z]{2,}\b")
_CJK_CHARACTER = re.compile(r"[\u3400-\u9fff]")


def changed_files(base: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def file_at_revision(revision: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def unreleased_bullets(content: str) -> Counter[str]:
    lines = content.splitlines()
    try:
        start = lines.index("## [Unreleased]") + 1
    except ValueError:
        return Counter()
    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith("## [")
        ),
        len(lines),
    )
    return Counter(
        line.strip()
        for line in lines[start:end]
        if line.lstrip().startswith("- ")
    )


def has_new_english_unreleased_bullet(base_content: str, current_content: str) -> bool:
    added = unreleased_bullets(current_content) - unreleased_bullets(base_content)
    return any(
        len(_ENGLISH_WORD.findall(bullet)) >= 2
        and _CJK_CHARACTER.search(bullet) is None
        for bullet in added
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Require an English changelog update in each PR.")
    parser.add_argument("--base", required=True, help="Git base reference, for example origin/main")
    args = parser.parse_args()

    files = changed_files(args.base)
    meaningful = {path for path in files if path != "CHANGELOG.md"}
    if meaningful:
        if "CHANGELOG.md" not in files:
            print(
                "CHANGELOG.md must be updated in English with every meaningful "
                "pull request."
            )
            return 1
        current = Path("CHANGELOG.md").read_text(encoding="utf-8")
        base_content = file_at_revision(args.base, "CHANGELOG.md")
        if not has_new_english_unreleased_bullet(base_content, current):
            print(
                "Add at least one new English bullet under '## [Unreleased]' in "
                "CHANGELOG.md."
            )
            return 1
    print("Changelog policy satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
