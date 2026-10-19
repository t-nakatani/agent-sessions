"""対応するアプリの登録。

各モジュールは次の3つを持つ。アプリを足すときは、同じ形のモジュールを作ってここに登録する。

- iter_sessions()：一覧の候補として (更新時刻, 読み込む関数) を返す。読み込む関数は Session か、一覧から外すなら None を返す
- find(ref)：セッションIDの前方一致か、そのアプリの記録のパスに合う Session の列を返す
- read_messages(session)：会話を Message の列で返す
"""
import os

from . import claude, codex, grok, pi

SOURCES = {"claude": claude, "codex": codex, "pi": pi, "grok": grok}


def find(ref):
    path = os.path.abspath(os.path.expanduser(ref))
    if os.path.isfile(path):
        ref = path
    return [(module, session) for module in SOURCES.values() for session in module.find(ref)]
