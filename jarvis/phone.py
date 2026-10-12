"""Twilio phone calls: outbound dialing plus the webhooks that make the call two-way."""

from __future__ import annotations

import logging
import secrets
import threading
from functools import wraps

from flask import Flask, Response, abort, request
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Gather, VoiceResponse

from .brain import Conversation
from .config import settings

log = logging.getLogger(__name__)

app = Flask(__name__)

# Text Jarvis will open the next call with, keyed by a one-time token in the webhook URL.
_pending_openings: dict[str, str] = {}
# Live conversations keyed by Twilio CallSid.
_calls: dict[str, Conversation] = {}
_lock = threading.Lock()

HANGUP = "[HANGUP]"


def twilio() -> Client:
    return Client(settings.twilio_sid, settings.twilio_token)


def call_owner(message: str) -> str:
    """Ring the owner's phone; when they pick up Jarvis says `message` and then listens."""
    token = secrets.token_urlsafe(16)
    with _lock:
        _pending_openings[token] = message
    call = twilio().calls.create(
        to=settings.owner_phone,
        from_=settings.twilio_number,
        url=f"{settings.public_url}/voice/start?t={token}",
        machine_detection="Enable",
        status_callback=f"{settings.public_url}/voice/status",
    )
    log.info("Calling %s (sid=%s)", settings.owner_phone, call.sid)
    return call.sid


def text_owner(message: str) -> None:
    twilio().messages.create(to=settings.owner_phone, from_=settings.twilio_number, body=message)


def _twilio_only(view):
    """Reject webhook requests that are not signed by Twilio."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        validator = RequestValidator(settings.twilio_token)
        url = settings.public_url + request.full_path.rstrip("?")
        if not validator.validate(url, request.form, request.headers.get("X-Twilio-Signature", "")):
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def _say_and_listen(text: str) -> str:
    vr = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice/respond",
        method="POST",
        speech_timeout="auto",
        language=settings.speech_language,
    )
    gather.say(text, voice=settings.voice)
    vr.append(gather)
    # Nothing heard: one gentle nudge, then hang up.
    vr.say("I'll leave you to it. Goodbye.", voice=settings.voice)
    vr.hangup()
    return str(vr)


def _twiml(xml: str) -> Response:
    return Response(xml, mimetype="text/xml")


@app.post("/voice/start")
@_twilio_only
def voice_start():
    with _lock:
        opening = _pending_openings.pop(request.args.get("t", ""), None)
    if opening is None:
        abort(404)

    # Voicemail picked up: leave the message and hang up.
    if request.form.get("AnsweredBy", "").startswith("machine"):
        vr = VoiceResponse()
        vr.say(opening, voice=settings.voice)
        vr.hangup()
        return _twiml(str(vr))

    with _lock:
        _calls[request.form["CallSid"]] = Conversation(opening)
    return _twiml(_say_and_listen(opening))


@app.post("/voice/respond")
@_twilio_only
def voice_respond():
    sid = request.form.get("CallSid", "")
    heard = request.form.get("SpeechResult", "")
    with _lock:
        convo = _calls.get(sid)
    if convo is None:
        convo = Conversation("Hello, this is Jarvis.")
        with _lock:
            _calls[sid] = convo

    try:
        answer = convo.reply(heard)
    except Exception:
        log.exception("Claude call failed")
        answer = "Apologies, my systems hiccupped. Could you say that again?"

    if HANGUP in answer:
        with _lock:
            _calls.pop(sid, None)
        vr = VoiceResponse()
        vr.say(answer.replace(HANGUP, "").strip(), voice=settings.voice)
        vr.hangup()
        return _twiml(str(vr))
    return _twiml(_say_and_listen(answer))


@app.post("/voice/status")
@_twilio_only
def voice_status():
    if request.form.get("CallStatus") in {"completed", "failed", "busy", "no-answer", "canceled"}:
        with _lock:
            _calls.pop(request.form.get("CallSid", ""), None)
    return "", 204


@app.post("/voice/incoming")
@_twilio_only
def voice_incoming():
    """When YOU call your Twilio number, Jarvis answers and you can ask anything."""
    if request.form.get("From") != settings.owner_phone:
        vr = VoiceResponse()
        vr.say("Sorry, this line is private.", voice=settings.voice)
        vr.hangup()
        return _twiml(str(vr))
    opening = f"Good to hear from you, {settings.owner_name}. What can I do for you?"
    with _lock:
        _calls[request.form["CallSid"]] = Conversation(opening)
    return _twiml(_say_and_listen(opening))


@app.get("/health")
def health():
    return {"ok": True}
