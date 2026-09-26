# Connect Poke

Poke is one example of a client that accepts remote MCP servers and bearer API keys. Its UI and CLI are maintained by Poke and may change.

1. Start the remote server and confirm the public HTTPS MCP endpoint is available at `https://<your-hostname>/mcp`.
2. Create a key file and configure `DEEPTUTOR_MCP_API_KEY_FILE` on the server.
3. In Poke, create an integration with the MCP URL and API key, or use the documented CLI form:

```sh
npx poke@latest mcp add https://<your-hostname>/mcp -n "DeepTutor" -k "YOUR_API_KEY"
```

4. Resync or rediscover tools after changing the server catalog.

Poke sends a user identifier in `X-Poke-User-Id`. If you configure distinct keys per Poke user, set `DEEPTUTOR_MCP_CLIENT_ID_HEADER=X-Poke-User-Id` and `DEEPTUTOR_MCP_CLIENT_KEYS_FILE` to a private JSON key map. Otherwise a single owner API key is sufficient for a private personal deployment.

Poke reports such as “Invalid MCP server URL” may represent a failed network request, authentication check, or MCP handshake, even when the URL itself is well-formed. See [Troubleshooting](TROUBLESHOOTING.md).
