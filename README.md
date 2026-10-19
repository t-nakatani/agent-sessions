# agent-sessions

Claude Code・Codex・pi・Grok Bot の直近セッションを、AgentSessions.app を起動せずに一覧し、会話の中身を共通の形で取り出す最小CLI。
各エージェントのセッションファイル（`~/.claude/projects`、`~/.codex/sessions`、`~/.pi/agent/sessions`）を直接読むため、アプリ側の索引更新を待たずに最新状態を確認できる。Python標準ライブラリのみで動く。

本体はエージェント向けのスキル `skills/agent-sessions` に入っており、リポジトリ直下の `agent-sessions` はそのスクリプトへのリンク。

## インストール

macOS と Python 3 を前提とする。PATH の通ったディレクトリへリンクを置く。

```bash
git clone https://github.com/t-nakatani/agent-sessions.git
ln -s "$PWD/agent-sessions/agent-sessions" ~/.local/bin/agent-sessions
```

エージェントから使う場合は、スキルのディレクトリを各エージェントのスキル置き場へリンクする。

```bash
ln -s "$PWD/agent-sessions/skills/agent-sessions" ~/.claude/skills/agent-sessions
ln -s "$PWD/agent-sessions/skills/agent-sessions" ~/.codex/skills/agent-sessions
```

## 一覧

```bash
agent-sessions                     # 直近15件
agent-sessions -n 30               # 件数を指定
agent-sessions -s codex            # claude / codex / pi / grok で絞り込み
agent-sessions -d ~/src/myapp      # 作業ディレクトリ（前方一致）で絞り込み
agent-sessions --json | jq .       # JSON Lines（id・path を含む）
```

出力列は「最終更新・エージェント・モデル・作業ディレクトリ・タイトル」。
サブエージェント（Claude の subagents、Codex の Guardian review など）は除外する。

Grok Bot は会話をサーバー側に持つため、アプリが手元に残すボット一覧のキャッシュから、ボットごとの最終活動時刻と最新メッセージを表示する。キャッシュはアプリの起動中に更新される。作業ディレクトリを持たないため、`-d` を指定すると表示されない。

## 会話

```bash
agent-sessions show 8d96c229             # ユーザーとエージェントの発言（IDは前方一致）
agent-sessions show 8d96c229 --tools     # ツールの呼び出しと結果の要約も含める
agent-sessions show 8d96c229 --tail 20   # 最後の20件
agent-sessions show 8d96c229 --max-chars 600 --json | jq '.messages[] | select(.role == "user")'
```

どのアプリでも、各発言は `role`（`user`・`assistant`・`tool`）・`ts`・`text` の形にそろえる。自動で差し込まれる文脈や思考は除く。
アプリごとの扱いと出力の項目は [SKILL.md](skills/agent-sessions/SKILL.md) にまとめた。

## 構成

```
skills/agent-sessions/scripts/
├── agent-sessions        入口。リンク越しでも隣のパッケージを読む
└── agent_sessions/
    ├── cli.py            引数と、一覧・show の出力
    ├── model.py          共通の形（Session・Message）、時刻の変換、切り詰め
    ├── files.py          ファイルの読み方（.zst の展開、末尾だけの読み込み）
    └── sources/          アプリごとの読み方（claude・codex・pi・grok）
```

アプリごとのモジュールは `iter_sessions()`・`find(ref)`・`read_messages(session)` の3つを持つ。アプリを足すときは同じ形のモジュールを作り、[sources/\_\_init\_\_.py](skills/agent-sessions/scripts/agent_sessions/sources/__init__.py) に登録する。

## テスト

`tests/fixtures` に各アプリの記録の形をまねた架空のセッションを置き、`HOME` を差し替えて CLI を動かす。アプリ側の記録の形が変わったら、ここにも同じ形を足す。

```bash
python3 -m unittest discover tests
```
