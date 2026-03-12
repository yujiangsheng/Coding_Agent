/**
 * Turing Chat View — 侧边栏聊天 Webview
 *
 * 提供类似 Copilot Chat 的聊天界面，通过 MCP 协议与 Turing 通信。
 */

import * as vscode from "vscode";
import { TuringMCPClient } from "./mcpClient";

export class TuringChatViewProvider implements vscode.WebviewViewProvider {
  private webviewView?: vscode.WebviewView;

  constructor(
    private context: vscode.ExtensionContext,
    private mcpClient: TuringMCPClient
  ) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.webviewView = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
    };

    webviewView.webview.html = this.getHtml();

    // 处理来自 Webview 的消息
    webviewView.webview.onDidReceiveMessage(
      async (message) => {
        if (message.type === "chat") {
          await this.handleChat(message.text);
        }
      },
      undefined,
      this.context.subscriptions
    );
  }

  async sendMessage(text: string): Promise<void> {
    if (this.webviewView) {
      this.webviewView.webview.postMessage({
        type: "userMessage",
        text,
      });
      await this.handleChat(text);
    }
  }

  private async handleChat(userMessage: string): Promise<void> {
    try {
      // 连接 MCP 服务器（如未连接）
      if (!this.mcpClient.isConnected()) {
        this.postToWebview("status", "正在连接 Turing Agent...");
        await this.mcpClient.connect();
        this.postToWebview("status", "已连接");
      }

      // 获取当前编辑器上下文
      const editor = vscode.window.activeTextEditor;
      let contextInfo = "";
      if (editor) {
        const filePath = editor.document.uri.fsPath;
        const language = editor.document.languageId;
        contextInfo = `\n[当前文件: ${filePath} (${language})]`;
      }

      // 通过 MCP 调用 Turing 的 search_code 或直接处理
      // 这里使用 read_file + run_command 组合来模拟 Agent 交互
      const result = await this.mcpClient.callTool("search_code", {
        query: userMessage,
        max_results: 5,
      });

      const response =
        typeof result === "object" && result !== null
          ? JSON.stringify(result, null, 2)
          : String(result);

      this.postToWebview("response", response);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      this.postToWebview("error", `错误: ${errorMessage}`);
    }
  }

  private postToWebview(type: string, text: string): void {
    this.webviewView?.webview.postMessage({ type, text });
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      color: var(--vscode-foreground);
      background: var(--vscode-sideBar-background);
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    #chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }
    .message {
      margin-bottom: 12px;
      padding: 8px 12px;
      border-radius: 6px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .message.user {
      background: var(--vscode-input-background);
      border: 1px solid var(--vscode-input-border);
    }
    .message.assistant {
      background: var(--vscode-editor-background);
      border: 1px solid var(--vscode-editorWidget-border);
    }
    .message.error {
      color: var(--vscode-errorForeground);
      background: var(--vscode-inputValidation-errorBackground);
    }
    .message.status {
      color: var(--vscode-descriptionForeground);
      font-style: italic;
      font-size: 0.9em;
    }
    .message-label {
      font-weight: bold;
      margin-bottom: 4px;
      font-size: 0.85em;
      color: var(--vscode-descriptionForeground);
    }
    #input-area {
      padding: 8px 12px;
      border-top: 1px solid var(--vscode-editorWidget-border);
      display: flex;
      gap: 8px;
    }
    #user-input {
      flex: 1;
      padding: 6px 10px;
      border: 1px solid var(--vscode-input-border);
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border-radius: 4px;
      font-family: inherit;
      font-size: inherit;
      resize: none;
      min-height: 36px;
      max-height: 120px;
    }
    #user-input:focus {
      outline: 1px solid var(--vscode-focusBorder);
    }
    #send-btn {
      padding: 6px 16px;
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: inherit;
    }
    #send-btn:hover {
      background: var(--vscode-button-hoverBackground);
    }
    #send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  </style>
</head>
<body>
  <div id="chat-messages">
    <div class="message status">欢迎使用 Turing Agent！输入问题开始对话。</div>
  </div>
  <div id="input-area">
    <textarea id="user-input" placeholder="输入你的问题..." rows="1"></textarea>
    <button id="send-btn">发送</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const messagesDiv = document.getElementById('chat-messages');
    const input = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');

    function addMessage(text, className, label) {
      const div = document.createElement('div');
      div.className = 'message ' + className;
      if (label) {
        const labelDiv = document.createElement('div');
        labelDiv.className = 'message-label';
        labelDiv.textContent = label;
        div.appendChild(labelDiv);
      }
      const content = document.createElement('div');
      content.textContent = text;
      div.appendChild(content);
      messagesDiv.appendChild(div);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function send() {
      const text = input.value.trim();
      if (!text) return;
      addMessage(text, 'user', '你');
      vscode.postMessage({ type: 'chat', text });
      input.value = '';
      sendBtn.disabled = true;
    }

    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });

    // 自动调整 textarea 高度
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    // 接收来自 Extension 的消息
    window.addEventListener('message', (event) => {
      const msg = event.data;
      sendBtn.disabled = false;
      switch (msg.type) {
        case 'response':
          addMessage(msg.text, 'assistant', 'Turing');
          break;
        case 'error':
          addMessage(msg.text, 'error', '错误');
          break;
        case 'status':
          addMessage(msg.text, 'status');
          break;
        case 'userMessage':
          addMessage(msg.text, 'user', '你');
          break;
      }
    });
  </script>
</body>
</html>`;
  }
}
