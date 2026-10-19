"""アプリによらない共通の形。各アプリのモジュールは、記録をここで定めた Session と Message にそろえる。"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime

TOOL_CHARS = 200


@dataclass
class Session:
    source: str
    id: str = ""
    cwd: str = ""
    model: str = ""
    title: str = ""
    # 会話を読み直すための記録の場所。Grok Bot ではボットの path
    path: str = ""

    def to_dict(self):
        return {"source": self.source, "id": self.id, "cwd": self.cwd, "model": self.model, "title": self.title}


@dataclass
class Message:
    role: str  # user / assistant / tool
    ts: str
    text: str
    kind: str | None = None  # automation / answer / commentary
    tool: str | None = None
    output: str | None = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


def message(role, ts, text, kind=None):
    return Message(role, local_time(ts), text.strip(), kind)


def tool(ts, name, call, output=""):
    return Message("tool", local_time(ts), brief(call), tool=name, output=brief(output) if output else "")


def keep(messages):
    """本文のない発言を落とす。ツールは呼び出しの要約が空でも残す。"""
    return [m for m in messages if m.role == "tool" or m.text]


def local_time(value):
    """ISO 文字列かミリ秒のエポックを、ローカル時刻の文字列にする。"""
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except (AttributeError, TypeError, ValueError):
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def clip(text, limit):
    return text if not limit or len(text) <= limit else text[:limit] + "…"


def brief(value):
    """ツールの入出力を1行に縮める。"""
    if isinstance(value, dict):
        for key in ("command", "cmd", "file_path", "path", "pattern", "query", "url", "description", "prompt"):
            if isinstance(value.get(key), str):
                value = value[key]
                break
    if isinstance(value, list):
        value = " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in value)
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    return clip(" ".join(value.split()), TOOL_CHARS)
