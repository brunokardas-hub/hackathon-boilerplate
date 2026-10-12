"""Command line entry point.

    python -m jarvis auth        # one-time Google login
    python -m jarvis preview     # print today's briefing (no phone call)
    python -m jarvis call        # call me right now with a briefing
    python -m jarvis chat        # talk to Jarvis in the terminal (test the conversation without a phone)
    python -m jarvis run         # start the webhook server + scheduler (the real thing)
"""

import argparse
import logging

from .config import settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("command", choices=["auth", "preview", "call", "chat", "run"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "auth":
        from .sources import run_google_auth

        run_google_auth()

    elif args.command == "preview":
        from .brain import write_briefing

        print(write_briefing("morning"))

    elif args.command == "call":
        from .brain import write_briefing
        from .phone import call_owner

        call_owner(write_briefing("morning"))
        print("Calling you now. Keep `python -m jarvis run` running so Jarvis can talk back.")

    elif args.command == "chat":
        from .brain import Conversation, write_briefing
        from .phone import HANGUP

        opening = write_briefing("morning")
        print(f"JARVIS: {opening}")
        convo = Conversation(opening)
        while True:
            try:
                heard = input("YOU: ")
            except (EOFError, KeyboardInterrupt):
                break
            answer = convo.reply(heard)
            print(f"JARVIS: {answer.replace(HANGUP, '').strip()}")
            if HANGUP in answer:
                break

    elif args.command == "run":
        from . import scheduler
        from .phone import app

        scheduler.start()
        app.run(host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
