from rythe.tags import extract_tags, normalize_tag


def test_extracts_simple_tag():
    assert extract_tags("had a good day #gratitude") == ["gratitude"]


def test_lowercases_and_dedupes():
    assert extract_tags("#Work stuff #work again") == ["work"]


def test_skips_markdown_heading():
    assert extract_tags("# Heading\nbody text") == []


def test_skips_url_fragment():
    assert extract_tags("see https://example.com/page#frag") == []


def test_skips_double_hash():
    assert extract_tags("##x not a tag") == []


def test_preserves_first_seen_order():
    assert extract_tags("#b then #a then #b again") == ["b", "a"]


def test_normalize_tag_strips_leading_hash_and_lowercases():
    assert normalize_tag("#Focus") == "focus"
    assert normalize_tag("focus") == "focus"
