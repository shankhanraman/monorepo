import pytest

from app.config import ConfigError, InvalidEntry, SourceEntry, collection_slugs, load_collection
from tests.conftest import write


def test_shared_lens_plus_college_tags_and_focus_note(config_dir):
    write(config_dir / "collections" / "yale.yaml", """\
        name: Yale
        lens: test-lens
        focus_note: Early Action
        tags: [ea-ed, essays]
        sources:
          - url: https://www.youtube.com/watch?v=abcdefghijk
            priority: high
    """)
    col = load_collection("yale", config_dir)
    assert col.name == "Yale" and col.lens_name == "test-lens"
    assert col.lens.tags == ["testing", "essays", "why-major", "ea-ed"]      # added, de-duplicated
    assert "Collection note: Early Action" in col.lens_text
    assert isinstance(col.entries[0], SourceEntry) and col.entries[0].priority == "high"


def test_inline_lens_overrides_shared_fields(config_dir):
    write(config_dir / "collections" / "mit.yaml", """\
        name: MIT
        lens: {extends: test-lens, focus: Research and makers, segment_seconds: 120}
    """)
    col = load_collection("mit", config_dir)
    assert col.lens.focus == "Research and makers" and col.lens.segment_seconds == 120
    assert col.lens.domain == "Admissions"


def test_bad_entry_fails_alone(config_dir):
    write(config_dir / "collections" / "yale.yaml", """\
        name: Yale
        lens: test-lens
        sources:
          - url: https://example.com/a
          - label: no url here
          - url: https://example.com/b
            type: podcast
    """)
    entries = load_collection("yale", config_dir).entries
    assert isinstance(entries[0], SourceEntry)
    assert isinstance(entries[1], InvalidEntry) and "url" in entries[1].reason
    assert isinstance(entries[2], InvalidEntry) and entries[2].url == "https://example.com/b"


@pytest.mark.parametrize("body, message", [
    ("name: Yale\nlens: nope\n", "lens 'nope' not found"),
    ("lens: test-lens\n", "name"),
    ("name: [unclosed\n", "not valid YAML"),
    ("name: X\nlens: test-lens\nsegment_seconds: 10\n", "segment_seconds"),
])
def test_broken_file_is_a_config_error(config_dir, body, message):
    write(config_dir / "collections" / "yale.yaml", body)
    with pytest.raises(ConfigError, match=message):
        load_collection("yale", config_dir)


def test_lens_value_range_checked(config_dir):
    write(config_dir / "collections" / "yale.yaml", "name: Yale\nlens: {extends: test-lens, segment_seconds: 10}\n")
    with pytest.raises(ConfigError, match="segment_seconds"):
        load_collection("yale", config_dir)


def test_unknown_slug_and_listing(config_dir):
    write(config_dir / "collections" / "yale.yaml", "name: Yale\nlens: test-lens\n")
    write(config_dir / "collections" / "Bad Name.yaml", "name: X\nlens: test-lens\n")
    assert collection_slugs(config_dir) == ["yale"]
    with pytest.raises(FileNotFoundError):
        load_collection("harvard", config_dir)
