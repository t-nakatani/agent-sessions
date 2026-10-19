"""架空のセッションファイルを置いたホームで CLI を動かし、各アプリの記録が共通の形にそろうか確かめる。

python3 -m unittest discover tests
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
ENTRY = os.path.join(HERE, "..", "skills", "agent-sessions", "scripts", "agent-sessions")

CLAUDE = "0000cccc-0000-4000-8000-000000000001"
CODEX = "0000aaaa-0000-7000-8000-000000000001"
GUARDIAN = "0000bbbb-0000-7000-8000-000000000001"
PI = "0000dddd-0000-7000-8000-000000000001"
GROK = "0000eeee-0000-4000-8000-000000000001"


class AgentSessionsTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)
        shutil.copytree(os.path.join(FIXTURES, "home"), self.home, dirs_exist_ok=True)
        # Grok Bot のキャッシュは、キーを base32 にしたファイル名で置かれる
        grok = os.path.join(self.home, "Library", "Application Support", "Grok Bot", "sand-client-persistence")
        os.makedirs(grok)
        with open(os.path.join(FIXTURES, "grok.json"), encoding="utf-8") as f:
            for key, value in json.load(f).items():
                name = base64.b32encode(key.encode()).decode().rstrip("=").lower()
                with open(os.path.join(grok, name + ".blob"), "w", encoding="utf-8") as out:
                    json.dump(value, out, ensure_ascii=False)
        # 一覧の並びを決めるため、更新時刻を固定する（Grok はキャッシュの時刻で並ぶので最も新しい）
        self.codex_dir = os.path.join(self.home, ".codex", "sessions", "2026", "01", "02")
        self.touch(os.path.join(".claude", "projects", "-tmp-demo", f"{CLAUDE}.jsonl"), 1000)
        self.touch(os.path.join(self.codex_dir, f"rollout-2026-01-02T10-00-00-{CODEX}.jsonl"), 2000)
        self.touch(os.path.join(self.codex_dir, f"rollout-2026-01-02T11-00-00-{CODEX}_0000aaaa-0000-7000-8000-000000000002.jsonl"), 3000)
        self.touch(os.path.join(self.codex_dir, f"rollout-2026-01-02T12-00-00-{GUARDIAN}.jsonl"), 3500)
        self.touch(os.path.join(".pi", "agent", "sessions", "--tmp-demo--", f"2026-01-02T04-00-00-000Z_{PI}.jsonl"), 4000)

    def touch(self, path, mtime):
        os.utime(os.path.join(self.home, path), (mtime, mtime))

    def run_cli(self, *args, check=True):
        env = {**os.environ, "HOME": self.home, "TZ": "UTC"}
        result = subprocess.run([sys.executable, ENTRY, *args], capture_output=True, text=True, env=env)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def show(self, ref, *args):
        return json.loads(self.run_cli("show", ref, "--tools", "--json", *args).stdout)

    def shape(self, ref):
        """発言を (role, kind, text, tool, output) の組にして、時刻を除いて比べやすくする。"""
        return [(m["role"], m.get("kind"), m["text"], m.get("tool"), m.get("output")) for m in self.show(ref)["messages"]]

    def test_list_orders_sessions_and_skips_subagents(self):
        rows = [json.loads(l) for l in self.run_cli("-n", "10", "--json").stdout.splitlines()]
        self.assertEqual([(r["source"], r["id"]) for r in rows], [("grok", GROK), ("pi", PI), ("codex", CODEX), ("claude", CLAUDE)])
        by_source = {r["source"]: r for r in rows}
        self.assertEqual((by_source["claude"]["title"], by_source["claude"]["model"]), ("README の修正", "claude-test"))
        self.assertEqual((by_source["codex"]["title"], by_source["codex"]["model"]), ("テストの追加", "gpt-test-2"))
        self.assertEqual((by_source["pi"]["title"], by_source["pi"]["model"]), ("重いプロセスの停止", "pi-test"))
        self.assertEqual(by_source["grok"]["title"], "pearl — 監視を始めました")

    def test_list_filters_by_source_and_cwd(self):
        rows = [json.loads(l) for l in self.run_cli("-d", "/tmp/demo", "--json").stdout.splitlines()]
        self.assertEqual({r["source"] for r in rows}, {"claude", "codex", "pi"})
        rows = [json.loads(l) for l in self.run_cli("list", "-s", "pi", "--json").stdout.splitlines()]
        self.assertEqual([r["id"] for r in rows], [PI])

    def test_claude(self):
        self.assertEqual(self.shape(CLAUDE[:8]), [
            ("user", None, "READMEを直して", None, None),
            ("assistant", None, "直します。", None, None),
            ("tool", None, "ls", "Bash", "README.md src"),
            ("user", None, "/review main", None, None),
            ("user", None, "! git status", None, None),
            ("user", None, "古い版の発言\n[画像]", None, None),
            ("assistant", None, "終わりました。", None, None),
        ])
        self.assertEqual(self.show(CLAUDE)["messages"][0]["ts"], "2026-01-02 03:00:00")

    def test_codex_joins_split_files(self):
        expected = [
            ("user", None, "テストを足して", None, None),
            ("assistant", "commentary", "既存のテストを見ます。", None, None),
            ("tool", None, "pytest -q", "shell", "1 passed"),
            ("user", "automation", "毎朝テストの結果を確認する", None, None),
            ("user", "answer", "Q: どちらで進めますか？\nA: 小さく", None, None),
            ("user", None, "この画像も見て\n[添付] a.png", None, None),
            ("tool", None, "pytest", "docs.search", "3件"),
            ("assistant", None, "テストを足しました。", None, None),
        ]
        self.assertEqual(self.shape(CODEX[:8]), expected)
        self.assertEqual(self.show(CODEX)["session"]["model"], "gpt-test-2")

    def test_codex_reads_compressed_files(self):
        path = os.path.join(self.codex_dir, f"rollout-2026-01-02T10-00-00-{CODEX}.jsonl")
        try:
            from compression import zstd
        except ImportError:
            if not shutil.which("zstd"):
                self.skipTest("zstd がない")
            subprocess.run(["zstd", "-q", "--rm", path], check=True)
        else:
            with open(path, "rb") as src, zstd.open(path + ".zst", "wb") as dst:
                dst.write(src.read())
            os.remove(path)
        self.assertEqual(self.shape(CODEX)[0], ("user", None, "テストを足して", None, None))
        self.assertEqual(len(self.shape(CODEX)), 8)

    def test_codex_subagent_can_be_shown_by_id(self):
        self.assertEqual(self.show(GUARDIAN)["session"]["id"], GUARDIAN)

    def test_pi_follows_active_branch(self):
        self.assertEqual(self.shape(PI[:8]), [
            ("user", None, "重いプロセスを止めて\n[画像]", None, None),
            ("assistant", "commentary", "調べます。", None, None),
            ("tool", None, "ps aux", "bash", "PID 123 heavy"),
            ("tool", None, "kill 123", "user-bash", ""),
            ("assistant", None, "止めました。", None, None),
        ])

    def test_grok(self):
        self.assertEqual(self.shape(GROK), [
            ("user", None, "ボットを見張って", None, None),
            ("assistant", None, "どの間隔にしますか？\n[選択肢] 毎時 / 毎日", None, None),
            ("assistant", None, "監視を始めました", None, None),
            ("tool", None, "bot", "search_posts", '{"data": []}'),
        ])

    def test_show_options(self):
        messages = self.show(CLAUDE, "--tail", "2", "--max-chars", "3")["messages"]
        self.assertEqual([m["text"] for m in messages], ["古い版…", "終わり…"])
        without_tools = json.loads(self.run_cli("show", CLAUDE, "--json").stdout)["messages"]
        self.assertNotIn("tool", {m["role"] for m in without_tools})
        text = self.run_cli("show", PI, "--tools").stdout
        self.assertIn("# pi  " + PI + "  pi-test", text)
        self.assertIn("[2026-01-02 04:01:01] assistant(commentary)\n調べます。", text)
        self.assertIn("tool bash: ps aux → PID 123 heavy", text)

    def test_show_by_path(self):
        rows = [json.loads(l) for l in self.run_cli("-s", "pi", "--json").stdout.splitlines()]
        self.assertEqual(self.show(rows[0]["path"])["session"]["id"], PI)

    def test_show_rejects_ambiguous_or_unknown_ids(self):
        ambiguous = self.run_cli("show", "0000", check=False)
        self.assertEqual(ambiguous.returncode, 1)
        self.assertIn("件に一致しました", ambiguous.stderr)
        unknown = self.run_cli("show", "ffff", check=False)
        self.assertEqual(unknown.returncode, 1)
        self.assertIn("見つかりません", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
