"""pi。~/.pi/agent/sessions/<作業ディレクトリ>/<時刻>_<セッションID>.jsonl を読む。"""
import glob
import os

from ..files import blocks, parse, under
from ..model import Session, brief, keep, message, tool

ROOT = os.path.join(os.path.expanduser("~"), ".pi", "agent", "sessions")


def iter_sessions():
    for path in glob.glob(os.path.join(ROOT, "*", "*.jsonl")):
        yield os.path.getmtime(path), lambda path=path: load(path)


def find(ref):
    paths = [ref] if under(ref, ROOT) else glob.glob(os.path.join(ROOT, "*", f"*_{ref}*.jsonl"))
    return [load(p) for p in paths]


def load(path):
    session = Session("pi", path=path)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"type":"session"' in line and not session.id:
                head = parse(line) or {}
                session.id, session.cwd = head.get("id", ""), head.get("cwd", "")
            elif '"type":"session_info"' in line:
                session.title = (parse(line) or {}).get("name") or session.title
            elif '"customType":"brayness-session-title"' in line:
                session.title = ((parse(line) or {}).get("data") or {}).get("title") or session.title
            elif '"type":"model_change"' in line:
                session.model = (parse(line) or {}).get("modelId") or session.model
    return session


def active_branch(path):
    """pi は会話を木で持つ。最後の項目から親をたどり、いま開いている枝だけを古い順に返す。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        entries = [e for e in map(parse, f) if e and e.get("id")]
    by_id = {e["id"]: e for e in entries}
    branch, node = [], entries[-1] if entries else None
    while node:
        branch.append(node)
        node = by_id.get(node.get("parentId"))
    return reversed(branch)


def read_messages(session):
    messages, calls = [], {}
    for e in active_branch(session.path):
        m, ts = e.get("message") or {}, e.get("timestamp")
        role, content = m.get("role"), blocks(m.get("content"))
        if role == "user":
            messages.append(message("user", ts, "\n".join(b.get("text", "") if b.get("type") == "text" else "[画像]" for b in content)))
        elif role == "assistant":
            for b in content:
                if b.get("type") == "text" and b.get("text", "").strip():
                    phase = (parse(b.get("textSignature") or "") or {}).get("phase")
                    messages.append(message("assistant", ts, b["text"], "commentary" if phase == "commentary" else None))
                elif b.get("type") == "toolCall":
                    calls[b.get("id")] = tool(ts, b.get("name", ""), b.get("arguments"))
                    messages.append(calls[b.get("id")])
        elif role == "toolResult" and m.get("toolCallId") in calls:
            calls[m["toolCallId"]].output = brief(m.get("content") or "")
        elif role == "bashExecution":
            # ユーザーが ! で自分で打ったコマンド
            messages.append(tool(ts, "user-bash", m.get("command", ""), m.get("output", "")))
    return keep(messages)
