# Turing Agent VS Code Extension

> v3.6 — 将 Turing 编程智能体集成到 VS Code

通过 MCP (Model Context Protocol) 协议连接 Turing 的 82 个工具能力，在 VS Code 中实现 AI 辅助编程。

## 功能

| 功能 | 说明 |
|------|------|
| **侧边栏聊天** | 类似 Copilot Chat 的 AI 对话界面，支持流式输出 |
| **代码解释** | 选中代码 → 右键 → *Turing: Explain Selected Code* |
| **MCP 工具调用** | 直接调用 Turing 的 82 个工具（文件编辑、Git、代码搜索等）|
| **上下文感知** | 自动获取当前文件、选中代码作为对话上下文 |

## 架构

```
VS Code Extension ←→ MCP stdio ←→ Turing Agent (Python)
     │                                    │
     ├── Chat Webview (chatView.ts)       ├── 82 Tools (19 modules)
     ├── Code Explain (extension.ts)      ├── 4-Layer Memory System
     └── MCP Client (mcpClient.ts)        └── Multi-LLM Router
```

**通信协议：** JSON-RPC 2.0 over stdio

1. 扩展启动时，`TuringMCPClient` 生成 `python -m turing.mcp.server` 子进程
2. 发送 `initialize` 握手 → `tools/list` 发现可用工具
3. 用户输入通过 `tools/call` 路由到对应 Turing 工具
4. 工具结果返回 Webview 渲染

## 安装与开发

### 前置条件

- **Node.js** 16+ 和 **npm**
- **Python** 3.9+
- Turing Agent 已安装：`pip install -e .`（在项目根目录）

### 编译与调试

```bash
cd vscode-extension
npm install
npm run compile
```

按 **F5** 启动 Extension Development Host 进行调试。

### 打包 VSIX

```bash
npm install -g @vscode/vsce
vsce package
```

生成的 `.vsix` 文件可通过 `code --install-extension turing-agent-x.x.x.vsix` 安装。

## 配置

在 VS Code Settings (`Ctrl+,`) 中搜索 "turing"：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `turing.pythonPath` | `python` | Python 解释器路径 |
| `turing.mcpCommand` | `python -m turing.mcp.server` | MCP 服务器启动命令 |

## 项目结构

```
vscode-extension/
├── src/
│   ├── extension.ts     # 扩展入口：激活钩子、命令注册、ChatView 初始化
│   ├── mcpClient.ts     # MCP 客户端：stdio 子进程管理 + JSON-RPC 2.0
│   └── chatView.ts      # 聊天面板：Webview Provider + 消息序列化
├── resources/
│   └── turing-icon.svg  # 扩展图标
├── package.json         # VS Code 扩展清单（commands, views, configuration）
├── tsconfig.json        # TypeScript 配置
└── README.md            # 本文件
```

## 常见问题

**Q: MCP 连接失败？**
- 确认 Turing 已安装：`python -c "import turing; print(turing.__version__)"`
- 检查 Python 路径是否正确：`which python`
- 查看 VS Code 输出面板 → Turing Agent 日志

**Q: 工具调用超时？**
- 默认 30 秒超时，大型文件操作可能需要更多时间
- 在 MCP 服务器端检查是否有 Ollama/LLM 连接问题
