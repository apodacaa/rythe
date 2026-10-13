from datetime import datetime, timedelta, timezone

from rythe.entry import Entry, id_for

TZ = timezone(timedelta(hours=2))


def test_id_for_strips_colons():
    dt = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    assert id_for(dt) == "2026-09-30T164608"


def test_round_trip_with_title_and_body():
    dt = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    entry = Entry(id="2026-09-30T164608", created=dt, source="cli", title="My day", body="hello #tag\n")

    restored = Entry.from_markdown(entry.id, entry.to_markdown())

    assert restored.created == dt
    assert restored.source == "cli"
    assert restored.title == "My day"
    assert restored.body == "hello #tag\n"


def test_round_trip_empty_title_and_body():
    dt = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    entry = Entry(id="2026-09-30T164608", created=dt)

    restored = Entry.from_markdown(entry.id, entry.to_markdown())

    assert restored.title == ""
    assert restored.body == ""
    assert restored.updated is None


def test_updated_omitted_from_markdown_when_none():
    dt = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    entry = Entry(id="x", created=dt)
    assert "updated:" not in entry.to_markdown()


def test_updated_round_trips_when_set():
    created = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    updated = datetime(2026, 10, 1, 9, 0, 0, tzinfo=TZ)
    entry = Entry(id="x", created=created, updated=updated, body="edited body")

    restored = Entry.from_markdown(entry.id, entry.to_markdown())

    assert restored.updated == updated


def test_title_with_colon_round_trips():
    dt = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    entry = Entry(id="x", created=dt, title='A title: with a colon and a "quote"', body="body")

    restored = Entry.from_markdown(entry.id, entry.to_markdown())

    assert restored.title == 'A title: with a colon and a "quote"'


def test_memo_fields_round_trip():
    dt = datetime(2026, 9, 30, 16, 46, 8, tzinfo=TZ)
    entry = Entry(
        id="x",
        created=dt,
        source="memo",
        message_id="<abc@mail>",
        audio="audio/x.m4a",
        transcriber="whisper.cpp small",
        body="transcribed text",
    )

    restored = Entry.from_markdown(entry.id, entry.to_markdown())

    assert restored.source == "memo"
    assert restored.message_id == "<abc@mail>"
    assert restored.audio == "audio/x.m4a"
    assert restored.transcriber == "whisper.cpp small"
