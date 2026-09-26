#!/usr/bin/env python3
"""Authenticated Streamable HTTP MCP endpoint for remote MCP clients."""

import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
import re
import secrets

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

import deeptutor_mcp as bridge


API_KEY_FILE = os.environ.get("DEEPTUTOR_MCP_API_KEY_FILE", os.environ.get("POKE_MCP_API_KEY_FILE", "")).strip()
USER_KEYS_FILE = os.environ.get("DEEPTUTOR_MCP_CLIENT_KEYS_FILE", os.environ.get("POKE_MCP_USER_KEYS_FILE", "")).strip()
KB_ROOT = os.environ.get("DEEPTUTOR_KB_ROOT", "").strip()
PUBLIC_HOST = os.environ.get("DEEPTUTOR_MCP_PUBLIC_HOST", os.environ.get("POKE_MCP_PUBLIC_HOST", "")).strip().lower()
PROXY_JWT_HOST = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_HOST", os.environ.get("CF_ACCESS_PUBLIC_HOST", "")).strip().lower()
PROXY_JWT_ISSUER = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_ISSUER", "").strip().rstrip("/")
if not PROXY_JWT_ISSUER and os.environ.get("CF_ACCESS_TEAM_DOMAIN"):
    PROXY_JWT_ISSUER = "https://" + os.environ["CF_ACCESS_TEAM_DOMAIN"].strip().strip("/")
PROXY_JWT_JWKS_URL = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_JWKS_URL", "").strip()
PROXY_JWT_AUDIENCE = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_AUDIENCE", os.environ.get("CF_ACCESS_AUD", "")).strip()
PROXY_JWT_ALLOWED_SUBJECT = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_ALLOWED_SUBJECT", os.environ.get("CF_ACCESS_EMAIL", "")).strip().lower()
default_proxy_header = "cf-access-jwt-assertion" if os.environ.get("CF_ACCESS_PUBLIC_HOST") else "x-mcp-auth-assertion"
PROXY_JWT_HEADER = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_HEADER", default_proxy_header).strip().lower().encode("ascii")
default_client_header = "X-Poke-User-Id" if os.environ.get("POKE_MCP_USER_KEYS_FILE") else "X-Client-Id"
CLIENT_ID_HEADER = os.environ.get("DEEPTUTOR_MCP_CLIENT_ID_HEADER", default_client_header).strip().lower().encode("ascii")
if not API_KEY_FILE and not USER_KEYS_FILE and not PROXY_JWT_HOST:
    raise RuntimeError("Configure an API key file, client key registry, or trusted proxy JWT validator")
if PROXY_JWT_HOST and not (PROXY_JWT_ISSUER and PROXY_JWT_AUDIENCE and PROXY_JWT_ALLOWED_SUBJECT):
    raise RuntimeError("Configure proxy JWT host, issuer, audience, and allowed subject together")
if PROXY_JWT_HOST:
    import jwt
    from jwt import PyJWKClient

    if not PROXY_JWT_JWKS_URL:
        if os.environ.get("CF_ACCESS_TEAM_DOMAIN"):
            PROXY_JWT_JWKS_URL = f"https://{os.environ['CF_ACCESS_TEAM_DOMAIN'].strip().strip('/')}/cdn-cgi/access/certs"
        else:
            raise RuntimeError("Set DEEPTUTOR_MCP_PROXY_JWT_JWKS_URL for proxy JWT authentication")
    PROXY_JWT_JWKS = PyJWKClient(PROXY_JWT_JWKS_URL, cache_keys=True)


TOOL_MAP = {item["name"]: dict(item) for item in bridge.TOOLS}
server = Server("deeptutor-learning-remote", version="0.1.0")


@server.list_tools()
async def list_tools():
    return [types.Tool(**item) for item in TOOL_MAP.values()]


@server.call_tool()
async def call_tool(name, arguments):
    if name not in TOOL_MAP:
        raise ValueError("Unknown or unavailable remote tool")
    result = await asyncio.to_thread(bridge.dispatch, name, arguments)
    if isinstance(result, list):
        result = {"count": len(result), "items": result}
    text_content = types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))
    return ([text_content], {"result": result})


manager = StreamableHTTPSessionManager(
    app=server,
    json_response=True,
    stateless=True,
    security_settings=TransportSecuritySettings(
        allowed_hosts=["localhost:*", "127.0.0.1:*", *([host for host in (PUBLIC_HOST, PROXY_JWT_HOST) if host])],
    ),
)


class MCPEndpoint:
    async def __call__(self, scope, receive, send):
        await manager.handle_request(scope, receive, send)


async def health(request):
    return PlainTextResponse("ready")


@asynccontextmanager
async def lifespan(app):
    async with manager.run():
        yield


inner_app = Starlette(routes=[Route("/mcp", endpoint=MCPEndpoint()), Route("/health", endpoint=health)], lifespan=lifespan)


async def app(scope, receive, send):
    if scope["type"] == "http" and scope.get("path") == "/mcp":
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode("ascii", "ignore").split(":", 1)[0].lower()
        authorized = False
        if PROXY_JWT_HOST and host == PROXY_JWT_HOST:
            assertion = headers.get(PROXY_JWT_HEADER, b"").decode("ascii", "ignore")
            if assertion:
                try:
                    signing_key = PROXY_JWT_JWKS.get_signing_key_from_jwt(assertion)
                    claims = jwt.decode(
                        assertion,
                        signing_key.key,
                        algorithms=["RS256"],
                        audience=PROXY_JWT_AUDIENCE,
                        issuer=PROXY_JWT_ISSUER,
                        leeway=30,
                        options={"require": ["exp", "iat", "iss", "aud"]},
                    )
                    identity_claim = os.environ.get("DEEPTUTOR_MCP_PROXY_JWT_IDENTITY_CLAIM", "email").strip()
                    identity = str(claims.get(identity_claim, claims.get("sub", ""))).lower()
                    authorized = identity == PROXY_JWT_ALLOWED_SUBJECT
                except Exception:
                    logging.getLogger(__name__).warning("Rejected invalid proxy identity assertion")
                    authorized = False
        if not authorized:
            supplied = headers.get(b"authorization", b"").decode("ascii", "ignore")
            user_id = headers.get(CLIENT_ID_HEADER, b"").decode("ascii", "ignore")
            credential = supplied.removeprefix("Bearer ")
            expected = ""
            if USER_KEYS_FILE and user_id and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", user_id):
                try:
                    with open(USER_KEYS_FILE, encoding="utf-8") as keys_file:
                        user_keys = json.load(keys_file)
                    expected = user_keys.get(user_id, "")
                    authorized = bool(expected) and hmac.compare_digest(credential, expected)
                except (OSError, ValueError):
                    authorized = False
            if not authorized and API_KEY_FILE:
                with open(API_KEY_FILE, encoding="utf-8") as token_file:
                    expected = token_file.read().strip()
                authorized = bool(expected) and hmac.compare_digest(credential, expected)
        if not authorized:
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return
    await inner_app(scope, receive, send)
