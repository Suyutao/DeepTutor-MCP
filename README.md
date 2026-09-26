# DeepTutor MCP

中文文档：[简体中文](README.zh-CN.md)。

DeepTutor MCP exposes DeepTutor's learning data and study-specific tools to MCP-compatible AI clients. It is designed for self-hosted DeepTutor installations: the user runs the MCP server and connects it to their own DeepTutor instance. The AI client handles the ordinary conversation and tutoring; DeepTutor supplies learning state, source material, and study operations through its APIs.

The same canonical tool catalog is available through local stdio and remote Streamable HTTP transports. Clients such as Codex, ChatGPT, and Poke are examples, not dependencies of the project. Authentication is selected for the deployment and client: API-key bearer authentication for clients that support it, or a trusted OAuth gateway that validates the user and forwards a signed identity assertion.

## Capabilities

The current catalog contains 58 tools covering:

- DeepTutor status, courses, syllabus, and linked resources
- Mastery Paths, outlines, evidence, change history, and review settings
- Native Question Bank and Practice queues, answer checks, reviews, and analytics
- Generated Books, Reading materials, notes, highlights, and bookmarks
- Notebooks and saved records
- Knowledge-base metadata, bounded original text, literal file search, and indexed vector passage retrieval
- Historical DeepTutor sessions and memory documents
- An explicit opt-in tool for sending a request into a DeepTutor capability conversation

Ordinary explanation, teaching, planning, and synthesis run in the connected AI client; they do not start a DeepTutor conversation. Vector search calls DeepTutor's LlamaIndex retriever and returns source passages. It requires a ready compatible index and access to the knowledge-base directory.

Writes are marked in tool descriptions and require `confirm: true`. This is an application-level guard, not a substitute for endpoint authentication, network controls, or user review. Outline replacement checks a revision; Practice reviews use the current item version and a unique request ID.

All 58 tools publish an MCP output schema and return the original DeepTutor payload under `structuredContent.result`. The existing text content channel continues to carry the JSON representation for clients that do not consume structured results. The schema intentionally leaves the payload's internal fields open because those are determined by the corresponding DeepTutor API and can vary by version.

The current 58 tool names and input schemas are kept identical across stdio and remote HTTP. `DEEPTUTOR_MCP_TIMEZONE` can set the default used by Practice tools; the legacy default remains `Asia/Shanghai` for existing installations, while `.env.example` shows `UTC` for a fresh deployment.

## Requirements

- Python 3.11 or newer
- A running DeepTutor server reachable through its HTTP API
- For the remote HTTP transport: the optional HTTP dependencies
- For vector retrieval, DeepTutor's runtime and index dependencies must be available on the MCP host, or reachable through the configured SSH route

## Local stdio connection

Install or download the project on the machine running your MCP client. Configure the environment variables in `.env.example` for your deployment, then register the stdio server with the client. Example for Codex CLI:

```sh
codex mcp add deeptutor \
  --env DEEPTUTOR_BASE_URL=http://127.0.0.1:8001 \
  -- python3 /path/to/deeptutor-mcp/deeptutor_mcp.py
```

If DeepTutor is on another machine, set `DEEPTUTOR_BASE_URL` to an address reachable from this computer. If the API is only reachable over SSH, use a local SSH port forward. The stdio bridge does not require the remote HTTP server dependencies.

## Remote Streamable HTTP service

Install the HTTP extras and run the server on the DeepTutor host or another host that can reach DeepTutor:

```sh
python3 -m venv .venv
.venv/bin/pip install '.[http]'
cp .env.example .env
# Edit .env with this deployment's values and store secrets outside Git.
set -a
. ./.env
set +a
.venv/bin/python -m uvicorn remote_mcp:app --host 127.0.0.1 --port 8000
```

The endpoint is `/mcp`; `/health` checks process availability. Bind to loopback when a reverse proxy or tunnel provides HTTPS. See [self-hosted deployment](docs/DEPLOYMENT.md), [ChatGPT setup](docs/CHATGPT.md), and [troubleshooting](docs/TROUBLESHOOTING.md).

### API key authentication

Set `DEEPTUTOR_MCP_API_KEY_FILE` to a private file containing a long random bearer key. A compatible client sends it as `Authorization: Bearer <key>`. `manage_mcp.py` can rotate the server key and optionally manage distinct client credentials. For Poke, set `DEEPTUTOR_MCP_CLIENT_ID_HEADER=X-Poke-User-Id` if using its per-user credential feature.

### OAuth through a trusted gateway

Some clients require OAuth instead of API keys. Place the MCP endpoint behind an OAuth-capable gateway. The gateway owns browser authorization and token issuance; configure it to add a signed identity assertion header on authenticated requests. Set the `DEEPTUTOR_MCP_PROXY_JWT_*` values to validate that assertion. This server validates the signature, issuer, audience, expiry, and allowed identity. Do not accept identity headers from untrusted clients or proxy them unchanged from user input.

The MCP project does not operate an OAuth account service. A gateway may be Cloudflare Access or another provider that can securely supply a verifiable signed assertion. Provider-specific setup belongs in the deployment guide, not in the core bridge.

## Client setup guides

- [ChatGPT custom MCP app](docs/CHATGPT.md)
- [Poke](docs/POKE.md)
- [Self-hosted deployment](docs/DEPLOYMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

ChatGPT's custom-app interface and plan availability vary by subscription and workspace policy. The current OpenAI guide lists read/fetch access for Pro and full read/write access for Business, Enterprise, and Edu, but does not list Plus. In maintainer testing, one Plus account could open the Developer Mode and Add MCP Server flows; this is account-specific evidence and may reflect staged rollout, not a guarantee for every Plus account or full read/write access. See [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt). ChatGPT plugin ZIP upload is a separate workspace feature and does not deploy the MCP backend; see [Plugins in ChatGPT and Codex](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt-and-codex).

## DeepTutor compatibility

The bridge targets DeepTutor's HTTP API and CLI. Those interfaces can change between DeepTutor releases. The current code was exercised against DeepTutor 1.6.11 on a Raspberry Pi deployment. Before relying on writes after a DeepTutor upgrade, compare the running `/openapi.json` and exercise the specific operation in a safe environment. Vector retrieval additionally imports DeepTutor's `RAGService`; this internal Python interface may change and its process must be able to read the index files.

## Project status

This is an independent adapter prepared for maintainer review. It is not an official DeepTutor component, and client examples do not imply every client/version has been tested. A public release still needs a project license chosen by the maintainers and a compatibility policy.
