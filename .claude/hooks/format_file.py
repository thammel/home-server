"""PostToolUse(Write|Edit): ruff-format and auto-fix the one Python file that changed.

Silently no-ops when .venv/bin/ruff is missing. Never blocks.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUFF = ROOT / ".venv" / "bin" / "ruff"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        file_path = (payload.get("tool_input") or {}).get("file_path")
        if not isinstance(file_path, str) or not file_path.endswith(".py") or not RUFF.exists():
            return
        subprocess.run([str(RUFF), "format", "-q", file_path], cwd=ROOT, timeout=20, check=False)
        subprocess.run([str(RUFF), "check", "-q", "--fix", file_path], cwd=ROOT, timeout=20, check=False)
    except Exception:
        pass  # formatting is a convenience; it never blocks work


if __name__ == "__main__":
    main()
