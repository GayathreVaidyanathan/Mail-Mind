"""
core/approval.py

Human-in-the-loop interface.
Called only by ComposerAgent — shows the email + AI draft
and waits for the human to decide what to do.
"""

import textwrap
from core.message_bus import EmailMessage


def display_email(msg: EmailMessage, draft: str, index: int, total: int) -> None:
    """Prints the original email and AI draft side by side."""
    width = 72
    print(f"\n{'═' * width}")
    print(f"  ✉  Email {index} of {total}  ·  Category: {msg.get('category', '?')}")
    if msg.get("label"):
        print(f"  🏷  Label: {msg['label']}")
    print(f"{'═' * width}")
    print(f"  From   : {msg['sender']}")
    print(f"  Subject: {msg['subject']}")
    print(f"  Date   : {msg['date']}")
    print(f"{'─' * width}")
    print("  Original message:\n")

    for line in msg["body"][:600].splitlines():
        print(textwrap.fill(line, 68, initial_indent="  ", subsequent_indent="  ") or "")
    if len(msg["body"]) > 600:
        print("  [... truncated ...]")

    print(f"\n{'─' * width}")
    print("  AI-drafted reply:\n")
    for line in draft.splitlines():
        print(textwrap.fill(line, 68, initial_indent="  ", subsequent_indent="  ") or "")
    print(f"\n{'═' * width}")


def get_approval(msg: EmailMessage, draft: str) -> tuple[str, str]:
    """
    Asks the human what to do with the draft.

    Returns:
        (action, final_reply)
        action: "send" | "regenerate" | "skip" | "quit"
    """
    print("\n  [S] Send  [E] Edit  [R] Regenerate  [X] Skip  [Q] Quit")

    while True:
        choice = input("\n  Your choice: ").strip().upper()

        if choice == "S":
            return ("send", draft)

        elif choice == "E":
            print("\n  Enter edited reply (blank line twice to finish):")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            edited = "\n".join(lines[:-1]).strip()
            return ("send", edited) if edited else ("skip", "")

        elif choice == "R":
            return ("regenerate", "")

        elif choice == "X":
            return ("skip", "")

        elif choice == "Q":
            return ("quit", "")

        else:
            print("  Invalid. Enter S, E, R, X, or Q.")
