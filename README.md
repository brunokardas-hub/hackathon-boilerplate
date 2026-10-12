# hackathon-boilerplate
🚀 Production-ready boilerplate for rapid hackathon development and high-performance econometric data analysis in 2026. Optimized for Cursor AI.

---

## 🎩 JARVIS — your voice assistant that calls you

JARVIS phones you and tells you what's going on, in a British-butler voice, and you can talk back.

| When | What JARVIS does |
|---|---|
| Every morning (default 08:00) | Calls with your **briefing**: today's calendar, what matters from your plan, and the emails that actually need you |
| Every 10 min | Checks Gmail; Claude triages new mail and **calls (or texts) you only for urgent ones** |
| 10 min before a meeting | **Reminder** call with what to prep |
| Any time you call your Twilio number | Answers and you can ask: *"what's next today?"*, *"anything from my bank?"* |
| Quiet hours (22:30–07:30) | Stays silent; urgent things wait for the morning briefing |

Each call is a two-way conversation: JARVIS speaks, listens (Twilio speech recognition), and Claude answers using your calendar, inbox and plan. Say *"thanks, that's all"* to hang up.

### How it works

```
APScheduler ──► sources.py (Google Calendar, Gmail, plan.md)
     │                    │
     ▼                    ▼
  phone.py  ◄──────  brain.py (Claude: briefing, email triage, conversation)
  Twilio call ◄──► Flask webhooks /voice/start, /voice/respond, /voice/incoming
```

### Setup (≈15 minutes)

1. **Install**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env          # fill it in as you go
   cp plan.example.md plan.md    # your goals/to-dos + rules for what counts as urgent
   ```
2. **Claude** — create an API key at console.anthropic.com → `ANTHROPIC_API_KEY`.
3. **Twilio** — sign up at twilio.com, buy a phone number with Voice, copy the Account SID, Auth Token and number into `.env`. On a trial account, verify your own mobile number first.
4. **Google Calendar + Gmail** (read-only)
   - In Google Cloud Console: create a project, enable **Google Calendar API** and **Gmail API**.
   - OAuth consent screen → External → add yourself as a test user.
   - Credentials → Create OAuth client ID → *Desktop app* → download as `credentials.json` into this folder.
   - Run `python -m jarvis auth` and log in in the browser. This creates `token.json`.
5. **Public URL** so Twilio can reach your machine:
   ```bash
   ngrok http 5000      # put the https URL in PUBLIC_URL
   ```
   In the Twilio console, set your number's **"A call comes in"** webhook to `POST {PUBLIC_URL}/voice/incoming` so you can call JARVIS too.

### Use it

```bash
python -m jarvis preview   # print today's briefing (no call) — check everything is wired up
python -m jarvis chat      # talk to JARVIS in the terminal, no phone needed
python -m jarvis run       # start server + scheduler (leave this running)
python -m jarvis call      # with `run` going in another terminal: call me now
```

To keep it running 24/7, deploy to any always-on host (Railway, Fly.io, a VPS, a Raspberry Pi) with `python -m jarvis run`, and set `PUBLIC_URL` to that host's HTTPS address.

### Customize

- **What's urgent** — write rules in `plan.md` (*"anything from my landlord is urgent"*); they're passed to the email triage.
- **Voice / language** — `JARVIS_VOICE` (any Twilio `<Say>` voice, e.g. `Polly.Amy`) and `SPEECH_LANGUAGE`.
- **SMS instead of calls for alerts** — `URGENT_ALERT_MODE=sms`.
- **Personality** — edit `PERSONA` in `jarvis/brain.py`.

### Privacy & cost notes

- Google access is **read-only**; JARVIS can't send or delete email or change your calendar.
- Webhooks reject any request not signed by Twilio, and inbound calls from numbers other than `OWNER_PHONE` are refused.
- Email subjects/snippets and calendar titles are sent to the Claude API to write briefings.
- Costs: Twilio charges per call minute and per number; Claude charges per request (each email check with new mail and each spoken reply is one request).

### Tests

```bash
pytest
```
