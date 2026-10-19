"""Grok Bot。会話はサーバー側にあるため、アプリが手元に残すキャッシュを読む。

キャッシュは sand-client-persistence/ の *.blob で、ファイル名はキーを base32 にしたもの。
ボット一覧は `*.roster.last-roster`、ボットごとの直近の会話は `*.transcript.replicas.<ボットID>` に入る。
"""
import base64
import glob
import os

from ..files import parse
from ..model import Session, keep, message, tool

ROOT = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Grok Bot", "sand-client-persistence")


def blobs():
    for path in glob.glob(os.path.join(ROOT, "*.blob")):
        name = os.path.basename(path)[:-5].upper()
        try:
            yield base64.b32decode(name + "=" * (-len(name) % 8)).decode(), path
        except ValueError:
            continue


def read_value(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return (parse(f.read()) or {}).get("value") or {}


def rows():
    for key, path in blobs():
        if key.endswith(".roster.last-roster"):
            yield from read_value(path).get("rows") or []


def iter_sessions():
    for row in rows():
        if row.get("lastActivityAt"):
            yield row["lastActivityAt"] / 1000, lambda row=row: load(row)


def find(ref):
    return [load(row) for row in rows() if row.get("id", "").startswith(ref)]


def load(row):
    last = " ".join(((row.get("lastEntry") or {}).get("text") or "").split())
    title = row.get("name", "") + (f" — {last[:60]}" if last else "")
    return Session("grok", id=row.get("id", ""), title=title, path=row.get("path", ""))


def read_messages(session):
    # アプリが手元に残すのは直近の会話だけなので、古い発言は含まれない
    path = next((p for k, p in blobs() if k.endswith(f".transcript.replicas.{session.id}")), None)
    entries = (read_value(path).get("entries") or []) if path else []
    messages = [convert(e) for e in sorted(entries, key=lambda e: int(e.get("seq") or 0))]
    return keep([m for m in messages if m])


def convert(e):
    kind, ts, m = e.get("kind"), int(e.get("timestampMs") or 0), e.get("message") or {}
    if kind == "message":
        return message(e.get("role") or "user", ts, e.get("content") or "")
    if kind == "user-attachment":
        return message("user", ts, f"[添付] {e.get('file_name', '')}")
    if kind == "mcp-app":
        return tool(ts, e.get("toolName", ""), parse(e.get("toolArgumentsJson") or "") or "", e.get("toolResultJson") or "")
    if kind != "send-message":
        return None
    if m.get("type") == "text":
        return message("assistant", ts, m.get("content") or "")
    if m.get("type") == "widget":
        widget = m.get("widget") or {}
        options = " / ".join(o.get("label", "") for o in widget.get("options") or [])
        return message("assistant", ts, f"{widget.get('prompt', '')}\n[選択肢] {options}")
    if m.get("type") == "attachment":
        return message("assistant", ts, f"[添付] {m.get('file_name', '')}")
    if m.get("type") == "auto-review-approval":
        approval = m.get("approval") or {}
        return tool(ts, "approval", approval.get("command") or approval.get("summary") or "", approval.get("status") or "")
    return None
