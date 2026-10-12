"""Where Jarvis gets its information: Google Calendar, Gmail and your plan file."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import settings

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime | None
    location: str = ""
    all_day: bool = False

    def describe(self) -> str:
        if self.all_day:
            when = "all day"
        else:
            when = self.start.strftime("%H:%M")
            if self.end:
                when += f"-{self.end.strftime('%H:%M')}"
        where = f" @ {self.location}" if self.location else ""
        return f"{when}: {self.title}{where}"


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    snippet: str
    received: datetime

    def describe(self) -> str:
        return f"[{self.id}] From: {self.sender} | Subject: {self.subject} | {self.snippet}"


def google_credentials():
    """Load (and refresh) the OAuth token created by `python -m jarvis auth`."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not settings.google_token.exists():
        raise RuntimeError("No Google token yet. Run: python -m jarvis auth")
    creds = Credentials.from_authorized_user_file(str(settings.google_token), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        settings.google_token.write_text(creds.to_json())
    return creds


def run_google_auth() -> None:
    """One-time interactive login that writes token.json."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(settings.google_credentials), SCOPES)
    creds = flow.run_local_server(port=0)
    settings.google_token.write_text(creds.to_json())
    print(f"Saved Google token to {settings.google_token}")


def _service(name: str, version: str):
    from googleapiclient.discovery import build

    return build(name, version, credentials=google_credentials(), cache_discovery=False)


def _parse_event_time(value: dict) -> tuple[datetime, bool]:
    if "dateTime" in value:
        return datetime.fromisoformat(value["dateTime"]).astimezone(settings.timezone), False
    day = datetime.fromisoformat(value["date"])
    return day.replace(tzinfo=settings.timezone), True


def get_events(start: datetime, end: datetime) -> list[Event]:
    try:
        items = (
            _service("calendar", "v3")
            .events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
            .get("items", [])
        )
    except Exception:
        log.exception("Could not read Google Calendar")
        return []

    events = []
    for item in items:
        if item.get("status") == "cancelled":
            continue
        event_start, all_day = _parse_event_time(item["start"])
        event_end = _parse_event_time(item["end"])[0] if "end" in item else None
        events.append(
            Event(
                id=item["id"],
                title=item.get("summary", "(no title)"),
                start=event_start,
                end=event_end,
                location=item.get("location", ""),
                all_day=all_day,
            )
        )
    return events


def todays_events() -> list[Event]:
    now = datetime.now(settings.timezone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_events(start, start + timedelta(days=1))


def upcoming_events(within_minutes: int) -> list[Event]:
    now = datetime.now(settings.timezone)
    return [e for e in get_events(now, now + timedelta(minutes=within_minutes)) if not e.all_day]


def unread_emails(query: str = "is:unread in:inbox newer_than:2d", limit: int = 25) -> list[Email]:
    try:
        gmail = _service("gmail", "v1")
        refs = gmail.users().messages().list(userId="me", q=query, maxResults=limit).execute()
        emails = []
        for ref in refs.get("messages", []):
            msg = (
                gmail.users()
                .messages()
                .get(userId="me", id=ref["id"], format="metadata", metadataHeaders=["From", "Subject"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            emails.append(
                Email(
                    id=msg["id"],
                    sender=headers.get("From", "unknown"),
                    subject=headers.get("Subject", "(no subject)"),
                    snippet=msg.get("snippet", ""),
                    received=datetime.fromtimestamp(int(msg["internalDate"]) / 1000, settings.timezone),
                )
            )
        return emails
    except Exception:
        log.exception("Could not read Gmail")
        return []


def read_plan() -> str:
    if settings.plan_file.exists():
        return settings.plan_file.read_text(encoding="utf-8").strip()
    return ""
