# 通过 MCP 使用 DeepTutor 内置 Mastery Tutor

本适配器用两个 MCP 工具开放 DeepTutor 原生 Mastery Tutor 流程：

- get_mastery_tutor_tools：读取 DeepTutor 发布的原生工具架构和调用说明。
- call_mastery_tutor：将选定的原生 Tutor 工具及参数转发给 DeepTutor。出题、批改、测评、复习状态和轮次记录均由 DeepTutor 内置实现处理。

## 上游版本要求

本适配器使用的 DeepTutor HTTP 接口由 [HKUDS/DeepTutor PR #1785](https://github.com/HKUDS/DeepTutor/pull/1785) 提出。截至 2026-10-14，该 PR 仍处于 open 状态，正在等待维护者合并。使用前需要将 DeepTutor 更新到已包含该补丁的部署版本；在此之前，获取 Tutor 工具目录可能返回 HTTP 404。

补丁增加：

- GET /api/mastery-paths/tutor-tools：返回原生 Tutor 工具架构和调用说明。
- POST /api/mastery-paths/topics/{path_id}/tutor：通过与 DeepTutor 内部 Tutor 相同的实现执行选定工具。

## 手动应用源码补丁

当前 PR #1785 提议的完整源码补丁已放在 `patches/deeptutor-mastery-tutor-http.patch`。其中包含 PR 的两个提交，包括对应的测试调整。补丁基于 DeepTutor 提交 `f07029cf`（v1.6.13）生成，适用于这个精确基线的源码副本；其他基线可能需要先变基或处理冲突。

在干净的 DeepTutor 源码副本中创建本地分支，检查基线并验证补丁后再应用：

~~~sh
git status --short --branch
git rev-parse --short HEAD  # 预期：f07029cf
git switch -c local/mastery-tutor-http
git apply --check /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
git apply /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
~~~

使用 DeepTutor 源码副本中的项目环境运行对应测试：

~~~sh
python -m pytest deeptutor/learning/tests/test_external_tutor.py -q
~~~

如果尚未在这些文件上继续修改，可以检查并反向应用补丁来撤销：

~~~sh
git apply --reverse --check /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
git apply --reverse /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
~~~

应用补丁只会修改源码。部署该源码副本并重启 DeepTutor 服务是单独的步骤；MCP 适配器和补丁文件不会更改正在运行的安装。

## 配置 MCP 服务

复用当前 DeepTutor API 地址和认证配置：

~~~dotenv
DEEPTUTOR_BASE_URL=http://127.0.0.1:8001
DEEPTUTOR_MCP_TUTOR_CLIENT_ID=chatgpt
~~~

DEEPTUTOR_MCP_TUTOR_CLIENT_ID 是该 MCP 客户端稳定且不含秘密信息的标识。不同 AI 客户端分别配置时使用不同值。DeepTutor API 认证仍通过 DEEPTUTOR_TOKEN 或 DEEPTUTOR_TOKEN_FILE 完成；Bearer 凭据应保存在私有环境文件中。

stdio 方式要将这些环境变量传给 MCP 进程。Streamable HTTP 方式要将它们加入服务环境并重启 MCP 服务。随后在客户端重新扫描 MCP 工具。本适配器不增加服务端口，也不引入新的 DeepTutor 凭据。

## Tutor 调用顺序

1. 开始 Mastery 学习前先调用 get_mastery_tutor_tools，并遵循返回的原生工具架构和说明。
2. 使用 list_mastery_paths 选取学习者已有的 path_id。
3. 每次 Tutor 操作调用 call_mastery_tutor，传入对应的原生 tool 名称和符合架构的 arguments。只有用户明确要求使用 Mastery Tutor 流程时才设置 confirm: true。
4. 同一学习过程保持 session_id 不变；同一个学习者轮次中的工具调用复用 turn_id；每次操作使用不同且至少 16 个字符的 request_id，重试同一请求时复用原 ID。
5. 每个学习者轮次的第一次调用都在 user_message 中原样传入学习者消息。Tutor 完成回复后，用 tool: record_turn 和 assistant_message 保存完整回复。

这些操作由 DeepTutor 现有 Tutor 工具执行。适配器不会推断学习者自我声明，也不会让外部模型直接写入掌握值。
