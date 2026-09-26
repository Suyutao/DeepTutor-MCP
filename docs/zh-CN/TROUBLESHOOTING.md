# DeepTutor MCP 故障排查

本指南分别检查 URL、网络路由、MCP 协议发现、认证和 DeepTutor 数据访问。客户端给出的通用错误，可能对应其中任意一层。

## 客户端提示 “Invalid MCP server URL”

例如 `https://mcp.example.net/mcp` 这样的地址可能语法正确，但客户端连接或执行 MCP 工具发现时仍会失败。应先把它视为连接或握手问题，从端到端检查：

1. 确认公网 DNS 能解析域名：`dig mcp.example.net`。
2. 确认 HTTPS 到达了预期服务：`curl -i https://mcp.example.net/health`。健康检查成功只代表 Web 进程可访问，不代表 MCP 协议正常。
3. 确认 URL 使用服务实际提供的传输路径。本项目通过 `/mcp` 提供 Streamable HTTP；只有服务明确启用 SSE 时才使用 `/sse`。
4. 检查反向代理或隧道路由。将域名转发到 MCP 源站地址和端口，并保留外部 `/mcp` 路径，除非明确配置了路径重写。源站通常是 `http://127.0.0.1:8000` 这样的协议、主机和端口，不是公网 MCP 路径。
5. 核对客户端支持的认证方式。API Key 模式应发送 `Authorization: Bearer <key>`；OAuth 模式应完成提供方授权，并发送获得的访问令牌或可信网关断言。不要把密钥写进 URL 或日志。
6. 使用与客户端相同的凭据执行 MCP 工具发现。如果健康检查成功但发现工具失败，检查服务和代理日志中的 MCP `initialize`、`tools/list` 请求、状态码和响应内容。

对 `/mcp` 发送 `GET` 可能得到 `405 Method Not Allowed`，因为 MCP 客户端使用 `POST` 发送 JSON-RPC 请求；单凭这个响应不能判定服务故障。`404` 通常是路径错误或路由缺失；`502` 通常表示上游不可达；`401` 表示凭据缺失或被拒绝；返回登录 HTML 通常表示客户端未完成或无法跟随认证流程。

## OAuth MCP 已显示工具，但调用返回 `401 Unauthorized`

客户端能够发现工具名称和参数结构，不代表已通过真实请求的 OAuth 鉴权。工具列表可能先于认证调用成功，因此不能仅凭工具已显示就认定令牌或网关到 MCP 服务的身份断言有效。

如果服务部署在 Cloudflare Access 后面，请确认 MCP 服务读取的请求头与 Cloudflare 实际发送的一致。Cloudflare 会在 `Cf-Access-Jwt-Assertion` 请求头中转发签名 JWT；请在 MCP 服务的私有环境文件中显式设置：

```dotenv
DEEPTUTOR_MCP_PROXY_JWT_HEADER=cf-access-jwt-assertion
```

请求头名称不区分大小写。修改环境配置后重启 MCP 服务。还要核对 JWT host、issuer、JWKS URL、audience、identity claim 和 allowed subject 是否与 Cloudflare Access 应用及令牌相符。不要记录或分享断言内容本身。

用同一个云端 OAuth 客户端验证修复：先调用只读的 `deeptutor_status`，再调用 `list_mastery_paths` 等数据工具。两者成功后，再单独用 `search_vector_knowledge` 测试向量检索；OAuth 正常时，索引或文件系统问题仍可能使向量检索失败。本地 stdio/API Key 调用或 `/health` 响应都不能证明云端 OAuth 路由可用。Cloudflare 在[ JWT 验证文档](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)中说明了该断言请求头。

### Poke CLI 包名写法

这是与服务 URL 故障不同的问题。`npx poke@mcp add ...` 会让 npm 查找名为 `mcp` 的包版本，可能得到 `ETARGET`。正确写法是：

```sh
npx poke@latest mcp add https://mcp.example.net/mcp -n "DeepTutor" -k "YOUR_API_KEY"
```

使用密钥管理器保存真实密钥，或交互式粘贴；不要把真实密钥留在共享命令记录中。

## 向量检索报知识库目录 `Operation not permitted`

一次树莓派部署在 exFAT 挂载盘上的中文知识库目录遇到 `PermissionError: [Errno 1] Operation not permitted`。堆栈显示错误发生在 DeepTutor 检查索引时调用 `Path.is_dir()` / `os.stat()` 的阶段，还没有进入向量检索。交互式 Shell 能读取目录，因此仅用文件属主或 `chmod` 解释并不充分。

系统调用路径显示，服务的 Python 进程使用 GBK 编码中文路径，而 exFAT 挂载预期 UTF-8；该服务继承了非 UTF-8 区域设置。通过 systemd 为服务设置显式 UTF-8 环境后解决：

```ini
[Service]
Environment=LANG=C.UTF-8
Environment=LC_ALL=C.UTF-8
Environment=PYTHONUTF8=1
```

知识库位于外接磁盘，因此还需确保挂载点在服务启动前可用：

```ini
[Unit]
RequiresMountsFor=/path/to/your/knowledge-base-mount
```

请填写当前部署的挂载路径。仅凭 `EPERM` 不应直接断定是 `chmod`、`chown` 或挂载选项；还要比较服务的环境变量、文件系统编码、挂载命名空间，以及失败进程产生的完整堆栈。

## 健康检查正常，但工具调用失败

健康检查只确认服务可用，不代表所有 DeepTutor 能力正常。按具体工具检查：

- DeepTutor API 工具需要可访问 `DEEPTUTOR_BASE_URL`；配置了 API Bearer Token 时还需令牌有效。
- 向量检索要求 LlamaIndex 知识库已就绪，并且进程可访问索引目录。根据部署方式，在 DeepTutor 主机设置 `DEEPTUTOR_KB_ROOT`，或配置到该主机的 SSH 访问。
- `send_message_to_deeptutor` 还需要 SSH 和 DeepTutor CLI。一般教学和内容综合不依赖这个工具。
- 写入工具要求 `confirm: true`。这是应用层确认保护，不可替代对 MCP 端点的认证和访问控制。

systemd 部署可检查服务日志，并确认服务账号能访问 DeepTutor 和知识库路径。分享日志前请删除令牌和个人学习内容。
