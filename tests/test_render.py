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


def test_resurface_prefers_the_longest_lookback():
    from datetime import date

    today = date(2026, 10, 4)
    for when, body in ((date(2024, 10, 4), "two years"), (date(2025, 10, 4), "one year"), (date(2026, 9, 4), "month"), (date(2026, 9, 27), "week")):
        store.create(created=datetime(when.year, when.month, when.day, 12, tzinfo=TZ), body=body)

    label, found = store.resurface(today)
    assert label == "2 years ago today" and found.body.strip() == "two years"


def test_resurface_falls_back_to_month_then_week_then_none():
    from datetime import date

    today = date(2026, 10, 31)
    assert store.resurface(today) is None
    store.create(created=datetime(2026, 10, 24, 8, tzinfo=TZ), body="week")
    assert store.resurface(today)[0] == "a week ago today"
    store.create(created=datetime(2026, 9, 30, 8, tzinfo=TZ), body="month")  # Sep has no 31st
    assert store.resurface(today)[0] == "a month ago today"


def test_new_prints_resurfaced_line_only_on_a_terminal_without_json(capsys, monkeypatch):
    _at(7, "a week back")
    monkeypatch.setattr("rythe.cli._interactive", lambda: True)

    main(["new", "--text", "today"])
    out = capsys.readouterr().out
    assert "a week ago today: a week back" in out

    main(["new", "--text", "again", "--json"])
    payload = json.loads(capsys.readouterr().out)  # only JSON: the human line isn't printed
    assert payload["resurfaced"]["label"] == "a week ago today"  # it's carried in the JSON instead

    monkeypatch.setattr("rythe.cli._interactive", lambda: False)
    main(["new", "--text", "piped"])
    assert "ago today" not in capsys.readouterr().out
