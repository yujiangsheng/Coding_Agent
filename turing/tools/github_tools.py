"""GitHub / GitLab API 工具集成（对标 Devin / Codex 的平台集成能力）

提供 GitHub REST API 工具，使 Agent 可以直接操作 GitHub 仓库：
- 创建 Pull Request / Issue
- 列出 Issue / PR
- 添加评论

通过环境变量 GITHUB_TOKEN 或 config.yaml 中 github.token 配置认证。
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any

from turing.tools.registry import tool


def _get_github_token() -> str:
    """获取 GitHub Token（优先环境变量，其次 config）"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        try:
            from turing.config import Config
            cfg = Config.load()
            token = cfg.get("github.token", "")
        except Exception:
            pass
    return token


def _github_api(
    method: str,
    endpoint: str,
    data: dict | None = None,
    token: str = "",
) -> dict:
    """统一 GitHub REST API 调用"""
    if not token:
        token = _get_github_token()
    if not token:
        return {"error": "未配置 GitHub Token。请设置环境变量 GITHUB_TOKEN 或在 config.yaml 中配置 github.token"}

    url = f"https://api.github.com{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Turing-Agent/3.0",
    }

    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = resp.read().decode("utf-8")
            if resp_data:
                return json.loads(resp_data)
            return {"status": "ok"}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            return {"error": f"GitHub API {e.code}: {err_json.get('message', err_body[:200])}"}
        except json.JSONDecodeError:
            return {"error": f"GitHub API {e.code}: {err_body[:200]}"}
    except urllib.error.URLError as e:
        return {"error": f"GitHub API 请求失败: {e.reason}"}


@tool(
    name="github_create_issue",
    description="在 GitHub 仓库创建 Issue。需要设置 GITHUB_TOKEN 环境变量。",
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "仓库所有者"},
            "repo": {"type": "string", "description": "仓库名"},
            "title": {"type": "string", "description": "Issue 标题"},
            "body": {"type": "string", "description": "Issue 内容（Markdown）"},
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签列表（可选）",
            },
        },
        "required": ["owner", "repo", "title"],
    },
)
def github_create_issue(
    owner: str, repo: str, title: str, body: str = "", labels: list[str] | None = None,
) -> dict:
    """创建 GitHub Issue"""
    data: dict[str, Any] = {"title": title}
    if body:
        data["body"] = body
    if labels:
        data["labels"] = labels
    result = _github_api("POST", f"/repos/{owner}/{repo}/issues", data)
    if "error" in result:
        return result
    return {
        "status": "created",
        "number": result.get("number"),
        "url": result.get("html_url", ""),
        "title": result.get("title", ""),
    }


@tool(
    name="github_create_pr",
    description="在 GitHub 仓库创建 Pull Request。需要设置 GITHUB_TOKEN 环境变量。",
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "仓库所有者"},
            "repo": {"type": "string", "description": "仓库名"},
            "title": {"type": "string", "description": "PR 标题"},
            "body": {"type": "string", "description": "PR 描述（Markdown）"},
            "head": {"type": "string", "description": "源分支名"},
            "base": {"type": "string", "description": "目标分支名（默认 main）"},
        },
        "required": ["owner", "repo", "title", "head"],
    },
)
def github_create_pr(
    owner: str, repo: str, title: str, head: str,
    body: str = "", base: str = "main",
) -> dict:
    """创建 GitHub Pull Request"""
    data = {"title": title, "head": head, "base": base}
    if body:
        data["body"] = body
    result = _github_api("POST", f"/repos/{owner}/{repo}/pulls", data)
    if "error" in result:
        return result
    return {
        "status": "created",
        "number": result.get("number"),
        "url": result.get("html_url", ""),
        "title": result.get("title", ""),
    }


@tool(
    name="github_list_issues",
    description="列出 GitHub 仓库的 Issue 列表。需要设置 GITHUB_TOKEN 环境变量。",
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "仓库所有者"},
            "repo": {"type": "string", "description": "仓库名"},
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "Issue 状态过滤（默认 open）",
            },
            "limit": {"type": "integer", "description": "返回条数（默认 10）"},
        },
        "required": ["owner", "repo"],
    },
)
def github_list_issues(
    owner: str, repo: str, state: str = "open", limit: int = 10,
) -> dict:
    """列出 GitHub Issue"""
    result = _github_api("GET", f"/repos/{owner}/{repo}/issues?state={state}&per_page={limit}")
    if isinstance(result, dict) and "error" in result:
        return result
    if isinstance(result, list):
        issues = [
            {
                "number": i.get("number"),
                "title": i.get("title", ""),
                "state": i.get("state", ""),
                "user": i.get("user", {}).get("login", ""),
                "labels": [l.get("name", "") for l in i.get("labels", [])],
                "url": i.get("html_url", ""),
            }
            for i in result[:limit]
        ]
        return {"count": len(issues), "issues": issues}
    return {"issues": [], "count": 0}


@tool(
    name="github_add_comment",
    description="在 GitHub Issue 或 PR 上添加评论。需要设置 GITHUB_TOKEN 环境变量。",
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "仓库所有者"},
            "repo": {"type": "string", "description": "仓库名"},
            "issue_number": {"type": "integer", "description": "Issue 或 PR 编号"},
            "body": {"type": "string", "description": "评论内容（Markdown）"},
        },
        "required": ["owner", "repo", "issue_number", "body"],
    },
)
def github_add_comment(
    owner: str, repo: str, issue_number: int, body: str,
) -> dict:
    """添加评论到 Issue/PR"""
    result = _github_api(
        "POST",
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"body": body},
    )
    if "error" in result:
        return result
    return {
        "status": "created",
        "url": result.get("html_url", ""),
    }


@tool(
    name="github_list_prs",
    description="列出 GitHub 仓库的 Pull Request 列表。需要设置 GITHUB_TOKEN 环境变量。",
    parameters={
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "仓库所有者"},
            "repo": {"type": "string", "description": "仓库名"},
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "PR 状态过滤（默认 open）",
            },
            "limit": {"type": "integer", "description": "返回条数（默认 10）"},
        },
        "required": ["owner", "repo"],
    },
)
def github_list_prs(
    owner: str, repo: str, state: str = "open", limit: int = 10,
) -> dict:
    """列出 GitHub Pull Request"""
    result = _github_api("GET", f"/repos/{owner}/{repo}/pulls?state={state}&per_page={limit}")
    if isinstance(result, dict) and "error" in result:
        return result
    if isinstance(result, list):
        prs = [
            {
                "number": p.get("number"),
                "title": p.get("title", ""),
                "state": p.get("state", ""),
                "user": p.get("user", {}).get("login", ""),
                "head": p.get("head", {}).get("ref", ""),
                "base": p.get("base", {}).get("ref", ""),
                "url": p.get("html_url", ""),
            }
            for p in result[:limit]
        ]
        return {"count": len(prs), "pull_requests": prs}
    return {"pull_requests": [], "count": 0}
