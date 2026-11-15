"""PreToolUse(Bash): block commands that destroy data or bypass the deploy flow.

Exit 2 blocks the call and returns stderr to Claude. Anything else passes.
"""

import json
import re
import sys

BLOCKED = [
    (r"\brm\b[^|;&]*\.db\b", "Deleting a SQLite DB loses real expense data."),
    (r"\bgit\s+push\b.*(--force|-f\b|--force-with-lease)", "Force-push rewrites history the server pulls from."),
    (r"\bgit\s+reset\s+--hard\b", "Hard reset discards work. Ask the user first."),
    (r"\bssh\b.*\b(rm\s+-rf|sqlite3|reboot|shutdown|systemctl\s+(stop|disable))\b",
     "Destructive command on the home server. Ask the user to run it."),
]


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return
    command = (payload.get("tool_input") or {}).get("command") or ""
    for pattern, reason in BLOCKED:
        if re.search(pattern, command):
            print(f"Blocked by .claude/hooks/guard.py: {reason}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
