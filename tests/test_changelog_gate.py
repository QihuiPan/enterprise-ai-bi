from __future__ import annotations

from scripts.check_changelog import has_new_english_unreleased_bullet

BASE = """# Changelog

## [Unreleased]

### Added

- Existing English entry.

## [0.1.0]

- Initial release.
"""


def test_gate_accepts_new_english_unreleased_bullet() -> None:
    current = BASE.replace(
        "- Existing English entry.",
        "- Existing English entry.\n- Added validated production controls.",
    )
    assert has_new_english_unreleased_bullet(BASE, current)


def test_gate_rejects_non_english_unreleased_bullet() -> None:
    current = BASE.replace(
        "- Existing English entry.",
        "- Existing English entry.\n- 新增 API 安全控制。",
    )
    assert not has_new_english_unreleased_bullet(BASE, current)


def test_gate_rejects_entry_added_only_to_released_section() -> None:
    current = BASE.replace("- Initial release.", "- Initial release.\n- Added old fix.")
    assert not has_new_english_unreleased_bullet(BASE, current)
