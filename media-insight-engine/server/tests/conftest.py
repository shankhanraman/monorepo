import textwrap
from pathlib import Path

import pytest

LENS = """\
name: test-lens
domain: Admissions
reader_role: Counselor
focus: Essays and testing
tags: [testing, essays, why-major]
segment_seconds: 60
stale_after_months: 18
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    write(tmp_path / "lenses" / "test-lens.yaml", LENS)
    return tmp_path
