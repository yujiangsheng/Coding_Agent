/**
 * Turing MCP Client — 通过 stdio 与 Turing MCP 服务器通信
 *
 * 使用 JSON-RPC 2.0 协议，通过子进程的 stdin/stdout 与 Turing 交互。
 * 支持：initialize → tools/list → tools/call 完整生命周期。
 */

import * as vscode from "vscode";
import { spawn, ChildProcess } from "child_process";

interface MCPRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

interface MCPResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

interface MCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export class TuringMCPClient {
  private process: ChildProcess | undefined;
  private requestId = 0;
  private pendingRequests = new Map<
    number,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();
  private buffer = "";
  private tools: MCPTool[] = [];
  private initialized = false;

  constructor(private context: vscode.ExtensionContext) {}

  async connect(): Promise<void> {
    if (this.process) {
      return;
    }

    const config = vscode.workspace.getConfiguration("turing");
    const pythonPath = config.get<string>("pythonPath", "python");
    const workspaceFolder =
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();

    this.process = spawn(pythonPath, ["-m", "turing.mcp.server"], {
      cwd: workspaceFolder,
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env },
    });

    this.process.stdout?.on("data", (data: Buffer) => {
      this.handleData(data.toString());
    });

    this.process.stderr?.on("data", (data: Buffer) => {
      console.error("[Turing MCP stderr]", data.toString());
    });

    this.process.on("exit", (code) => {
      console.log(`[Turing MCP] 进程退出，code=${code}`);
      this.process = undefined;
      this.initialized = false;
    });

    // 初始化握手
    await this.sendRequest("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "vscode-turing", version: "0.1.0" },
    });

    // 获取工具列表
    const toolsResult = (await this.sendRequest("tools/list", {})) as {
      tools: MCPTool[];
    };
    this.tools = toolsResult?.tools || [];
    this.initialized = true;
  }

  async callTool(
    name: string,
    args: Record<string, unknown>
  ): Promise<unknown> {
    if (!this.initialized) {
      await this.connect();
    }
    return this.sendRequest("tools/call", { name, arguments: args });
  }

  getTools(): MCPTool[] {
    return this.tools;
  }

  isConnected(): boolean {
    return this.initialized && this.process !== undefined;
  }

  dispose(): void {
    if (this.process) {
      this.process.kill();
      this.process = undefined;
    }
    this.pendingRequests.clear();
  }

  private sendRequest(
    method: string,
    params: Record<string, unknown>
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.process?.stdin?.writable) {
        reject(new Error("MCP 进程未启动"));
        return;
      }

      const id = ++this.requestId;
      const request: MCPRequest = {
        jsonrpc: "2.0",
        id,
        method,
        params,
      };

      this.pendingRequests.set(id, { resolve, reject });
      const msg = JSON.stringify(request);
      const header = `Content-Length: ${Buffer.byteLength(msg)}\r\n\r\n`;
      this.process.stdin.write(header + msg);

      // 超时保护
      setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error(`MCP 请求超时: ${method}`));
        }
      }, 30000);
    });
  }

  private handleData(data: string): void {
    this.buffer += data;

    // 解析 Content-Length 分帧的 JSON-RPC 消息
    while (this.buffer.length > 0) {
      const headerEnd = this.buffer.indexOf("\r\n\r\n");
      if (headerEnd === -1) {
        break;
      }

      const header = this.buffer.substring(0, headerEnd);
      const match = header.match(/Content-Length:\s*(\d+)/i);
      if (!match) {
        // 跳过无效头
        this.buffer = this.buffer.substring(headerEnd + 4);
        continue;
      }

      const contentLength = parseInt(match[1], 10);
      const bodyStart = headerEnd + 4;

      if (this.buffer.length < bodyStart + contentLength) {
        break; // 数据不完整，等待更多
      }

      const body = this.buffer.substring(bodyStart, bodyStart + contentLength);
      this.buffer = this.buffer.substring(bodyStart + contentLength);

      try {
        const response = JSON.parse(body) as MCPResponse;
        const pending = this.pendingRequests.get(response.id);
        if (pending) {
          this.pendingRequests.delete(response.id);
          if (response.error) {
            pending.reject(
              new Error(`MCP Error: ${response.error.message}`)
            );
          } else {
            pending.resolve(response.result);
          }
        }
      } catch {
        console.error("[Turing MCP] 解析响应失败:", body.substring(0, 200));
      }
    }
  }
}
