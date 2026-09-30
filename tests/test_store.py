from datetime import date, datetime, timedelta, timezone

import pytest

from journal import store

TZ = timezone(timedelta(hours=2))


def dt(h, m=0, s=0):
    return datetime(2026, 9, 30, h, m, s, tzinfo=TZ)


def dt_on(year, month, day, h=12):
    return datetime(year, month, day, h, 0, 0, tzinfo=TZ)


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


def test_list_filters_by_on_exact_date():
    store.create(created=dt_on(2026, 9, 30, 8), body="today")
    store.create(created=dt_on(2026, 10, 1, 8), body="tomorrow")

    results = store.list_entries(on=date(2026, 9, 30))

    assert len(results) == 1
    assert results[0].body.strip() == "today"


def test_list_filters_by_exclude_tag():
    store.create(created=dt(8), body="#work morning standup")
    store.create(created=dt(9), body="#personal evening walk")

    results = store.list_entries(exclude_tags=["work"])

    assert len(results) == 1
    assert "personal" in results[0].body


def test_list_filters_by_untagged():
    store.create(created=dt(8), body="no tags here")
    store.create(created=dt(9), body="#work tagged")

    results = store.list_entries(untagged=True)

    assert len(results) == 1
    assert results[0].body.strip() == "no tags here"


def test_on_this_day_matches_month_and_day_across_years():
    store.create(created=dt_on(2024, 9, 30), body="two years ago")
    store.create(created=dt_on(2025, 9, 30), body="last year")
    store.create(created=dt_on(2025, 10, 1), body="a day off, wrong date")
    store.create(created=dt_on(2026, 9, 30), body="this year")

    results = store.on_this_day(date(2026, 9, 30))

    assert [e.body.strip() for e in results] == ["this year", "last year", "two years ago"]


def test_on_this_day_respects_tag_filter():
    store.create(created=dt_on(2025, 9, 30), body="#work last year")
    store.create(created=dt_on(2024, 9, 30), body="#personal two years ago")

    results = store.on_this_day(date(2026, 9, 30), tags=["work"])

    assert len(results) == 1
    assert "work" in results[0].body


def test_on_this_day_no_matches_returns_empty_list():
    store.create(created=dt_on(2025, 5, 1), body="unrelated date")
    assert store.on_this_day(date(2026, 9, 30)) == []


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


def test_search_with_only_tag_filter_returns_full_body():
    store.create(created=dt(8), body="line one\nline two #work")
    store.create(created=dt(9), body="unrelated #personal")

    results = store.search(tags=["work"])

    assert len(results) == 1
    entry, matches = results[0]
    assert matches == ["line one", "line two #work"]


def test_search_regex_without_query_raises():
    with pytest.raises(ValueError):
        store.search(regex=True)


def test_search_with_exclude_tag():
    store.create(created=dt(8), body="line about coffee #work")
    store.create(created=dt(9), body="line about coffee #personal")

    results = store.search("coffee", exclude_tags=["work"])

    assert len(results) == 1
    entry, _ = results[0]
    assert "personal" in entry.body


def test_search_with_on_date():
    store.create(created=dt_on(2026, 9, 30, 8), body="coffee today")
    store.create(created=dt_on(2026, 10, 1, 8), body="coffee tomorrow")

    results = store.search("coffee", on=date(2026, 9, 30))

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


def test_add_tags_sets_updated_when_a_tag_is_added():
    entry = store.create(created=dt(8), body="had a day")
    assert entry.updated is None

    updated = store.add_tags(entry.id, ["focus"])

    assert updated.updated is not None


def test_add_tags_leaves_updated_alone_when_nothing_new():
    entry = store.create(created=dt(8), body="#work already tagged")
    first = store.add_tags(entry.id, ["work"])
    assert first.updated is None  # "work" was already present, nothing changed

    store.create(created=dt(9), body="unrelated")  # advance the clock a little
    second = store.add_tags(entry.id, ["work"])
    assert second.updated is None


def test_add_tags_on_missing_entry_raises():
    with pytest.raises(store.EntryNotFoundError):
        store.add_tags("2026-01-01T000000", ["work"])


def test_path_for_returns_entry_path():
    entry = store.create(created=dt(8), body="hello")
    path = store.path_for(entry.id)
    assert "hello" in path.read_text()


def test_path_for_missing_raises():
    with pytest.raises(store.EntryNotFoundError):
        store.path_for("2026-01-01T000000")


def test_delete_moves_entry_to_trash():
    entry = store.create(created=dt(8), body="to be deleted")
    original_path = store.path_for(entry.id)

    trashed = store.delete(entry.id)

    assert not original_path.exists()
    assert trashed.exists()
    assert "to be deleted" in trashed.read_text()
    with pytest.raises(store.EntryNotFoundError):
        store.get(entry.id)


def test_touch_sets_updated():
    entry = store.create(created=dt(8), body="hello")
    assert entry.updated is None

    when = dt(9, 30)
    touched = store.touch(entry.id, when)

    assert touched.updated == when
    assert store.get(entry.id).updated == when


def test_touch_missing_raises():
    with pytest.raises(store.EntryNotFoundError):
        store.touch("2026-01-01T000000", dt(8))


def test_delete_missing_raises():
    with pytest.raises(store.EntryNotFoundError):
        store.delete("2026-01-01T000000")


def test_delete_moves_audio_too(journal_dir):
    audio_file = journal_dir / "audio" / "clip.m4a"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"fake audio")

    entry = store.create(created=dt(8), body="a memo", source="memo", audio="audio/clip.m4a")

    trashed = store.delete(entry.id)

    assert not audio_file.exists()
    trashed_audio = list((journal_dir / ".trash" / "audio").glob("clip.*.m4a"))
    assert len(trashed_audio) == 1
    assert trashed_audio[0].read_bytes() == b"fake audio"
    assert trashed.exists()
