"""Claude Code。~/.claude/projects/<作業ディレクトリ>/<セッションID>.jsonl を読む。"""
import glob
import os
import re

from ..files import blocks, parse, tail_lines, under
from ..model import Session, brief, keep, message, tool

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
# 発言の前に自動で差し込まれる文脈。ユーザーの言葉ではないので取り除く
INJECTED = re.compile(r"<(system-reminder)\b[^>]*>.*?</\1>\s*", re.S)
NOISE = ("<task-notification", "<local-command-", "<wake", "<relay", "<teammate-message",
         "<bash-stdout", "<bash-stderr", "[Request interrupted")
COMMAND = re.compile(r"<command-name>(.*?)</command-name>(?:.*?<command-args>(.*?)</command-args>)?", re.S)
BASH = re.compile(r"<bash-input>(.*?)</bash-input>", re.S)


def iter_sessions():
    # サブエージェントの記録は <セッションID>/subagents/ の下にあるので、この深さでは拾わない
    for path in glob.glob(os.path.join(ROOT, "*", "*.jsonl")):
        yield os.path.getmtime(path), lambda path=path: load(path)


def find(ref):
    paths = [ref] if under(ref, ROOT) else glob.glob(os.path.join(ROOT, "*", f"{ref}*.jsonl"))
    return [load(p) for p in paths]


def load(path):
    session = Session("claude", id=os.path.basename(path)[:-6], path=path)
    custom = ai = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not session.cwd and '"cwd"' in line:
                session.cwd = (parse(line) or {}).get("cwd", "")
            if '"type":"custom-title"' in line:
                custom = (parse(line) or {}).get("customTitle", custom)
            elif '"type":"ai-title"' in line:
                ai = (parse(line) or {}).get("aiTitle", ai)
    for line in reversed(tail_lines(path)):
        if '"type":"assistant"' in line:
            model = ((parse(line) or {}).get("message") or {}).get("model")
            if model and model != "<synthetic>":
                session.model = model
                break
    session.title = custom or ai
    return session


def read_messages(session):
    messages, calls = [], {}
    with open(session.path, encoding="utf-8", errors="replace") as f:
        for line in f:
            d = parse(line) or {}
            # 圧縮しても元の発言は残るので、圧縮の要約は読まない
            if d.get("type") not in ("user", "assistant") or d.get("isSidechain") or d.get("isMeta") \
                    or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
                continue
            ts, content = d.get("timestamp"), blocks((d.get("message") or {}).get("content"))
            if d["type"] == "assistant":
                for b in content:
                    if b.get("type") == "text" and b.get("text", "").strip():
                        messages.append(message("assistant", ts, b["text"]))
                    elif b.get("type") == "tool_use":
                        calls[b.get("id")] = tool(ts, b.get("name", ""), b.get("input"))
                        messages.append(calls[b.get("id")])
                continue
            for b in content:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                    calls[b["tool_use_id"]].output = brief(b.get("content") or "")
            # 新しい版は origin で人の発言を示す。古い版は origin がない
            if (d.get("origin") or {}).get("kind") in (None, "human") and (text := user_text(content)):
                messages.append(message("user", ts, text))
    return keep(messages)


def user_text(content):
    text = "\n".join(b.get("text", "") if b.get("type") == "text" else "[画像]" for b in content if b.get("type") in ("text", "image"))
    text = INJECTED.sub("", text).strip()
    if text.startswith(NOISE):
        return ""
    if m := COMMAND.search(text):
        return f"{m.group(1)} {(m.group(2) or '').strip()}"
    if m := BASH.search(text):
        return f"! {m.group(1).strip()}"
    return text
