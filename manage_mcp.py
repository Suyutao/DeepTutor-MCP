#!/usr/bin/env python3
"""Interactive helper for checking and rotating DeepTutor MCP credentials."""

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import urllib.error
import urllib.request


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = Path(os.environ.get("DEEPTUTOR_MCP_ENV_FILE", os.environ.get("POKE_MCP_ENV_FILE", SCRIPT_DIR / ".env")))


def read_env():
    values = {}
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError as exc:
        raise RuntimeError(f"Cannot read {ENV_FILE}: {exc}") from exc
    return values


def configured(env, key, legacy=None, default=""):
    return env.get(key, env.get(legacy, default) if legacy else default).strip()


def read_keys(path):
    try:
        content = path.read_text(encoding="utf-8") if path.exists() else "{}"
        values = json.loads(content)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read client key registry: {exc}") from exc
    if not isinstance(values, dict):
        raise RuntimeError("Client key registry must contain a JSON object")
    return values


def write_keys(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(values, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def write_secret(path, secret):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(secret + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def endpoint_urls(env):
    local = configured(env, "DEEPTUTOR_MCP_LOCAL_URL", default="http://127.0.0.1:8000").rstrip("/")
    public = configured(env, "DEEPTUTOR_MCP_PUBLIC_URL").rstrip("/")
    host = configured(env, "DEEPTUTOR_MCP_PUBLIC_HOST", "POKE_MCP_PUBLIC_HOST")
    if not public and host:
        public = "https://" + host
    return local, public


def http_check(url, token=None, client_id=None, client_id_header="X-Client-Id"):
    headers = {"User-Agent": "DeepTutor-MCP-manager/1.0"}
    data = None
    if token:
        headers.update({"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        if client_id:
            headers[client_id_header] = client_id
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if not data:
                return response.status, None
            raw = response.read().decode("utf-8", "replace")
            payload = json.loads(raw)
            tools = payload.get("result", {}).get("tools", [])
            return response.status, f"MCP tools available: {len(tools)}" if tools else "MCP replied, but returned no tools"
    except urllib.error.HTTPError as exc:
        return exc.code, "HTTP " + str(exc.code)
    except Exception as exc:
        return None, str(exc)


def service_status(env):
    service = configured(env, "DEEPTUTOR_MCP_SERVICE", "POKE_MCP_SERVICE")
    if not service:
        print("Service status: not configured (set DEEPTUTOR_MCP_SERVICE to check systemd)")
        return
    try:
        result = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True, check=False)
        print("Service status:", result.stdout.strip() or "unknown")
    except OSError as exc:
        print("Service status unavailable:", exc)


def status(env):
    local, public = endpoint_urls(env)
    key_file_value = configured(env, "DEEPTUTOR_MCP_API_KEY_FILE", "POKE_MCP_API_KEY_FILE")
    keys_file_value = configured(env, "DEEPTUTOR_MCP_CLIENT_KEYS_FILE", "POKE_MCP_USER_KEYS_FILE")
    client_header_default = "X-Poke-User-Id" if "POKE_MCP_USER_KEYS_FILE" in env else "X-Client-Id"
    client_header = configured(env, "DEEPTUTOR_MCP_CLIENT_ID_HEADER", "POKE_MCP_CLIENT_ID_HEADER", client_header_default)
    service_status(env)
    for label, url in (("Local health", local + "/health"), ("Public health", public + "/health" if public else "")):
        if url:
            code, detail = http_check(url)
            print(f"{label}:", detail or code or "unreachable")
    if key_file_value and Path(key_file_value).is_file():
        key_file = Path(key_file_value)
        token = key_file.read_text(encoding="utf-8").strip()
        for label, base in (("Local MCP", local), ("Public MCP", public)):
            if base:
                code, detail = http_check(base + "/mcp", token)
                print(f"{label}:", detail or code or "unreachable")
    if not keys_file_value:
        return
    keys_file = Path(keys_file_value)
    clients = read_keys(keys_file)
    if not clients:
        print("No per-client credentials configured.")
        return
    names = list(clients)
    print("Configured client IDs:")
    for index, client_id in enumerate(names, 1):
        print(f"  {index}. {client_id}")
    selected = input("Test client number (Enter to skip): ").strip()
    if not selected:
        return
    if not selected.isdigit() or not 1 <= int(selected) <= len(names):
        print("Invalid selection.")
        return
    client_id = names[int(selected) - 1]
    for label, base in (("Local MCP", local), ("Public MCP", public)):
        if base:
            code, detail = http_check(base + "/mcp", clients[client_id], client_id, client_header)
            print(f"{label} ({client_id}):", detail or code or "unreachable")


def create_client_key(env):
    registry_value = configured(env, "DEEPTUTOR_MCP_CLIENT_KEYS_FILE", "POKE_MCP_USER_KEYS_FILE")
    if not registry_value:
        raise RuntimeError("Set DEEPTUTOR_MCP_CLIENT_KEYS_FILE in the environment file")
    registry = Path(registry_value)
    client_id = input("Client ID (Poke user ID, if applicable): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", client_id):
        print("Invalid ID. Use 1–128 letters, digits, underscores or hyphens.")
        return
    clients = read_keys(registry)
    token = secrets.token_urlsafe(36)
    clients[client_id] = token
    write_keys(registry, clients)
    print("\nNew client key (shown once):")
    print(token)
    print("Keep it private. Rotating this client replaces the previous key immediately.")


def rotate_server_key(env):
    path_value = configured(env, "DEEPTUTOR_MCP_API_KEY_FILE", "POKE_MCP_API_KEY_FILE")
    if not path_value:
        raise RuntimeError("Set DEEPTUTOR_MCP_API_KEY_FILE in the environment file")
    path = Path(path_value)
    if input("Rotate the main bearer key? Existing API-key connections stop working until updated. Type ROTATE: ").strip() != "ROTATE":
        print("Cancelled.")
        return
    token = secrets.token_urlsafe(36)
    write_secret(path, token)
    print("\nNew server key (shown once):")
    print(token)


def revoke_client_key(env):
    registry_value = configured(env, "DEEPTUTOR_MCP_CLIENT_KEYS_FILE", "POKE_MCP_USER_KEYS_FILE")
    if not registry_value:
        raise RuntimeError("Set DEEPTUTOR_MCP_CLIENT_KEYS_FILE in the environment file")
    registry = Path(registry_value)
    clients = read_keys(registry)
    client_id = input("Client ID to revoke: ").strip()
    if client_id not in clients:
        print("No key is configured for that client.")
        return
    if input(f"Revoke key for {client_id}? Type REVOKE to confirm: ").strip() != "REVOKE":
        print("Cancelled.")
        return
    del clients[client_id]
    write_keys(registry, clients)
    print("Client key revoked.")


def main():
    try:
        env = read_env()
    except RuntimeError as exc:
        print(exc)
        return 1
    local, public = endpoint_urls(env)
    print("DeepTutor MCP endpoint:", (public or local) + "/mcp")
    while True:
        print("\nDeepTutor MCP manager")
        print("1. Check service and connection")
        print("2. Create or rotate a client key")
        print("3. Revoke a client key")
        print("4. List configured client IDs")
        print("5. Rotate the main bearer key")
        print("0. Exit")
        choice = input("> ").strip()
        try:
            if choice == "1":
                status(env)
            elif choice == "2":
                create_client_key(env)
            elif choice == "3":
                revoke_client_key(env)
            elif choice == "4":
                registry_value = configured(env, "DEEPTUTOR_MCP_CLIENT_KEYS_FILE", "POKE_MCP_USER_KEYS_FILE")
                if not registry_value:
                    print("Set DEEPTUTOR_MCP_CLIENT_KEYS_FILE to manage client-specific keys.")
                else:
                    registry = Path(registry_value)
                    clients = read_keys(registry)
                    print("\n".join(clients) if clients else "No client keys configured.")
            elif choice == "5":
                rotate_server_key(env)
            elif choice == "0":
                return 0
            else:
                print("Choose 0, 1, 2, 3, 4 or 5.")
        except (RuntimeError, OSError, ValueError) as exc:
            print("Error:", exc)


if __name__ == "__main__":
    raise SystemExit(main())
