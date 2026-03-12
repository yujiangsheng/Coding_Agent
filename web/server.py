"""Turing Web UI — Flask 后端（v0.6.0）

提供 VS Code 风格前端的 HTTP API 和 SSE 流式聊天接口。

API 路由（10 个端点）::

    POST /api/chat           — SSE 流式聊天（Server-Sent Events）
    GET  /api/status         — 记忆与演化统计（含十一维评分）
    GET  /api/memory/search  — 跨层记忆搜索 (?q=关键词)
    GET  /api/strategies     — 列出策略模板（含预播种策略）
    GET  /api/evolution      — 获取进化日志（最近 20 条）
    POST /api/new-session    — 开始新会话
    POST /api/index-project  — 索引项目到 RAG 知识库
    GET  /api/files/list     — 列出目录内容 (?path=目录路径)
    GET  /api/files/read     — 读取文件内容 (?path=文件路径)
    POST /api/shutdown       — 关闭服务器

启动方式::

    python web/server.py                  # 默认 http://127.0.0.1:5000
    python web/server.py -p 8080          # 自定义端口
    python web/server.py --host 0.0.0.0   # 允许外部访问

Author: Jiangsheng Yu
License: MIT
"""

from __future__ import annotations

import functools
import json
import logging
import os
import secrets
import sys
import time as _time
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)

# 添加项目根目录到 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from turing.agent import TuringAgent  # noqa: E402
from turing.config import Config  # noqa: E402

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)
app.config["SECRET_KEY"] = os.environ.get("TURING_SECRET", secrets.token_hex(32))

# --- CORS 白名单 ---
_ALLOWED_ORIGINS = {"http://127.0.0.1:5000", "http://localhost:5000"}

@app.after_request
def _add_cors(response):
    origin = request.headers.get("Origin", "")
    if origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# --- 认证中间件 ---
_API_TOKEN = os.environ.get("TURING_API_TOKEN", "")

def require_auth(f):
    """Bearer token 认证装饰器（仅在设置了 TURING_API_TOKEN 时生效）"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _API_TOKEN:
            return f(*args, **kwargs)  # 未配置 token 时不启用认证
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not secrets.compare_digest(token, _API_TOKEN):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# --- 速率限制 ---
import threading as _threading
_rate_lock = _threading.Lock()
_rate_tracker: dict = {}  # {ip: [timestamps]}
_RATE_LIMIT = 30  # 每分钟最大请求数
_RATE_WINDOW = 60  # 秒

def _check_rate_limit() -> bool:
    ip = request.remote_addr or "unknown"
    now = _time.time()
    with _rate_lock:
        # v7.0: 定期清理过期 IP，防止无界增长
        if len(_rate_tracker) > 1000:
            stale = [k for k, v in _rate_tracker.items()
                     if not v or now - v[-1] > _RATE_WINDOW]
            for k in stale:
                del _rate_tracker[k]
        if ip not in _rate_tracker:
            _rate_tracker[ip] = []
        _rate_tracker[ip] = [t for t in _rate_tracker[ip] if now - t < _RATE_WINDOW]
        if len(_rate_tracker[ip]) >= _RATE_LIMIT:
            return False
        _rate_tracker[ip].append(now)
        return True

# --- 工作区路径约束 ---
_WORKSPACE_ROOT = ROOT

def _validate_path(path_str: str) -> Path | None:
    """验证路径在工作区范围内，返回 resolved Path 或 None"""
    try:
        target = Path(path_str).resolve()
        # 必须在工作区根目录之下
        target.relative_to(_WORKSPACE_ROOT)
        return target
    except (ValueError, OSError):
        return None

# ---------------------------------------------------------------------------
# 全局 Agent 实例
# ---------------------------------------------------------------------------

_agent: TuringAgent | None = None


def get_agent() -> TuringAgent:
    """获取或创建全局 Agent 单例"""
    global _agent
    if _agent is None:
        Config.reset()
        cfg_path = ROOT / "config.yaml"
        config = Config.load(str(cfg_path) if cfg_path.exists() else None)
        _agent = TuringAgent(config)
        _agent.start_session()
    return _agent


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------


@app.route("/api/chat", methods=["POST"])
@require_auth
def chat():
    """流式聊天接口 (Server-Sent Events)"""
    if not _check_rate_limit():
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "消息不能为空"}), 400
    if len(message) > 50000:
        return jsonify({"error": "消息过长（上限 50000 字符）"}), 400

    agent = get_agent()

    def generate():
        try:
            for event in agent.chat(message):
                payload = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {payload}\n\n"
        except Exception as e:
            err = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        yield 'data: {"type": "stream_end"}\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/status")
def status():
    """获取记忆与演化统计"""
    agent = get_agent()
    return jsonify({
        "memory": agent.get_memory_stats(),
        "evolution": agent.get_evolution_stats(),
    })


@app.route("/api/memory/search")
def memory_search():
    """搜索记忆"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": []})
    agent = get_agent()
    results = agent.memory.retrieve(q, ["working", "long_term", "persistent"], top_k=10)
    return jsonify({"results": results})


