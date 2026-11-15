"""
Source files spell invisible characters as escapes: a literal one is unreadable and easy to paste by mistake.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Zero-width and format characters, soft hyphen, and the blanks channels use as spacers
INVISIBLE = {*range(0x200B, 0x2010), *range(0x2060, 0x2065), 0x00AD, 0x115F, 0x1160, 0x2800, 0x3164, 0xFEFF, 0xFFA0}
SOURCES = sorted([*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/**/*.py")])


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_source_has_no_literal_invisible_characters(path):
    found = [
        f"line {number}: U+{ord(char):04X}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for char in line
        if ord(char) in INVISIBLE
    ]
    assert not found, f"write these as escapes (\\u....): {found}"
