#!/usr/bin/env python3
"""Create or rotate a bearer key for a client identified by a stable ID."""

import json
import os
from pathlib import Path
import re
import secrets
import sys


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sys.argv[1]):
        raise SystemExit("Usage: provision_client_key.py <client ID>")
    registry_value = os.environ.get("DEEPTUTOR_MCP_CLIENT_KEYS_FILE", "").strip()
    if not registry_value:
        raise SystemExit("Set DEEPTUTOR_MCP_CLIENT_KEYS_FILE")
    path = Path(registry_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        clients = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read client key registry: {exc}") from exc
    if not isinstance(clients, dict):
        raise SystemExit("Client key registry must contain a JSON object")
    clients[sys.argv[1]] = secrets.token_urlsafe(36)
    token = clients[sys.argv[1]]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(clients, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)
    print(token)


if __name__ == "__main__":
    main()
