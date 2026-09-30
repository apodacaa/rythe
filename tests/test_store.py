from datetime import datetime, timedelta, timezone

import pytest

from journal import store

TZ = timezone(timedelta(hours=2))


def dt(h, m=0, s=0):
    return datetime(2026, 9, 30, h, m, s, tzinfo=TZ)


def test_create_writes_file_at_year_month_path(journal_dir):
    entry = store.create(created=dt(16, 46, 8), body="hello #work")
    path = journal_dir / "entries" / "2026" / "09" / f"{entry.id}.md"
    assert path.exists()


def test_create_handles_id_collision_with_suffix():
    a = store.create(created=dt(16, 46, 8), body="one")
    b = store.create(created=dt(16, 46, 8), body="two")
    assert b.id == f"{a.id}-2"


def test_get_round_trip():
    created = store.create(created=dt(9, 0), body="morning pages #reflect")
    fetched = store.get(created.id)
    assert fetched.body == "morning pages #reflect\n"


def test_get_missing_raises_entry_not_found():
    with pytest.raises(store.EntryNotFoundError):
        store.get("2026-01-01T000000")


def test_list_filters_by_tag():
    store.create(created=dt(8), body="#work morning standup")
    store.create(created=dt(20), body="#personal evening walk")
    results = store.list_entries(tags=["work"])
    assert len(results) == 1
    assert "work" in results[0].body


def test_list_filters_by_since():
    store.create(created=dt(8), body="morning")
    store.create(created=dt(20), body="evening")
    results = store.list_entries(since=dt(12))
    assert len(results) == 1
    assert results[0].body.startswith("evening")


def test_list_sorted_newest_first():
    store.create(created=dt(8), body="first")
    store.create(created=dt(20), body="second")
    results = store.list_entries()
    assert [e.body.strip() for e in results] == ["second", "first"]


def test_search_returns_matching_lines_only():
    store.create(created=dt(8), body="line one\nline about coffee\nline three")
    results = store.search("coffee")
    assert len(results) == 1
    entry, matches = results[0]
    assert matches == ["line about coffee"]


def test_search_is_case_insensitive_by_default():
    store.create(created=dt(8), body="Coffee in the morning")
    results = store.search("coffee")
    assert len(results) == 1


def test_search_regex():
    store.create(created=dt(8), body="temp was 72F today")
    results = store.search(r"\d+F", regex=True)
    assert len(results) == 1


def test_create_with_duplicate_message_id_raises():
    store.create(created=dt(8), body="memo one", source="memo", message_id="<abc@mail>")
    with pytest.raises(store.DuplicateMessageError):
        store.create(created=dt(9), body="memo again", source="memo", message_id="<abc@mail>")


def test_create_with_duplicate_message_id_and_force_succeeds():
    store.create(created=dt(8), body="memo one", source="memo", message_id="<abc@mail>")
    second = store.create(
        created=dt(9), body="memo again", source="memo", message_id="<abc@mail>", force=True
    )
    assert second.message_id == "<abc@mail>"


def test_find_by_message_id():
    entry = store.create(created=dt(8), body="memo", source="memo", message_id="<xyz@mail>")
    found = store.find_by_message_id("<xyz@mail>")
    assert found is not None
    assert found.id == entry.id
    assert store.find_by_message_id("<nope@mail>") is None


def test_tag_counts():
    store.create(created=dt(8), body="#work #focus")
    store.create(created=dt(9), body="#work")
    counts = store.tag_counts()
    assert counts == {"work": 2, "focus": 1}


def test_add_tags_appends_only_missing_tags():
    entry = store.create(created=dt(8), body="had a day #work")
    updated = store.add_tags(entry.id, ["work", "focus"])
    assert updated.body.count("#work") == 1
    assert "#focus" in updated.body


def test_add_tags_on_missing_entry_raises():
    with pytest.raises(store.EntryNotFoundError):
        store.add_tags("2026-01-01T000000", ["work"])
