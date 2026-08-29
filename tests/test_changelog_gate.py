from __future__ import annotations

from subprocess import CompletedProcess

from scripts import check_changelog
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


def test_git_content_is_decoded_as_utf8_on_windows(monkeypatch) -> None:
    def fake_run(command, **options):
        assert options["encoding"] == "utf-8"
        return CompletedProcess(command, 0, stdout="- Added CJK-safe UTF-8 support.\n")

    monkeypatch.setattr(check_changelog.subprocess, "run", fake_run)

    assert (
        check_changelog.file_at_revision("base", "CHANGELOG.md")
        == "- Added CJK-safe UTF-8 support.\n"
    )
