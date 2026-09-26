# Troubleshooting DeepTutor MCP

This guide separates URL formatting, network routing, MCP protocol discovery, authentication, and DeepTutor data access. A generic client error can hide a failure in any of these layers.

## Client says “Invalid MCP server URL”

A URL such as `https://mcp.example.net/mcp` can be syntactically valid and still fail when the client connects or performs MCP discovery. Treat this message as a connection or handshake failure until the endpoint has been checked end to end.

1. Confirm that public DNS resolves the hostname: `dig mcp.example.net`.
2. Check that HTTPS reaches the expected server: `curl -i https://mcp.example.net/health`. A successful health response only proves that the web process is reachable; it does not prove MCP works.
3. Confirm that the configured URL uses the server's actual MCP transport path. This project serves Streamable HTTP at `/mcp`; an `/sse` URL is for a server that explicitly exposes SSE.
4. Check reverse proxy or tunnel routing. Route the hostname to the MCP server's origin address and port, and preserve the external `/mcp` request path unless an intentional rewrite is configured. The origin is normally a scheme/host/port, for example `http://127.0.0.1:8000`, not the public MCP path.
5. Check the authentication mode the client supports. A client configured for an API key must send `Authorization: Bearer <key>`. A client configured for OAuth must complete the provider's authorization flow and send the resulting access token or a trusted gateway assertion. Do not paste secrets into URLs or logs.
6. Verify MCP discovery with the same credentials the client uses. If health works but tool discovery fails, inspect server and proxy logs for the MCP `initialize` / `tools/list` request, status code, and response content.

A `GET /mcp` request may return `405 Method Not Allowed` because MCP clients use POST for JSON-RPC requests. That response alone does not show that the server is broken. A `404` usually points to a wrong path or missing route; `502` usually points to an unreachable upstream; `401` points to missing or rejected credentials; a login HTML page usually means the client did not complete, or cannot follow, the configured authentication flow.

### Poke CLI package-name typo

This is a separate issue from a server URL failure. `npx poke@mcp add ...` asks npm for a package version named `mcp` and can fail with `ETARGET`. The documented form is:

```sh
npx poke@latest mcp add https://mcp.example.net/mcp -n "DeepTutor" -k "YOUR_API_KEY"
```

Use a key stored in a secret manager or paste it interactively; never place a real key in a shared command transcript.

## Vector search reports `Operation not permitted` for a knowledge-base folder

A reported Raspberry Pi deployment initially returned `PermissionError: [Errno 1] Operation not permitted` for a Chinese-named knowledge-base directory on an exFAT mount. The traceback reached `Path.is_dir()` / `os.stat()` while DeepTutor checked the index, before it ran vector retrieval. The directory was readable from an interactive shell, which made a simple file ownership or `chmod` explanation unlikely.

The captured system-call path showed the service's Python process encoding the Chinese path with GBK while the exFAT mount expected UTF-8. The service had inherited a non-UTF-8 locale. The fix was to give the systemd service an explicit UTF-8 environment:

```ini
[Service]
Environment=LANG=C.UTF-8
Environment=LC_ALL=C.UTF-8
Environment=PYTHONUTF8=1
```

The knowledge-base disk was also external, so the service was made dependent on its mount being available before startup:

```ini
[Unit]
RequiresMountsFor=/path/to/your/knowledge-base-mount
```

Use the actual mount path for your installation. Reload systemd and restart the service after editing the unit. Do not assume `chmod`, `chown`, or mount flags are the cause solely from `EPERM`; compare the service environment, filesystem encoding, mount namespace, and a traceback from the failing process first.

## Health is ready, but a tool call fails

Health checks cover service availability, not all DeepTutor capabilities. Check the error for the specific tool:

- DeepTutor API tools need a reachable `DEEPTUTOR_BASE_URL` and, when configured, a valid API bearer token.
- Vector search requires a ready LlamaIndex-backed knowledge base and access to its index directory. Depending on the deployment, set `DEEPTUTOR_KB_ROOT` on the DeepTutor host or configure SSH access to that host.
- `send_message_to_deeptutor` additionally requires SSH and the DeepTutor CLI. Ordinary tutoring and synthesis do not require this tool.
- Write tools require `confirm: true`; this is an application-level confirmation guard, not a replacement for authenticating and restricting access to the MCP endpoint.

For systemd deployments, inspect the service journal and verify that the service user can reach DeepTutor and read the configured knowledge-base paths. Redact tokens and personal learning content before sharing logs.
