# 自托管部署

本指南在 DeepTutor 同一台机器或另一台可访问其 API 的主机上部署 MCP 端点。建议只通过反向代理或隧道暴露 MCP 服务，并保持 DeepTutor API 为私有服务。

## 1. 安装

使用 Python 3.11 或更新版本，安装远程服务依赖：

```sh
python3 -m venv .venv
.venv/bin/pip install '.[http]'
```

从源码运行时，请在项目目录中执行命令。复制 `.env.example` 为私有环境文件，设置 `DEEPTUTOR_BASE_URL`，并将 Bearer 密钥保存在仅服务账号可读的文件中。不要把 `.env` 或密钥文件提交到 Git。

## 2. 选择端点认证方式

支持 API Key 的客户端可使用高熵密钥，并将 `DEEPTUTOR_MCP_API_KEY_FILE` 指向密钥文件。客户端发送 `Authorization: Bearer <key>`。

要求 OAuth 的客户端可安装 JWT 验证依赖 `.[http,proxy-jwt]`，并在 MCP 服务前部署支持 OAuth 的身份网关。配置网关验证用户，并在请求中添加其签名身份断言。MCP 服务配置 `DEEPTUTOR_MCP_PROXY_JWT_HOST`、`..._ISSUER`、`..._JWKS_URL`、`..._AUDIENCE`、`..._IDENTITY_CLAIM` 和 `..._ALLOWED_SUBJECT` 来验证断言。网关必须先删除请求中已有的同名请求头，再写入自己的断言。

这套配置用于让自托管服务所有者保护自己的 MCP；它不提供多用户 DeepTutor 数据隔离。

Cloudflare Access 的 JWT 请求头和签发方/JWKS 地址属于供应商配置，应从 Cloudflare 控制台取得并保存在私有服务环境文件中。通用服务配置不依赖 Cloudflare。

## 3. 启动并配置路由

启动服务：

```sh
.venv/bin/python -m uvicorn remote_mcp:app --host 127.0.0.1 --port 8000
```

通过公网 HTTPS 访问时，将反向代理或隧道指向源站 `http://127.0.0.1:8000`，并保留 `/mcp` 路径。客户端使用 `https://<你的域名>/mcp`。不要暴露 DeepTutor API 端口。

若 ChatGPT 支持 Secure MCP Tunnel，可用于私有连接。详见 [ChatGPT 接入指南](CHATGPT.md)。

## 4. 使用 systemd 运行

根据实际 Linux 用户、项目路径、Python 可执行文件、环境文件和知识库挂载情况修改 [`deeptutor-mcp.service.example`](../../deploy/systemd/deeptutor-mcp.service.example)。示例设置 UTF-8 环境并在进程失败时重启。如果知识库索引位于独立挂载盘，可添加 `RequiresMountsFor=`；请填写当前部署的挂载路径，不要照抄他人的机器路径。

## 5. 检查连接

`GET /health` 仅代表 Web 进程有响应。请使用配置了相同认证方式的 MCP 客户端或 Inspector 发现工具，并调用一个无副作用的只读工具。连接失败时参阅[故障排查](TROUBLESHOOTING.md)。
