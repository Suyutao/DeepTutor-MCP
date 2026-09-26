# 将自托管 DeepTutor MCP 连接到 ChatGPT

本指南用于将你自己的 DeepTutor 部署连接到你自己的 ChatGPT 账号或工作区，不会创建共用的托管服务。

## 开始前

- 在你控制的设备上运行 DeepTutor 和 DeepTutor MCP。
- 选择 ChatGPT 访问 MCP 服务的方式：
  - **私有连接：**在适用的产品中使用 OpenAI Secure MCP Tunnel。MCP 服务可以保持私有，不需要公网入站端口或公开域名。
  - **远程 HTTPS 连接：**通过 HTTPS 发布 MCP 端点，并使用域名及认证服务。隧道、反向代理和 OAuth 身份网关都是部署选择；本项目不要求使用特定供应商。
- 确认 ChatGPT 套餐和工作区策略允许使用自定义 MCP 应用。根据 OpenAI 在 2026-09-26 的官方说明，Pro 可在开发者模式中使用只读/检索 MCP；完整读写 MCP 目前面向 Business、Enterprise 和 Edu。Plus 未列在该说明中。该功能仅支持 ChatGPT 网页版，具体权限以官方页面和账号界面为准。

## 在 ChatGPT 中添加应用

自定义应用的设置分布在多个页面，按以下顺序操作：

1. 在网页版 ChatGPT 中启用开发者模式或自定义 MCP 连接器。如果是受管理工作区，管理员可能要先启用该功能或授予你的权限。
2. 打开 **设置 → 应用**（或工作区的 **应用** 设置），选择 **创建**。
3. 输入名称，例如 **DeepTutor Learning**，并填写以 `/mcp` 结尾的 Streamable HTTP 地址。
4. 选择部署和客户端支持的认证方式：
   - 公网 HTTPS 地址由 OAuth 网关保护时，选择 **OAuth**，然后完成浏览器授权。如果身份服务支持刷新令牌，应正确配置离线访问以维持连接。
   - 只有在 Secure MCP Tunnel 或等效工作区/网络访问控制保护的私有连接中，才考虑选择 **无需身份验证**。不要让个人学习服务在公网无认证开放。
   - 使用 Secure MCP Tunnel 时，选择 **Tunnel**，并选择与 ChatGPT 工作区关联的隧道，而不是填写公网 URL。
5. 选择 **扫描工具** 并等待发现完成。若扫描失败，检查地址、传输路径、认证模式，并按[故障排查](TROUBLESHOOTING.md)检查服务端和代理日志。
6. 创建应用。打开新对话，从工具菜单中选择应用，先尝试列课程或精通之路等只读操作，再进行写入操作。
7. 写入前检查目标与拟写入内容。服务要求 `confirm: true`；ChatGPT 也可能根据权限和操作风险要求额外确认。

该应用保存在你自己的 ChatGPT 设置中。本指南不发布公开应用商店条目。

## 注意事项

- Secure MCP Tunnel 用于私有连接和开发，不是公开插件分发机制。
- 工具能否完整使用取决于 ChatGPT 套餐、工作区策略及应用权限。若写工具不可用，请核对套餐支持和应用操作权限。
- ChatGPT 界面会变化。菜单名称不同时，请以 [OpenAI 官方说明](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)为准。
