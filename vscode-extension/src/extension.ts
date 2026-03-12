/**
 * Turing Agent VS Code Extension
 *
 * 通过 MCP (Model Context Protocol) 连接 Turing 智能体，
 * 在 VS Code 中提供 AI 编程助手功能：
 * - 侧边栏聊天面板
 * - 代码解释（右键菜单）
 * - Diff 应用（将 Turing 建议的编辑应用到文件）
 *
 * 架构：Extension ↔ MCP stdio ↔ Turing Agent (Python)
 */

import * as vscode from "vscode";
import { TuringMCPClient } from "./mcpClient";
import { TuringChatViewProvider } from "./chatView";

let mcpClient: TuringMCPClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  // 初始化 MCP 客户端
  mcpClient = new TuringMCPClient(context);

  // 注册聊天面板
  const chatProvider = new TuringChatViewProvider(context, mcpClient);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("turingChat", chatProvider)
  );

  // 注册命令
  context.subscriptions.push(
    vscode.commands.registerCommand("turing.startChat", () => {
      vscode.commands.executeCommand("turingChat.focus");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("turing.applyDiff", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("没有打开的编辑器");
        return;
      }
      // Diff application will be handled via chat interaction
      vscode.window.showInformationMessage("请在 Turing 聊天中发送编辑请求");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("turing.explainSelection", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        return;
      }
      const selection = editor.document.getText(editor.selection);
      if (!selection) {
        vscode.window.showWarningMessage("请先选择代码");
        return;
      }
      const filePath = editor.document.uri.fsPath;
      const prompt = `请解释以下代码（来自 ${filePath}）：\n\n\`\`\`\n${selection}\n\`\`\``;
      chatProvider.sendMessage(prompt);
      vscode.commands.executeCommand("turingChat.focus");
    })
  );

  vscode.window.showInformationMessage("Turing Agent 已激活");
}

export function deactivate() {
  mcpClient?.dispose();
}
