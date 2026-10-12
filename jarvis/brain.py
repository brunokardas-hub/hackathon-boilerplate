"""Claude-powered thinking: writing briefings, triaging email and holding a phone conversation."""

from __future__ import annotations

import logging
from datetime import datetime

import anthropic
from pydantic import BaseModel

from . import sources
from .config import settings

log = logging.getLogger(__name__)

client = anthropic.Anthropic()

# If the main model declines a request, the API retries it on a fallback model in the same call.
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

PERSONA = f"""You are JARVIS, a calm, witty, British-butler style personal assistant to {settings.owner_name}.
You speak to them over the PHONE, so everything you write will be read aloud by a text-to-speech voice:
- Plain spoken sentences only. No markdown, bullet points, emoji, URLs or email addresses read out letter by letter.
- Say times naturally ("half past two", "at 14:30" is fine too). Keep sender names short ("Anna from Stripe").
- Be brief and lead with what matters most. Never invent events, emails or facts that are not in the context.
- Address them as "{settings.owner_name}" occasionally, not every sentence."""


class TriagedEmail(BaseModel):
    id: str
    important: bool
    urgent: bool
    reason: str
    spoken_summary: str


class Triage(BaseModel):
    emails: list[TriagedEmail]


def _text(response) -> str:
    if response.stop_reason == "refusal":
        return "I'm afraid I can't help with that one."
    return " ".join(b.text for b in response.content if b.type == "text").strip()


def build_context(include_emails: bool = True) -> str:
    """Snapshot of the owner's day that Claude reasons over."""
    now = datetime.now(settings.timezone)
    parts = [f"Current time: {now.strftime('%A %d %B %Y, %H:%M')} ({settings.timezone.key})."]

    events = sources.todays_events()
    upcoming = [e for e in events if e.all_day or (e.end or e.start) >= now]
    parts.append(
        "Today's calendar:\n" + ("\n".join(e.describe() for e in upcoming) or "Nothing else scheduled today.")
    )

    plan = sources.read_plan()
    if plan:
        parts.append(f"Their plan / to-do list:\n{plan}")

    if include_emails:
        emails = sources.unread_emails()
        parts.append(
            "Unread emails (last 2 days):\n" + ("\n".join(e.describe() for e in emails) or "Inbox zero.")
        )
    return "\n\n".join(parts)


def triage_emails(emails: list[sources.Email], extra_rules: str = "") -> list[TriagedEmail]:
    """Decide which emails deserve to interrupt the owner."""
    if not emails:
        return []
    listing = "\n".join(e.describe() for e in emails)
    response = client.beta.messages.parse(
        model=settings.model,
        max_tokens=4000,
        betas=FALLBACK_BETAS,
        fallbacks="default",
        output_config={"effort": "low"},
        system=(
            "You triage a busy person's inbox. 'important' = a real human or service needs their attention "
            "(work, money, deadlines, family, security alerts, deliveries needing action). Newsletters, promos, "
            "social notifications and automated receipts are NOT important. 'urgent' = they should hear about it "
            "within the hour (time-sensitive, a deadline today, a security problem, someone waiting on them). "
            "spoken_summary is one short sentence to be read aloud on a phone call."
            + (f"\nOwner's own rules: {extra_rules}" if extra_rules else "")
        ),
        messages=[{"role": "user", "content": f"Triage every email below, keeping its id.\n\n{listing}"}],
        output_format=Triage,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        log.warning("Email triage returned no result (stop_reason=%s)", response.stop_reason)
        return []
    return response.parsed_output.emails


def write_briefing(kind: str = "morning", extra: str = "") -> str:
    """A spoken briefing. kind: 'morning', 'urgent' or 'reminder'."""
    instructions = {
        "morning": (
            "Give the morning briefing: greet them, today's schedule in order, what from their plan matters today, "
            "then only the emails that actually need them (skip newsletters/promos). Under 150 words. "
            "End by asking if they'd like anything else."
        ),
        "urgent": "Open with 'Sorry to interrupt' and tell them about the urgent item(s) below in under 60 words.",
        "reminder": "Remind them about the upcoming meeting below in under 40 words, and anything they should prep.",
    }[kind]
    response = client.beta.messages.create(
        model=settings.model,
        max_tokens=4000,
        betas=FALLBACK_BETAS,
        fallbacks="default",
        output_config={"effort": "low"},
        system=PERSONA,
        messages=[
            {
                "role": "user",
                "content": f"{build_context()}\n\n{('Details: ' + extra) if extra else ''}\n\nTask: {instructions}",
            }
        ],
    )
    return _text(response)


class Conversation:
    """Multi-turn phone conversation. History is append-only (full response content is kept)."""

    def __init__(self, opening: str):
        self.messages: list = [
            {
                "role": "user",
                "content": f"Context for this call:\n{build_context()}\n\n"
                "You have just called them and said the opening line that follows. Continue the call from there.",
            },
            {"role": "assistant", "content": opening},
        ]

    def reply(self, heard: str) -> str:
        self.messages.append({"role": "user", "content": heard or "(silence)"})
        response = client.beta.messages.create(
            model=settings.model,
            max_tokens=4000,
            betas=FALLBACK_BETAS,
            fallbacks="default",
            output_config={"effort": "low"},
            system=PERSONA
            + "\nThis is a live call: answer in one to three short sentences. If they say goodbye, thanks "
            "that's all, or similar, say a short farewell and end your reply with the exact token [HANGUP].",
            messages=self.messages,
        )
        text = _text(response)
        self.messages.append({"role": "assistant", "content": response.content or text})
        return text
