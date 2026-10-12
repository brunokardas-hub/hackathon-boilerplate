"""Background jobs: morning briefing, urgent-email alerts and meeting reminders."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, time

from apscheduler.schedulers.background import BackgroundScheduler

from . import brain, phone, sources
from .config import settings

log = logging.getLogger(__name__)
_state_lock = threading.Lock()


def load_state() -> dict:
    if settings.state_file.exists():
        return json.loads(settings.state_file.read_text())
    return {"seen_emails": [], "reminded_events": []}


def save_state(state: dict) -> None:
    # Keep the files small: only remember the most recent ids.
    state["seen_emails"] = state["seen_emails"][-500:]
    state["reminded_events"] = state["reminded_events"][-200:]
    settings.state_file.write_text(json.dumps(state))


def in_quiet_hours(now: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # window wraps past midnight


def _quiet() -> bool:
    return in_quiet_hours(datetime.now(settings.timezone).time(), settings.quiet_start, settings.quiet_end)


def _alert(text: str) -> None:
    if settings.urgent_alert_mode == "sms":
        phone.text_owner(text)
    else:
        phone.call_owner(text)


def morning_briefing() -> None:
    log.info("Morning briefing")
    phone.call_owner(brain.write_briefing("morning"))


def check_email() -> None:
    with _state_lock:
        state = load_state()
        new = [e for e in sources.unread_emails() if e.id not in state["seen_emails"]]
        if not new:
            return
        triaged = brain.triage_emails(new, extra_rules=sources.read_plan()[:2000])
        # Mark everything as seen so nothing is announced twice.
        state["seen_emails"].extend(e.id for e in new)
        save_state(state)

    urgent = [t for t in triaged if t.urgent]
    log.info("Email check: %d new, %d urgent", len(new), len(urgent))
    if not urgent:
        return
    if _quiet():
        log.info("Quiet hours - holding urgent email alert for the morning briefing")
        return
    details = " ".join(t.spoken_summary for t in urgent)
    _alert(brain.write_briefing("urgent", extra=details))


def meeting_reminders() -> None:
    if _quiet():
        return
    with _state_lock:
        state = load_state()
        due = [
            e
            for e in sources.upcoming_events(settings.meeting_reminder_minutes)
            if e.id not in state["reminded_events"]
        ]
        if not due:
            return
        state["reminded_events"].extend(e.id for e in due)
        save_state(state)
    details = "; ".join(e.describe() for e in due)
    _alert(brain.write_briefing("reminder", extra=details))


def _safe(job):
    def run():
        try:
            job()
        except Exception:
            log.exception("Job %s failed", job.__name__)

    run.__name__ = job.__name__
    return run


def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    scheduler.add_job(
        _safe(morning_briefing),
        "cron",
        hour=settings.briefing_time.hour,
        minute=settings.briefing_time.minute,
    )
    scheduler.add_job(_safe(check_email), "interval", minutes=settings.email_check_minutes)
    scheduler.add_job(_safe(meeting_reminders), "interval", minutes=1)
    scheduler.start()
    log.info(
        "Scheduler running: briefing at %s, email every %d min, reminders %d min before meetings",
        settings.briefing_time.strftime("%H:%M"),
        settings.email_check_minutes,
        settings.meeting_reminder_minutes,
    )
    return scheduler
