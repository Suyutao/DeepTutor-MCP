# Connect a self-hosted DeepTutor MCP to ChatGPT

This setup is for connecting your own DeepTutor installation to your own ChatGPT account or workspace. It does not create a shared hosted service.

## Before starting

- Run DeepTutor and DeepTutor MCP somewhere you control.
- Choose how ChatGPT will reach the MCP server:
  - **Private connection:** use OpenAI Secure MCP Tunnel where available. The server can remain private and does not need an inbound public port or public domain.
  - **Remote HTTPS connection:** publish only the MCP endpoint behind HTTPS, using a domain and an authentication provider. A tunnel/reverse proxy and an OAuth identity gateway are deployment choices; this MCP project does not require a particular provider.
- Confirm that your ChatGPT subscription and workspace allow custom MCP apps. As of 2026-09-26, OpenAI's help page explicitly lists read/fetch MCP access for Pro and full read/write MCP support for Business, Enterprise, and Edu; it does not list Plus. In maintainer testing, a Plus account showed Developer Mode in ChatGPT web settings and could open the Add MCP Server flow after enabling it. This confirms that the flow was available to that account, but does not establish availability for every Plus account or confirm full read/write access; staged rollout or account-level experiments may explain the difference. The custom-app flow is web-only.

## Add the app in ChatGPT

The custom-app flow is spread across settings, so follow this order:

1. Open ChatGPT on the web and enable Developer Mode or custom MCP connectors if your plan and workspace expose that setting. In a managed workspace, an administrator may need to enable it or grant your account access.
2. Open **Settings → Apps** (or the workspace's **Apps** settings) and choose **Create**.
3. Enter a name such as **DeepTutor Learning** and the Streamable HTTP endpoint URL ending in `/mcp`. **Upload the icon before creating the app:** maintainer testing found that the icon could not be changed after creation; without an upload, ChatGPT showed a blank black icon. The upload limit is under 10 KB. This repository includes a [DeepTutor icon](../assets/DeepTutor-icon.png), a 64 × 63 PNG of 7,361 bytes.
4. Pick the authentication mode supported by your deployment and client connection:
   - In the current custom-app flow, use **OAuth** when protecting a public HTTPS endpoint with an OAuth-capable provider. Complete the browser authorization when prompted. If the provider supports refresh tokens, configure offline access so the connection can renew.
   - If the app offers **No authentication**, use it only for a private connection protected by Secure MCP Tunnel or equivalent workspace/network controls. Do not expose a personal learning server publicly without authentication.
   - With Secure MCP Tunnel, select **Tunnel** and choose the tunnel associated with the ChatGPT workspace instead of entering a public URL.
5. Choose **Scan Tools** and wait for discovery. If scanning fails, check the endpoint, transport path, auth mode, and server logs using [Troubleshooting](TROUBLESHOOTING.md).
6. Create the app. Open a new chat, select the app from the tools menu, and ask for a read-only action such as listing courses or mastery paths before trying a write operation.
7. For writes, inspect the proposed target and values. The server requires `confirm: true`, and ChatGPT may also ask for its own confirmation depending on app permissions and action risk.

The app is managed in your own ChatGPT settings. This guide does not publish a public store listing.

## Keep in mind

- Secure MCP Tunnel is for private connections and development; it is not a public plugin distribution mechanism.
- Full tool access depends on the ChatGPT plan and workspace policy. If write tools do not appear or cannot run, verify plan support and app action permissions.
- Prepare and upload the icon during app creation. Custom PNG icons must be smaller than 10 KB.
- The UI changes over time. If the labels differ, use the current OpenAI guide: [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).
