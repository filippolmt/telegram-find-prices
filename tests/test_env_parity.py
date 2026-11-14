"""
Every environment variable read in src/ must reach the container and be documented in the templates.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
READ_VARS = {
    name
    for path in (ROOT / "src").glob("*.py")
    for name in re.findall(r'getenv\(\s*"([A-Z0-9_]+)"', path.read_text())
}


def test_src_reads_some_variables():
    # Guards the regex: an empty set would make every check below pass vacuously.
    assert {"BOT_TOKEN", "ALLOWED_USERS"} <= READ_VARS


@pytest.mark.parametrize(("file", "pattern"), [
    ("production/docker-compose.yml", r"^\s+([A-Z0-9_]+):"),
    # Optional variables are documented commented out: "# NAME=default".
    ("example.env", r"^(?:#\s*)?([A-Z0-9_]+)="),
    ("production/example.env", r"^(?:#\s*)?([A-Z0-9_]+)="),
])
def test_every_variable_is_listed(file, pattern):
    listed = set(re.findall(pattern, (ROOT / file).read_text(), re.MULTILINE))
    assert sorted(READ_VARS - listed) == []
