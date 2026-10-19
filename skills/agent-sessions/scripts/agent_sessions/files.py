"""セッションファイルの読み方。"""
import io
import json
import os
import subprocess

TAIL_BYTES = 512 * 1024


def open_text(path):
    if not path.endswith(".zst"):
        return open(path, encoding="utf-8", errors="replace")
    try:
        from compression import zstd
    except ImportError:  # Python 3.13 以前は zstd コマンドで展開する
        out = subprocess.run(["zstd", "-dcq", path], capture_output=True).stdout
        return io.StringIO(out.decode("utf-8", "replace"))
    return zstd.open(path, "rt", encoding="utf-8", errors="replace")


def tail_lines(path):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        return f.read().decode("utf-8", "replace").splitlines()


def reversed_file(path):
    with open_text(path) as f:
        return reversed(f.readlines())


def parse(line):
    try:
        return json.loads(line)
    except ValueError:
        return None


def blocks(content):
    """文字列か内容ブロックの列を、ブロックの列にそろえる。"""
    return [{"type": "text", "text": content}] if isinstance(content, str) else content or []


def under(path, root):
    return os.path.isfile(path) and path.startswith(root + os.sep)
