import json
from datetime import datetime, timedelta, timezone

from rythe import store
from rythe.cli import main
from rythe.entry import Entry
from rythe.render import render_entries, render_entry

TZ = timezone(timedelta(hours=2))


def entry(day, hour, body, **kw):
    created = datetime(2026, 10, day, hour, 14, tzinfo=TZ)
    return Entry(id=f"id{day}{hour}", created=created, body=body, **kw)


def test_groups_by_day_and_labels_sources():
    text = render_entries(
        [
            entry(3, 21, "first\n", source="memo"),
            entry(3, 22, "second\n", title="Late"),
            entry(4, 9, "third\n"),
        ]
    )
    assert sum(line.startswith("── ") for line in text.splitlines()) == 2  # one header per day
    assert "Saturday, October 3, 2026" in text and "Sunday, October 4, 2026" in text
    assert "9:14 PM · voice memo" in text
    assert "10:14 PM · “Late”" in text
    assert "9:14 AM\nthird" in text
    assert text.index("first") < text.index("second") < text.index("third")


def test_show_id_appends_id():
    assert "id49" in render_entry(entry(4, 9, "x\n"), show_id=True)
    assert "id49" not in render_entry(entry(4, 9, "x\n"))


def test_read_defaults_to_last_seven_days_oldest_first(capsys):
    now = datetime.now().astimezone()
    store.create(created=now - timedelta(days=30), body="too old")
    store.create(created=now - timedelta(days=2), body="earlier")
    store.create(created=now - timedelta(hours=1), body="later")

    assert main(["read"]) == 0
    out = capsys.readouterr().out
    assert "too old" not in out
    assert out.index("earlier") < out.index("later")


def test_read_filters_and_empty_message(capsys):
    store.create(created=datetime.now().astimezone(), body="work thing #work")
    store.create(created=datetime.now().astimezone() - timedelta(minutes=1), body="home thing #home")

    main(["read", "--tag", "work"])
    out = capsys.readouterr().out
    assert "work thing" in out and "home thing" not in out

    main(["read", "--on", "2001-01-01"])
    assert "nothing written" in capsys.readouterr().out


def test_show_plain_is_prose_and_raw_is_the_file(capsys):
    main(["new", "--text", "hello there", "--json"])
    entry_id = json.loads(capsys.readouterr().out)["id"]

    main(["show", entry_id])
    prose = capsys.readouterr().out
    assert "hello there" in prose and "created:" not in prose and entry_id in prose

    main(["show", entry_id, "--raw"])
    assert "created:" in capsys.readouterr().out


def _at(days_ago, body):
    return store.create(created=datetime.now().astimezone() - timedelta(days=days_ago), body=body)
