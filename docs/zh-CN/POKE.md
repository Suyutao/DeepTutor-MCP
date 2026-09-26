# 连接 Poke

Poke 是一个支持远程 MCP 和 Bearer API Key 的客户端示例。它的界面和命令行由 Poke 维护，可能会变化。

1. 启动远程服务，并确认公网 HTTPS MCP 地址为 `https://<你的域名>/mcp`。
2. 创建密钥文件，并在服务端设置 `DEEPTUTOR_MCP_API_KEY_FILE`。
3. 在 Poke 中创建集成，填写 MCP 地址和 API Key；也可使用其文档中的命令：

```sh
npx poke@latest mcp add https://<你的域名>/mcp -n "DeepTutor" -k "YOUR_API_KEY"
```

4. 修改服务端工具目录后，在 Poke 中重新同步或发现工具。

Poke 会发送 `X-Poke-User-Id` 用户标识。如果为每位 Poke 用户配置不同密钥，设置 `DEEPTUTOR_MCP_CLIENT_ID_HEADER=X-Poke-User-Id`，并将 `DEEPTUTOR_MCP_CLIENT_KEYS_FILE` 指向私有 JSON 密钥映射文件。个人自托管部署也可只使用所有者自己的 API Key。

Poke 提示 “Invalid MCP server URL” 时，原因可能是网络请求、认证或 MCP 握手失败，不一定是 URL 语法错误。请按[故障排查指南](TROUBLESHOOTING.md)逐层检查。
