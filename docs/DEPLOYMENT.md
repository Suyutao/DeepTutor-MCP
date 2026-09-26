# Self-hosted deployment

This guide installs the MCP endpoint beside DeepTutor or on another machine that can reach its API. The endpoint is intended to be the only service exposed through a reverse proxy or tunnel; keep the DeepTutor API private.

## 1. Install

Use Python 3.11 or newer and install the remote-server extras:

```sh
python3 -m venv .venv
.venv/bin/pip install '.[http]'
```

For a source checkout, run these commands from the project directory. Create a private environment file from `.env.example`, set `DEEPTUTOR_BASE_URL`, and store bearer keys in files readable only by the service account. Do not commit `.env` or secret files.

## 2. Select endpoint authentication

For clients that support API keys, create a high-entropy key and set `DEEPTUTOR_MCP_API_KEY_FILE`. The client sends `Authorization: Bearer <key>`.

For clients that require OAuth, install the JWT verification extra with `.[http,proxy-jwt]`, then use an OAuth-capable identity gateway in front of the endpoint. Configure the gateway to authenticate users and attach its signed identity assertion. Configure `DEEPTUTOR_MCP_PROXY_JWT_HOST`, `..._ISSUER`, `..._JWKS_URL`, `..._AUDIENCE`, `..._IDENTITY_CLAIM`, and `..._ALLOWED_SUBJECT` on the MCP service. The server validates the assertion. The gateway must remove any incoming header of the same name before adding its own. This configuration allows a self-hosted owner to protect their own MCP; it does not provide multi-user DeepTutor data isolation.

If using Cloudflare Access, its JWT assertion header and issuer/JWKS values are provider-specific. Use the Cloudflare values shown in its dashboard and keep them in the private service environment file. The generic server configuration does not require Cloudflare.

## 3. Start and route

Run:

```sh
.venv/bin/python -m uvicorn remote_mcp:app --host 127.0.0.1 --port 8000
```

For a public HTTPS setup, configure a reverse proxy or tunnel to the origin `http://127.0.0.1:8000`, preserving the request path `/mcp`. Configure the client with `https://<your-hostname>/mcp`. Do not expose DeepTutor's API port.

For a private ChatGPT connection, OpenAI Secure MCP Tunnel can keep the endpoint private when available. See [ChatGPT setup](CHATGPT.md).

## 4. Run with systemd

Adapt [`deeptutor-mcp.service.example`](../deploy/systemd/deeptutor-mcp.service.example) for the selected Linux user, project path, Python executable, environment file, and any knowledge-base mount. The example uses UTF-8 settings and restarts the process on failure. Add `RequiresMountsFor=` if the knowledge-base index resides on a separately mounted drive; do not copy a machine-specific mount path literally.

## 5. Check the connection

`GET /health` only checks that the web process responds. Use a client or MCP inspector with the same authentication configuration to discover tools and call a harmless read tool. For connection failures, follow [Troubleshooting](TROUBLESHOOTING.md).
