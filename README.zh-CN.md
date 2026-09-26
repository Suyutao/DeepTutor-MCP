# DeepTutor MCP

**English:** [README](README.md)

DeepTutor MCP 将 DeepTutor 的学习数据与学习专用工具，通过 MCP 提供给兼容的 AI 客户端。它面向自托管部署：用户自行运行 MCP 服务，并连接自己的 DeepTutor。日常对话、讲解、规划和归纳由 ChatGPT、Codex、Poke 等客户端完成；DeepTutor 提供学习状态、资料和学习操作接口。

## 能力

当前工具目录包含 58 个工具，涵盖：

- DeepTutor 状态、课程、教学大纲和课程资源
- 精通之路、完整大纲、证据、变更记录和复习设置
- DeepTutor 原生题库、练习队列、答案核对、复习记录和统计
- 生成式教材、阅读材料、批注、高亮和书签
- 笔记本及已保存的学习记录
- 知识库元数据、受限长度的原文读取、字面搜索和向量检索片段
- DeepTutor 历史会话和记忆文档
- 一个需要明确选择的工具，用于直接向 DeepTutor 的能力对话发送请求

一般的讲解、教学、计划和综合分析由当前 AI 客户端完成，不会启动 DeepTutor 对话。向量检索调用 DeepTutor 的 LlamaIndex 检索器并返回来源片段；对应索引必须已就绪，运行 MCP 的进程必须能访问知识库文件。

写入工具在描述中带有警告，并要求 `confirm: true`。这只是应用层保护，不能代替接口认证、网络访问限制或用户检查。替换精通之路大纲时会校验修订版本；练习复习会使用当前题目版本和唯一请求 ID。

本项目为 58 个工具公布 MCP 输出架构，并在 `structuredContent` 中以 `result` 字段提供 DeepTutor 原始结果。文本内容通道继续保留原有 JSON 表示，兼顾不读取结构化结果的旧客户端。输出架构故意不约束 DeepTutor API 返回对象的内部字段，因此不会把随 DeepTutor 版本变化的 API 结构伪装成稳定承诺。

本地 stdio 与远程 HTTP 共用同一组 58 个工具名称和输入架构。可用 `DEEPTUTOR_MCP_TIMEZONE` 设置练习工具默认时区；为兼容既有部署，代码仍默认使用 `Asia/Shanghai`，新部署的 `.env.example` 使用 `UTC`。

## 环境要求

- Python 3.11 或更高版本
- 可通过 HTTP API 访问的 DeepTutor 服务
- 远程 HTTP 传输需要安装 HTTP 可选依赖
- 向量检索要求 MCP 主机上具备 DeepTutor 运行环境和索引依赖，或可通过配置的 SSH 通道访问这些依赖

## 连接本地 stdio 服务

在运行 MCP 客户端的机器上安装或下载本项目。根据部署情况配置 `.env.example` 中的环境变量，再在客户端注册 stdio 服务。Codex CLI 示例：

```sh
codex mcp add deeptutor \
  --env DEEPTUTOR_BASE_URL=http://127.0.0.1:8001 \
  -- python3 /path/to/deeptutor-mcp/deeptutor_mcp.py
```

如果 DeepTutor 在另一台机器上，把 `DEEPTUTOR_BASE_URL` 设为本机可访问的地址。如果 API 只能通过 SSH 访问，可使用本机 SSH 端口转发。stdio 桥接不需要安装远程 HTTP 服务的依赖。

## 运行远程 Streamable HTTP 服务

安装 HTTP 依赖并启动服务：

```sh
python3 -m venv .venv
.venv/bin/pip install '.[http]'
cp .env.example .env
# 按当前部署编辑 .env，并将密钥保存在 Git 仓库之外。
set -a
. ./.env
set +a
.venv/bin/python -m uvicorn remote_mcp:app --host 127.0.0.1 --port 8000
```

MCP 地址为 `/mcp`；`/health` 只检查进程是否响应。若由反向代理或隧道提供 HTTPS，应将服务绑定到回环地址。详见[自托管部署](docs/zh-CN/DEPLOYMENT.md)、[ChatGPT 接入](docs/zh-CN/CHATGPT.md)和[故障排查](docs/zh-CN/TROUBLESHOOTING.md)。

### API Key 认证

将 `DEEPTUTOR_MCP_API_KEY_FILE` 指向一个权限严格的文件，文件中保存足够长的随机 Bearer 密钥。客户端应发送 `Authorization: Bearer <key>`。`manage_mcp.py` 可轮换服务密钥，并可选管理不同客户端的密钥。Poke 用户级凭据功能可使用 `DEEPTUTOR_MCP_CLIENT_ID_HEADER=X-Poke-User-Id`。

### 通过可信网关使用 OAuth

一些客户端只支持 OAuth。可在 MCP 地址前部署支持 OAuth 的身份网关，由网关处理浏览器授权和令牌签发，并在已认证请求上添加签名身份断言。使用 `DEEPTUTOR_MCP_PROXY_JWT_*` 配置验证该断言。本服务验证签名、签发方、受众、有效期和允许的身份。不要接受不可信客户端自行提供的身份请求头，也不要原样转发用户输入中的同名请求头。

本项目不提供 OAuth 账号服务。网关可以是 Cloudflare Access，也可以是其他能提供可验证签名断言的服务。核心桥接不依赖某一家供应商。

## ChatGPT 客户端说明

ChatGPT 的自定义 MCP 应用需要用户自己在网页端配置远程地址、认证方式并扫描工具。官方套餐说明没有列出 Plus；但维护者实测某个 Plus 账号在开启开发者模式后能看到添加 MCP 服务器的入口。这只能证明该账号可进入接入流程，不能保证所有 Plus 账号或完整读写能力均可用，可能与灰度或分批开放有关。维护者还实测网页端添加并授权后，同一账号可在 ChatGPT 手机应用及其他支持 ChatGPT Apps 的客户端中调用。该观察与 OpenAI 当前“仅支持网页端”的说明不一致，不能保证所有用户都可复现。上传 ChatGPT 插件 ZIP 与部署 MCP 后端是两件不同的事；上传不会替用户运行 DeepTutor 或完成后端授权。请查看[ChatGPT 官方开发者模式与 MCP 应用说明](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)、[插件 ZIP 说明](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt-and-codex)和[接入步骤](docs/zh-CN/CHATGPT.md)。

应用图标需要在创建 MCP 应用时上传。维护者测试发现，创建后无法更换图标；不上传时会显示黑色空图标。上传图标必须小于 10 KB。仓库提供的 [DeepTutor 图标](assets/DeepTutor-icon.png)为 64 × 63 PNG，大小 7,361 字节。

## DeepTutor 兼容性

桥接依赖 DeepTutor 的 HTTP API 和 CLI；这些接口可能随 DeepTutor 版本变化。当前代码曾在 Raspberry Pi 上的 DeepTutor 1.6.11 部署中运行。DeepTutor 升级后，在依赖写操作前，应对比运行中 `/openapi.json` 并在安全环境核对对应操作。向量检索还会导入 DeepTutor 的 `RAGService` 内部 Python 接口，该接口可能变化，运行进程也必须能读取索引文件。

## 项目状态

本独立适配器采用 Apache-2.0 许可证，供维护者审阅。它不是 DeepTutor 官方组件，客户端示例也不代表所有客户端及版本都已完成测试。兼容性政策仍待维护者审阅。