@app.route("/api/strategies")
def strategies():
    """列出策略模板"""
    agent = get_agent()
    names = agent.memory.persistent.list_strategies()
    items = []
    for name in names:
        data = agent.memory.persistent.load_strategy(name)
        items.append({"name": name, "data": data})
    return jsonify({"strategies": items})


@app.route("/api/evolution")
def evolution_log():
    """获取演化日志"""
    agent = get_agent()
    log = agent.memory.persistent.get_evolution_log()
    return jsonify({"log": log[-20:]})


@app.route("/api/new-session", methods=["POST"])
@require_auth
def new_session():
    """开始新会话"""
    agent = get_agent()
    agent.memory.cleanup_session()
    agent.start_session()
    return jsonify({"status": "ok"})


@app.route("/api/index-project", methods=["POST"])
@require_auth
def index_project():
    """索引项目到 RAG 知识库"""
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify({"error": "请提供项目路径"}), 400
    agent = get_agent()
    result = agent.index_project(path)
    return jsonify(result)


@app.route("/api/files/list")
@require_auth
def files_list():
    """列出指定目录下的文件和子目录"""
    dir_path = request.args.get("path", "").strip()
    if not dir_path:
        dir_path = str(ROOT)

    target = _validate_path(dir_path)
    if target is None:
        return jsonify({"error": "安全限制：路径超出工作区范围"}), 403

    if not target.is_dir():
        return jsonify({"error": "路径不存在或不是目录"}), 404

    items = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            # 跳过隐藏文件和常见噪声目录
            if entry.name.startswith(".") and entry.name not in (".env",):
                continue
            if entry.name in ("__pycache__", "node_modules", ".git", "turing_data"):
                continue
            items.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
            })
    except PermissionError:
        return jsonify({"error": "无权读取该目录"}), 403

    return jsonify({
        "path": str(target),
        "parent": str(target.parent) if target != target.parent else None,
        "items": items,
    })


@app.route("/api/files/read")
@require_auth
def files_read():
    """读取文件内容"""
    file_path = request.args.get("path", "").strip()
    if not file_path:
        return jsonify({"error": "缺少文件路径"}), 400

    target = _validate_path(file_path)
    if target is None:
        return jsonify({"error": "安全限制：路径超出工作区范围"}), 403

    if not target.is_file():
        return jsonify({"error": "文件不存在"}), 404

    # 检查文件大小（限制 2MB）
    size = target.stat().st_size
    if size > 2 * 1024 * 1024:
        return jsonify({"error": "文件过大（超过 2MB）"}), 413

    # 检测是否为二进制文件
    try:
        content = target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return jsonify({"error": "无法显示二进制文件"}), 415

    # 推断语言
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".html": "html", ".css": "css", ".json": "json", ".yaml": "yaml",
        ".yml": "yaml", ".md": "markdown", ".sh": "bash", ".bash": "bash",
        ".rs": "rust", ".go": "go", ".java": "java", ".c": "c",
        ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".rb": "ruby",
        ".php": "php", ".sql": "sql", ".xml": "xml", ".toml": "toml",
        ".txt": "plaintext", ".cfg": "ini", ".ini": "ini",
        ".lean": "lean", ".swift": "swift", ".kt": "kotlin",
        ".dockerfile": "dockerfile", ".lua": "lua", ".r": "r",
    }
    suffix = target.suffix.lower()
    lang = lang_map.get(suffix, "plaintext")
    if target.name == "Dockerfile":
        lang = "dockerfile"
    elif target.name == "Makefile":
        lang = "makefile"

    return jsonify({
        "path": str(target),
        "name": target.name,
        "language": lang,
        "size": size,
        "content": content,
        "line_count": content.count("\n") + 1,
    })


@app.route("/api/shutdown", methods=["POST"])
@require_auth
def shutdown():
    """关闭服务器（需要认证）"""
    logger.info("收到关闭请求，来源: %s", request.remote_addr)
    func = request.environ.get("werkzeug.server.shutdown")
    if func is not None:
        func()
    else:
        import threading
        import signal
        # 使用 SIGTERM 安全关闭，允许清理
        threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
    return jsonify({"status": "ok", "message": "服务器正在关闭"})


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Turing Web UI")
    parser.add_argument("-p", "--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"\n  🤖 Turing Web UI")
    print(f"  → http://{args.host}:{args.port}\n")

    app.run(host=args.host, port=args.port,
            debug=os.environ.get("TURING_DEBUG", "").lower() in ("1", "true"),
            threaded=True)
