"""Codex。~/.codex/sessions/<年>/<月>/<日>/rollout-*.jsonl（古いものは .jsonl.zst）を読む。

1つのセッションが複数の rollout ファイルに分かれることがある。ファイル名の最初のIDがセッションID。
"""
import glob
import os
import re

from ..files import open_text, parse, reversed_file, tail_lines, under
from ..model import Session, keep, message, tool

ROOT = os.path.join(os.path.expanduser("~"), ".codex", "sessions")
INDEX = os.path.join(os.path.expanduser("~"), ".codex", "session_index.jsonl")
SESSION_ID = re.compile(r"T\d\d-\d\d-\d\d-([0-9a-f-]{36})")
# 発言の前に自動で差し込まれる文脈。ユーザーの言葉ではないので取り除く
INJECTED = re.compile(r"<(system-reminder|in-app-browser-context|environment_context)\b[^>]*>.*?</\1>\s*", re.S)
REQUEST = re.compile(r"^## My request:\s*\n", re.M)
ATTACHMENT = re.compile(r"^## (.+?): ", re.M)


def files():
    pattern = os.path.join(ROOT, "*", "*", "*", "*.jsonl")
    return glob.glob(pattern) + glob.glob(pattern + ".zst")


def session_id(path):
    m = SESSION_ID.search(os.path.basename(path))
    return m.group(1) if m else path


def latest_files(paths):
    """セッションIDごとに、最後に更新されたファイルを選ぶ。"""
    latest = {}
    for path in paths:
        mtime = os.path.getmtime(path)
        key = session_id(path)
        if key not in latest or mtime > latest[key][1]:
            latest[key] = (path, mtime)
    return latest.values()


def iter_sessions():
    names = titles()
    for path, mtime in latest_files(files()):
        yield mtime, lambda path=path: load(path, names, skip_subagents=True)


def find(ref):
    if under(ref, ROOT):
        ref = session_id(ref)
    paths = files()
    sids = {session_id(p) for p in paths if session_id(p).startswith(ref)}
    names = titles()
    return [load(path, names) for path, _ in latest_files(p for p in paths if session_id(p) in sids)]


def titles():
    names = {}
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8", errors="replace") as f:
            for line in f:
                row = parse(line) or {}
                if row.get("id") and row.get("thread_name"):
                    names[row["id"]] = row["thread_name"]
    return names


def load(path, names, skip_subagents=False):
    with open_text(path) as f:
        meta = (parse(f.readline()) or {}).get("payload", {})
    # Guardian review などのサブエージェントは一覧から外す
    if skip_subagents and meta.get("thread_source", "user") != "user":
        return None
    session = Session("codex", id=meta.get("id", ""), cwd=meta.get("cwd", ""), title=names.get(meta.get("id"), ""), path=path)
    readers = (reversed_file,) if path.endswith(".zst") else (lambda p: reversed(tail_lines(p)), reversed_file)
    for lines in (read(path) for read in readers):
        line = next((l for l in lines if '"type":"turn_context"' in l), None)
        if line:
            session.model = ((parse(line) or {}).get("payload") or {}).get("model", "")
            break
    return session


def read_messages(session):
    sid = session_id(session.path)
    paths = sorted((p for p in files() if session_id(p) == sid), key=os.path.basename)
    messages, seen = [], set()
    for path in paths:
        with open_text(path) as f:
            for line in f:
                if '"item_completed"' not in line:
                    continue
                d = parse(line) or {}
                item = (d.get("payload") or {}).get("item") or {}
                # 分割をまたいで同じ項目が出ることがあるので、IDで重複を除く
                if item.get("id") in seen:
                    continue
                seen.add(item.get("id"))
                if msg := convert(d.get("timestamp"), item):
                    messages.append(msg)
    return keep(messages)


def convert(ts, item):
    kind = item.get("type")
    text = "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))
    if kind == "UserMessage":
        return user_message(ts, text)
    if kind == "AgentMessage":
        return message("assistant", ts, text, "commentary" if item.get("phase") == "commentary" else None)
    if kind in ("Reasoning", "ContextCompaction"):
        return None
    return tool_message(ts, item)


def user_message(ts, text):
    text = INJECTED.sub("", text).strip()
    if text.startswith("<turn_aborted"):
        return None
    if text.startswith("<heartbeat>"):
        m = re.search(r"<instructions>(.*?)</instructions>", text, re.S)
        return message("user", ts, m.group(1) if m else text, "automation")
    if text.startswith("<send_user_message_question_reply>"):
        rows = parse(text.split(">", 1)[1].rsplit("<", 1)[0]) or []
        return message("user", ts, "\n".join(f"Q: {r.get('question', '')}\nA: {r.get('answer', '')}" for r in rows), "answer")
    if m := REQUEST.search(text):
        names = ATTACHMENT.findall(text[:m.start()])
        text = text[m.end():] + (f"\n[添付] {', '.join(names)}" if names else "")
    return message("user", ts, text)


def tool_message(ts, item):
    kind = item.get("type")
    if kind == "CommandExecution":
        command = item.get("command") or ""
        return tool(ts, "shell", command[-1] if isinstance(command, list) else command, item.get("aggregated_output") or "")
    if kind == "McpToolCall":
        result = item.get("result") or {}
        output = result.get("content") if isinstance(result, dict) else result
        return tool(ts, f"{item.get('server')}.{item.get('tool')}", item.get("arguments"), output or item.get("error") or "")
    if kind == "FileChange":
        return tool(ts, "edit", ", ".join(item.get("changes") or {}))
    if kind == "Extension":
        return tool(ts, item.get("kind") or "extension", item.get("query") or item.get("action"))
    if kind == "ImageView":
        return tool(ts, "view_image", item.get("path", ""))
    if kind in ("SubAgentActivity", "CollabAgentToolCall"):
        return tool(ts, "subagent", item.get("agent_path") or item.get("tool") or "")
    if kind == "FunctionCallOutput":
        return tool(ts, item.get("name") or "function", "", item.get("output") or "")
    return None
