#!/usr/bin/env python3
"""入口：Turing 自进化编程智能体 CLI（v0.6.0）

提供两种运行模式：

交互式 REPL::

    python main.py                         # 默认配置
    python main.py -m qwen3-coder:30b      # 指定模型
    python main.py -c my_config.yaml       # 指定配置文件

单次执行::

    python main.py --one-shot "用 Python 实现一个 LRU Cache"

支持的斜杠命令::

    /help        — 显示帮助
    /status      — 查看记忆和演化统计
    /memory <kw> — 搜索所有记忆层
    /strategies  — 列出已学会的策略模板
    /evolution   — 查看进化日志
    /index <路径> — 索引项目到 RAG 知识库
    /new         — 开始新会话
    /save        — 保存当前会话
    /load <id>   — 加载历史会话
    /sessions    — 列出历史会话
    /exit        — 退出

Author: Jiangsheng Yu
License: MIT
"""

from __future__ import annotations

import argparse
import json
import sys
import os

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from turing.agent import TuringAgent
from turing.config import Config

console = Console()

BANNER = r"""
 ___________            .__
 \__    ___/_ _______  _|__| ____    ____
   |    | |  |  \_  __ \|  |/    \  / ___\
   |    | |  |  /|  | \/|  |   |  \/ /_/  >
   |____| |____/ |__|   |__|___|  /\___  /
                                \//_____/
    自进化编程智能体 · Powered by Qwen3-Coder
"""


