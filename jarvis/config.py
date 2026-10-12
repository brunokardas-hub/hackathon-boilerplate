"""Settings loaded from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


@dataclass
class Settings:
    # Who Jarvis works for
    owner_name: str = os.getenv("OWNER_NAME", "sir")
    owner_phone: str = os.getenv("OWNER_PHONE", "")  # E.164, e.g. +48123456789
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo(os.getenv("TIMEZONE", "Europe/Warsaw")))

    # Twilio
    twilio_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")  # e.g. https://abc.ngrok.app
    voice: str = os.getenv("JARVIS_VOICE", "Polly.Brian")
    speech_language: str = os.getenv("SPEECH_LANGUAGE", "en-GB")

    # Claude
    model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

    # Google
    google_credentials: Path = Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
    google_token: Path = Path(os.getenv("GOOGLE_TOKEN_FILE", "token.json"))

    # Your own plan / to-do list (markdown, free form)
    plan_file: Path = Path(os.getenv("PLAN_FILE", "plan.md"))

    # Schedule
    briefing_time: time = field(default_factory=lambda: _time(os.getenv("BRIEFING_TIME", "08:00")))
    email_check_minutes: int = int(os.getenv("EMAIL_CHECK_MINUTES", "10"))
    meeting_reminder_minutes: int = int(os.getenv("MEETING_REMINDER_MINUTES", "10"))
    quiet_start: time = field(default_factory=lambda: _time(os.getenv("QUIET_HOURS_START", "22:30")))
    quiet_end: time = field(default_factory=lambda: _time(os.getenv("QUIET_HOURS_END", "07:30")))
    # "call" = phone call for urgent things, "sms" = text message instead
    urgent_alert_mode: str = os.getenv("URGENT_ALERT_MODE", "call")

    state_file: Path = Path(os.getenv("STATE_FILE", "jarvis_state.json"))
    port: int = int(os.getenv("PORT", "5000"))


settings = Settings()
