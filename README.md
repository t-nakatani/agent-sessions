# agent-sessions

Claude Code・Codex・pi・Grok Bot の直近セッションを、AgentSessions.app を起動せずに一覧する最小CLI。
各エージェントのセッションファイル（`~/.claude/projects`、`~/.codex/sessions`、`~/.pi/agent/sessions`）を直接読むため、アプリ側の索引更新を待たずに最新状態を確認できる。Python標準ライブラリのみで動く。

## インストール

macOS と Python 3 を前提とする。PATH の通ったディレクトリへリンクを置く。

```bash
git clone https://github.com/t-nakatani/agent-sessions.git
ln -s "$PWD/agent-sessions/agent-sessions" ~/.local/bin/agent-sessions
```

## 使い方

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
