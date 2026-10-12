from datetime import time
from unittest.mock import patch

import pytest

from jarvis import scheduler, sources
from jarvis.brain import TriagedEmail


@pytest.mark.parametrize(
    "now,expected",
    [(time(23, 0), True), (time(3, 0), True), (time(7, 29), True), (time(7, 30), False), (time(12, 0), False)],
)
def test_quiet_hours_wraps_midnight(now, expected):
    assert scheduler.in_quiet_hours(now, time(22, 30), time(7, 30)) is expected


def test_quiet_hours_same_day():
    assert scheduler.in_quiet_hours(time(13, 0), time(12, 0), time(14, 0))
    assert not scheduler.in_quiet_hours(time(15, 0), time(12, 0), time(14, 0))


def _email(i):
    from datetime import datetime

    return sources.Email(id=i, sender="a@b.c", subject="s", snippet="x", received=datetime.now())


def test_check_email_alerts_once_per_urgent_email(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler.settings, "state_file", tmp_path / "state.json")
    emails = [_email("1"), _email("2")]
    triaged = [
        TriagedEmail(id="1", important=True, urgent=True, reason="", spoken_summary="Bank alert."),
        TriagedEmail(id="2", important=False, urgent=False, reason="", spoken_summary="Promo."),
    ]
    with (
        patch.object(sources, "unread_emails", return_value=emails),
        patch.object(sources, "read_plan", return_value=""),
        patch.object(scheduler.brain, "triage_emails", return_value=triaged) as triage,
        patch.object(scheduler.brain, "write_briefing", return_value="Sorry to interrupt") as brief,
        patch.object(scheduler, "_quiet", return_value=False),
        patch.object(scheduler, "_alert") as alert,
    ):
        scheduler.check_email()
        scheduler.check_email()  # same emails again: nothing new

    assert triage.call_count == 1
    brief.assert_called_once_with("urgent", extra="Bank alert.")
    alert.assert_called_once_with("Sorry to interrupt")
