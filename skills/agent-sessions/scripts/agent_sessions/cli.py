"""コマンドの引数と出力。一覧（既定）と show の2つ。"""
import argparse
import json
import os
import sys
from datetime import datetime

from .model import clip
from .sources import SOURCES, find

HOME = os.path.expanduser("~")


def list_main(argv):
    p = argparse.ArgumentParser(prog="agent-sessions", description="直近の Claude Code / Codex / pi / Grok Bot セッションを一覧する。会話を読むには show を使う")
    p.add_argument("-n", type=int, default=15, help="表示件数（既定: 15）")
    p.add_argument("-s", "--source", choices=list(SOURCES), help="エージェントで絞り込む")
    p.add_argument("-d", "--cwd", help="作業ディレクトリで絞り込む（前方一致）")
    p.add_argument("--json", action="store_true", help="JSON Lines で出力する")
    args = p.parse_args(argv)

    candidates = []
    for name, module in SOURCES.items():
        if args.source in (None, name):
            candidates += module.iter_sessions()
    candidates.sort(key=lambda c: c[0], reverse=True)

    cwd_filter = os.path.abspath(os.path.expanduser(args.cwd)) if args.cwd else None
    rows = []
    for mtime, load in candidates:
        if len(rows) >= args.n:
            break
        session = load()
        if not session or (cwd_filter and not session.cwd.startswith(cwd_filter)):
            continue
        row = {"source": session.source, "updated": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")}
        rows.append({**row, **session.to_dict(), "path": session.path})

    if args.json:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        return
    for row in rows:
        cwd = row["cwd"].replace(HOME, "~", 1) or ("(Grok Bot)" if row["source"] == "grok" else "")
        print(f'{row["updated"]}  {row["source"]:<6}  {row["model"][:18]:<18}  {cwd[:45]:<45}  {row["title"] or "(無題)"}')


def show_main(argv):
    p = argparse.ArgumentParser(prog="agent-sessions show", description="セッションの会話を、アプリによらない共通の形で出力する")
    p.add_argument("session", help="セッションID（前方一致）か、一覧の --json にある path")
    p.add_argument("--tools", action="store_true", help="ツールの呼び出しと結果の要約も含める")
    p.add_argument("--tail", type=int, help="最後の N 件だけ出す")
    p.add_argument("--max-chars", type=int, default=0, help="各発言をこの文字数で切る（既定: 切らない）")
    p.add_argument("--json", action="store_true", help='{"session": {...}, "messages": [...]} の JSON で出力する')
    args = p.parse_args(argv)

    found = find(args.session)
    if len(found) != 1:
        sys.exit(f"セッションが見つかりません: {args.session}" if not found else f"{len(found)}件に一致しました。IDをもう少し長く指定してください")
    module, session = found[0]
    messages = [m for m in module.read_messages(session) if args.tools or m.role != "tool"]
    if args.tail:
        messages = messages[-args.tail:]
    for m in messages:
        m.text = clip(m.text, args.max_chars)

    if args.json:
        print(json.dumps({"session": session.to_dict(), "messages": [m.to_dict() for m in messages]}, ensure_ascii=False, indent=1))
        return
    print(f"# {session.source}  {session.id}  {session.model}")
    print(f'# {session.cwd.replace(HOME, "~", 1) or "-"}  {session.title or "(無題)"}')
    for m in messages:
        if m.role == "tool":
            print(f"\n[{m.ts}] tool {m.tool}: {m.text}" + (f" → {m.output}" if m.output else ""))
        else:
            print(f"\n[{m.ts}] {m.role}" + (f"({m.kind})" if m.kind else "") + f"\n{m.text}")


def main(argv):
    if argv[:1] == ["show"]:
        show_main(argv[1:])
    else:
        list_main(argv[1:] if argv[:1] == ["list"] else argv)