def run_repl(agent: TuringAgent):
    """交互式 REPL 主循环

    启动后显示 ASCII Banner，进入 Read-Eval-Print 循环：
    - 以 '/' 开头的输入交由 :func:`handle_command` 处理（斜杠命令）
    - 其余输入作为编程任务传入 :func:`process_chat` 进行流式对话
    - Ctrl+C / EOF 优雅退出
    """
    console.print(Panel(BANNER, style="bold cyan", expand=False))
    console.print("[dim]输入编程任务开始对话。输入 /help 查看命令。输入 /exit 退出。[/dim]\n")

    agent.start_session()

    while True:
        try:
            user_input = console.input("[bold green]You > [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        if not user_input:
            continue

        # 斜杠命令
        if user_input.startswith("/"):
            handled = handle_command(user_input, agent)
            if handled == "exit":
                break
            continue

        # 正常对话
        console.print()
        process_chat(agent, user_input)
        console.print()


def process_chat(agent: TuringAgent, user_input: str):
    """处理一次对话，将 Agent 流式事件渲染为 Rich 终端输出

    事件类型与渲染：
      - thinking   : 💭 灰色斜体显示推理过程
      - tool_call  : 🔧 黄色显示工具名 + 参数预览（截断 120 字符）
      - tool_result: ✓/✗ 绿色成功 / 红色失败
      - text       : Markdown 面板渲染最终回答
      - reflection : 📝 经验记录摘要
      - error      : ❌ 红色错误信息

    Args:
        agent: TuringAgent 实例
        user_input: 用户输入的编程任务描述
    """
    for event in agent.chat(user_input):
        etype = event["type"]

        if etype == "thinking":
            console.print(f"[dim italic]💭 {event['content']}[/dim italic]")

        elif etype == "tool_call":
            name = event["name"]
            args_preview = json.dumps(event["args"], ensure_ascii=False)
            if len(args_preview) > 120:
                args_preview = args_preview[:120] + "..."
            console.print(f"[yellow]🔧 调用工具: {name}[/yellow] [dim]{args_preview}[/dim]")

        elif etype == "tool_result":
            result = event["result"]
            if "error" in result:
                console.print(f"[red]   ✗ {result['error']}[/red]")
            else:
                # 如果结果包含 diff 预览，高亮显示（对标 Claude Code / Aider）
                diff_text = result.get("diff", "")
                if diff_text:
                    from rich.syntax import Syntax
                    console.print(f"[green]   ✓[/green] {result.get('path', '')} ({result.get('replacements', 1)} edit)")
                    console.print(Syntax(diff_text[:2000], "diff", theme="monokai", padding=1))
                else:
                    result_preview = json.dumps(result, ensure_ascii=False)
                    if len(result_preview) > 200:
                        result_preview = result_preview[:200] + "..."
                    console.print(f"[green]   ✓[/green] [dim]{result_preview}[/dim]")

        elif etype == "text":
            console.print(Panel(
                Markdown(event["content"]),
                title="[bold cyan]Turing[/bold cyan]",
                border_style="cyan",
                expand=True,
            ))

        elif etype == "reflection":
            data = event["data"]
            outcome = data.get("outcome", "unknown")
            color = "green" if outcome == "success" else "red" if outcome == "failure" else "yellow"
            console.print(
                f"[dim italic]📝 经验记录: {outcome} "
                f"(使用了 {data.get('actions_count', 0)} 次工具调用)[/dim italic]"
            )

        elif etype == "error":
            console.print(f"[bold red]❌ {event['content']}[/bold red]")

        elif etype == "done":
            pass


def handle_command(cmd: str, agent: TuringAgent) -> str | None:
    """处理斜杠命令

    支持的命令:
      /help         — 显示命令帮助
      /status       — 显示记忆与演化统计面板
      /memory <kw>  — 跨层搜索记忆
      /strategies   — 列出已归纳的策略模板
      /evolution    — 显示最近 5 条进化日志
      /index <path> — 将项目索引到 RAG 知识库
      /compact      — 压缩对话上下文（对标 Claude Code）
      /cost         — 显示本次会话 Token 消耗统计
      /diff         — 显示最近的文件编辑 diff
      /undo         — 回滚最近一次 git commit（自动提交的检查点）
      /config [key] — 查看当前配置
      /clear        — 清空终端屏幕
      /save         — 保存当前会话
      /load <id>    — 加载历史会话
      /sessions     — 列出历史会话
      /new          — 清空工作记忆，开始新会话
      /exit         — 退出 REPL
    """
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit", "/q"):
        agent.memory.cleanup_session()
        console.print("[dim]会话已结束，工作记忆已清理。再见！[/dim]")
        return "exit"

    elif command == "/help":
        help_table = Table(title="Turing 命令", show_header=True)
        help_table.add_column("命令", style="cyan")
        help_table.add_column("说明")
        help_table.add_row("/help", "显示此帮助")
        help_table.add_row("/status", "显示记忆和演化统计")
        help_table.add_row("/memory <query>", "搜索记忆（所有层）")
        help_table.add_row("/strategies", "列出已学会的策略")
        help_table.add_row("/evolution", "显示演化日志")
        help_table.add_row("/index <path>", "索引项目到 RAG 知识库")
        help_table.add_row("/compact", "压缩对话上下文（释放空间）")
        help_table.add_row("/cost", "显示 Token 消耗统计")
        help_table.add_row("/diff", "显示最近的文件编辑 diff")
        help_table.add_row("/undo", "回滚最近一次 git 自动提交")
        help_table.add_row("/config [key]", "查看配置项")
        help_table.add_row("/clear", "清空终端屏幕")
        help_table.add_row("/save", "保存当前会话")
        help_table.add_row("/load <id>", "加载历史会话")
        help_table.add_row("/sessions", "列出历史会话")
        help_table.add_row("/new", "开始新会话（清空工作记忆）")
        help_table.add_row("/exit", "退出")
        console.print(help_table)

    elif command == "/status":
        mem_stats = agent.get_memory_stats()
        evo_stats = agent.get_evolution_stats()
        table = Table(title="Turing 状态", show_header=True)
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")
        table.add_row("工作记忆条目", str(mem_stats.get("working_items", 0)))
        table.add_row("长期记忆条目", str(mem_stats.get("long_term_items", 0)))
        table.add_row("持久策略数", str(mem_stats.get("persistent_strategies", 0)))
        table.add_row("累计任务数", str(evo_stats.get("total_tasks", 0)))
        table.add_row("已掌握策略", ", ".join(evo_stats.get("strategies", [])) or "暂无")
        outcomes = evo_stats.get("outcomes", {})
        if outcomes:
            success = outcomes.get("success", 0)
            total = sum(outcomes.values())
            rate = f"{success}/{total} ({success/max(total,1)*100:.0f}%)"
            table.add_row("成功率", rate)
        console.print(table)

    elif command == "/memory":
        if not arg:
            console.print("[yellow]用法: /memory <搜索关键词>[/yellow]")
        else:
            results = agent.memory.retrieve(arg, ["working", "long_term", "persistent"], top_k=10)
            if results:
                for r in results:
                    layer = r.get("layer", "?")
                    content = r.get("content", "")[:200]
                    tags = ", ".join(r.get("tags", []))
                    console.print(f"[cyan][{layer}][/cyan] {content}")
                    if tags:
                        console.print(f"  [dim]标签: {tags}[/dim]")
            else:
                console.print("[dim]未找到相关记忆[/dim]")

    elif command == "/strategies":
        strategies = agent.memory.persistent.list_strategies()
        if strategies:
            for s in strategies:
                data = agent.memory.persistent.load_strategy(s)
                rate = data.get("success_rate", 0) if data else 0
                console.print(f"  📋 [cyan]{s}[/cyan] (成功率: {rate:.0%})")
        else:
            console.print("[dim]暂无策略模板[/dim]")

    elif command == "/evolution":
        log = agent.memory.persistent.get_evolution_log()
        if log:
            for entry in log[-5:]:  # 最近 5 条
                console.print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            console.print("[dim]暂无进化日志[/dim]")

    elif command == "/index":
        if not arg:
            console.print("[yellow]用法: /index <项目路径>[/yellow]")
        else:
            console.print(f"[dim]正在索引 {arg} ...[/dim]")
            result = agent.index_project(arg)
            console.print(f"[green]索引完成: {result}[/green]")

    elif command == "/new":
        agent.memory.cleanup_session()
        agent.start_session()
        console.print("[dim]已开始新会话，工作记忆已清空。[/dim]")

    elif command == "/compact":
        result = agent.compact()
        if result.get("status") == "ok":
            console.print(
                f"[green]上下文已压缩[/green]: "
                f"{result['messages_before']} → {result['messages_after']} 条消息, "
                f"压缩率 {result['compression_ratio']}"
            )
        else:
            console.print(f"[dim]{result.get('reason', '无需压缩')}[/dim]")

    elif command == "/cost":
        stats = agent.get_token_stats()
        table = Table(title="Token 消耗统计", show_header=True)
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")
        table.add_row("LLM 调用次数", str(stats.get("llm_calls", 0)))
        table.add_row("输入 Tokens", f"{stats.get('total_input_tokens', 0):,}")
        table.add_row("输出 Tokens", f"{stats.get('total_output_tokens', 0):,}")
        total = stats.get("total_input_tokens", 0) + stats.get("total_output_tokens", 0)
        table.add_row("总计 Tokens", f"{total:,}")
        budget = agent.config.get("model.token_budget")
        if budget:
            pct = total / budget * 100
            table.add_row("预算使用", f"{pct:.1f}% ({total:,}/{budget:,})")
        console.print(table)

    elif command == "/diff":
        import subprocess
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "--stat"], capture_output=True, text=True, timeout=10,
                cwd=agent.config.get("security.workspace_root", "."),
            )
            if result.stdout.strip():
                console.print(Panel(result.stdout.strip(), title="最近变更", border_style="yellow"))
                # 显示详细 diff
                detail = subprocess.run(
                    ["git", "diff", "HEAD~1"], capture_output=True, text=True, timeout=10,
                    cwd=agent.config.get("security.workspace_root", "."),
                )
                if detail.stdout.strip():
                    diff_text = detail.stdout.strip()
                    if len(diff_text) > 3000:
                        diff_text = diff_text[:3000] + "\n... (truncated)"
                    from rich.syntax import Syntax
                    console.print(Syntax(diff_text, "diff", theme="monokai"))
            else:
                console.print("[dim]无最近变更[/dim]")
        except Exception:
            console.print("[dim]无法获取 diff（可能不在 git 仓库中）[/dim]")

    elif command == "/undo":
        import subprocess
        try:
            # 检查最近一次提交是否是自动检查点
            log_result = subprocess.run(
                ["git", "log", "--oneline", "-1"], capture_output=True, text=True, timeout=5,
                cwd=agent.config.get("security.workspace_root", "."),
            )
            last_commit = log_result.stdout.strip()
            if "turing-checkpoint" in last_commit.lower() or "auto-commit" in last_commit.lower():
                console.print(f"[yellow]即将回滚: {last_commit}[/yellow]")
                try:
                    confirm = console.input("[yellow]确认回滚? [y/N]: [/yellow]").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    confirm = "n"
                if confirm in ("y", "yes"):
                    subprocess.run(
                        ["git", "reset", "--soft", "HEAD~1"], timeout=5,
                        cwd=agent.config.get("security.workspace_root", "."),
                    )
                    console.print("[green]已回滚最近一次自动提交[/green]")
                else:
                    console.print("[dim]已取消[/dim]")
            else:
                console.print(f"[dim]最近提交不是自动检查点: {last_commit}[/dim]")
        except Exception:
            console.print("[dim]无法执行 undo（可能不在 git 仓库中）[/dim]")

    elif command == "/config":
        if arg:
            val = agent.config.get(arg)
            if val is not None:
                console.print(f"[cyan]{arg}[/cyan] = [green]{val}[/green]")
            else:
                console.print(f"[dim]配置项 '{arg}' 不存在[/dim]")
        else:
            console.print(Panel(
                json.dumps(agent.config._data, ensure_ascii=False, indent=2),
                title="当前配置", border_style="cyan",
            ))

    elif command == "/clear":
        console.clear()

    elif command == "/save":
        sid = agent.save_conversation()
        console.print(f"[green]会话已保存: {sid}[/green]")

    elif command == "/load":
        if not arg:
            console.print("[yellow]用法: /load <session_id>[/yellow]")
        else:
            if agent.load_conversation(arg):
                console.print(f"[green]会话 {arg} 已恢复[/green]")
            else:
                console.print(f"[red]会话 {arg} 未找到[/red]")

    elif command == "/sessions":
        sessions = agent.list_conversations()
        if sessions:
            table = Table(title="历史会话", show_header=True)
            table.add_column("ID", style="cyan")
            table.add_column("消息数")
            table.add_column("摘要")
            for s in sessions[:10]:
                table.add_row(
                    s["session_id"],
                    str(s["message_count"]),
                    s.get("first_message", "")[:60],
                )
            console.print(table)
        else:
            console.print("[dim]暂无历史会话[/dim]")

    else:
        console.print(f"[yellow]未知命令: {command}。输入 /help 查看可用命令。[/yellow]")

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Turing —— 自进化编程智能体",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help="覆盖配置中的模型名（如 qwen3-coder:30b）",
    )
    parser.add_argument(
        "--one-shot",
        default=None,
        help="单次执行模式：直接处理指定任务后退出",
    )
    parser.add_argument(
        "--continue", dest="continue_session",
        action="store_true",
        help="恢复最近一次会话（对标 Claude Code --continue）",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="恢复指定 session_id 的会话（对标 Claude Code --resume）",
    )
    args = parser.parse_args()

    # 加载配置
    Config.reset()
    config = Config.load(args.config)

    # 命令行参数覆盖
    if args.model:
        config._data["model"]["name"] = args.model

    # 初始化 Agent
    agent = TuringAgent(config)

    if args.one_shot:
        # 单次执行模式
        agent.start_session()
        process_chat(agent, args.one_shot)
    elif args.continue_session or args.resume:
        # 会话恢复模式（对标 Claude Code --continue / --resume）
        agent.start_session()
        restored = False
        if args.resume:
            restored = agent.load_conversation(args.resume)
            if not restored:
                console.print(f"[red]会话 {args.resume} 未找到[/red]")
        else:
            # --continue: 恢复最近一次会话
            sessions = agent.list_conversations()
            if sessions:
                restored = agent.load_conversation(sessions[0]["session_id"])

        if restored:
            console.print(f"[green]已恢复会话: {agent._session_id}[/green]")
        else:
            console.print("[dim]未找到可恢复的会话，开始新会话[/dim]")
        run_repl(agent)
    else:
        # 交互式 REPL
        run_repl(agent)


if __name__ == "__main__":
    main()
